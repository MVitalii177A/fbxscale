"""Scanning a folder of FBX files and producing a report.

This is the layer the user actually asks for: "I have fifty props, which ones
are broken?" It walks a folder, reads each file through ``core.fbx``, and returns
a result that can be printed, written as CSV, or written as HTML.

No Blender here either, for the same reason as ``core.fbx``: this is the logic
that decides what the report says, and it must be testable without launching
Blender. ``ui.py`` only draws what this produces.
"""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from pathlib import Path

from .fbx import FbxFile, judge_scale, read_fbx

__all__ = [
    "Finding",
    "ScanResult",
    "scan_folder",
    "scan_files",
    "DEFAULT_EXTENSIONS",
]

#: What counts as a model file. ``.fbx`` is the point; the others are common
#: neighbours in an asset folder and are worth naming rather than silently
#: skipping, so the report can say "12 files skipped" and not look like it
#: missed them.
DEFAULT_EXTENSIONS = (".fbx",)

#: Extensions the report mentions as deliberately not read.
KNOWN_OTHER = (".blend", ".obj", ".gltf", ".glb", ".dae", ".3ds", ".stl", ".ply")

#: Ordering for the report: worst first, because the reader's eye stops at the
#: top. If "ok" sorted first, the broken files would be below the fold.
SEVERITY = {"bad": 0, "warn": 1, "unknown": 2, "ok": 3}


@dataclass(frozen=True)
class Finding:
    """One file's result, flattened for reporting."""

    path: Path
    relative: str
    level: str
    summary: str
    detail: str
    declared_factor: float | None
    original_factor: float | None
    metres_per_unit: float | None
    creator: str | None
    version: int | None
    is_binary: bool
    error: str | None

    @property
    def is_problem(self) -> bool:
        return self.level in {"bad", "warn"}


@dataclass
class ScanResult:
    """Everything a report needs, and nothing that depends on a UI."""

    root: Path
    findings: list[Finding] = field(default_factory=list)
    #: Files that matched the extension filter but could not be read.
    skipped_other: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.is_problem]

    @property
    def counts(self) -> dict[str, int]:
        counts = {"ok": 0, "warn": 0, "bad": 0, "unknown": 0}
        for finding in self.findings:
            counts[finding.level] = counts.get(finding.level, 0) + 1
        return counts

    @property
    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda finding: (SEVERITY.get(finding.level, 9), finding.relative.lower()),
        )

    def headline(self) -> str:
        """One sentence, the kind a person reads first."""
        counts = self.counts
        total = len(self.findings)
        if total == 0:
            return "No FBX files found."
        broken = counts.get("bad", 0)
        warned = counts.get("warn", 0)
        if broken == 0 and warned == 0:
            return f"{total} FBX files, all with a sane declared scale."
        parts = []
        if broken:
            parts.append(f"{broken} with a broken scale")
        if warned:
            parts.append(f"{warned} worth a look")
        return f"{total} FBX files: " + ", ".join(parts) + "."

    def as_text(self) -> str:
        """The report as plain text, for the Blender console and for tests."""
        lines = [self.headline(), f"Folder: {self.root}", ""]
        for finding in self.sorted_findings:
            marker = {"bad": "FAIL", "warn": "WARN", "unknown": "????", "ok": "ok  "}[
                finding.level
            ]
            lines.append(f"[{marker}] {finding.relative}")
            lines.append(f"         {finding.summary}")
            if finding.detail:
                lines.append(f"         {finding.detail}")
            if finding.declared_factor is not None:
                factor = f"{finding.declared_factor:g}"
                metres = finding.metres_per_unit
                metres_text = "unknown" if metres is None else f"{metres:g} m"
                line = f"         factor {factor}, one unit = {metres_text}"
                if (
                    finding.original_factor is not None
                    and finding.original_factor != finding.declared_factor
                ):
                    line += f" (original was {finding.original_factor:g})"
                lines.append(line)
            if finding.creator:
                lines.append(f"         wrote: {finding.creator}")
            lines.append("")
        if self.skipped_other:
            lines.append(
                f"Not read ({len(self.skipped_other)} other files): "
                + ", ".join(sorted(self.skipped_other)[:8])
            )
        return "\n".join(lines)

    def as_csv(self) -> str:
        """CSV, because the next thing anyone does is sort it in a spreadsheet."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "file",
                "level",
                "summary",
                "unit_scale_factor",
                "original_unit_scale_factor",
                "metres_per_unit",
                "creator",
                "fbx_version",
                "binary",
                "error",
            ]
        )
        for finding in self.sorted_findings:
            writer.writerow(
                [
                    finding.relative,
                    finding.level,
                    finding.summary,
                    "" if finding.declared_factor is None else f"{finding.declared_factor:g}",
                    "" if finding.original_factor is None else f"{finding.original_factor:g}",
                    "" if finding.metres_per_unit is None else f"{finding.metres_per_unit:g}",
                    finding.creator or "",
                    finding.version or "",
                    "yes" if finding.is_binary else "no",
                    finding.error or "",
                ]
            )
        return buffer.getvalue()

    def as_html(self) -> str:
        """A standalone report, openable without Blender.

        Kept self-contained — no external CSS, no scripts — because the whole
        point of a local tool is that the artefact it produces still opens in ten
        years.

        The page declares a **light** colour scheme explicitly rather than
        following the reader's system theme. It was written that way after looking
        at the output: the report is a table on a white background, and a viewer
        that inverted the text for a dark theme would have rendered it unreadable.
        A fixed light page inside a dark browser is a small rudeness; an
        unreadable file is a bug.
        """
        colours = {
            "bad": ("#7f1d1d", "#fee2e2"),
            "warn": ("#78350f", "#fef3c7"),
            "unknown": ("#1e3a5f", "#dbeafe"),
            "ok": ("#14532d", "#dcfce7"),
        }
        rows = []
        for finding in self.sorted_findings:
            foreground, background = colours.get(finding.level, ("#111", "#eee"))
            factor = "—" if finding.declared_factor is None else f"{finding.declared_factor:g}"
            metres = (
                "—" if finding.metres_per_unit is None else f"{finding.metres_per_unit:g} m"
            )
            note = finding.detail or ""
            if finding.error:
                note = finding.error
            rows.append(
                "<tr>"
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;'
                f'font-family:ui-monospace,monospace">{html.escape(finding.relative)}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb">'
                f'<span style="background:{background};color:{foreground};padding:2px 8px;'
                f'border-radius:999px;font-size:12px">{html.escape(finding.level)}</span></td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb">'
                f"{html.escape(finding.summary)}"
                f'<div style="color:#6b7280;font-size:12px;margin-top:2px">'
                f"{html.escape(note)}</div></td>"
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;'
                f'text-align:right">{factor}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;'
                f'text-align:right">{metres}</td>'
                "</tr>"
            )

        counts = self.counts
        return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="color-scheme" content="light">
<title>FBX scale report</title>
<style>
  body {{ font: 14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif;
          margin: 0; padding: 32px; color: #111827; background: #fff; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #6b7280; margin-bottom: 20px; }}
  .summary span {{ display: inline-block; margin-right: 14px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
  th {{ text-align: left; font-size: 12px; text-transform: uppercase;
        letter-spacing: .04em; color: #6b7280; padding: 0 10px 6px;
        white-space: nowrap; }}
  th.num {{ text-align: right; }}
  td {{ vertical-align: top; }}
  footer {{ margin-top: 28px; color: #9ca3af; font-size: 12px; }}
</style>
<h1>{html.escape(self.headline())}</h1>
<div class="sub">{html.escape(str(self.root))}</div>
<div class="summary">
  <span><strong>{counts.get('bad', 0)}</strong> broken</span>
  <span><strong>{counts.get('warn', 0)}</strong> worth a look</span>
  <span><strong>{counts.get('ok', 0)}</strong> fine</span>
  <span><strong>{counts.get('unknown', 0)}</strong> unreadable</span>
</div>
<table>
  <thead><tr>
    <th>File</th><th>Verdict</th><th>What was found</th>
    <th class="num">Factor</th><th class="num">1 unit&nbsp;=</th>
  </tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
<footer>Nothing was modified. FBX declares lengths in centimetres, so the factor
is what one file unit means; a factor of 1 is a centimetre and a factor of 100 is
a metre.</footer>
</html>
"""


def _finding_from(path: Path, root: Path, result: FbxFile) -> Finding:
    """Turns a parse result into a report row."""
    settings = result.global_settings
    verdict = judge_scale(settings)

    # A file we could not read at all outranks the scale verdict: "binary, not
    # read" is more important than whatever the (absent) settings implied.
    if result.is_binary:
        verdict_level = "unknown"
        verdict_summary = "Binary FBX — not read"
        verdict_detail = (
            "This tool reads ASCII FBX only. Blender writes ASCII by default, so "
            "this file probably came from a bought pack or CAD software. Open it "
            "in Blender and re-export to check its scale."
        )
    elif result.error is not None:
        verdict_level = "unknown"
        verdict_summary = "Could not be read"
        verdict_detail = result.error
    else:
        verdict_level = verdict.level
        verdict_summary = verdict.summary
        verdict_detail = verdict.detail

    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = str(path)

    return Finding(
        path=path,
        relative=relative,
        level=verdict_level,
        summary=verdict_summary,
        detail=verdict_detail,
        declared_factor=None if settings is None else settings.unit_scale_factor,
        original_factor=None if settings is None else settings.original_unit_scale_factor,
        metres_per_unit=None if settings is None else settings.metres_per_unit,
        creator=result.creator,
        version=result.file_version,
        is_binary=result.is_binary,
        error=result.error,
    )


def scan_files(paths, root: Path | None = None, extensions=DEFAULT_EXTENSIONS) -> ScanResult:
    """Scans an explicit list of paths. Used by the tests and by the UI."""
    paths = [Path(path) for path in paths]
    if root is None:
        root = paths[0].parent if paths else Path(".")
    root = Path(root)

    result = ScanResult(root=root)
    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            result.skipped_other.append(path.name)
            continue
        result.findings.append(_finding_from(path, root, read_fbx(path)))
    return result


def scan_folder(
    folder: str | Path,
    recursive: bool = True,
    extensions=DEFAULT_EXTENSIONS,
) -> ScanResult:
    """Scans a folder of FBX files.

    ``recursive`` defaults to True because asset folders are almost always nested
    by category, and a scan that silently misses the subfolder is worse than
    slow. The report lists what it skipped, so a wrong guess is visible rather
    than hidden.
    """
    folder = Path(folder)
    result = ScanResult(root=folder)

    if not folder.is_dir():
        return result

    walker = folder.rglob("*") if recursive else folder.glob("*")
    candidates = sorted(
        (path for path in walker if path.is_file()),
        key=lambda path: str(path).lower(),
    )

    for path in candidates:
        suffix = path.suffix.lower()
        if suffix in extensions:
            result.findings.append(_finding_from(path, folder, read_fbx(path)))
        elif suffix in KNOWN_OTHER:
            result.skipped_other.append(path.name)

    return result
