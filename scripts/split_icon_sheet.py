#!/usr/bin/env python3
"""Splits a one-image icon sheet into the sizes the catalogue wants.

The owner produced the artwork; it arrived as a single 2048-pixel square holding
four tiles of the icon at different sizes. That is fine for looking at and useless
for shipping, so this reads the sheet, finds the tiles, and writes one PNG per
size — measuring the artwork rather than scaling a single copy down, because
scaling is what makes small icons look wrong.

A JPEG sheet also means the flat background is not quite flat and the edges are
not quite clean. Both are repaired here rather than shipped: the background is
snapped back to one colour and the edge is left alone. Being honest about that:
this is a photograph of a design, not the design, so the result is good rather
than perfect. The right long-term fix is an SVG or a layered original.

Usage: python scripts/split_icon_sheet.py <sheet.jpg|png>
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent

# Import the PNG writer rather than repeating it. The icon generator already has
# one, and two copies of an encoder is two places for a bug.
sys.path.insert(0, str(PRODUCT / "scripts"))
from make_icon import png_bytes  # noqa: E402


def read_image(path: Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    """Reads a PNG. JPEG is not supported by the standard library, deliberately.

    If the sheet is a JPEG, the caller is expected to have converted it — this is
    a build-time tool, and pretending to decode JPEG in pure Python would be a lot
    of code to get subtly wrong.
    """
    if path.suffix.lower() != ".png":
        raise SystemExit(
            f"{path.name}: only PNG is read here. Convert the sheet to PNG first."
        )

    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit(f"{path.name}: not a PNG")

    width = height = 0
    idat = bytearray()
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, colour_type = struct.unpack(">IIBB", payload[:10])
            if depth != 8 or colour_type not in (2, 6):
                raise SystemExit(
                    f"{path.name}: need 8-bit RGB or RGBA, got depth {depth} type {colour_type}"
                )
            channels = 3 if colour_type == 2 else 4
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            break

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows: list[list[tuple[int, int, int]]] = []
    previous = bytearray(stride)

    position = 0
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        # Undo the per-scanline filter. PNG allows five; the encoder that made
        # this sheet used whichever it liked, so all five are handled.
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 0xFF
            elif filter_type == 2:
                line[index] = (line[index] + up) & 0xFF
            elif filter_type == 3:
                line[index] = (line[index] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                estimate = left + up - up_left
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
                nearest = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                line[index] = (line[index] + nearest) & 0xFF
        previous = line
        rows.append(
            [
                (line[x * channels], line[x * channels + 1], line[x * channels + 2])
                for x in range(width)
            ]
        )

    return width, height, rows


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    sheet = Path(sys.argv[1])
    width, height, pixels = read_image(sheet)
    print(f"Sheet: {sheet.name}  {width}x{height}")

    # The tiles are found by looking for columns and rows that contain the accent
    # colour, which the background does not. Measuring beats guessing at
    # coordinates, and it survives the sheet being re-rendered at another size.
    accent = (45, 212, 191)

    def is_accent(pixel: tuple[int, int, int]) -> bool:
        return (
            abs(pixel[0] - accent[0]) < 60
            and abs(pixel[1] - accent[1]) < 60
            and abs(pixel[2] - accent[2]) < 60
        )

    column_hits = [0] * width
    row_hits = [0] * height
    for y in range(height):
        row = pixels[y]
        for x in range(width):
            if is_accent(row[x]):
                column_hits[x] += 1
                row_hits[y] += 1

    def spans(hits: list[int], minimum: int) -> list[tuple[int, int]]:
        """Groups consecutive positions with enough hits into ranges."""
        found = []
        start = None
        for index, count in enumerate(hits):
            if count >= minimum:
                if start is None:
                    start = index
            elif start is not None:
                if index - start > 4:
                    found.append((start, index))
                start = None
        if start is not None:
            found.append((start, len(hits)))
        return found

    threshold = max(2, height // 200)
    columns = spans(column_hits, threshold)
    rows = spans(row_hits, threshold)

    # Rows and columns cross everywhere, so the tiles are found as the
    # intersections that actually contain accent pixels, then merged when they
    # overlap — a tile's border and its inner tick marks land in separate runs.
    boxes = []
    for top, bottom in rows:
        for left, right in columns:
            hits = sum(
                1
                for y in range(top, bottom)
                for x in range(left, right)
                if is_accent(pixels[y][x])
            )
            if hits > 20:
                boxes.append((left, top, right, bottom))

    print(f"  raw boxes: {len(boxes)}")

    # Merge overlapping boxes into one per tile.
    merged: list[list[int]] = []
    for box in sorted(boxes, key=lambda b: (b[1], b[0])):
        for existing in merged:
            if not (
                box[2] < existing[0]
                or box[0] > existing[2]
                or box[3] < existing[1]
                or box[1] > existing[3]
            ):
                existing[0] = min(existing[0], box[0])
                existing[1] = min(existing[1], box[1])
                existing[2] = max(existing[2], box[2])
                existing[3] = max(existing[3], box[3])
                break
        else:
            merged.append(list(box))

    if not merged:
        print("No tiles found. Nothing written.")
        return 1

    target = PRODUCT / "icons"
    target.mkdir(exist_ok=True)

    for left, top, right, bottom in sorted(merged, key=lambda b: b[2] - b[0]):
        side = max(right - left, bottom - top)
        size = side
        print(f"  tile {right - left}x{bottom - top} at ({left},{top}) -> {size}px")

        # Snap the near-flat background back to one colour. A JPEG sheet leaves
        # the dark area slightly noisy, and a noisy background in a 16-pixel icon
        # reads as dirt.
        background = pixels[top][left]
        tile = []
        for y in range(top, top + size):
            if y >= height:
                break
            row = []
            for x in range(left, left + size):
                pixel = pixels[y][x] if x < width else background
                if (
                    abs(pixel[0] - background[0]) < 26
                    and abs(pixel[1] - background[1]) < 26
                    and abs(pixel[2] - background[2]) < 26
                ):
                    pixel = background
                row.append(pixel)
            while len(row) < size:
                row.append(background)
            tile.append(row)
        while len(tile) < size:
            tile.append([background] * size)

        path = target / f"sheet-{size}.png"
        path.write_bytes(png_bytes(size, size, tile))
        print(f"    wrote {path.relative_to(PRODUCT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
