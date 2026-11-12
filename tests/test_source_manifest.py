"""The source integrity manifest must match the tree.

The manifest is what the owner verifies before building. If it drifts away
from the files, the verification is worthless, so the test suite checks it on
every run.
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'source_manifest.py')
ICONS = os.path.join(ROOT, 'iphone-pwa', 'icons', 'restore-icons.py')


def restore_icons():
    """The PWA icons are build output, so they are restored before the check."""
    if not os.path.exists(ICONS):
        return
    spec = importlib.util.spec_from_file_location('restore_icons', ICONS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    restore = getattr(module, 'restore', None)
    if restore is not None:
        restore()


def test_the_source_manifest_matches_the_tree():
    restore_icons()
    result = subprocess.run(
        [sys.executable, SCRIPT, '--check', '--root', ROOT],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        'docs/SOURCE_INTEGRITY.sha256 does not match the tree. '
        'Run: python scripts/source_manifest.py\n' + result.stdout
    )


def test_the_manifest_covers_every_source_file():
    spec = importlib.util.spec_from_file_location('source_manifest', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(os.path.join(ROOT, 'docs', 'SOURCE_INTEGRITY.sha256'), encoding='utf-8') as handle:
        lines = [line for line in handle if not line.startswith('#') and line.strip()]
    assert len(lines) > 100
    assert len(lines) == len(module.collect(ROOT))
    for line in lines:
        digest, _, path = line.partition('  ')
        path = path.strip()
        assert len(digest) == 64, path
        assert os.path.exists(os.path.join(ROOT, path)), path
