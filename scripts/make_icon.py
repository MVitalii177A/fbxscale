#!/usr/bin/env python3
"""Draws the add-on's icon, with no image library.

Not art, and not a dependency either. ``PIL`` is not installed here and adding it
would mean the icon could only be regenerated on a machine that has it, so this
writes the PNG itself: the standard library's ``zlib`` and ``struct`` are all a
PNG needs, and the format is old enough to be worth understanding.

The picture is geometric rather than typographic on purpose. Text would need a
font, fonts differ between machines, and at 16 pixels — where most people will
see this in the add-on list — lettering turns to mud. A measuring bar with ticks
survives being small, which is the whole job.

Reads as: a dark tile, a teal border, a scale bar with ticks, and the middle tick
marked longer. It is a ruler, which is what the tool is.

Deliberately not the clipper's icon. Two products from one publisher sharing a
picture would make the catalogue look like one product listed twice.

Usage: python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PRODUCT = Path(__file__).resolve().parent.parent
SIZES = (512, 128, 64, 32, 16)

BACKGROUND = (17, 24, 39)
ACCENT = (45, 212, 191)
TEXT = (241, 245, 249)
DIM = (148, 163, 184)


def png_bytes(width: int, height: int, rows: list[list[tuple[int, int, int]]]) -> bytes:
    """Minimal PNG writer: 8-bit RGB, no interlacing, no ancillary chunks.

    Compressed at level 9. The first version used no compression at all, which
    made the 512-pixel icon 277 KB — larger than the entire rest of the add-on —
    and that was noticed only when the icon set was assembled from real artwork
    rather than from the flat shapes this file used to draw. Flat colour
    compresses to almost nothing either way; a glow does not.
    """

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0: none
        for red, green, blue in row:
            raw += bytes((red, green, blue))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


class Canvas:
    """A grid of pixels with the few drawing calls this icon needs."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.pixels = [[BACKGROUND for _ in range(size)] for _ in range(size)]

    def set(self, x: int, y: int, colour: tuple[int, int, int]) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            self.pixels[y][x] = colour

    def rectangle(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        colour: tuple[int, int, int],
    ) -> None:
        for y in range(round(top), round(bottom)):
            for x in range(round(left), round(right)):
                self.set(x, y, colour)

    def rounded_border(self, inset: float, radius: float, thickness: float, colour) -> None:
        """A rounded square outline, drawn as a filled shape minus its middle.

        Antialiasing is not attempted. At the sizes that matter here a hard edge
        looks deliberate rather than cheap, and pretending otherwise would mean
        writing a lot more arithmetic for a worse result than the eye expects.
        """
        size = self.size
        inner = inset + thickness

        def inside(x: float, y: float, margin: float) -> bool:
            low, high = margin, size - margin
            if not (low <= x < high and low <= y < high):
                return False
            corner = margin + radius
            for cx, cy in (
                (corner, corner),
                (high - radius, corner),
                (corner, high - radius),
                (high - radius, high - radius),
            ):
                near_x = x < corner if cx == corner else x > high - radius
                near_y = y < corner if cy == corner else y > high - radius
                if near_x and near_y:
                    if (x - cx) ** 2 + (y - cy) ** 2 > radius**2:
                        return False
            return True

        for y in range(size):
            for x in range(size):
                if inside(x, y, inset) and not inside(x, y, inner):
                    self.set(x, y, colour)

    def scale_bar(self) -> None:
        """A ruler with ticks and a longer middle mark.

        Proportions were adjusted after looking at the render: the first version
        put seven ticks hard against the bottom border, and at 64 pixels it read as
        noise rather than a measurement. Five ticks, a thinner bar, and more room
        below it.
        """
        size = self.size
        baseline = size * 0.78
        thickness = max(1.0, size / 64)
        left, right = size * 0.20, size * 0.80

        self.rectangle(left, baseline - thickness / 2, right, baseline + thickness / 2, DIM)

        ticks = 5
        for index in range(ticks):
            x = left + (right - left) * index / (ticks - 1)
            long_tick = index in (0, ticks // 2, ticks - 1)
            length = size * (0.16 if long_tick else 0.09)
            self.rectangle(
                x - thickness / 2,
                baseline - length,
                x + thickness / 2,
                baseline,
                ACCENT,
            )

    def glyph(self) -> None:
        """Three bars of different heights: three models, three sizes.

        Chosen over letters because it needs no font and still says "things that
        are not the same size", which is the problem the add-on reports. Sits
        higher than the first attempt, which crowded the ruler.
        """
        size = self.size
        bottom = size * 0.52
        width = size * 0.11
        gap = size * 0.07
        start = (size - (width * 3 + gap * 2)) / 2
        heights = (0.17, 0.30, 0.22)

        for index, height in enumerate(heights):
            left = start + index * (width + gap)
            self.rectangle(
                left,
                bottom - size * height,
                left + width,
                bottom,
                TEXT if index == 1 else ACCENT,
            )

    def to_rows(self):
        return self.pixels


def draw(size: int) -> Canvas:
    canvas = Canvas(size)
    canvas.rounded_border(
        inset=max(1.0, size / 22),
        radius=max(2.0, size / 7),
        thickness=max(1.0, size / 20),
        colour=ACCENT,
    )
    canvas.glyph()
    canvas.scale_bar()
    return canvas


def main() -> int:
    target = PRODUCT / "icons"
    target.mkdir(exist_ok=True)

    for size in SIZES:
        path = target / f"icon-{size}.png"
        canvas = draw(size)
        path.write_bytes(png_bytes(size, size, canvas.to_rows()))
        print(f"  {path.relative_to(PRODUCT)}  ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
