"""The workflow patches have to keep applying, and keep saying what they say.

The GitHub App that pushes this repository cannot write
`.github/workflows/`, so every change to a workflow travels as a patch
file. A patch that no longer applies is worse than no patch at all: the
owner is told to run it and it fails.

Each patch is checked in both directions: it must either apply cleanly
or already have been fully applied. This keeps tests valid after the owner
applies the workflow patches to prepare a release.
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATCHES = sorted((ROOT / 'patches').glob('*.patch'))


def test_there_are_patches_to_check():
    assert PATCHES, 'the patch directory is empty, so nothing would be checked'


@pytest.mark.parametrize('patch', PATCHES, ids=lambda path: path.name)
def test_the_patch_applies_to_the_tree_as_it_is(patch):
    forward = subprocess.run(
        ['git', 'apply', '--check', str(patch)],
        cwd=ROOT, capture_output=True, text=True)
    reverse = subprocess.run(
        ['git', 'apply', '--reverse', '--check', str(patch)],
        cwd=ROOT, capture_output=True, text=True)
    assert forward.returncode == 0 or reverse.returncode == 0, (
        f'{patch.name} is neither cleanly applicable nor fully applied. '
        f'Forward: {forward.stderr.strip()} '
        f'Reverse: {reverse.stderr.strip()}')


def test_the_stack_patch_builds_the_phone_on_a_pull_request():
    body = (ROOT / 'patches' / 'ci-stack-verification.patch').read_text(encoding='utf-8')
    assert 'android-integration.yml' in body
    assert 'pull_request:' in body
    # The rules of the phone are in :core:common, and they have to be
    # run, or the tests of the rules never happen.
    assert ':core:common:test' in body


def test_the_stack_patch_builds_the_installer_for_any_branch():
    body = (ROOT / 'patches' / 'ci-stack-verification.patch').read_text(encoding='utf-8')
    assert 'windows-integration.yml' in body
    # The stack is a stack of pull requests to the branch below, so the
    # installer has to be built for a pull request to any branch.
    assert "branches: ['**']" in body


def test_workflow_state_matches_its_patch():
    """Accept either untouched or fully applied workflows, never partial edits."""
    android = (ROOT / '.github/workflows/android-integration.yml').read_text(
        encoding='utf-8')
    windows = (ROOT / '.github/workflows/windows-integration.yml').read_text(
        encoding='utf-8')
    if 'pull_request:' in android.split('jobs:')[0]:
        assert ':core:common:test' in android
        assert ':app:assembleDebug' in android
    if "branches: ['**']" in windows:
        assert 'pull_request:' in windows.split('jobs:')[0]
