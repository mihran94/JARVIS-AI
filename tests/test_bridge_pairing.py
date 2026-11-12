"""The pairing code that the desktop draws and the iPhone reads.

The test that matters is the last one: it draws the code with the desktop
encoder and reads it back with the decoder that the phone uses, so the two
halves are checked against each other.
"""
import json
import os
import shutil
import subprocess

import pytest

from desktop.bridge_pairing import (
    PAIRING_FORMAT, PairingCodeError, expires_at, pairing_matrix, pairing_payload,
    pairing_svg,
)

SECRET = 'shared-secret-for-tests-0123456789abcdef'
PWA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'iphone-pwa')


def test_the_code_has_the_agreed_shape():
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1', SECRET,
                               expires_at(now=1700000000))
    lines = payload.split('\n')
    assert lines[0] == PAIRING_FORMAT
    assert lines[1] == 'bridge=https://pc.example.lan:8765'
    assert lines[2] == 'key=jarvis-iphone-v1'
    assert lines[3] == 'secret=' + SECRET
    assert lines[4].startswith('expires=')


def test_the_expiry_is_in_the_future():
    assert expires_at(now=1700000000) == 1700000000 + 900
    assert expires_at(now=1700000000, lifetime_seconds=60) == 1700000060


def test_the_expiry_without_a_moment_is_in_the_future():
    import time
    assert expires_at() > int(time.time())


def test_an_address_without_https_is_refused():
    with pytest.raises(PairingCodeError):
        pairing_payload('http://pc.example.lan', 'key', SECRET, 1)
    with pytest.raises(PairingCodeError):
        pairing_payload('', 'key', SECRET, 1)


def test_a_short_secret_is_refused():
    with pytest.raises(PairingCodeError):
        pairing_payload('https://pc.example.lan', 'key', 'short', 1)


def test_a_missing_key_or_expiry_is_refused():
    with pytest.raises(PairingCodeError):
        pairing_payload('https://pc.example.lan', '', SECRET, 1)
    with pytest.raises(PairingCodeError):
        pairing_payload('https://pc.example.lan', 'key', SECRET, 0)


def test_the_code_is_drawn_as_a_picture():
    svg = pairing_svg('JARVIS-BRIDGE-v1')
    assert svg.lstrip().startswith('<?xml') or svg.lstrip().startswith('<svg')
    assert 'svg' in svg


def test_the_phone_reads_the_code_the_desktop_drew():
    """The desktop encoder and the phone decoder have to agree."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed on this machine')
    payload = pairing_payload('https://pc.example.lan:8765', 'jarvis-iphone-v1', SECRET,
                               expires_at(now=1700000000))
    matrix = pairing_matrix(payload)
    completed = subprocess.run(
        [node, os.path.join(PWA, 'tools', 'decode-matrix.mjs')],
        input=json.dumps(matrix), capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == payload
