#!/usr/bin/env python3
"""Extracts the individual icon sizes from a one-image icon sheet.

The owner produced the artwork; it arrived as a single 4096-pixel square holding
four tiles of the same icon at 16, 32, 64 and 128 pixels, rendered large. This
reads the sheet and writes one PNG per size, **measured rather than scaled down**,
because scaling is what makes small icons look wrong.

Three earlier attempts failed, and the reasons are the design of this one:

1. **Merging by the accent colour welded tiles together.** The glow around each
   tile is itself accent-coloured and the glows touch, so a column of four
   separate icons became one box 188 pixels wide and 461 tall.
2. **Projecting ink onto the axes did not separate them either**, for the same
   reason: the glow makes a continuous band.
3. **Flood-filling finds the shapes but fragments them.** The frame, the bars and
   the ruler ticks are separate connected regions, so one icon arrives as eight
   islands.

So: find the islands, then grow each one by absorbing neighbours that are close
enough to be part of the same drawing. The gap between an icon's own parts is a
few pixels; the gap between icons is tens. That difference is what makes the
grouping reliable, and it is measured here rather than assumed — the script prints
the gaps it saw.

Usage: python scripts/extract_tiles.py <sheet.png> [--write]
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PRODUCT / "scripts"))

from make_icon import png_bytes  # noqa: E402
from split_icon_sheet import read_image  # noqa: E402

#: How much brighter than the corner a pixel must be to count as artwork.
BACKGROUND_TOLERANCE = 40

#: An island smaller than this is noise from the JPEG, not a drawn part.
MINIMUM_ISLAND = 8

#: Islands closer than this many pixels are treated as one icon. The sheet's own
#: separator is wider, and the script reports the observed gaps so the number can
#: be checked rather than trusted.
JOIN_DISTANCE = 14


def islands(pixels, width: int, height: int, cutoff: int) -> list[list[int]]:
    """Every connected area of artwork, as [left, top, right, bottom]."""
    seen = [[False] * width for _ in range(height)]
    found: list[list[int]] = []

    for start_y in range(height):
        for start_x in range(width):
            if seen[start_y][start_x] or max(pixels[start_y][start_x]) <= cutoff:
                continue
            queue = deque([(start_x, start_y)])
            seen[start_y][start_x] = True
            left = right = start_x
            top = bottom = start_y
            count = 0
            while queue:
                x, y = queue.popleft()
                count += 1
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and not seen[ny][nx]
                        and max(pixels[ny][nx]) > cutoff
                    ):
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            if count >= MINIMUM_ISLAND:
                found.append([left, top, right, bottom])

    return found


def gap_between(first: list[int], second: list[int]) -> float:
    """Distance between two rectangles, zero when they overlap."""
    dx = max(0, max(first[0], second[0]) - min(first[2], second[2]))
    dy = max(0, max(first[1], second[1]) - min(first[3], second[3]))
    return max(dx, dy)


def group(regions: list[list[int]], distance: int) -> list[list[int]]:
    """Absorbs regions that are close to each other into single boxes."""
    boxes = [list(region) for region in regions]
    changed = True
    while changed:
        changed = False
        for first in range(len(boxes)):
            for second in range(first + 1, len(boxes)):
                if gap_between(boxes[first], boxes[second]) <= distance:
                    a, b = boxes[first], boxes[second]
                    a[0], a[1] = min(a[0], b[0]), min(a[1], b[1])
                    a[2], a[3] = max(a[2], b[2]), max(a[3], b[3])
                    boxes.pop(second)
                    changed = True
                    break
            if changed:
                break
    return boxes


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    sheet = Path(sys.argv[1])
    write = "--write" in sys.argv
    width, height, pixels = read_image(sheet)
    print(f"Sheet: {sheet.name}  {width}x{height}")

    corner = pixels[0][0]
    cutoff = max(corner) + BACKGROUND_TOLERANCE

    found = islands(pixels, width, height, cutoff)
    print(f"  {len(found)} separate areas of artwork")

    boxes = group(found, JOIN_DISTANCE)
    print(f"  {len(boxes)} groups after joining anything within {JOIN_DISTANCE}px")

    # The gaps actually present, so the join distance can be judged rather than
    # believed. The nearest pair of groups is printed next to the one used.
    if len(boxes) > 1:
        nearest = min(
            gap_between(boxes[a], boxes[b])
            for a in range(len(boxes))
            for b in range(a + 1, len(boxes))
        )
        print(f"  smallest gap between groups: {nearest:.0f}px")
        if nearest <= JOIN_DISTANCE:
            print("  WARNING: groups are still touching; the sheet may have merged")

    tiles = []
    for left, top, right, bottom in boxes:
        wide, tall = right - left + 1, bottom - top + 1
        if wide < 20 or tall < 20:
            continue
        ratio = wide / tall
        if not 0.6 <= ratio <= 1.7:
            print(f"  skipped {wide}x{tall} at ({left},{top}) — not square enough")
            continue
        tiles.append((left, top, right, bottom))

    tiles.sort(key=lambda tile: tile[2] - tile[0])
    print(f"  {len(tiles)} square tiles")
    for left, top, right, bottom in tiles:
        print(f"    {right - left + 1}x{bottom - top + 1} at ({left},{top})")

    if not write:
        print("\nDry run. Pass --write to save the tiles.")
        return 0

    if not tiles:
        print("Nothing to write.")
        return 1

    target = PRODUCT / "icons"
    target.mkdir(exist_ok=True)

    for index, (left, top, right, bottom) in enumerate(tiles, start=1):
        # Squared off by centring the shorter side. The glow makes one axis a
        # pixel or two larger, and a non-square icon is rejected at upload.
        side = max(right - left + 1, bottom - top + 1)
        centre_x, centre_y = (left + right) // 2, (top + bottom) // 2
        start_x, start_y = centre_x - side // 2, centre_y - side // 2

        tile = []
        for y in range(start_y, start_y + side):
            row = []
            for x in range(start_x, start_x + side):
                row.append(pixels[y][x] if 0 <= x < width and 0 <= y < height else corner)
            tile.append(row)

        path = target / f"tile-{index}-{side}.png"
        path.write_bytes(png_bytes(side, side, tile))
        print(f"    wrote {path.relative_to(PRODUCT)}  ({side}x{side})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
