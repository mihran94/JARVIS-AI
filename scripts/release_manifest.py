"""Write a release manifest for a built application.

The manifest lists every file of the built application with its size and its
SHA-256, so the owner can verify the artefact on their machine and later
record exactly what was distributed. It also records the source revision and
the version, so a report can be traced back to the tree it came from.

Usage:

    python scripts/release_manifest.py dist/JarvisAI dist/JarvisAI-RELEASE.txt \
        --version 0.3.0 --revision <git sha> --channel beta

Exit code 0 when the manifest was written, 1 when the directory is missing.
"""
import argparse
import hashlib
import os
import sys

IGNORED_DIRECTORIES = ('__pycache__',)


def file_digest(path: str) -> str:
    """The SHA-256 of a file, read in blocks so a large file is not loaded."""
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def collect(root: str):
    """Every file under the root, with its size and digest."""
    entries = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRECTORIES]
        for name in filenames:
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root).replace(os.sep, '/')
            entries.append((relative, os.path.getsize(path), file_digest(path)))
    return sorted(entries)


def write_manifest(root: str, output: str, version: str = '', revision: str = '',
                   channel: str = '') -> str:
    """Write the manifest and return its text."""
    entries = collect(root)
    lines = [
        'JARVIS AI release manifest',
        '',
        'version:  ' + (version or 'unknown'),
        'revision: ' + (revision or 'unknown'),
        'channel:  ' + (channel or 'unspecified'),
        'root:     ' + os.path.abspath(root),
        'files:    %d' % len(entries),
        '',
        'size  sha256  path',
    ]
    for relative, size, digest in entries:
        lines.append('%d  %s  %s' % (size, digest, relative))
    text = '\n'.join(lines) + '\n'
    directory = os.path.dirname(os.path.abspath(output))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Write a release manifest for a built application.')
    parser.add_argument('root', help='The built application directory')
    parser.add_argument('output', help='Where the manifest is written')
    parser.add_argument('--version', default='')
    parser.add_argument('--revision', default='')
    parser.add_argument('--channel', default='')
    arguments = parser.parse_args(argv)
    if not os.path.isdir(arguments.root):
        print('Not a directory: ' + arguments.root, file=sys.stderr)
        return 1
    write_manifest(arguments.root, arguments.output, arguments.version, arguments.revision,
                   arguments.channel)
    print('Wrote ' + arguments.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
