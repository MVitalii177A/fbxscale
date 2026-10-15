#!/usr/bin/env python3
"""Command-line entry point: report the declared scale of a folder of FBX files.

Exists for three reasons, in order of importance:

1. **It makes the tool usable without Blender.** A technical artist who wants to
   check a delivery before opening an engine should not have to launch a 3D
   application to do it.
2. **It makes the tool testable end to end.** The tests import the modules; this
   proves the modules work when driven the way a person drives them.
3. **It is the escape hatch.** If the Blender add-on's UI is wrong — and a first
   version's UI usually is — the logic underneath is still reachable.

Exit code is 1 when a file has a broken scale, 0 otherwise, so it can be put in
a pipeline or a git hook. Unreadable files (binary, truncated) do not fail the
run: they are reported, not blamed.

Usage:
    python -m core.cli <folder>
    python -m core.cli <folder> --csv report.csv --html report.html
    python -m core.cli <folder> --quiet          # only the headline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .scan import DEFAULT_EXTENSIONS, scan_folder

__all__ = ["main", "build_parser", "configure_output"]


def configure_output() -> None:
    """Makes printing the report work on Windows.

    The reports contain em dashes and the reader's own text, and Windows consoles
    default to a legacy code page that cannot encode them — which turned a dash
    into a replacement character in the first end-to-end run. Reconfiguring to
    UTF-8 is the fix that belongs in the tool rather than in the user's terminal
    settings.

    Guarded because ``reconfigure`` exists only on ``TextIOWrapper``, and because
    a redirected stream may not support it. Failure is not worth reporting: the
    only consequence is uglier output, never a wrong answer.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - depends on the stream
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fbxscale",
        description=(
            "Report the unit scale declared inside FBX files. Reads the files, "
            "changes nothing."
        ),
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="folder to scan",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="only look at the folder itself, not its subfolders",
    )
    parser.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help=f"comma-separated extensions to read (default: {','.join(DEFAULT_EXTENSIONS)})",
    )
    parser.add_argument("--csv", type=Path, help="also write a CSV report here")
    parser.add_argument("--html", type=Path, help="also write an HTML report here")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print the headline only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_output()

    parser = build_parser()
    arguments = parser.parse_args(argv)

    extensions = tuple(
        extension if extension.startswith(".") else f".{extension}"
        for extension in (part.strip() for part in arguments.extensions.split(","))
        if extension
    )

    if not arguments.folder.is_dir():
        print(f"Not a folder: {arguments.folder}", file=sys.stderr)
        return 2

    result = scan_folder(
        arguments.folder,
        recursive=not arguments.no_recursive,
        extensions=extensions,
    )

    print(result.as_text() if not arguments.quiet else result.headline())

    if arguments.csv is not None:
        arguments.csv.write_text(result.as_csv(), encoding="utf-8")
        print(f"CSV written to {arguments.csv}")

    if arguments.html is not None:
        arguments.html.write_text(result.as_html(), encoding="utf-8")
        print(f"HTML written to {arguments.html}")

    # Broken scale fails the run; an unreadable file does not, because refusing
    # to read a binary FBX is a correct answer rather than a defect.
    return 1 if result.counts.get("bad", 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
