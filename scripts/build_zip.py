#!/usr/bin/env python3
"""Builds the package the Blender extensions catalogue expects.

Two things happen here, and the order matters:

1. **The tests run first, and a failure stops the build.** That refusal is the
   point of this file. A manifest with a stale version, or a syntax error in a
   file nobody imported locally, is the sort of thing that reaches a reviewer
   instead of a developer.
2. **Blender's own builder produces the archive**, when Blender can be found. It
   applies the ``[build] paths`` allowlist from the manifest and stamps the
   archive with generated metadata, so the artifact is one Blender made rather
   than one we imitated. Without Blender, the same list is packed with the
   standard library.

The allowlist is read out of the manifest rather than repeated here, so there is
exactly one place that decides what ships.

Usage: python scripts/build_zip.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
REPO = PRODUCT.parent.parent
DIST = PRODUCT / "dist"
TOOLS = REPO / "_tools"

#: Files needed at runtime even if the manifest's list were somehow incomplete.
#: Checked before packing, so an omission is an error here rather than an
#: ImportError in somebody's Blender.
REQUIRED = [
    "__init__.py",
    "ui.py",
    "core/__init__.py",
    "core/fbx.py",
    "core/scan.py",
    "core/cli.py",
]


def read_manifest() -> dict:
    text = (PRODUCT / "blender_manifest.toml").read_text(encoding="utf-8")
    values: dict = {}
    paths: list[str] = []
    in_paths = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line == "":
            continue
        if in_paths:
            if line.startswith("]"):
                in_paths = False
                continue
            entry = line.strip().strip(",").strip().strip('"')
            if entry:
                paths.append(entry)
            continue
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        if key == "paths" and value.startswith("[") and "]" not in value:
            in_paths = True
            continue
        values[key] = value.strip('"')

    if not paths:
        raise SystemExit("No [build] paths found in blender_manifest.toml")
    values["paths"] = paths
    return values


def run(command: list[str], description: str) -> bool:
    print(f"\n--- {description} ---")
    finished = subprocess.run(
        command, cwd=PRODUCT, text=True, encoding="utf-8", errors="replace"
    )
    return finished.returncode == 0


def find_blender() -> Path | None:
    explicit = os.environ.get("FBXSCALE_BLENDER")
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


def build_with_blender(blender: Path, version: str, allowed: list[str]) -> Path | None:
    """Uses Blender's builder, working around where it is allowed to write.

    Blender writes the archive through a dot-prefixed temporary file beside the
    target, and on this machine such writes are refused under the product folder
    while succeeding under ``_tools/``. Rather than explain that away, the build
    happens where it works and the finished archive is copied to ``dist/``. What
    is verified either way is unchanged: the archive is built by Blender's own
    builder from the manifest's own allowlist.
    """
    scratch = TOOLS / "fbxscale-build"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    try:
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / ".writable").write_text("", encoding="utf-8")
        (scratch / ".writable").unlink()
    except OSError:
        print("  _tools/ is not usable here; packing with the standard library instead")
        return None

    finished = subprocess.run(
        [
            str(blender),
            "--command",
            "extension",
            "build",
            "--source-dir",
            ".",
            "--output-dir",
            str(scratch),
        ],
        cwd=PRODUCT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=600,
    )
    for line in (finished.stdout + finished.stderr).splitlines():
        if "created:" in line or "building:" in line or "FATAL" in line:
            print(f"  {line.strip()}")

    if finished.returncode != 0:
        print("  Blender's builder failed; packing with the standard library instead")
        return None

    produced = sorted(scratch.glob("*.zip"))
    if not produced:
        return None

    DIST.mkdir(exist_ok=True)
    target = DIST / f"fbxscale-{version}.zip"
    if target.exists():
        target.unlink()
    shutil.copy2(produced[0], target)
    return target


def build_with_stdlib(version: str, allowed: list[str]) -> Path:
    """Packs the allowlist with the standard library, for machines without Blender."""
    DIST.mkdir(exist_ok=True)
    target = DIST / f"fbxscale-{version}.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in allowed:
            archive.write(PRODUCT / name, name)

    return target


def main() -> int:
    manifest = read_manifest()
    version = str(manifest["version"])
    allowed = list(manifest["paths"])
    print(f"FbxScale {version}")
    print(f"Files in the package, from the manifest: {len(allowed)}")

    missing = [name for name in REQUIRED if name not in allowed]
    if missing:
        print(f"\nThe manifest's [build] paths omit files the add-on needs: {missing}")
        return 1

    absent = [name for name in allowed if not (PRODUCT / name).exists()]
    if absent:
        print(f"\nThe manifest lists files that do not exist: {absent}")
        return 1

    for command, description in (
        ([sys.executable, "tests/test_fbx.py"], "Reader tests"),
        ([sys.executable, "tests/test_scan.py"], "Scanner tests"),
        ([sys.executable, "tests/test_cli.py"], "Command-line tests"),
        ([sys.executable, "scripts/check_addon.py"], "Manifest and packaging checks"),
    ):
        if not run(command, description):
            print(f"\n{description} failed. Nothing was built.")
            return 1

    print("\n--- Packing ---")
    blender = find_blender()
    target = None
    if blender is not None:
        print(f"  using Blender's builder: {blender}")
        target = build_with_blender(blender, version, allowed)
    if target is None:
        target = build_with_stdlib(version, allowed)
        print("  packed with the standard library")

    # Opened again and checked, because an archive that unpacks into a subfolder
    # is rejected by the catalogue with a message that names nothing useful.
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        if "blender_manifest.toml" not in names:
            print("The manifest is not at the root of the archive. Refusing.")
            return 1
        corrupt = archive.testzip()
        if corrupt is not None:
            print(f"Corrupt entry in the archive: {corrupt}")
            return 1

    print(f"\n  {len(names)} files, manifest at the root, archive readable:")
    for name in sorted(names):
        print(f"    {name}")

    print(f"\nBuilt {target}  ({target.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
