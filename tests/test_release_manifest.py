"""Tests for the release manifest writer."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'scripts'))

from release_manifest import collect, file_digest, main, write_manifest


def test_the_digest_matches_the_file(tmp_path):
    target = tmp_path / 'app.exe'
    target.write_bytes(b'hello')
    assert file_digest(str(target)) == (
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824')


def test_every_file_is_collected_with_its_size(tmp_path):
    (tmp_path / 'app.exe').write_bytes(b'hello')
    nested = tmp_path / 'lib'
    nested.mkdir()
    (nested / 'data.bin').write_bytes(b'x' * 10)
    entries = collect(str(tmp_path))
    assert [entry[0] for entry in entries] == ['app.exe', 'lib/data.bin']
    assert entries[1][1] == 10


def test_the_manifest_records_the_version_and_revision(tmp_path):
    build = tmp_path / 'dist'
    build.mkdir()
    (build / 'app.exe').write_bytes(b'hello')
    output = tmp_path / 'manifest.txt'
    write_manifest(str(build), str(output), version='0.3.0', revision='abc123', channel='beta')
    text = output.read_text()
    assert 'version:  0.3.0' in text
    assert 'revision: abc123' in text
    assert 'channel:  beta' in text
    assert 'files:    1' in text
    assert 'app.exe' in text


def test_the_manifest_can_be_verified(tmp_path):
    import hashlib
    build = tmp_path / 'dist'
    build.mkdir()
    (build / 'app.exe').write_bytes(b'hello')
    output = tmp_path / 'manifest.txt'
    write_manifest(str(build), str(output))
    line = [row for row in output.read_text().splitlines() if row.endswith('app.exe')][0]
    _, digest, name = line.split('  ')
    assert digest == hashlib.sha256(b'hello').hexdigest()


def test_a_missing_directory_is_reported(tmp_path):
    assert main([str(tmp_path / 'nope'), str(tmp_path / 'out.txt')]) == 1
