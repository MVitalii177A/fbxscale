"""Logic that does not depend on Blender.

``fbx`` reads what a file declares; ``scan`` walks a folder and builds the
reports; ``cli`` drives scan from a terminal. Everything here runs under plain
Python, which is what makes it testable on a machine without Blender — see
``DECISIONS.md``, ADR-002.
"""
