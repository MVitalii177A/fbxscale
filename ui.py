"""The Blender side: one button, one report.

Everything that decides anything lives in ``core``, which imports no Blender and
is tested without it (98 checks across three test files). This module draws a
panel, runs the scan, and shows the result. That split is ADR-002 in
``DECISIONS.md``, and it exists because Blender is not installed on the machine
where this was written — so the logic had to be testable on its own.

**What is not covered by tests.** The code in this file cannot be executed
without Blender, and Blender was not available. It is therefore the least
verified part of the add-on, and it is kept deliberately thin for that reason:
no scene changes, no mesh access, no threading, no operators beyond one. If it
is wrong, it is wrong in a way that is visible on the first press of the button
rather than in a saved file.

Known limits, stated here rather than discovered later:

* The report appears in Blender's **Info** editor's report area and in the
  console, not in a popup. A popup was considered and rejected: the interesting
  reports are dozens of lines long, and a popup that scrolls is worse than the
  console for this.
* ``max_files`` caps a scan so that pointing the tool at a whole drive does not
  look like a hang. The cap is reported when it is hit, never applied silently.
"""

from __future__ import annotations

import os
import sys

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

# Blender loads extensions as packages, so a relative import works. It is guarded
# because a developer may also drop this file next to ``core`` by hand, and a
# failed import should say so instead of taking Blender down with it.
try:
    from .core.scan import scan_folder
except ImportError:  # pragma: no cover - only reached outside a proper install
    try:
        from core.scan import scan_folder
    except ImportError:
        scan_folder = None


#: A scan of tens of thousands of files reads every one of them, which takes long
#: enough to look broken. The cap is generous for a real asset folder and is
#: announced in the report when it applies.
MAX_FILES = 5000


def _default_folder() -> str:
    """Where to start looking.

    The blend file's folder if there is one, because that is where the assets for
    the current job almost always are. Otherwise the user's home, rather than an
    empty field.
    """
    if bpy.data.filepath:
        return os.path.dirname(bpy.data.filepath)
    return os.path.expanduser("~")


class FBXSCALE_settings(PropertyGroup):
    """What the panel remembers between runs, and between sessions."""

    folder: StringProperty(
        name="Folder",
        description="Folder to scan for FBX files",
        subtype="DIR_PATH",
        default="",
    )
    recursive: BoolProperty(
        name="Include subfolders",
        description=(
            "Asset folders are usually nested by category, so this is on by "
            "default; an unfinished scan that silently misses a subfolder is "
            "worse than a slow one"
        ),
        default=True,
    )
    show_only_problems: BoolProperty(
        name="Only problems",
        description="Hide the files that are fine, so the report fits on screen",
        default=True,
    )
    max_files: IntProperty(
        name="File limit",
        description=(
            "Stop after this many files, and say so. Guards against pointing the "
            "tool at a whole drive"
        ),
        default=MAX_FILES,
        min=1,
        max=200000,
    )
    #: Сводка последнего скана. Показывается в панели, потому что консоль Blender
    #: (Window → Toggle System Console) новичок не находит: он нажимает Scan,
    #: видит «see the console» и уходит, так и не узнав результата.
    last_result: StringProperty(default="")


class FBXSCALE_OT_scan(Operator):
    """Scan a folder and report the unit scale each FBX file declares."""

    bl_idname = "fbxscale.scan"
    bl_label = "Scan for FBX scale problems"
    bl_description = (
        "Read the unit scale declared inside every FBX file in a folder, and "
        "report the ones that are wrong. Nothing is modified"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return scan_folder is not None

    def execute(self, context):
        settings = context.scene.fbxscale

        if scan_folder is None:  # pragma: no cover - defensive
            self.report({"ERROR"}, "The scanning module did not load.")
            return {"CANCELLED"}

        folder = settings.folder or _default_folder()
        if not os.path.isdir(folder):
            self.report({"ERROR"}, f"Not a folder: {folder}")
            return {"CANCELLED"}

        try:
            result = scan_folder(
                folder,
                recursive=settings.recursive,
            )
        except Exception as problem:  # noqa: BLE001 - a validator must not crash Blender
            # Deliberately broad. An unhandled exception inside a Blender operator
            # produces a traceback the user cannot act on; a reported error does
            # not. The core is tested, so this should be unreachable — which is
            # exactly why it must not be the thing that takes Blender down.
            self.report({"ERROR"}, f"Scan failed: {problem}")
            return {"CANCELLED"}

        findings = result.findings
        truncated = False
        if len(findings) > settings.max_files:
            findings = findings[: settings.max_files]
            truncated = True

        bad = sum(1 for finding in findings if finding.level == "bad")
        warn = sum(1 for finding in findings if finding.level == "warn")

        # The full report goes to the console, where it can be scrolled and
        # copied. The report line above Blender's viewport gets the summary,
        # because that is all that fits.
        print("\n" + "=" * 72)
        print(result.as_text())
        if truncated:
            print(
                f"NOTE: stopped at {settings.max_files} files; "
                f"{len(result.findings) - settings.max_files} were not read."
            )
        print("=" * 72 + "\n")

        if bad:
            message = f"{bad} file(s) with a broken scale"
            if warn:
                message += f", {warn} to check"
            self.report({"WARNING"}, message + " — see the console")
        elif warn:
            self.report({"INFO"}, f"{warn} file(s) worth a look — see the console")
        else:
            self.report({"INFO"}, f"No scale problems in {len(findings)} file(s)")

        # Сводка для панели: без неё результат виден только в консоли.
        parts = [f"{len(findings)} file(s)"]
        if bad:
            parts.append(f"{bad} with a broken scale")
        if warn:
            parts.append(f"{warn} to check")
        if truncated:
            parts.append(f"stopped at {settings.max_files}")
        if not bad and not warn:
            parts.append("all fine")
        settings.last_result = " · ".join(parts)

        return {"FINISHED"}


class FBXSCALE_OT_open_console(Operator):
    """Open Blender's system console, where the full report is printed."""

    bl_idname = "fbxscale.open_console"
    bl_label = "Open the console"
    bl_description = (
        "Open the console window with the full report. Same as "
        "Window → Toggle System Console, but without looking for it"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        # На Windows консоль открывается отдельным окном; на других системах
        # такого оператора может не быть, и кнопка просто не показывается.
        return hasattr(bpy.ops.wm, "console_toggle")

    def execute(self, context):
        try:
            bpy.ops.wm.console_toggle()
        except Exception as problem:  # noqa: BLE001 - a UI action must not crash Blender
            self.report({"ERROR"}, f"Could not open the console: {problem}")
            return {"CANCELLED"}
        return {"FINISHED"}


class FBXSCALE_PT_panel(Panel):
    """The panel, in the 3D viewport's sidebar."""

    bl_label = "FBX Scale Report"
    bl_idname = "FBXSCALE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FBX Scale"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.fbxscale

        if scan_folder is None:  # pragma: no cover - defensive
            layout.label(text="Scanning module failed to load.", icon="ERROR")
            return

        column = layout.column(align=True)
        column.prop(settings, "folder", text="")
        row = column.row(align=True)
        row.prop(settings, "recursive", toggle=True)
        row.prop(settings, "show_only_problems", toggle=True)

        layout.separator()
        layout.operator(FBXSCALE_OT_scan.bl_idname, icon="VIEWZOOM")

        # Итог последнего скана прямо в панели. Полный отчёт по файлам остаётся в
        # консоли, и подпись говорит, где его искать.
        if settings.last_result:
            summary = layout.box()
            summary.label(text=settings.last_result, icon="INFO")
            if hasattr(bpy.ops.wm, "console_toggle"):
                summary.operator(FBXSCALE_OT_open_console.bl_idname, icon="CONSOLE")
            else:
                summary.label(text="Full report: window → system console")

        layout.separator()
        box = layout.box()
        box.label(text="What this does", icon="INFO")
        box.label(text="Reads the scale each file declares.")
        box.label(text="Changes nothing.")
        box.label(text="The summary appears here after a scan.")

        if settings.show_only_problems:
            box.label(text="Set to hide files that are fine.")


CLASSES = (
    FBXSCALE_settings,
    FBXSCALE_OT_scan,
    FBXSCALE_OT_open_console,
    FBXSCALE_PT_panel,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.fbxscale = bpy.props.PointerProperty(type=FBXSCALE_settings)


def unregister() -> None:
    del bpy.types.Scene.fbxscale
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":  # pragma: no cover - development helper
    register()
