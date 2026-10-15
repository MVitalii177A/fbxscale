"""End-to-end tests: the command line, driven the way a person drives it.

The other two test files import modules. This one runs the process, because the
things most likely to be wrong about a command-line tool are not in its logic —
they are in its arguments, its exit codes and its output paths.

Run with ``python -m tests.test_cli`` from the product folder.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
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


def run(*arguments: str) -> subprocess.CompletedProcess:
    """Runs the CLI in a real subprocess and captures what a user would see."""
    return subprocess.run(
        [sys.executable, "-m", "core.cli", *arguments],
        cwd=PRODUCT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_reports_a_clean_folder() -> None:
    section("A folder with nothing wrong")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        shutil.copy(FIXTURES / "centimetres_default.fbx", root / "crate.fbx")
        shutil.copy(FIXTURES / "metres_factor100.fbx", root / "barrel.fbx")

        finished = run(str(root))

        equal(finished.returncode, 0, "a clean folder exits successfully")
        check("all with a sane declared scale" in finished.stdout, "and says so")
        check("[FAIL]" not in finished.stdout, "with no failures listed")


def test_fails_on_a_broken_scale() -> None:
    section("A folder with a broken file")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        shutil.copy(FIXTURES / "broken_small_scale.fbx", root / "bracket.fbx")

        finished = run(str(root))

        equal(
            finished.returncode,
            1,
            "a broken scale is a failing exit code, so a pipeline can catch it",
        )
        check("[FAIL]" in finished.stdout, "the failure is visible in the output")
        check("bracket.fbx" in finished.stdout, "and names the file")


def test_binary_is_not_a_failure() -> None:
    section("A folder containing only a binary file")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "bought.fbx").write_bytes(
            b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 32
        )

        finished = run(str(root))

        equal(
            finished.returncode,
            0,
            "refusing to read a binary file is an answer, not a failure",
        )
        check("Binary FBX" in finished.stdout, "and the reason is printed")


def test_writes_reports() -> None:
    section("Writing report files")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        shutil.copy(FIXTURES / "broken_small_scale.fbx", root / "bracket.fbx")
        shutil.copy(FIXTURES / "centimetres_default.fbx", root / "crate.fbx")

        csv_path = root / "report.csv"
        html_path = root / "report.html"
        finished = run(str(root), "--csv", str(csv_path), "--html", str(html_path))

        check(csv_path.exists(), "the CSV file is written")
        check(html_path.exists(), "the HTML file is written")

        rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))))
        equal(len(rows), 2, "the CSV has a row per file")
        equal(rows[0]["level"], "bad", "worst first, same as the console output")

        page = html_path.read_text(encoding="utf-8")
        check(page.startswith("<!doctype html>"), "the HTML is a complete page")
        check("bracket.fbx" in page, "and names the broken file")

        equal(finished.returncode, 1, "the exit code still reflects the broken file")


def test_quiet_and_recursive_flags() -> None:
    section("Flags")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "nested").mkdir()
        shutil.copy(FIXTURES / "broken_small_scale.fbx", root / "nested" / "deep.fbx")
        shutil.copy(FIXTURES / "centimetres_default.fbx", root / "top.fbx")

        quiet = run(str(root), "--quiet")
        equal(
            quiet.stdout.strip(),
            "2 FBX files: 1 with a broken scale.",
            "quiet prints the headline and nothing else",
        )

        shallow = run(str(root), "--no-recursive")
        check(
            "deep.fbx" not in shallow.stdout,
            "a non-recursive scan does not reach the subfolder",
        )
        check("top.fbx" in shallow.stdout, "but does read the top level")
        equal(shallow.returncode, 0, "and finds nothing wrong there")


def test_rejects_a_missing_folder() -> None:
    section("Bad input")

    finished = run(str(Path(tempfile.gettempdir()) / "definitely_not_here_12345"))

    equal(finished.returncode, 2, "a missing folder is a usage error, not a finding")
    check("Not a folder" in finished.stderr, "and says so on stderr")


def test_help_works() -> None:
    section("Help")

    finished = run("--help")
    equal(finished.returncode, 0, "help exits successfully")
    check("Report the unit scale" in finished.stdout, "and describes the tool")


def main() -> int:
    print("FBX scale command line")

    test_reports_a_clean_folder()
    test_fails_on_a_broken_scale()
    test_binary_is_not_a_failure()
    test_writes_reports()
    test_quiet_and_recursive_flags()
    test_rejects_a_missing_folder()
    test_help_works()

    print()
    if _failures:
        print(f"{len(_failures)} of {_checks} checks failed.")
        return 1
    print(f"all {_checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
