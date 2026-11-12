"""Write the PWA icons from their base64 sidecars.

The icons are pictures, and the repository only carries text files, so each
picture travels next to its own base64 copy. Running this script writes the
pictures again:

    python iphone-pwa/icons/restore-icons.py

It is safe to run it more than once, and it is needed before the page is
served, because the manifest and the apple touch icon point at the pictures.
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The pictures that are restored, and the size each one has to have.
ICONS = {
    'icon-180.png': (180, 180),
    'icon-192.png': (192, 192),
    'icon-512.png': (512, 512),
}

#: The first eight bytes of every PNG file.
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def png_size(path):
    """The width and the height of a PNG, read from its header."""
    with open(path, 'rb') as handle:
        header = handle.read(24)
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
        raise ValueError('That is not a PNG file: ' + path)
    width = int.from_bytes(header[16:20], 'big')
    height = int.from_bytes(header[20:24], 'big')
    return width, height


def restore(directory=HERE):
    """Write every icon and return the paths that were written."""
    written = []
    for name, expected in sorted(ICONS.items()):
        sidecar = os.path.join(directory, name + '.b64')
        target = os.path.join(directory, name)
        if not os.path.exists(sidecar):
            raise FileNotFoundError('Missing sidecar: ' + sidecar)
        with open(sidecar, encoding='ascii') as handle:
            data = base64.b64decode(''.join(handle.read().split()))
        with open(target, 'wb') as handle:
            handle.write(data)
        size = png_size(target)
        if size != expected:
            raise ValueError('%s is %dx%d, expected %dx%d.' % ((name,) + size + expected))
        written.append(target)
    return written


if __name__ == '__main__':
    for path in restore():
        print('wrote ' + path)
    sys.exit(0)
