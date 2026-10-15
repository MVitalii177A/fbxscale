"""Tests for the FBX scale reader.

Run with ``python -m tests.test_fbx`` from the product folder, or via
``npm test`` where Node drives Python. No third-party test runner is used on
purpose: the add-on must install into Blender with nothing but the standard
library, and a test suite that needs pytest would be a dependency we do not
otherwise have.

The fixtures are hand-written ASCII FBX files. Hand-written rather than exported
from Blender because Blender is not installed on the development machine — which
is the whole reason the parser was separated from the add-on in the first place
(see ``DECISIONS.md``, ADR-002).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.fbx import BINARY_MAGIC, GlobalSettings, judge_scale, read_fbx  # noqa: E402

FIXTURES = HERE / "fixtures"

_failures: list[str] = []
_checks = 0


def check(condition: bool, message: str) -> None:
    """Records one assertion. Kept tiny so the file reads as a list of claims."""
    global _checks
    _checks += 1
    if not condition:
        _failures.append(message)
        print(f"  FAIL {message}")


def equal(actual, expected, message: str) -> None:
    check(actual == expected, f"{message} (expected {expected!r}, got {actual!r})")


def section(title: str) -> None:
    print(f"\n{title}")


def test_normalises_scale() -> None:
    """The arithmetic that everything else rests on."""
    section("Scale arithmetic")

    centimetres = GlobalSettings(unit_scale_factor=1.0)
    equal(centimetres.metres_per_unit, 0.01, "factor 1 means one unit is a centimetre")

    metres = GlobalSettings(unit_scale_factor=100.0)
    equal(metres.metres_per_unit, 1.0, "factor 100 means one unit is a metre")

    inches = GlobalSettings(unit_scale_factor=2.54)
    check(
        abs((inches.metres_per_unit or 0) - 0.0254) < 1e-9,
        "factor 2.54 means one unit is an inch",
    )

    undeclared = GlobalSettings()
    equal(undeclared.metres_per_unit, None, "no factor means no metres")
    check(not undeclared.declared, "an empty file does not declare a scale")


def test_reads_default_blender_export() -> None:
    """The most common file in this audience: Blender's own output."""
    section("Blender default export (centimetres)")

    result = read_fbx(FIXTURES / "centimetres_default.fbx")

    check(result.readable, f"file should be readable (error: {result.error})")
    check(not result.is_binary, "an ASCII file is not binary")
    equal(result.file_version, 7400, "version is read from the header")
    check(
        result.creator is not None and "Blender" in result.creator,
        "creator is read",
    )
    settings = result.global_settings
    check(settings is not None, "settings are present")
    if settings is None:
        return
    equal(settings.unit_scale_factor, 1.0, "UnitScaleFactor 1 is read")
    equal(settings.original_unit_scale_factor, 1.0, "OriginalUnitScaleFactor is read")
    equal(settings.up_axis, 1.0, "UpAxis is read")
    # Membership in a tuple of names, not a substring search. The first version
    # of this check used ``in`` against the tuple and was testing for an exact
    # node called "Geometry", which never exists — the node is "Geometry::Cube"
    # nested under "Objects".
    check("Objects" in result.top_level_nodes, "top-level nodes are listed")
    check(
        any(node.startswith("FBX") for node in result.top_level_nodes),
        "the header node is among them",
    )

    verdict = judge_scale(settings)
    equal(verdict.level, "ok", "centimetres are fine")


def test_reads_metres_export() -> None:
    """A metre-based file is legitimate, and must not be reported as broken."""
    section("Maya-style metres export (factor 100)")

    result = read_fbx(FIXTURES / "metres_factor100.fbx")
    settings = result.global_settings
    check(settings is not None, "settings are present")
    if settings is None:
        return

    equal(settings.unit_scale_factor, 100.0, "factor 100 is read")
    equal(settings.metres_per_unit, 1.0, "one unit is a metre")
    verdict = judge_scale(settings)
    equal(verdict.level, "ok", "metres are not a problem")
    check("Maya" in (result.creator or ""), "creator names the exporter")


def test_flags_small_scale() -> None:
    """The case the whole tool exists for."""
    section("Broken file (factor 0.01)")

    result = read_fbx(FIXTURES / "broken_small_scale.fbx")
    settings = result.global_settings
    check(settings is not None, "settings are present")
    if settings is None:
        return

    equal(settings.unit_scale_factor, 0.01, "the tiny factor is read")
    verdict = judge_scale(settings)
    equal(verdict.level, "bad", "a hundredth-of-a-centimetre unit is reported as broken")
    check(
        "mm" in verdict.detail.lower() or "smaller than a millimetre" in verdict.detail.lower(),
        "the explanation says what the size means",
    )
    check(
        settings.original_unit_scale_factor == 1.0,
        "the original factor is kept, so a report can say what it was changed from",
    )
    check(
        settings.original_unit_scale_factor != settings.unit_scale_factor,
        "the mismatch between declared and original is visible",
    )


def test_flags_missing_scale() -> None:
    """A file that declares nothing is worse than one that declares something odd."""
    section("No scale declared")

    result = read_fbx(FIXTURES / "no_scale_declared.fbx")
    settings = result.global_settings
    check(settings is not None, "GlobalSettings is found even without a scale")
    if settings is None:
        return

    equal(settings.unit_scale_factor, None, "no factor is read as absent")
    check(not settings.declared, "the file does not declare a scale")
    verdict = judge_scale(settings)
    equal(verdict.level, "bad", "a missing scale is reported as a problem")


def test_refuses_binary() -> None:
    """Refusing honestly beats guessing."""
    section("Binary FBX")

    # Written into a temporary folder rather than into ``fixtures/``. An earlier
    # version created it beside the fixtures and left it behind on every run,
    # which meant the repository grew a file that nothing owned.
    with tempfile.TemporaryDirectory() as temporary:
        binary = Path(temporary) / "binary.fbx"
        binary.write_bytes(BINARY_MAGIC + b"\x00" + b"\x1a\x00" * 8)

        result = read_fbx(binary)
        check(result.is_binary, "the binary magic is recognised")
        check(not result.readable, "a binary file is not reported as readable")
        equal(result.error, None, "refusing is not an error, it is an answer")

        verdict = judge_scale(result.global_settings)
        equal(verdict.level, "unknown", "a file we could not read gets no verdict")

        # The bytes after the magic are not a real binary FBX, and that must not
        # matter: the decision to refuse is made on the header alone.
        check(
            result.global_settings is None,
            "nothing is parsed out of a binary file",
        )


def test_survives_junk() -> None:
    """A validator that crashes on the broken file it was pointed at is useless."""
    section("Files that are not FBX")

    empty = FIXTURES / "empty.fbx"
    empty.write_text("", encoding="utf-8")
    result = read_fbx(empty)
    check(result.error is not None, "an empty file produces an error, not an exception")
    check(not result.readable, "an empty file is not readable")

    text = FIXTURES / "not_fbx.fbx"
    text.write_text("hello, this is a text file\nwith lines\n", encoding="utf-8")
    result = read_fbx(text)
    check(result.error is not None, "a non-FBX text file produces an error")
    check(not result.readable, "a non-FBX text file is not readable")

    missing = read_fbx(FIXTURES / "does_not_exist.fbx")
    check(missing.error is not None, "a missing file produces an error, not an exception")

    broken = FIXTURES / "truncated.fbx"
    broken.write_text(
        "; FBX 7.4.0 project file\nGlobalSettings:  {\n\tProperties70:  {\n"
        '\t\tP: "UnitScaleFactor", "double", "Number", "",',
        encoding="utf-8",
    )
    result = read_fbx(broken)
    check(result.readable, "a truncated file still yields what it did manage to say")

    for junk in (empty, text, broken):
        junk.unlink()


def test_judgement_boundaries() -> None:
    """Every branch of the verdict, so a threshold change cannot pass unnoticed."""
    section("Verdict boundaries")

    cases = [
        (None, "unknown"),
        (GlobalSettings(), "bad"),
        (GlobalSettings(unit_scale_factor=0.0), "bad"),
        (GlobalSettings(unit_scale_factor=-5.0), "bad"),
        (GlobalSettings(unit_scale_factor=1.0), "ok"),
        (GlobalSettings(unit_scale_factor=100.0), "ok"),
        (GlobalSettings(unit_scale_factor=2.54), "warn"),
        (GlobalSettings(unit_scale_factor=10.0), "warn"),
        (GlobalSettings(unit_scale_factor=0.01), "bad"),
        (GlobalSettings(unit_scale_factor=0.5), "bad"),
        (GlobalSettings(unit_scale_factor=1000.0), "warn"),
    ]
    for settings, expected in cases:
        factor = "absent" if settings is None else settings.unit_scale_factor
        equal(judge_scale(settings).level, expected, f"factor {factor}")

    # The threshold that matters most: 1.0 is fine, anything under it is not.
    check(
        judge_scale(GlobalSettings(unit_scale_factor=1.0)).level == "ok"
        and judge_scale(GlobalSettings(unit_scale_factor=0.99)).level == "bad",
        "the boundary at 1.0 falls on the right side",
    )


def main() -> int:
    print("FBX scale reader")

    test_normalises_scale()
    test_reads_default_blender_export()
    test_reads_metres_export()
    test_flags_small_scale()
    test_flags_missing_scale()
    test_refuses_binary()
    test_survives_junk()
    test_judgement_boundaries()

    print()
    if _failures:
        print(f"{len(_failures)} of {_checks} checks failed.")
        return 1
    print(f"all {_checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
