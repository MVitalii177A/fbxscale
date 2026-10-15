"""Converts an image to PNG, as a raw pixel dump this project can read.

Run by ``scripts/convert_sheet.py`` inside Blender, because Blender ships an image
library and the machine's own Python does not. That is the honest reason: not
elegance, just that one of the two interpreters on this machine can open a JPEG
and the other cannot.

Writes a plain RGB PNG: no palette, no alpha, no interlacing — the same shape
``make_icon.py`` writes and ``split_icon_sheet.py`` reads.

    blender --background --python scripts/blender_image_to_png.py -- <in> <out>
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import bpy


def png_bytes(width: int, height: int, rows: list[list[tuple[int, int, int]]]) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rows:
        raw.append(0)
        for red, green, blue in row:
            raw += bytes((red, green, blue))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    argv = sys.argv
    if "--" not in argv or len(argv) < argv.index("--") + 3:
        raise SystemExit("Usage: ... -- <input image> <output png>")
    rest = argv[argv.index("--") + 1 :]
    source, target = Path(rest[0]), Path(rest[1])

    image = bpy.data.images.load(str(source))
    width, height = image.size
    print(f"loaded {source.name}: {width}x{height}, channels {image.channels}")

    pixels = list(image.pixels)

    # Blender stores images bottom-up in linear space. Both have to be undone or
    # the icon comes out upside down and washed out — which is exactly what the
    # first attempt produced.
    rows: list[list[tuple[int, int, int]]] = []
    for y in range(height - 1, -1, -1):
        row = []
        for x in range(width):
            index = (y * width + x) * 4
            red, green, blue = pixels[index], pixels[index + 1], pixels[index + 2]
            # Linear to sRGB. Without this, mid tones come out dark.
            def to_srgb(value: float) -> int:
                if value <= 0.0031308:
                    encoded = value * 12.92
                else:
                    encoded = 1.055 * (value ** (1 / 2.4)) - 0.055
                return max(0, min(255, round(encoded * 255)))

            alpha = pixels[index + 3]
            if alpha < 1.0:
                # Composite over the dark background so transparency does not
                # become black fringing.
                red = red * alpha + 0.066 * (1 - alpha)
                green = green * alpha + 0.078 * (1 - alpha)
                blue = blue * alpha + 0.129 * (1 - alpha)

            row.append((to_srgb(red), to_srgb(green), to_srgb(blue)))
        rows.append(row)

    target.write_bytes(png_bytes(width, height, rows))
    print(f"wrote {target}  ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
