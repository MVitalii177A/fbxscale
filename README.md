# FBX Scale Report

Tells you what **unit scale an FBX file declares**, before you find out the hard
way in an engine.

A Blender add-on, and a command-line tool that does not need Blender.

**Your model arrived 100× too big or too small?** That is usually the file's own
declaration rather than the import setting, and this reads it for a whole folder in
one press. Files it cannot read are named, not skipped. It changes nothing.

## Get it

| | |
|---|---|
| **Download** | [`dist/fbxscale-0.1.2.zip`](dist/fbxscale-0.1.2.zip) — install in Blender via *Preferences → Add-ons → Install from Disk* |
| **Blender catalogue** | `FBX Scale Report` — search for it in Blender's *Get Extensions*, once the listing is approved |
| **Source** | this repository, GPL-3.0-or-later |
| **Studio** | [quiettoolsstudio.com](https://quiettoolsstudio.com/) |
| **Problems** | [issues](https://github.com/MVitalii177A/fbxscale/issues) · itwins19@gmail.com |

## Answers to the questions this tool exists for

Written out in full on the studio's site, because the answer is useful even to
somebody who never installs anything:

- [FBX unit scale: what the file declares](https://quiettoolsstudio.com/fbx-unit-scale/) —
  what `UnitScaleFactor` means, and what each value (`0.01`, `1`, `2.54`, `100`) implies.
- [FBX imports at the wrong size](https://quiettoolsstudio.com/fbx-imports-at-the-wrong-size/) —
  the error factor is *declared ÷ assumed*; the three cases and their three fixes.
- [FBX scale in Unity and Unreal](https://quiettoolsstudio.com/fbx-scale-unity-unreal/) —
  what each engine converts from, and what no import setting can repair.

---

## The problem

An FBX file does not just contain a model. It contains a **statement about how
big the model is** — a field called `UnitScaleFactor` in the file's
`GlobalSettings`. FBX counts in centimetres, so a factor of `1` means one unit is
a centimetre and a factor of `100` means one unit is a metre.

When those files arrive from different places — some from Blender, some bought,
some exported from CAD — the factors disagree, and the models come out at the
wrong size. Blender has patched this area repeatedly:

- "**Attempt to fix** FBX scaling issues in a different way"
- "FBX Import: fix scale handling to match again our exporter's one"
- "FBX Export: **Hopefully fix once and for all** default scale issue"

Words like *attempt* and *hopefully once and for all* in a commit history are a
description of a problem that keeps coming back.

And there is a reason it is hard to catch: **Blender applies the factor while
importing and then forgets it.** Once a mesh is in the scene, the file's own
declaration is gone. A tool that imports can tell you what Blender made of the
file; it cannot tell you what the file said.

This one reads the file.

## What it does

Point it at a folder. It reports, for every FBX file:

| | |
|---|---|
| The declared factor | `1`, `100`, `2.54`, `0.01` |
| What that means | one unit = 1 cm, 1 m, 1 inch… |
| Whether it is a problem | fine / worth a look / broken |
| Who wrote the file | the creator string, when there is one |
| What it could not read | binary files, truncated files, non-FBX files |

Output comes as text, CSV, or a self-contained HTML page that opens offline.

**It never modifies anything.** Not the FBX files, not the scene. It reads bytes
and writes a report where you ask it to.

## What it deliberately does not do

- **It does not fix the scale.** Changing a factor is a decision about intent: a
  file that is ten times off might need the file changed, or the export settings,
  or nothing at all. A tool that silently "corrects" that destroys work. It
  reports; you decide.
- **It does not read binary FBX.** It says so, by name, rather than guessing.
  A validator that reports "fine" on a file it could not read is worse than one
  that admits it.
- **It does not import.** That is the point, not a limitation.

## Installing in Blender

Requires Blender **4.2 or later** — the first release that reads the extension
manifest format this add-on uses.

1. Download the `.zip` from the extensions catalogue, or build it yourself
   (below).
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk**, and pick the
   zip.
3. The panel appears in the 3D viewport sidebar under the **FBX Scale** tab.

Press **Scan for FBX scale problems**. The summary appears in the status bar; the
**full report goes to the console** (Window → Toggle System Console on Windows).
The console is deliberate: the useful reports are dozens of lines long, and a
popup that scrolls is worse than a console that does not.

## Using it without Blender

The logic has no Blender dependency, so it runs anywhere Python 3.8+ does:

```bash
python -m core.cli /path/to/assets
python -m core.cli /path/to/assets --csv report.csv --html report.html
python -m core.cli /path/to/assets --quiet      # headline only
python -m core.cli /path/to/assets --no-recursive
```

The exit code is **1** when a file has a broken scale, so it can go in a pipeline
or a pre-commit hook. Unreadable files do not fail the run — refusing to read a
binary FBX is a correct answer, not a defect.

## Building the zip

The extensions catalogue wants a zip whose root contains `blender_manifest.toml`:

```bash
python scripts/build_zip.py
```

That writes `dist/fbxscale-0.1.2.zip`. The script refuses to build if any test
fails, which is the only thing standing between a broken edit and a published
version.

When Blender is installed, the archive is produced **by Blender's own builder**
(`blender --command extension build`), which applies the same `[build] paths`
allowlist from the manifest and stamps the archive with generated metadata. Blender
is looked for at `FBXSCALE_BLENDER`, then on `PATH`, then as a portable build under
`_tools/`. Without it, the same list is packed with the standard library, and the
result is equivalent apart from that generated table.

## Checking it inside Blender

```bash
python scripts/check_in_blender.py
```

This is the check that matters most, because it is the only one that uses
Blender's code rather than our description of it. It validates the manifest,
builds the package, installs it with `install-file` into a **throwaway**
preferences folder, confirms Blender lists it, then starts Blender again to load
it and check the operator, the panel and the settings.

It needs a Blender; without one it says so and exits. Downloading a portable build
is enough — nothing is installed into the system, and nothing is written to the
real `%APPDATA%`.

## What is tested, and what is not

The split between `core/` and `ui.py` exists so that the decisions live where they
can be tested: `core/` imports no Blender, so the suite runs in a second on a
machine with nothing installed, and the part that needs Blender is kept thin.

| | |
|---|---|
| **Tested** — 122 checks in three files | FBX parsing, scale arithmetic, every verdict branch, folder walking, all three report formats, HTML escaping, the command line end to end, exit codes |
| **Checked without Blender** — 50 checks | the manifest parses and has every field the catalogue requires, string lengths, platform names, every Python file compiles, versions do not drift, `core/` imports no Blender, required documents exist |
| **Checked inside Blender** — 33 checks | Blender validates the manifest, builds the package, installs it with `install-file`, lists it, loads it, registers the operator and the panel in the right sidebar with the intended setting defaults, produces the same report as the command line, and cleans up on disable |

```bash
python tests/test_fbx.py             # 54 checks — the reader
python tests/test_scan.py            # 45 checks — the scanner and the reports
python tests/test_cli.py             # 23 checks — the command line
python scripts/check_addon.py        # 50 checks — the manifest and the packaging
python scripts/check_in_blender.py   # 33 checks — all of the above, inside Blender
```

Every count on this page was wrong in an earlier draft, written from memory
instead of from a run. These come from the actual output.

### What Blender found that our own checks had not

Worth recording, because it is the argument for installing Blender rather than
trusting a checker we wrote ourselves. `blender --command extension validate`
rejected the manifest four times, over things no amount of reading our own code
would have revealed:

- the tagline was 66 characters against a limit of 64 — and then 65, after a fix
  that was one character short;
- a permission description was written as prose, when that field is capped at 64
  characters;
- `platforms` was written as `[[platforms]]` tables, when the schema wants a list
  of strings;
- `platforms` was placed *after* `[permissions]`, where TOML quietly files it
  inside that table.

The last one is the instructive one. Our checker read the same file and reported
success, because it was a parser we wrote and it shared our assumptions.

The same happened to the in-Blender check twice: it called `register()` on an
already-enabled extension and reported "already registered as a subclass" as a
defect, and it asserted that a `PropertyGroup` appears as an attribute of
`bpy.types`, which Blender does not do. Both were bugs in the test, found by
running the test.

### What still cannot be checked here

The panel has never been **seen**. It is registered in the right place with the
right metadata, its `draw` method exists, and the settings it reads are correct —
but nothing running without a window can click a button or photograph a sidebar.
The screenshot in `dist/` is of the HTML report, not of Blender.

If the panel is wrong, it is wrong in a way that shows on the first press of the
button rather than in a saved file. It is kept to one operator, one panel and no
scene access for exactly that reason.

No test runner is installed on purpose: the add-on must work in Blender with
nothing but the standard library, so the tests use nothing else either.

## Why the code is shaped this way

`DECISIONS.md` records each choice with the evidence that produced it — why the
core parses rather than imports, why ASCII only, why it reports instead of fixes,
why it ships free. A later reader can disagree with the reasoning there instead
of guessing at it.

## Licence

GPL-3.0-or-later. Blender is GPL-2.0-or-later and expects add-ons that use its
Python API to be GPL-compatible; a permissive licence here would be a question
rather than a gift.
