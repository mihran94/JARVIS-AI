"""Fetch and verify a source snapshot from the official JARVIS repository."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import time
import zipfile

import httpx

from core.updates import (MAX_ARCHIVE, UpdateError, check_compatibility, inspect_zip)

REPOSITORY = 'mihran94/JARVIS-AI'
API = f'https://api.github.com/repos/{REPOSITORY}'
ARCHIVES = f'https://codeload.github.com/{REPOSITORY}/zip'
METADATA_LIMIT = 2_000_000


def _object_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[a-f0-9]{40}', value) is None:
        raise UpdateError('GitHub returned an invalid source identifier.')
    return value


def _download(client, url, output, limit, check):
    deadline = time.monotonic() + 45
    check()
    with client.stream('GET', url, headers={'Accept': 'application/vnd.github+json', 'Accept-Encoding': 'identity'}) as response:
        if response.status_code == 404:
            raise UpdateError('GitHub source was not available publicly. Use the reviewed ZIP option.')
        if response.status_code in {403, 429}:
            raise UpdateError('GitHub refused or limited the source check. Try again later.')
        if response.status_code != 200:
            raise UpdateError(f'GitHub source download failed (HTTP {response.status_code}).')
        if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
            raise UpdateError('GitHub returned an unexpected transfer encoding.')
        total = 0
        for chunk in response.iter_raw():
            check()
            if time.monotonic() > deadline:
                raise UpdateError('GitHub source download timed out.')
            total += len(chunk)
            if total > limit:
                raise UpdateError('GitHub source response exceeds the allowed size.')
            output.write(chunk)
    check()


def _metadata(client, url, check):
    with BytesIO() as output:
        _download(client, url, output, METADATA_LIMIT, check)
        return json.loads(output.getvalue())


def _blob_id(data):
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode('ascii'), usedforsecurity=False)
    blob.update(data)
    return blob.hexdigest()


def _verify_tree(tree, tree_id, files, check):
    if tree['truncated'] is not False or tree['sha'] != tree_id:
        raise UpdateError('GitHub did not return the complete source tree.')
    expected = {}
    for entry in tree['tree']:
        if entry['type'] == 'tree' and entry['mode'] == '040000':
            continue
        if entry['type'] != 'blob' or entry['mode'] not in {'100644', '100755'}:
            raise UpdateError('This source tree contains an unsupported entry.')
        name = entry['path']
        if not isinstance(name, str) or name in expected:
            raise UpdateError('GitHub returned an invalid source tree.')
        expected[name] = _object_id(entry['sha'])
    if expected.keys() != files.keys():
        raise UpdateError('The source ZIP contents differ from the GitHub commit.')
    for name, data in files.items():
        check()
        if _blob_id(data) == expected[name]:
            continue
        # Git archives can apply the Windows batch-file eol rules in .gitattributes.
        if name.endswith(('.cmd', '.bat')) and _blob_id(data.replace(b'\r\n', b'\n')) == expected[name]:
            continue
        raise UpdateError('The source ZIP failed GitHub commit verification.')


def fetch_latest_source(root, *, check, transport=None):
    """Download the latest commit on `main` and verify it against its tree.

    Nothing on disk is selected and no version is changed: the caller decides
    what to do with the source. The owner requirement for this draft is that
    the automatic check prepares a candidate for review and leaves the
    running version alone.

    Returns the revision, the digest of the archive and the verified files.
    """
    root = Path(root)
    try:
        with httpx.Client(transport=transport, timeout=10, follow_redirects=False,
                          trust_env=False, headers={'User-Agent': 'JARVIS-AI-source-updates'}) as client:
            commit = _metadata(client, f'{API}/commits/main', check)
            revision = _object_id(commit['sha'])
            tree_id = _object_id(commit['commit']['tree']['sha'])
            tree = _metadata(client, f'{API}/git/trees/{tree_id}?recursive=1', check)
            with tempfile.TemporaryDirectory(prefix='jarvis-source-') as temp:
                archive = Path(temp) / 'source.zip'
                with archive.open('wb') as output:
                    _download(client, f'{ARCHIVES}/{revision}', output, MAX_ARCHIVE, check)
                digest, files = inspect_zip(archive)
            _verify_tree(tree, tree_id, files, check)
    except httpx.HTTPError:
        raise UpdateError('Could not reach GitHub for a source update. Try again later.') from None
    except UpdateError:
        raise
    except (KeyError, TypeError, ValueError, zipfile.BadZipFile, NotImplementedError):
        raise UpdateError('GitHub returned invalid source update data.') from None
    check()
    check_compatibility(root, files)
    return revision, digest, files
