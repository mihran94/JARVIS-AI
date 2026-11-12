"""Tests for the signing material checker."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'scripts'))

from check_signing_material import main, scan


def test_a_clean_tree_reports_nothing(tmp_path):
    (tmp_path / 'README.md').write_text('hello')
    (tmp_path / 'app.py').write_text('print("hello")')
    assert scan(str(tmp_path)) == []
    assert main(['check', str(tmp_path)]) == 0


def test_a_keystore_is_reported(tmp_path):
    (tmp_path / 'release.p12').write_bytes(b'binary')
    found = scan(str(tmp_path))
    assert len(found) == 1
    assert found[0][0].endswith('release.p12')


def test_a_credential_file_is_reported(tmp_path):
    (tmp_path / 'secrets.properties').write_text('password=secret')
    found = scan(str(tmp_path))
    assert len(found) == 1
    assert 'credential file name' in found[0][1]


def test_a_keystore_configuration_is_reported(tmp_path):
    (tmp_path / 'keystore.properties').write_text('storePassword=secret')
    found = scan(str(tmp_path))
    assert len(found) == 1


def test_ignored_directories_are_not_scanned(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'release.p12').write_bytes(b'binary')
    assert scan(str(tmp_path)) == []


def test_the_exit_code_is_one_when_something_is_found(tmp_path):
    (tmp_path / 'key.p12').write_bytes(b'binary')
    assert main(['check', str(tmp_path)]) == 1


def test_a_missing_directory_is_a_usage_error(tmp_path):
    assert main(['check', str(tmp_path / 'nope')]) == 2
