# FbxScale — decision record

Companion to `F:\Game_v1\products\clipper\store\MARKET.md`, nineteenth pass. That
pass ended the niche search and chose a probe. This file records what the probe
is and why it is shaped this way, in the same spirit as the clipper's `PLAN.md`:
decisions with the evidence that produced them, so a later reader can disagree
with the reasoning rather than guess at it.

---

## ADR-001: the task

**Chosen:** detect and report a wrong **unit scale** in FBX files, as a Blender
add-on.

**Where the task came from.** Not from a survey. From the developer of a
competing add-on, who published his own to-do list in a forum thread:

> "I have a list of things I want to add (**custom naming regex per profile, FBX
> unit scale detection, armature/rig checks**) and feedback is welcome."
> — [AssetSentinel 1.1](https://blenderartists.org/t/assetsentinel-1-1-batch-validate-fbx-gltf-folders-against-unity-unreal-and-marketplace-specs-h/1634156)

Of the three open tasks, unit scale is the one where our existing experience
applies: the clipper's whole job was reading foreign file formats correctly, and
that work was almost entirely about *scale and measurement being declared in one
place and applied in another*.

**Why not the other two.** Custom naming regex is configuration, not a problem;
a user can already do it with a text field. Armature checks need real rigging
knowledge, which we do not have, and getting them wrong would be worse than not
shipping them.

---

## ADR-002: the core parses FBX, it does not import it

**Decision:** the validation logic reads FBX files **as data**, in pure Python,
with no dependency on Blender and no import.

**Why this is the important decision.**

1. **It is testable.** Blender is not installed on the development machine and
   cannot be assumed. Logic that only runs inside Blender can only be verified by
   launching Blender, which makes every test slow and makes the logic impossible
   to check in CI. Logic that parses a file can be tested with fixture files.

2. **It does not modify the scene.** The competing add-on's own selling point is
   "**Never modifies source files**". Importing fifty FBX files to inspect them
   pollutes the scene, takes minutes, and can crash on a corrupt file. Reading
   bytes cannot.

3. **It can see the declaration, not the result of it.** This is the whole point.
   Blender applies `UnitScaleFactor` on import and then forgets it: once a mesh is
   in the scene, the file's declaration is gone. A tool that imports *cannot
   report what the file said* — only what Blender made of it. We need the former,
   because that is where the bugs live.

**Consequence accepted:** we re-implement part of a format parser, and we will be
wrong about some files until fixtures prove otherwise. That cost is worth paying
for testability and for the ability to report the file's own declaration.

---

## ADR-003: ASCII FBX first, binary detected and refused

**Decision:** parse ASCII FBX. Detect binary FBX by its magic header and report
"binary — not read" rather than failing or guessing.

**Why.** From the survey in `MARKET.md`, the FBX files that reach technical
artists come from three places: Blender exports (ASCII by default), bought asset
packs (mixed), and CAD software (often binary). ASCII is the Blender default and
therefore the common case for this audience.

**Why refuse instead of guessing.** A validator that reports "fine" on a file it
could not read is worse than useless: it actively misleads. Saying "binary, not
read" is a smaller failure and an honest one. Parsing the binary format is real
work — it needs its own ADR if the demand appears.

---

## ADR-004: report, do not fix

**Decision:** version 0.1 **reports**; it does not correct a scale.

**Why.** Changing a scale is a decision about intent: a 10x-off model might need
the file scaled, or the export settings changed, or the mesh truly is that size.
A tool that silently "fixes" that destroys work. Reporting keeps the human in
charge, and reporting is the part the competing add-on has not done yet.

**Revisit when** a user asks for the fix, which is the signal that they trust the
diagnosis.

---

## ADR-005: free, in the official catalogue, no price yet

**Decision:** ship at $0 in Blender's official extensions catalogue. No paid tier
in 0.1.

**Why, and it is the same reason as the clipper's:** store rules forbid charging
for what was previously given away, so a paid tier cannot be introduced later
onto something already free. Keeping 0.1 free leaves the *option* of a separate
paid tool open, and the probe's purpose is not revenue — it is **finding out
whether anyone wants this at all**.

**The success criterion is fixed in advance, so the result cannot be reinterpreted
later:**

- **20 downloads and any real feedback** → the problem is real, continue.
- **Fewer than 20 downloads, or silence** → the problem is not felt, stop.
- **Downloads but no questions or reviews** → it is a toy, not a tool. Stop.

---

## What would falsify the whole probe

If unit scale turns out to be a problem that **Blender's importer already
handles**, then the tool has nothing to say and the niche is empty for a reason.
That has to be checked before publishing, not after: the next step is to read
Blender's own documentation and issue tracker on `UnitScaleFactor` handling and
find out whether this is a live bug or a solved one.
