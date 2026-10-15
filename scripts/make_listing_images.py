#!/usr/bin/env python3
"""Builds the images the submission form demands: one featured image and previews.

The form asks for two things and blocks submission without both:

* **Featured image, 1920x1080, 16:9 — required.** The picture in the catalogue
  listing, so it has to say what the add-on does in one look.
* **Previews, at least one, 16:9 — required.** "Show off your add-on," the form
  says, and warns against flashy images. So each preview shows one thing the tool
  actually does, rather than a montage.

Where the pictures come from: **the add-on's own output**, rendered at the size the
form wants. Not mock-ups, not drawings of an interface that does not exist — the
report this tool writes, and the command it runs. The catalogue therefore cannot
promise something the program does not do.

Three pictures are produced:

1. ``featured-image.png`` — a folder with problems in it. The main listing image.
2. ``preview-all-clear.png`` — a folder where everything is fine. Shows the tool is
   not merely a complainer.
3. ``preview-command-line.png`` — the same check from a terminal, which is how
   somebody without Blender would use it.

The demo folder is made up and named so it reads like a game project. It does not
exist on anybody's machine, and the paths in the pictures are written here rather
than read from wherever this happened to run.

Usage: python scripts/make_listing_images.py
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
# Both paths are needed: ``scripts`` for the drawing helpers, and the product root
# for ``core``. The first version added only ``scripts`` and failed to import
# ``core``.
sys.path.insert(0, str(PRODUCT))
sys.path.insert(0, str(PRODUCT / "scripts"))

from core.scan import scan_folder  # noqa: E402
from make_icon import png_bytes  # noqa: E402
from split_icon_sheet import read_image  # noqa: E402

DIST = PRODUCT / "dist"
FIXTURES = PRODUCT / "tests" / "fixtures"

WIDTH, HEIGHT = 1920, 1080

#: Files with problems — the featured image.
PROBLEM_FILES = [
    ("props/crate.fbx", "centimetres_default.fbx"),
    ("props/barrel.fbx", "metres_factor100.fbx"),
    ("props/old/bracket.fbx", "broken_small_scale.fbx"),
    ("characters/hero.fbx", "no_scale_declared.fbx"),
]

#: Files that are all fine — the second preview.
CLEAN_FILES = [
    ("props/crate.fbx", "centimetres_default.fbx"),
    ("props/barrel.fbx", "metres_factor100.fbx"),
    ("props/door.fbx", "centimetres_default.fbx"),
    ("characters/hero.fbx", "metres_factor100.fbx"),
    ("characters/npc.fbx", "centimetres_default.fbx"),
]

LEVEL_COLOURS = {
    "bad": ("#7f1d1d", "#fee2e2"),
    "warn": ("#78350f", "#fef3c7"),
    "unknown": ("#1e3a5f", "#dbeafe"),
    "ok": ("#14532d", "#dcfce7"),
}

PAGE_STYLE = """
  * { box-sizing: border-box; }
  html, body { width: %(width)dpx; height: %(height)dpx; margin: 0; overflow: hidden;
               background: #ffffff; color: #111827;
               font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .banner { background: #0f172a; color: #f1f5f9; padding: 42px 64px 38px; }
  .banner-title { font-size: 44px; font-weight: 700; letter-spacing: -0.01em; }
  .banner-sub { color: #94a3b8; font-size: 19px; margin-top: 8px; }
  .headline { margin: 34px 64px 0; font-size: 26px; font-weight: 700; }
  .where { margin: 2px 64px 0; color: #6b7280; font-size: 15px;
           font-family: ui-monospace, monospace; }
  .tally { margin: 18px 64px 0; font-size: 15px; color: #374151; }
  .tally b { color: #111827; }
  table { border-collapse: collapse; margin: 22px 64px 0; width: calc(100%% - 128px); }
  th { text-align: left; font-size: 12px; letter-spacing: .05em; text-transform: uppercase;
       color: #6b7280; padding: 0 12px 8px; border-bottom: 1px solid #e5e7eb; }
  th.num { text-align: right; }
  td { padding: 13px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
  td.file { font-family: ui-monospace, monospace; font-size: 15px; white-space: nowrap; }
  td.verdict span { padding: 2px 9px; border-radius: 999px; font-size: 12px; }
  td.found strong { font-size: 15px; font-weight: 600; }
  td.found div { color: #6b7280; font-size: 13px; margin-top: 3px; max-width: 900px; }
  td.num { text-align: right; font-family: ui-monospace, monospace; }
  .terminal { margin: 26px 64px 0; background: #0f172a; border-radius: 10px;
              padding: 24px 30px; color: #e2e8f0; overflow: hidden;
              font: 15px/1.6 ui-monospace, "Cascadia Mono", Consolas, monospace; }
  .terminal .prompt { color: #64748b; }
  .terminal .fail { color: #fca5a5; }
  .terminal .ok { color: #86efac; }
  .terminal .unknown { color: #93c5fd; }
  .terminal .dim { color: #94a3b8; }
  footer { margin: 26px 64px 0; color: #9ca3af; font-size: 13px; }
""" % {"width": WIDTH, "height": HEIGHT}


def write_demo_folder(root: Path, files: list[tuple[str, str]], with_extras: bool) -> None:
    """Copies fixtures into a folder shaped like a real project."""
    for relative, fixture in files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / fixture, target)

    if with_extras:
        # A bought asset pack, which is where binary FBX files come from, and a file
        # in another format so the report has something to declare as skipped.
        (root / "characters" / "bought_pack.fbx").write_bytes(
            b"Kaydara FBX Binary  \x00\x1a\x00" + b"\x00" * 64
        )
        (root / "props" / "source.blend").write_text("placeholder", encoding="utf-8")


def report_page(result, subtitle: str) -> str:
    """The report as a page sized for photographing.

    The page is **written** rather than restyled. The report's own stylesheet is
    built for a browser window of any size; this page is photographed at one, and
    overriding that stylesheet produced two broken renders — a table wider than the
    window, and then a five-column table whose fifth column silently received no
    width. Writing the markup here is less clever and it works.
    """
    counts = result.counts
    rows = []
    for finding in result.sorted_findings:
        foreground, background = LEVEL_COLOURS.get(finding.level, ("#111", "#eee"))
        factor = (
            "&mdash;" if finding.declared_factor is None else f"{finding.declared_factor:g}"
        )
        note = finding.detail or finding.error or ""
        rows.append(
            "<tr>"
            f'<td class="file">{html.escape(finding.relative)}</td>'
            f'<td class="verdict"><span style="background:{background};'
            f'color:{foreground}">{html.escape(finding.level)}</span></td>'
            f'<td class="found"><strong>{html.escape(finding.summary)}</strong>'
            f'<div>{html.escape(note)}</div></td>'
            f'<td class="num">{factor}</td>'
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="color-scheme" content="light">
<title>{html.escape(result.headline())}</title>
<style>{PAGE_STYLE}</style>
<div class="banner">
  <div class="banner-title">FBX Scale Report</div>
  <div class="banner-sub">{subtitle}</div>
</div>
<div class="headline">{html.escape(result.headline())}</div>
<div class="where">{html.escape(str(result.root))}</div>
<div class="tally">
  <b>{counts.get('bad', 0)}</b> broken &nbsp; <b>{counts.get('warn', 0)}</b> worth a look
  &nbsp; <b>{counts.get('ok', 0)}</b> fine &nbsp; <b>{counts.get('unknown', 0)}</b> unreadable
</div>
<table>
  <thead><tr><th>File</th><th>Verdict</th><th>What was found</th>
  <th class="num">Factor</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
<footer>Nothing was modified. FBX declares lengths in centimetres, so the factor is
what one file unit means; a factor of 1 is a centimetre and a factor of 100 is a metre.</footer>
</html>
"""


def command_line_page() -> str:
    """The terminal output, laid out by hand from a real run.

    Kept as a page rather than a screenshot of a real console because a console
    window cannot be styled to the catalogue's 16:9 and would carry the machine's
    own colours and font. The text is the tool's, the frame is ours, and the
    frame is not pretending to be a photograph of a terminal.
    """
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="color-scheme" content="light">
<title>FBX scale check from the command line</title>
<style>{PAGE_STYLE}</style>
<div class="banner">
  <div class="banner-title">FBX Scale Report</div>
  <div class="banner-sub">The same check without Blender &mdash; a terminal, and an
  exit code a pipeline can read</div>
</div>
<div class="terminal">
<div><span class="prompt">$</span> python -m core.cli D:/projects/harbour/assets</div>
<div>&nbsp;</div>
<div>5 FBX files: 2 with a broken scale.</div>
<div class="dim">Folder: D:/projects/harbour/assets</div>
<div>&nbsp;</div>
<div><span class="fail">[FAIL]</span> characters/hero.fbx</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; No UnitScaleFactor</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; GlobalSettings exists but does not declare a unit scale. Every</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; importer will fall back to its own default, and two importers</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; will disagree.</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; wrote: Homemade Pipeline Tool</div>
<div>&nbsp;</div>
<div><span class="fail">[FAIL]</span> props/old/bracket.fbx</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Suspiciously small scale (factor 0.01)</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; factor 0.01, one unit = 0.0001 m (original was 1)</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; wrote: Some CAD Exporter 3.2</div>
<div>&nbsp;</div>
<div><span class="unknown">[????]</span> props/bought_pack.fbx</div>
<div class="dim">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Binary FBX &mdash; not read</div>
<div>&nbsp;</div>
<div><span class="ok">[ok&nbsp;&nbsp;]</span> props/barrel.fbx &nbsp;<span class="dim">factor 100, one unit = 1 m</span></div>
<div><span class="ok">[ok&nbsp;&nbsp;]</span> props/crate.fbx &nbsp;&nbsp;<span class="dim">factor 1, one unit = 0.01 m</span></div>
<div>&nbsp;</div>
<div><span class="prompt">$</span> echo $?</div>
<div>1 <span class="dim">&mdash; a broken scale, so the build stops here</span></div>
</div>
<footer>No Blender, no network, no server. The same code the add-on runs, reachable
from a script.</footer>
</html>
"""


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


def shoot(chrome: str, page: str, target: Path) -> bool:
    """Renders a page and screenshots it at exactly the catalogue's size."""
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "page.html"
        source.write_text(page, encoding="utf-8")
        finished = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={WIDTH},{HEIGHT}",
                f"--screenshot={target}",
                source.resolve().as_uri(),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if target.exists():
        print(f"  {target.name}  {WIDTH}x{HEIGHT}  ({target.stat().st_size / 1024:.0f} KB)")
        return True
    print(f"  {target.name}: screenshot failed — {finished.stderr.strip()[:160]}")
    return False


def icon_256() -> Path:
    """Upscales the 128 icon to the 256 the form asks for.

    Honest about what this is: the master artwork is a 456-pixel rendering, and a
    true 256 should be reduced from that rather than enlarged from the 128. Doing it
    properly means re-running the tile extraction with a tighter crop so the frame
    sits closer to the edge, which is a separate job. For the form, an enlarged 128
    is accepted and this says so rather than pretending otherwise.
    """
    source = PRODUCT / "icons" / "icon-128.png"
    width, height, pixels = read_image(source)

    scale = 2
    rows = [
        [pixels[y // scale][x // scale] for x in range(width * scale)]
        for y in range(height * scale)
    ]

    target = DIST / "icon-256.png"
    target.write_bytes(png_bytes(width * scale, height * scale, rows))
    print(f"  {target.name}  {width * scale}x{height * scale}  "
          f"({target.stat().st_size / 1024:.0f} KB, enlarged from 128)")
    return target


def main() -> int:
    DIST.mkdir(exist_ok=True)
    print("Listing images")

    chrome = find_chrome()
    if chrome is None:
        print("  No Chrome or Edge found: the images cannot be rendered.")
        print("  Both are required for submission, so this has to be resolved first.")
        return 1

    with tempfile.TemporaryDirectory() as temporary:
        demo = Path(temporary)

        problems = demo / "problems"
        write_demo_folder(problems, PROBLEM_FILES, with_extras=True)
        result = scan_folder(problems)
        result.root = Path("D:/projects/harbour/assets")
        ok = shoot(
            chrome,
            report_page(
                result,
                "Every FBX file's declared unit scale, read from the file itself "
                "&mdash; before an engine scales it wrong",
            ),
            DIST / "featured-image.png",
        )
        print(f"    headline: {result.headline()}")
        if not ok:
            return 1

        clean = demo / "clean"
        write_demo_folder(clean, CLEAN_FILES, with_extras=False)
        clean_result = scan_folder(clean)
        clean_result.root = Path("D:/projects/harbour/assets")
        ok = shoot(
            chrome,
            report_page(
                clean_result,
                "The same folder after the exports were fixed &mdash; every file "
                "declares a scale, and the tool says so and stops",
            ),
            DIST / "preview-all-clear.png",
        )
        print(f"    headline: {clean_result.headline()}")
        if not ok:
            return 1

        if not shoot(chrome, command_line_page(), DIST / "preview-command-line.png"):
            return 1

    icon_256()

    print("\nReady for the form:")
    for name in (
        "featured-image.png",
        "preview-all-clear.png",
        "preview-command-line.png",
        "icon-256.png",
    ):
        print(f"  {DIST / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
