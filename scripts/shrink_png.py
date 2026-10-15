"""Scales a PNG down by an integer factor, without an image library.

Written because the icon sheet arrived at 4096x4096 — 67 million pixels, which is
16 million Python tuples once decoded, and no reason to handle that when the
largest icon in it is 512 pixels across.

Averaging whole blocks rather than sampling one pixel per block: sampling turns
the soft glow around the artwork into a jagged ring, and the glow is the part the
owner actually drew.

Usage: python scripts/shrink_png.py <in.png> <out.png> <factor>
"""

from __future__ import annotations

import sys
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PRODUCT / "scripts"))

from make_icon import png_bytes  # noqa: E402
from split_icon_sheet import read_image  # noqa: E402


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    factor = int(sys.argv[3])
    if factor < 1:
        raise SystemExit("factor must be 1 or more")

    width, height, pixels = read_image(source)
    print(f"{source.name}: {width}x{height}")

    if factor == 1:
        target.write_bytes(png_bytes(width, height, pixels))
        print(f"copied to {target.name}")
        return 0

    out_width, out_height = width // factor, height // factor
    rows: list[list[tuple[int, int, int]]] = []

    for out_y in range(out_height):
        row = []
        base_y = out_y * factor
        for out_x in range(out_width):
            base_x = out_x * factor
            total_red = total_green = total_blue = 0
            for dy in range(factor):
                source_row = pixels[base_y + dy]
                for dx in range(factor):
                    red, green, blue = source_row[base_x + dx]
                    total_red += red
                    total_green += green
                    total_blue += blue
            count = factor * factor
            row.append(
                (total_red // count, total_green // count, total_blue // count)
            )
        rows.append(row)

    target.write_bytes(png_bytes(out_width, out_height, rows))
    print(f"{target.name}: {out_width}x{out_height}  ({target.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
