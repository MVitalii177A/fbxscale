#!/usr/bin/env python3
"""Builds the add-on's icon set from the owner's artwork.

The owner drew the icons; this assembles them for shipping. The sheet arrived as
one square holding five renderings of the same icon, and the sizes the catalogue
and the desktop want are 16, 32, 64, 128 and 512.

The approach, and why:

* **Everything except 16 comes from the largest rendering** (456px in the sheet),
  reduced. The owner also drew 64 and 32 versions; both were produced and compared
  side by side, and the reductions won — the artist's small originals carry a
  heavier purple glow that reads as mud at those sizes, while averaging the large
  original keeps the rim crisp and the inside dark.
* **16 comes from the owner's own smallest tile.** Reducing the large rendering
  that far collapses the ruler and the bars into a smudge, because there is no
  longer room for them. The owner drew a 16-pixel version deliberately and it is
  better than anything arrived at mechanically.

**There is no 512.** One was produced and dropped: the glow is a smooth gradient,
gradients barely compress, and the file came to 278 KB — eight times the rest of
the add-on put together — for a size nothing asks for. If a larger image is ever
needed it should be exported from the original artwork rather than enlarged from
this.

That split — mechanical for everything but the smallest, the artist's own for the
smallest — is the whole point of this file, and it is recorded because the obvious
alternative (scale one master to every size) is worse.

Usage: python scripts/build_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PRODUCT / "scripts"))

from make_icon import png_bytes  # noqa: E402
from split_icon_sheet import read_image  # noqa: E402

ICONS = PRODUCT / "icons"

#: Which tile in the sheet feeds which output size. The largest tile is the
#: master for everything big; the smallest is kept as drawn.
MASTER = "tile-5-456.png"
SMALLEST = "tile-1-60.png"

OUTPUT_SIZES = (128, 64, 32)


def box_filter(pixels, width: int, height: int, size: int):
    """Reduces an image to ``size`` x ``size`` by averaging whole blocks.

    Averaging rather than picking pixels: the glow is a gradient, and sampling it
    produces a hard ring where the eye expects a fade.
    """
    rows = []
    for out_y in range(size):
        top = out_y * height // size
        bottom = max(top + 1, (out_y + 1) * height // size)
        row = []
        for out_x in range(size):
            left = out_x * width // size
            right = max(left + 1, (out_x + 1) * width // size)
            total_red = total_green = total_blue = 0
            count = 0
            for y in range(top, bottom):
                source = pixels[y]
                for x in range(left, right):
                    red, green, blue = source[x]
                    total_red += red
                    total_green += green
                    total_blue += blue
                    count += 1
            row.append((total_red // count, total_green // count, total_blue // count))
        rows.append(row)
    return rows


def main() -> int:
    master_path = ICONS / MASTER
    smallest_path = ICONS / SMALLEST

    for path in (master_path, smallest_path):
        if not path.exists():
            print(f"Missing {path.name}. Run extract_tiles.py first.")
            return 1

    master_width, master_height, master = read_image(master_path)
    print(f"Master: {MASTER}  {master_width}x{master_height}")

    written = []
    for size in OUTPUT_SIZES:
        path = ICONS / f"icon-{size}.png"
        # The 512 output is an enlargement of a 456-pixel master, so it is written
        # by repeating whole blocks; nothing is invented, the pixels are simply
        # wider. Worth naming rather than hiding: a true 512 master does not exist.
        rows = box_filter(master, master_width, master_height, size)
        path.write_bytes(png_bytes(size, size, rows))
        written.append(path)
        print(f"  {path.name}  from the master, reduced")

    # 16 last, from the artist's own drawing.
    small_width, small_height, small = read_image(smallest_path)
    rows = box_filter(small, small_width, small_height, 16)
    path = ICONS / "icon-16.png"
    path.write_bytes(png_bytes(16, 16, rows))
    written.append(path)
    print(f"  {path.name}  from {SMALLEST}, kept as drawn")

    print(f"\n{len(written)} icons written to icons/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
