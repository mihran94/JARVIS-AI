"""Report signing material that must never enter a source tree.

The Android release key is deliberately absent from every repository, and the
release workflow refuses to publish when the signing material shows up. This
script is the same idea as a local check: it walks a directory and reports any
file that looks like a private key, a keystore or a credential dump.

It is a reporting tool, not a secret scanner. It looks for the file names and
the extensions that are used for signing material, and for a few well known
names. A file that is not on those lists can still be a secret.

Usage:

    python scripts/check_signing_material.py [directory ...]

Exit code 0 when nothing was found, 1 when something was found, 2 on a usage
error.
"""
import os
import sys

#: Extensions that hold private keys, keystores or certificates.
SIGNING_EXTENSIONS = (
    '.p12', '.pfx', '.jks', '.keystore', '.pem', '.key', '.der', '.cer',
    '.crt', '.asc', '.gpg', '.ppk', '.pkcs12',
)

#: File names that hold credentials of any kind.
CREDENTIAL_NAMES = (
    'keystore.properties', 'secrets.properties', 'credentials.json',
    'credentials.txt', 'local.properties', '.env', '.env.local',
    'google-services.json', 'service-account.json',
)

#: Directories that are never committed.
IGNORED_DIRECTORIES = ('.git', '__pycache__', 'node_modules', 'build', '.gradle',
                       'dist', '.idea', '.pytest_cache')


def _is_ignored(name: str) -> bool:
    return name in IGNORED_DIRECTORIES


def scan(root: str):
    """Return the paths under `root` that look like signing material."""
    found = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if not _is_ignored(name)]
        for name in filenames:
            path = os.path.join(directory, name)
            lowered = name.lower()
            if lowered.endswith(SIGNING_EXTENSIONS):
                found.append((path, 'signing file extension'))
            elif lowered in CREDENTIAL_NAMES:
                found.append((path, 'credential file name'))
            elif 'keystore' in lowered and lowered.endswith(('.properties', '.json', '.txt')):
                found.append((path, 'keystore configuration'))
    return sorted(found)


def main(argv) -> int:
    roots = argv[1:] or ['.']
    for root in roots:
        if not os.path.isdir(root):
            print('Not a directory: ' + root, file=sys.stderr)
            return 2
    total = []
    for root in roots:
        for path, reason in scan(root):
            total.append((path, reason))
            print('FOUND  ' + path + '  (' + reason + ')')
    if total:
        print('')
        print('%d file(s) that must not be committed. Remove them before committing.'
              % len(total))
        return 1
    print('No signing material found in: ' + ', '.join(roots))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
