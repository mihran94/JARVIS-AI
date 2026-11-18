"""Drawing the application icon.

WHAT THIS IS FOR
    The installed application and the installer had no icon of their own:
    Windows showed the default PyInstaller picture, and the installer had
    none at all. An application the owner installs should look like the
    application they chose.

WHAT IT DOES
    It draws the same orb the desktop draws, at the sizes Windows asks
    for, and writes a real `.ico` file.

    The file is written by hand rather than by an image library, because
    the Windows icon format is a small container: a header, one entry
    per picture, and the pictures themselves. Each picture is an
    uncompressed 32-bit bitmap with its own mask, which every version of
    Windows understands.

HOW IT IS RUN
    python tools/make_icon.py installers/JarvisAI.ico

    The icon is part of the source, so it does not have to be drawn on
    the machine that builds the installer. This script is kept so the
    icon can be changed and the change reviewed.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

#: The sizes Windows asks for in an icon.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: The colours of the orb, taken from `desktop/blue_orb.py`.
GROUND = (5, 9, 16)
RING = (50, 210, 255)
RING_SOFT = (75, 235, 255)
SPOKE = (114, 237, 255)
GLOW = (22, 158, 227)


def _blend(base, top, amount):
    """One colour laid over another."""
    return tuple(int(round(base[index] * (1 - amount) + top[index] * amount))
                 for index in range(3))


def draw(size: int):
    """The orb at one size, as a list of rows of (r, g, b, a)."""
    import math

    centre = size / 2
    radius = size * 0.30
    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            colour = GROUND
            alpha = 255
            distance = math.hypot(x + 0.5 - centre, y + 0.5 - centre)
            if distance > radius * 1.62:
                # Outside the glow the icon is transparent, so it takes the
                # shape of the desktop rather than a black square.
                row.append((0, 0, 0, 0))
                continue
            if distance < radius * 1.62:
                amount = max(0.0, 1 - distance / (radius * 1.62))
                colour = _blend(GROUND, GLOW, amount * 0.65)
            if distance < radius * 1.02:
                colour = _blend(colour, (8, 24, 40), 0.55)
            # Three rings, the same ones the desktop draws.
            for ring in range(3):
                r = radius * (0.58 + ring * 0.18)
                if abs(distance - r) < max(1.0, size * 0.022):
                    colour = _blend(colour, RING if ring == 0 else RING_SOFT, 0.92)
            # The spokes of the outer ring.
            if radius * 0.80 < distance < radius * 1.06:
                angle = math.atan2(y + 0.5 - centre, x + 0.5 - centre)
                spoke = (angle % (math.pi / 6))
                if spoke < 0.16 or spoke > math.pi / 6 - 0.16:
                    colour = _blend(colour, SPOKE, 0.85)
            if distance < radius * 0.20:
                colour = _blend(colour, (210, 250, 255), 0.8)
            row.append((*colour, alpha))
        pixels.append(row)
    return pixels


def _bmp(pixels, size):
    """One picture as the uncompressed bitmap a .ico file holds."""
    header = struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
    body = bytearray()
    mask = bytearray()
    for row in reversed(pixels):
        for red, green, blue, alpha in row:
            body += bytes((blue, green, red, alpha))
    # The AND mask is one bit per pixel, padded to whole bytes. Every pixel
    # is opaque inside the icon, so the mask is all zeroes here.
    mask_row_bytes = ((size + 31) // 32) * 4
    mask += bytes(mask_row_bytes * size)
    return header + bytes(body) + bytes(mask)


def write_ico(path, sizes=SIZES):
    """Write a Windows icon file holding the orb at every size."""
    pictures = []
    for size in sizes:
        data = _bmp(draw(size), size)
        pictures.append((size, data))

    out = bytearray()
    out += struct.pack('<HHH', 0, 1, len(pictures))
    offset = 6 + 16 * len(pictures)
    for size, data in pictures:
        out += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32,
                            len(data), offset)
        offset += len(data)
    for _size, data in pictures:
        out += data
    Path(path).write_bytes(bytes(out))
    return path


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else 'installers/JarvisAI.ico'
    written = write_ico(target)
    print(f'wrote {written} ({Path(written).stat().st_size} bytes)')


if __name__ == '__main__':
    main()
