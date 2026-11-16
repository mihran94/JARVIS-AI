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

from core.updates import (MAX_ARCHIVE, UpdateError, backup_history, check_compatibility,
                          inspect_zip, read_state, release_path, stage_snapshot)

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


def stage_latest(root, running_root, history, *, check, publish, transport=None):
    state = read_state(root)
    if release_path(root, state['active']) != Path(running_root).resolve():
        return 'A version is already selected. Restart from START_JARVIS.cmd to use it.'
    try:
        with httpx.Client(transport=transport, timeout=10, follow_redirects=False,
                          trust_env=False, headers={'User-Agent': 'JARVIS-AI-source-updates'}) as client:
            commit = _metadata(client, f'{API}/commits/main', check)
            revision = _object_id(commit['sha'])
            if revision == state.get('last_source_revision'):
                return f'Source commit {revision[:12]} has already been checked.'
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
    check_compatibility(Path(root), files)
    if read_state(root) != state:
        raise UpdateError('Another update changed the selected version. Check again.')
    if state['active'] != digest:
        backup_history(history)
    stage_snapshot(root, digest, files, revision=revision, expected_state=state,
                   check=check, publish=publish)
    if state['active'] == digest:
        return f'Source commit {revision[:12]} matches the selected version.'
    return f'Source commit {revision[:12]} staged. Restart from START_JARVIS.cmd to use it.'
