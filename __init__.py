"""FbxScale — reports the unit scale an FBX file declares.

Blender entry point. This file is deliberately tiny: it imports the UI module and
forwards ``register``/``unregister``, which is all Blender asks of an add-on.

The interesting code is in ``core``, which imports nothing from Blender and is
therefore testable without it (see ``DECISIONS.md``, ADR-002). ``ui.py`` is the
only file here that needs Blender, and it is kept thin for that reason.

Why this tool exists, in one sentence: FBX files record how big they are in a
header field, Blender applies that field on import and then forgets it, so the
only way to know what a file declares is to read the file rather than to open it.
"""

from . import ui


def register() -> None:
    ui.register()


def unregister() -> None:
    ui.unregister()


__all__ = ["register", "unregister", "ui"]
