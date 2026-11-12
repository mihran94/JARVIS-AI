"""Write the source integrity manifest.

`docs/SOURCE_INTEGRITY.sha256` lists the SHA-256 of every file in the tree, in
`sha256sum` format, so the checkout can be verified before it is built:

    sha256sum -c docs/SOURCE_INTEGRITY.sha256

The manifest covers the bytes as they are checked out. A `.cmd` file is
checked out with Windows line endings, so the manifest is written from a
checkout, not from the raw repository blobs.

Usage:
    python scripts/source_manifest.py            # write the manifest
    python scripts/source_manifest.py --check    # verify it, do not write
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

MANIFEST = os.path.join('docs', 'SOURCE_INTEGRITY.sha256')

#: Directories that never belong to the source tree.
SKIP_DIRS = {
    '.git', '.github-cache', '.mypy_cache', '.pytest_cache', '.venv',
    '__pycache__', 'build', 'dist', 'node_modules', 'venv',
}

HEADER = """# JARVIS AI source integrity manifest
#
# SHA-256 of every file on the main branch.
# The manifest does not list itself. Verify with:
#
#     sha256sum -c docs/SOURCE_INTEGRITY.sha256
#
# The manifest covers the bytes as they are stored in the repository. A file
# with Windows line endings is checked out with Windows line endings, so
# check out the branch first and then verify the files that are not text.
#
# The PWA icons are build output and are not in the repository. Restore them
# before verifying, or three files will be reported as missing:
#
#     python iphone-pwa/icons/restore-icons.py
#
# {count} files
"""


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def collect(root: str) -> list[str]:
    """Every source file in the tree, in a stable order."""
    found = []
    for directory, sub_directories, files in os.walk(root):
        sub_directories[:] = sorted(d for d in sub_directories if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root).replace(os.sep, '/')
            if relative == MANIFEST.replace(os.sep, '/'):
                continue
            found.append(relative)
    return sorted(found)


def build(root: str) -> str:
    files = collect(root)
    lines = [HEADER.format(count=len(files))]
    for relative in files:
        lines.append(f'{sha256(os.path.join(root, relative))}  {relative}\n')
    return ''.join(lines)


def difference(current: str, expected: str) -> list[str]:
    """The files that make the two manifests different."""
    def read(text):
        entries = {}
        for line in text.splitlines():
            if line.startswith('#') or not line.strip():
                continue
            digest, _, path = line.partition('  ')
            entries[path.strip()] = digest
        return entries

    old, new = read(current), read(expected)
    problems = []
    for path in sorted(set(old) | set(new)):
        if path not in new:
            problems.append(f'{path} is in the manifest but not in the tree')
        elif path not in old:
            problems.append(f'{path} is in the tree but not in the manifest')
        elif old[path] != new[path]:
            problems.append(f'{path} has a different content')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='verify the manifest instead of writing it')
    parser.add_argument('--root', default='.', help='the tree to read')
    arguments = parser.parse_args(argv)

    root = os.path.abspath(arguments.root)
    manifest_path = os.path.join(root, MANIFEST)
    expected = build(root)

    if arguments.check:
        if not os.path.exists(manifest_path):
            print(f'{MANIFEST} is missing.')
            return 1
        with open(manifest_path, encoding='utf-8') as handle:
            current = handle.read()
        if current != expected:
            print(f'{MANIFEST} does not match the tree.')
            for line in difference(current, expected):
                print(f'  {line}')
            return 1
        print(f'{MANIFEST} matches the tree.')
        return 0

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(expected)
    print(f'{MANIFEST} written with {len(collect(root))} files.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
