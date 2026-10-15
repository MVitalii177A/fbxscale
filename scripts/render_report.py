"""Renders the HTML report and screenshots it, so it can be looked at.

A report nobody has looked at is a report with unknown layout bugs. The unit
tests check that the HTML is well-formed, escaped and self-contained; they cannot
tell whether a column is unreadable or a colour is invisible. This script exists
to close that gap without a human opening a browser by hand.

Usage: python scripts/render_report.py [output-folder]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PRODUCT))

from core.scan import scan_folder  # noqa: E402

FIXTURES = PRODUCT / "tests" / "fixtures"


def build_demo_folder(root: Path) -> None:
    """A folder holding one of every verdict, so the report shows all colours."""
    (root / "props" / "old").mkdir(parents=True)
    (root / "characters").mkdir(parents=True)

    shutil.copy(FIXTURES / "centimetres_default.fbx", root / "props" / "crate.fbx")
    shutil.copy(FIXTURES / "metres_factor100.fbx", root / "props" / "barrel.fbx")
    shutil.copy(FIXTURES / "broken_small_scale.fbx", root / "props" / "old" / "bracket.fbx")
    shutil.copy(FIXTURES / "no_scale_declared.fbx", root / "characters" / "hero.fbx")

    # A binary file, so the "unknown" row colour appears too.
    (root / "characters" / "bought_pack.fbx").write_bytes(
        b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 64
    )


def find_chrome() -> str | None:
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else PRODUCT / "dist"
    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temporary:
        demo = Path(temporary)
        build_demo_folder(demo)

        result = scan_folder(demo)
        # The report names the temporary folder, which is noise in a screenshot.
        # Rewriting the root keeps the rendered example honest about everything
        # except where it happened to live.
        result.root = Path("C:/Projects/game/assets")

        report = destination / "report-example.html"
        report.write_text(result.as_html(), encoding="utf-8")
        print(f"Wrote {report}")
        print(f"  {result.headline()}")

        chrome = find_chrome()
        if chrome is None:
            print("\nNo Chrome or Edge found, so no screenshot was taken.")
            print("Open the file above in a browser to look at it.")
            return 0

        image = destination / "report-example.png"
        finished = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=1280,900",
                f"--screenshot={image}",
                report.resolve().as_uri(),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if image.exists():
            print(f"Wrote {image}  ({image.stat().st_size / 1024:.0f} KB)")
        else:
            print(f"Screenshot failed: {finished.stderr.strip()[:300]}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
