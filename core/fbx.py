"""Reading the parts of an FBX file that decide how big a model is.

Why this exists as its own module, with no Blender import at the top: the
question this tool answers is *what does the file declare*, and Blender cannot
answer it. Blender applies ``UnitScaleFactor`` while importing and then forgets
it, so by the time a mesh is in the scene the original declaration is gone. A
tool that imports can only report what Blender made of the file. We need what
the file said.

The second reason is testability. This module parses bytes, so it can be tested
with fixture files, on a machine with no Blender installed. Everything that
decides anything lives here; ``ui.py`` only draws.

Format notes, gathered from FBX files produced by Blender, Unity, Maya and
various CAD exporters:

* ASCII FBX starts with ``; FBX <version> project file`` and is a tree of
  ``Name: key, key { ... }`` nodes.
* Binary FBX starts with ``Kaydara FBX Binary  \\x00`` and is not handled here.
* The scale lives in ``GlobalSettings`` as three integers —
  ``UnitScaleFactor``, ``OriginalUnitScaleFactor`` and ``UpAxis`` — expressed in
  centimetres, which is FBX's internal unit.

Nothing in this module writes to a file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "FbxFile",
    "GlobalSettings",
    "read_fbx",
    "UnitVerdict",
    "judge_scale",
    "BINARY_MAGIC",
]

#: A binary FBX file begins with these bytes. We detect it in order to refuse it
#: honestly rather than to parse it.
BINARY_MAGIC = b"Kaydara FBX Binary"

#: FBX stores lengths in centimetres. Everything the report says about metres is
#: derived from this one number, so it is named rather than inlined.
CENTIMETRES_PER_METRE = 100.0

#: ``UnitScaleFactor`` values seen in the wild, and what each means. Used for the
#: explanation text, not for the verdict.
KNOWN_SCALES = {
    1.0: "1 unit = 1 cm — FBX's internal unit. Blender's default export.",
    2.54: "1 unit = 1 inch",
    100.0: "1 unit = 1 m — metres declared explicitly (Maya, some CAD exports).",
    0.01: "1 unit = 0.01 cm — a scale of 0.01, almost always a mistake.",
    0.1: "1 unit = 0.1 cm — millimetre-based file with the wrong factor.",
    10.0: "1 unit = 10 cm",
}

#: ``Name: value`` inside a node body, e.g. ``P: "UnitScaleFactor", "int", "1"``.
_PROPERTY = re.compile(r'^\s*([A-Za-z]+):\s*(.*)$')

#: The first quoted string on a property line is the property's name.
_QUOTED = re.compile(r'"([^"]*)"')


@dataclass(frozen=True)
class GlobalSettings:
    """The scale-related fields of the ``GlobalSettings`` node.

    Every field is ``None`` when the file does not declare it, which is itself a
    finding: a file with no ``UnitScaleFactor`` is one whose size depends on the
    importer's default.
    """

    unit_scale_factor: float | None = None
    original_unit_scale_factor: float | None = None
    up_axis: int | None = None
    up_axis_name: str | None = None
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def metres_per_unit(self) -> float | None:
        """How many metres one FBX unit is, according to the file.

        ``None`` when the file does not say. FBX's unit is the centimetre, so
        this is simply the factor divided by a hundred — but the division is the
        part people get wrong, so it is written out rather than assumed.
        """
        if self.unit_scale_factor is None:
            return None
        return self.unit_scale_factor / CENTIMETRES_PER_METRE

    @property
    def declared(self) -> bool:
        """Whether the file states a scale at all."""
        return self.unit_scale_factor is not None

    def explanation(self) -> str | None:
        """A sentence describing the declared scale, or ``None``."""
        if self.unit_scale_factor is None:
            return None
        known = KNOWN_SCALES.get(round(self.unit_scale_factor, 6))
        if known is not None:
            return known
        return (
            f"1 unit = {self.unit_scale_factor:g} cm — "
            "a non-standard factor, so check the exporter"
        )


@dataclass(frozen=True)
class FbxFile:
    """What we were able to read from one FBX file."""

    path: Path
    is_binary: bool = False
    error: str | None = None
    file_version: int | None = None
    creator: str | None = None
    global_settings: GlobalSettings | None = None
    #: Top-level node names, kept so a report can say whether a file looks like a
    #: model at all rather than an animation or a material library.
    top_level_nodes: tuple[str, ...] = ()

    @property
    def readable(self) -> bool:
        """Whether the file was read to the point where a verdict is possible."""
        return not self.is_binary and self.error is None and self.global_settings is not None


def _number(text: str) -> float | None:
    """Pulls the property's value out of a line body.

    A property line looks like ``P: "UnitScaleFactor", "double", "Number", "",1``
    — note that the **value is not quoted**, it trails after the quoted type
    names. An earlier version took the last quoted string, which is the empty
    format field, and so read every factor as blank. The tests caught it.

    Files in the wild also write it quoted (``"1"``), so the last number-looking
    token anywhere in the line is taken rather than the last field.
    """
    if text is None:
        return None

    # Take the final token that parses as a number. ``re`` rather than split
    # because values appear both bare and quoted, and with and without trailing
    # commas.
    matches = re.findall(r'"?(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"?', text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def read_fbx(path: str | Path) -> FbxFile:
    """Reads an FBX file and returns what its header declares.

    Never raises for a bad file: a validator that crashes on the broken file it
    was pointed at is not a validator. Problems come back in ``error``.
    """
    path = Path(path)

    try:
        head = path.read_bytes()[:32]
    except OSError as problem:
        return FbxFile(path=path, error=f"cannot read: {problem}")

    if head.startswith(BINARY_MAGIC):
        return FbxFile(path=path, is_binary=True)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as problem:
        return FbxFile(path=path, error=f"cannot read: {problem}")

    first_line = text.split("\n", 1)[0]
    version = None
    # Dotted on purpose. A bare ``\d+`` matches the "7" in "FBX 7.4.0", which is
    # how this was wrong the first time the tests ran.
    version_match = re.search(r"FBX\s+(\d+\.\d+\.\d+)", first_line)
    if version_match is not None:
        # Blender reports 7400 for 7.4.0; keep the file's own dotted form too.
        parts = version_match.group(1).split(".")
        version = int(parts[0]) * 1000 + int(parts[1]) * 100 + int(parts[2])

    creator = None
    settings = GlobalSettings()
    found_settings: dict[str, str] = {}
    top_level: list[str] = []

    # A line scanner rather than a full tree parser, deliberately. We need one
    # node's contents, and a real parser would be more code to be wrong in.
    #
    # The brace bookkeeping is the part that was wrong on the first run: the
    # node name sits on the SAME line as its opening brace, so the body starts
    # one level deeper than the line where the name was seen. Tracking depth
    # relative to that line, rather than in absolute terms, is what makes it
    # right.
    depth = 0
    inside_settings = False
    settings_depth = 0

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("GlobalSettings:"):
            inside_settings = True
            settings_depth = depth + 1

        if depth == 0:
            name_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", stripped)
            if name_match is not None:
                top_level.append(name_match.group(1))

        if stripped.endswith("{"):
            depth += 1
            continue

        if stripped.startswith("}"):
            depth -= 1
            if inside_settings and depth < settings_depth:
                inside_settings = False
            continue

        if inside_settings:
            # Deliberately not checking the depth here. The properties live
            # inside ``Properties70``, one level below ``GlobalSettings``, and an
            # earlier version compared against the wrong level and therefore
            # found nothing — every file looked broken. Collecting from the whole
            # subtree is also more tolerant: exporters that omit the
            # ``Properties70`` wrapper still work.
            #
            # Split on the first colon rather than matching a pattern, because
            # FBX writes ``P: "UpAxis", ...`` with no space after the colon.
            key, separator, body = stripped.partition(":")
            if separator == "":
                continue
            key = key.strip()
            if key not in {"P", "C"}:
                continue
            names = _QUOTED.findall(body)
            if len(names) < 1:
                continue
            found_settings[names[0]] = body
            if names[0] == "Creator" and len(names) >= 2:
                creator = names[-1]

    # Creator also appears as its own node in some exporters.
    if creator is None:
        creator_match = re.search(r'Creator:\s*"([^"]*)"', text)
        if creator_match is not None:
            creator = creator_match.group(1)

    def setting(name: str) -> float | None:
        body = found_settings.get(name)
        return None if body is None else _number(body)

    settings = GlobalSettings(
        unit_scale_factor=setting("UnitScaleFactor"),
        original_unit_scale_factor=setting("OriginalUnitScaleFactor"),
        up_axis=setting("UpAxis"),
        up_axis_name=found_settings.get("UpAxisSign") and None,
        raw={name: body for name, body in found_settings.items()},
    )

    if not found_settings:
        return FbxFile(
            path=path,
            error="no GlobalSettings node — not an FBX file, or truncated",
            file_version=version,
            creator=creator,
            top_level_nodes=tuple(top_level),
        )

    return FbxFile(
        path=path,
        file_version=version,
        creator=creator,
        global_settings=settings,
        top_level_nodes=tuple(top_level),
    )


@dataclass(frozen=True)
class UnitVerdict:
    """A judgement about one file's scale, with the reason it was reached."""

    level: str  # "ok", "warn", "bad", "unknown"
    summary: str
    detail: str = ""

    @property
    def is_problem(self) -> bool:
        return self.level in {"warn", "bad"}


def judge_scale(settings: GlobalSettings | None) -> UnitVerdict:
    """Decides whether a declared scale is a problem, and says why.

    Deliberately conservative. Only two things are called outright wrong: a
    factor that makes a unit a hundredth of a centimetre, and a file that does
    not declare a factor at all while claiming to come from an exporter that
    always writes one. Everything else is a warning, because a scale that looks
    odd can be entirely correct for a millimetre-based CAD workflow.
    """
    if settings is None:
        return UnitVerdict(
            level="unknown",
            summary="No scale declared",
            detail=(
                "The file has no GlobalSettings, so its size depends entirely on "
                "the importer's default. Expect a surprise."
            ),
        )

    factor = settings.unit_scale_factor
    if factor is None:
        return UnitVerdict(
            level="bad",
            summary="No UnitScaleFactor",
            detail=(
                "GlobalSettings exists but does not declare a unit scale. Every "
                "importer will fall back to its own default, and two importers "
                "will disagree."
            ),
        )

    if factor <= 0:
        return UnitVerdict(
            level="bad",
            summary=f"UnitScaleFactor is {factor:g}",
            detail="A scale of zero or less cannot describe a size. The exporter wrote nonsense.",
        )

    metres = settings.metres_per_unit or 0.0

    if abs(factor - 1.0) < 1e-9:
        return UnitVerdict(
            level="ok",
            summary="Centimetres (factor 1)",
            detail=(
                "FBX's internal unit. 1 unit = 1 cm, so a 2 m model is 200 units. "
                "This is what Blender writes by default, and every engine reads it."
            ),
        )

    if abs(factor - 100.0) < 1e-9:
        return UnitVerdict(
            level="ok",
            summary="Metres declared (factor 100)",
            detail=(
                "1 unit = 1 m. Legitimate, and common from Maya and CAD. Worth "
                "knowing, because a 2-unit model is 2 metres, not 2 centimetres."
            ),
        )

    if abs(factor - 2.54) < 1e-9:
        return UnitVerdict(
            level="warn",
            summary="Inches (factor 2.54)",
            detail=(
                "1 unit = 1 inch. Engines work in metres; the importer has to "
                "convert, and its rounding is a place for small errors to appear."
            ),
        )

    if factor < 1.0:
        return UnitVerdict(
            level="bad",
            summary=f"Suspiciously small scale (factor {factor:g})",
            detail=(
                f"1 unit = {metres:g} m. A scale below 0.1 makes a unit smaller "
                "than a millimetre, which is almost never intended and is the "
                "classic symptom of a scene built at the wrong scale and exported "
                "anyway. Blender's FBX scale handling has been patched repeatedly "
                "over this exact case."
            ),
        )

    if abs(factor - 10.0) < 1e-9:
        return UnitVerdict(
            level="warn",
            summary="Factor 10",
            detail=(
                "1 unit = 10 cm. Sometimes deliberate (decimetre workflows), more "
                "often a half-applied conversion. Check one known dimension."
            ),
        )

    return UnitVerdict(
        level="warn",
        summary=f"Unusual scale (factor {factor:g})",
        detail=(
            f"1 unit = {metres:g} m. Not a standard factor, so nothing will "
            "convert it by default."
        ),
    )
