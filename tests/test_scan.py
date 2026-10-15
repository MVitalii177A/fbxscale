"""Tests for folder scanning and the three report formats.

Kept separate from ``test_fbx.py`` because the two answer different questions:
that file asks "did we read this file correctly", this one asks "did we find the
right files and say the right thing about them".

Run with ``python -m tests.test_scan`` from the product folder.
"""

from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from core.scan import DEFAULT_EXTENSIONS, scan_folder, scan_files  # noqa: E402

FIXTURES = HERE / "fixtures"

_failures: list[str] = []
_checks = 0


def check(condition: bool, message: str) -> None:
    global _checks
    _checks += 1
    if not condition:
        _failures.append(message)
        print(f"  FAIL {message}")


def equal(actual, expected, message: str) -> None:
    check(actual == expected, f"{message} (expected {expected!r}, got {actual!r})")


def section(title: str) -> None:
    print(f"\n{title}")


def build_tree(root: Path) -> None:
    """A folder shaped like a real asset dump, not like a test fixture."""
    (root / "props").mkdir(parents=True)
    (root / "props" / "old").mkdir()
    (root / "characters").mkdir()

    shutil.copy(FIXTURES / "centimetres_default.fbx", root / "props" / "crate.fbx")
    shutil.copy(FIXTURES / "metres_factor100.fbx", root / "props" / "barrel.fbx")
    shutil.copy(
        FIXTURES / "broken_small_scale.fbx", root / "props" / "old" / "bracket.fbx"
    )
    shutil.copy(
        FIXTURES / "no_scale_declared.fbx", root / "characters" / "hero.fbx"
    )
    # A binary file, written by hand: the magic header is all the reader needs.
    (root / "characters" / "bought.fbx").write_bytes(
        b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 32
    )
    # Two at the top level, so a non-recursive scan has something to find.
    shutil.copy(FIXTURES / "centimetres_default.fbx", root / "table.fbx")
    shutil.copy(FIXTURES / "metres_factor100.fbx", root / "chair.fbx")
    # Files that are deliberately not FBX. They must be counted, not ignored.
    (root / "props" / "source.blend").write_text("not really a blend file")
    (root / "props" / "crate.obj").write_text("v 0 0 0")
    (root / "notes.txt").write_text("hello")


def test_finds_files_in_subfolders() -> None:
    section("Folder walking")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)

        result = scan_folder(root)
        equal(len(result.findings), 7, "all seven FBX files are found")

        # Sorted by path text, so "chair.fbx" comes before "characters/…" —
        # "chai" is less than "char". The order is the walker's, not an accident
        # of the test, so the expectation matches it exactly.
        names = sorted(finding.relative.replace("\\", "/") for finding in result.findings)
        equal(
            names,
            [
                "chair.fbx",
                "characters/bought.fbx",
                "characters/hero.fbx",
                "props/barrel.fbx",
                "props/crate.fbx",
                "props/old/bracket.fbx",
                "table.fbx",
            ],
            "nested files are found and named relative to the root",
        )

        check(
            "source.blend" in result.skipped_other and "crate.obj" in result.skipped_other,
            "known other formats are counted as skipped",
        )
        check(
            "notes.txt" not in result.skipped_other,
            "unrelated files are not reported at all",
        )

        shallow = scan_folder(root, recursive=False)
        equal(len(shallow.findings), 2, "a non-recursive scan stops at the top level")
        equal(
            sorted(finding.relative for finding in shallow.findings),
            ["chair.fbx", "table.fbx"],
            "and finds exactly the top-level files",
        )


def test_counts_and_ordering() -> None:
    section("Counts and ordering")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)
        result = scan_folder(root)

        counts = result.counts
        equal(counts["ok"], 4, "four files have a sane scale")
        equal(counts["bad"], 2, "the tiny factor and the missing factor are both broken")
        equal(counts["unknown"], 1, "the binary file gets no verdict")
        equal(counts["warn"], 0, "nothing here is merely a warning")

        levels = [finding.level for finding in result.sorted_findings]
        equal(levels[0], "bad", "the worst file is listed first")
        equal(levels[-1], "ok", "the fine files are listed last")

        # The binary file is *not* a problem: refusing to read it is an answer,
        # not a fault, and counting it as one would train the reader to ignore
        # the summary.
        equal(len(result.problems), 2, "problems counts files with a bad scale only")
        check(
            all(not finding.is_problem for finding in result.findings if finding.is_binary),
            "an unreadable file is reported but not counted as a problem",
        )


def test_headline_says_something_useful() -> None:
    section("Headline")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)
        result = scan_folder(root)

        headline = result.headline()
        check("7 FBX files" in headline, f"the count is in the headline: {headline!r}")
        check("2 with a broken scale" in headline, "the broken count is named")

        empty = scan_folder(root / "nothing_here")
        equal(empty.headline(), "No FBX files found.", "an empty folder says so plainly")
        equal(empty.findings, [], "and finds nothing")


def test_text_report() -> None:
    section("Text report")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)
        text = scan_folder(root).as_text()

        check("props/old/bracket.fbx" in text or "props\\old\\bracket.fbx" in text,
              "the broken file is named")
        check("[FAIL]" in text, "broken files are marked")
        check("Binary FBX" in text, "the binary file is explained, not hidden")
        check("one unit = 0.01 m" in text or "one unit = 0.0001 m" in text,
              "the file's meaning is stated in metres")
        check("Not read" in text, "skipped files are declared")


def test_csv_report_parses() -> None:
    section("CSV report")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)
        content = scan_folder(root).as_csv()

        rows = list(csv.DictReader(io.StringIO(content)))
        equal(len(rows), 7, "one row per FBX file")
        equal(
            rows[0]["level"],
            "bad",
            "the CSV is ordered worst first, same as the text report",
        )

        bracket = next(row for row in rows if "bracket.fbx" in row["file"])
        equal(bracket["unit_scale_factor"], "0.01", "the factor is written plainly")
        equal(bracket["binary"], "no", "the binary column is filled")

        binary = next(row for row in rows if "bought.fbx" in row["file"])
        equal(binary["binary"], "yes", "a binary file is marked as binary")
        equal(binary["level"], "unknown", "and gets no scale verdict")


def test_html_report_is_standalone() -> None:
    section("HTML report")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)
        page = scan_folder(root).as_html()

        check(page.startswith("<!doctype html>"), "it is a complete document")
        check("<table>" in page and "</html>" in page, "the body is closed")
        check(
            "http://" not in page and "https://" not in page,
            "nothing is loaded from the network — the report must open offline",
        )
        check("<script" not in page.lower(), "no scripts, so nothing can break it")
        check("bracket.fbx" in page, "the broken file appears")

    section("HTML escaping")

    # Windows forbids ``<`` and ``>`` in file names, so the escaping is exercised
    # directly rather than by creating a file that cannot exist. The value being
    # protected is the same either way: whatever text ends up in the page.
    from core.scan import Finding, ScanResult

    hostile = Finding(
        path=Path("evil <script>alert(1)</script>.fbx"),
        relative="evil <script>alert(1)</script>.fbx",
        level="bad",
        summary='factor "<img onerror=1>"',
        detail="</td></tr><script>alert(2)</script>",
        declared_factor=0.01,
        original_factor=None,
        metres_per_unit=0.0001,
        creator=None,
        version=None,
        is_binary=False,
        error=None,
    )
    page = ScanResult(root=Path("/tmp"), findings=[hostile]).as_html()

    check("<script>alert(1)</script>" not in page, "a hostile file name is escaped")
    check("&lt;script&gt;" in page, "and shown as text instead")
    check("<img onerror=1>" not in page, "a hostile summary is escaped")
    check("<script>alert(2)</script>" not in page, "a hostile detail is escaped")
    check("&lt;img onerror=1&gt;" in page, "and its angle brackets are entity-encoded")


def test_scan_files_accepts_any_list() -> None:
    section("Scanning an explicit list")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)

        picked = [root / "props" / "crate.fbx", root / "props" / "crate.obj"]
        result = scan_files(picked, root=root)
        equal(len(result.findings), 1, "only the FBX file is read")
        equal(len(result.skipped_other), 1, "the other file is declared as skipped")

        nothing = scan_files([], root=root)
        equal(nothing.findings, [], "an empty list is not an error")
        equal(nothing.root, root, "the root is remembered even with no files")


def test_extension_filter_is_configurable() -> None:
    section("Extension filter")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_tree(root)

        result = scan_folder(root, extensions=(".fbx", ".obj"))
        names = [finding.relative for finding in result.findings]
        check(
            any(name.endswith(".obj") for name in names),
            "a wider filter picks up the other format",
        )
        check(DEFAULT_EXTENSIONS == (".fbx",), "and the default is unchanged")


def main() -> int:
    print("FBX folder scanner")

    test_finds_files_in_subfolders()
    test_counts_and_ordering()
    test_headline_says_something_useful()
    test_text_report()
    test_csv_report_parses()
    test_html_report_is_standalone()
    test_scan_files_accepts_any_list()
    test_extension_filter_is_configurable()

    print()
    if _failures:
        print(f"{len(_failures)} of {_checks} checks failed.")
        return 1
    print(f"all {_checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
