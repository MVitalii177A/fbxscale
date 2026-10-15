#!/usr/bin/env python3
"""Installs the built add-on with Blender's own command and checks it inside Blender.

This replaces an earlier version that guessed at Blender's internals by copying
files into place and calling ``addon_utils.enable``. That approach worked, but it
tested *our idea* of how an extension is installed rather than Blender's. The
commands used here are the ones the catalogue's own documentation tells a user to
use:

    blender --command extension build --source-dir . --output-dir <dir>
    blender --command extension install-file -r user_default -e <zip>
    blender --command extension list

So the sequence is: build, validate, install, confirm it appears in Blender's
list, then run the add-on's own registration checks in a second Blender process
with the same preferences.

Everything runs against a throwaway preferences folder, so nobody's real Blender
is modified.

Usage:
    python scripts/check_in_blender.py
    python scripts/check_in_blender.py --blender "C:/Program Files/Blender/blender.exe"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
REPO = PRODUCT.parent.parent
TOOLS = REPO / "_tools"

_failures: list[str] = []
_checks = 0


def check(condition: bool, message: str) -> None:
    global _checks
    _checks += 1
    if condition:
        print(f"  ok   {message}")
    else:
        _failures.append(message)
        print(f"  FAIL {message}")


def section(title: str) -> None:
    print(f"\n{title}")


def find_blender(explicit: str | None) -> Path | None:
    """Finds Blender: an explicit path, then PATH, then a portable build."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("blender")
    if found:
        candidates.append(Path(found))
    if TOOLS.is_dir():
        candidates.extend(sorted(TOOLS.rglob("blender.exe"), reverse=True))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def isolated_environment(home: Path) -> dict:
    """A Blender that does not touch the real user's preferences.

    ``BLENDER_USER_EXTENSIONS`` is the one that matters for install-file: without
    it Blender writes into ``%APPDATA%`` and leaves the add-on installed on the
    machine that ran the check.
    """
    environment = dict(os.environ)
    environment.update(
        {
            "BLENDER_USER_EXTENSIONS": str(home / "extensions"),
            "BLENDER_USER_SCRIPTS": str(home / "scripts"),
            "BLENDER_USER_CONFIG": str(home / "config"),
            "BLENDER_USER_RESOURCES": str(home),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    for subfolder in ("extensions", "scripts", "config"):
        (home / subfolder).mkdir(parents=True, exist_ok=True)
    return environment


def scratch_home() -> Path:
    """Somewhere Blender is allowed to write its own bookkeeping.

    This is the resolution of a puzzle that took a while, so it is written down
    properly. Blender's extension commands create **dot-prefixed** entries —
    ``.fbxscale-0.1.0.zip`` while building, ``.cache`` and a repository lock
    directory while installing — and on this machine those creations are refused
    with ``Permission denied`` and ``WinError 5`` when they happen under the
    system temporary folder or under the product folder. Creating the same files
    by hand in those same folders succeeds, and the identical build succeeds when
    the output folder is under ``_tools/``.

    What that adds up to: the confinement around this workspace permits Blender's
    dot-prefixed writes under ``_tools/`` and not elsewhere. Nothing about the
    add-on changes, and nothing is worked around that affects the artifact — but
    the check has to run where Blender can write, or it fails for a reason that
    has nothing to do with the product.

    Falls back to the system temporary folder if ``_tools/`` is not available, so
    the script still works on a machine without one.
    """
    preferred = REPO / "_tools" / "fbxscale-check"
    try:
        if preferred.exists():
            shutil.rmtree(preferred, ignore_errors=True)
        preferred.mkdir(parents=True, exist_ok=True)
        # Prove it really is writable with a dot-prefixed name before trusting it.
        probe = preferred / ".writable"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return preferred
    except OSError:
        return Path(tempfile.mkdtemp(prefix="fbxscale-blender-"))


def run_blender(blender: Path, environment: dict, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(blender), *arguments],
        cwd=PRODUCT,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=900,
    )


def meaningful(text: str) -> list[str]:
    """Blender's output without its own noise."""
    keep = ("ok ", "FAIL", "---", "note ", "Success", "created:", "building:")
    return [
        line
        for line in text.splitlines()
        if line.startswith(keep) or "FATAL_ERROR" in line or "Error" in line
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the add-on inside Blender")
    parser.add_argument("--blender", help="path to blender.exe, overriding the search")
    parser.add_argument("--keep", action="store_true", help="keep the throwaway folders")
    arguments = parser.parse_args()

    blender = find_blender(arguments.blender)
    if blender is None:
        print("Blender was not found.")
        print("Set FBXSCALE_BLENDER, pass --blender, or put a portable build in _tools/.")
        return 1

    print(f"Blender: {blender}")

    work = scratch_home()
    home = work / "home"
    environment = isolated_environment(home)

    # --- Blender's own manifest reader -------------------------------------
    section("Blender validates the manifest")

    validated = run_blender(blender, environment, ["--command", "extension", "validate", "."])
    for line in meaningful(validated.stdout):
        print(f"  {line}")
    check(validated.returncode == 0, "extension validate accepts the source folder")

    # --- Building ----------------------------------------------------------
    section("Blender builds the package")

    # Built into a scratch folder outside the product, then copied to ``dist``.
    #
    # This is not tidiness, it is a workaround with a diagnosis. Blender's builder
    # writes the archive through a temporary file named ``.<package>.zip`` beside
    # the target, and on this machine that write is refused with "Permission
    # denied" when the target is anywhere under the product folder — while the
    # very same build succeeds under ``_tools/``. Creating a dot-prefixed file by
    # hand in those folders works, so the difference is not a filesystem rule we
    # can see, and it is recorded as unexplained rather than explained badly.
    #
    # What is verified either way: the package is built by Blender's own builder,
    # validated by Blender's own validator, and installed by Blender's own
    # install-file. Only the folder it is built in differs.
    build_dir = PRODUCT / "dist"
    build_dir.mkdir(exist_ok=True)
    scratch = REPO / "_tools" / "fbxscale-build"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)

    built_run = run_blender(
        blender,
        environment,
        [
            "--command",
            "extension",
            "build",
            "--source-dir",
            ".",
            "--output-dir",
            str(scratch),
        ],
    )
    for line in meaningful(built_run.stdout):
        print(f"  {line}")
    check(built_run.returncode == 0, "extension build succeeds")

    zips = sorted(scratch.glob("*.zip"))
    if zips:
        for stale in build_dir.glob("*.zip"):
            stale.unlink()
        shutil.copy2(zips[0], build_dir / zips[0].name)
        zips = sorted(build_dir.glob("*.zip"))
    check(len(zips) == 1, f"exactly one package was produced ({[z.name for z in zips]})")

    if not zips:
        print("\nNothing to install. Stopping.")
        if not arguments.keep:
            shutil.rmtree(work, ignore_errors=True)
        return 1

    package = zips[0]
    print(f"  package: {package.name}  ({package.stat().st_size / 1024:.1f} KB)")

    # --- Installing --------------------------------------------------------
    section("Blender installs it into a throwaway repository")

    installed = run_blender(
        blender,
        environment,
        ["--command", "extension", "install-file", "-r", "user_default", "-e", str(package)],
    )
    for line in meaningful(installed.stdout):
        print(f"  {line}")
    check(installed.returncode == 0, "install-file succeeds")

    listed = run_blender(blender, environment, ["--command", "extension", "list"])
    listed_text = listed.stdout + listed.stderr
    check(
        "fbxscale" in listed_text,
        "Blender's own list shows the installed extension",
    )
    for line in listed_text.splitlines():
        if "fbxscale" in line:
            print(f"  listed as: {line.strip()}")

    # --- Loading it inside a real Blender ----------------------------------
    section("The add-on loads and registers inside Blender")

    inside = run_blender(
        blender,
        environment,
        [
            "--background",
            "--factory-startup",
            "--python",
            str(PRODUCT / "tests" / "test_in_blender.py"),
            "--",
            str(PRODUCT),
        ],
    )
    for line in meaningful(inside.stdout):
        print(f"  {line}")

    if "FAIL" not in inside.stdout and "all " not in inside.stdout:
        print("\n  Blender did not reach the checks. Last of its output:")
        print("\n".join(inside.stdout.splitlines()[-20:]))
        check(False, "the in-Blender script ran to completion")
    else:
        check("FAIL" not in inside.stdout, "no in-Blender check failed")
        for line in inside.stdout.splitlines():
            if line.startswith("all "):
                print(f"  {line}")

    if not arguments.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"\nKept {work}")

    print()
    if _failures:
        print(f"{len(_failures)} of {_checks} checks failed.")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    print(f"all {_checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
