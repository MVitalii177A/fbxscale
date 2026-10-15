#!/usr/bin/env python3
"""Checks that can be made about the add-on without Blender installed.

This is not a substitute for testing in Blender — the UI has never been run
inside Blender and this file does not pretend otherwise. What it does catch is
the class of mistake that would make the add-on fail to *load*: a manifest that
does not parse, a manifest missing a field the catalogue requires, a Python file
with a syntax error, a version that disagrees with itself between two files.

A load failure is the worst kind of bug to ship, because the user sees "the
extension is invalid" and has nothing to act on. Every check here exists because
it can be checked on a machine without Blender.

Usage: python scripts/check_addon.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent

#: Platform names Blender accepts in the manifest. Taken from Blender's own
#: validator output rather than from documentation, because the two disagreed
#: about the *shape* of the field even when the names were right.
KNOWN_PLATFORMS = {
    "windows-x64",
    "windows-arm64",
    "linux-x64",
    "macos-x64",
    "macos-arm64",
}

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


def parse_toml(text: str) -> dict:
    """A minimal TOML reader, for exactly the shapes this manifest uses.

    Python 3.11 has ``tomllib``, but this check should also run under Blender's
    own Python, which may be older. Only what the manifest needs is supported:
    top-level ``key = value`` pairs, simple ``[table]`` headers, and multiline
    arrays.

    Multiline arrays were added after the manifest grew a ``[build] paths`` list
    written one entry per line. This reader had no support for them and raised
    "not a key = value line" on the second entry — while Blender read the same
    file happily. A hand-written parser is only ever as good as the cases it has
    been shown, which is the recurring lesson of this file.
    """
    result: dict = {}
    table: dict = result
    number = 0
    lines = text.splitlines()

    while number < len(lines):
        raw = lines[number]
        number += 1
        line = raw.split("#", 1)[0].strip()
        if line == "":
            continue

        if line.startswith("[[") and line.endswith("]]"):
            name = line[2:-2].strip().strip('"')
            entry: dict = {}
            target = result.setdefault(name, [])
            if not isinstance(target, list):  # pragma: no cover - defensive
                raise ValueError(f"line {number}: {name} is not an array of tables")
            target.append(entry)
            table = entry
            continue

        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().strip('"')
            table = result.setdefault(name, {})
            if not isinstance(table, dict):  # pragma: no cover - defensive
                raise ValueError(f"line {number}: {name} is not a table")
            continue

        key, separator, value = line.partition("=")
        if separator == "":
            raise ValueError(f"line {number}: not a key = value line: {raw!r}")
        key = key.strip().strip('"')
        value = value.strip()

        # A value that opens a bracket and does not close it runs on across the
        # following lines until one does.
        if value.startswith("[") and "]" not in value:
            while "]" not in value and number < len(lines):
                value += " " + lines[number].split("#", 1)[0].strip()
                number += 1

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            table[key] = [
                item.strip().strip('"') for item in inner.split(",") if item.strip()
            ]
        elif value.startswith('"') and value.endswith('"'):
            table[key] = value[1:-1]
        else:
            table[key] = value

    return result


def check_manifest() -> None:
    section("blender_manifest.toml")

    path = PRODUCT / "blender_manifest.toml"
    check(path.exists(), "the manifest exists")

    try:
        manifest = parse_toml(path.read_text(encoding="utf-8"))
    except ValueError as problem:
        check(False, f"the manifest parses ({problem})")
        return
    check(True, "the manifest parses")

    # Fields the catalogue requires. Missing any of these means the extension is
    # rejected at upload, which is a slow way to find out.
    required = [
        "schema_version",
        "id",
        "name",
        "version",
        "tagline",
        "type",
        "maintainer",
        "license",
        "blender_version_min",
    ]
    for field in required:
        check(field in manifest, f"'{field}' is present")

    check(
        manifest.get("schema_version") == "1.0.0",
        f"schema_version is 1.0.0 (got {manifest.get('schema_version')!r})",
    )
    check(
        manifest.get("type") == "add-on",
        f"type is 'add-on' (got {manifest.get('type')!r})",
    )
    check(
        manifest.get("id") == PRODUCT.name,
        f"id matches the folder name (id={manifest.get('id')!r}, folder={PRODUCT.name!r})",
    )

    version = str(manifest.get("version", ""))
    check(
        re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
        f"version is three numbers, as the catalogue requires (got {version!r})",
    )

    # Length limits. These were added after Blender's own validator rejected two
    # versions of the manifest that this file had passed: the catalogue enforces
    # limits this checker did not know about, which is exactly the sort of gap a
    # home-made check produces. Kept here anyway, because failing in a second is
    # better than failing after Blender starts.
    tagline = str(manifest.get("tagline", ""))
    check(
        len(tagline) <= 64,
        f"tagline is within 64 characters (got {len(tagline)})",
    )
    check(len(tagline) > 10, f"tagline says something (got {len(tagline)} characters)")

    permissions = manifest.get("permissions", {})
    if isinstance(permissions, dict):
        allowed = {"files", "clipboard", "microphone", "network", "camera"}
        unknown = sorted(set(permissions) - allowed)
        check(
            not unknown,
            f"every permission key is one Blender knows (unknown: {unknown})",
        )
        for key, value in permissions.items():
            check(
                len(str(value)) <= 64,
                f"the '{key}' permission text is within 64 characters "
                f"(got {len(str(value))})",
            )
    else:
        check(False, f"permissions is a table (got {type(permissions).__name__})")

    platforms = manifest.get("platforms")
    check(
        isinstance(platforms, list) and len(platforms) > 0,
        "at least one platform is declared",
    )
    if isinstance(platforms, list):
        check(
            all(isinstance(item, str) for item in platforms),
            "platforms is a list of strings, not a list of tables",
        )
        check(
            all(item in KNOWN_PLATFORMS for item in platforms),
            f"every platform is a name Blender knows (got {platforms})",
        )

    licenses = manifest.get("license")
    check(
        isinstance(licenses, list) and len(licenses) > 0,
        "license is a non-empty list",
    )
    if isinstance(licenses, list):
        check(
            all(str(item).startswith("SPDX:") for item in licenses),
            "every license entry uses the SPDX: prefix the schema requires",
        )

    minimum = str(manifest.get("blender_version_min", ""))
    check(
        re.fullmatch(r"\d+\.\d+(\.\d+)?", minimum) is not None,
        f"blender_version_min is a version number (got {minimum!r})",
    )
    check(
        minimum >= "4.2",
        f"the minimum is 4.2 or later, the first release reading this format (got {minimum})",
    )


def check_python_files() -> None:
    section("Python syntax")

    files = sorted(PRODUCT.rglob("*.py"))
    check(len(files) > 0, f"found Python files to check ({len(files)})")

    for path in files:
        relative = path.relative_to(PRODUCT)
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            check(True, f"{relative} compiles")
        except SyntaxError as problem:
            check(False, f"{relative} compiles (line {problem.lineno}: {problem.msg})")
        except UnicodeDecodeError as problem:
            check(False, f"{relative} is valid UTF-8 ({problem})")


def check_versions_agree() -> None:
    section("Versions agree")

    manifest = parse_toml((PRODUCT / "blender_manifest.toml").read_text(encoding="utf-8"))
    manifest_version = str(manifest.get("version"))

    cli = (PRODUCT / "core" / "cli.py").read_text(encoding="utf-8")
    check(
        "__version__" not in cli,
        "the CLI does not keep a second copy of the version",
    )

    # The version lives in exactly one place on purpose. Two copies drift, and a
    # catalogue entry whose version disagrees with the code is a support question
    # nobody can answer.
    mentions = [
        path.relative_to(PRODUCT)
        for path in PRODUCT.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".toml"}
        and path.name != "check_addon.py"
        and re.search(r'version\s*=\s*"', path.read_text(encoding="utf-8", errors="replace"))
    ]
    check(
        len(mentions) == 1,
        f"the version appears in one file only (found: {[str(m) for m in mentions]})",
    )
    check(
        manifest_version == "0.1.0",
        f"the version is the one we intend to publish (got {manifest_version!r})",
    )


def check_no_blender_import_in_core() -> None:
    section("core does not import Blender")

    core = PRODUCT / "core"
    offenders = []
    for path in sorted(core.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        # ``import bpy`` at the start of a line, so that a mention inside a
        # docstring explaining *why* there is none does not count.
        if re.search(r"^\s*(import bpy|from bpy)", text, re.MULTILINE):
            offenders.append(str(path.relative_to(PRODUCT)))

    check(
        not offenders,
        f"nothing under core/ imports bpy (offenders: {offenders})",
    )
    check(
        (PRODUCT / "ui.py").exists(),
        "there is a ui.py, which is where the Blender import is allowed to live",
    )
    ui = (PRODUCT / "ui.py").read_text(encoding="utf-8")
    check("import bpy" in ui, "and it does import bpy")


def check_docs_exist() -> None:
    section("Documents")

    for name in ("README.md", "DECISIONS.md", "LICENSE"):
        check((PRODUCT / name).exists(), f"{name} exists")


def main() -> int:
    print(f"Checking the add-on at {PRODUCT}")

    check_manifest()
    check_python_files()
    check_versions_agree()
    check_no_blender_import_in_core()
    check_docs_exist()

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
