"""The workflow patches have to keep applying, and keep saying what they say.

The GitHub App that pushes this repository cannot write
`.github/workflows/`, so every change to a workflow travels as a patch
file. A patch that no longer applies is worse than no patch at all: the
owner is told to run it and it fails.

So every patch is checked here, one at a time, against the tree as it is
now.
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
    result = subprocess.run(
        ['git', 'apply', '--check', str(patch)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (
        f'{patch.name} does not apply any more:\n{result.stderr.strip()}')


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


def test_the_workflows_in_the_tree_still_need_the_patches():
    """The tree must still be in the state the patches are meant to change."""
    android = (ROOT / '.github/workflows/android-integration.yml').read_text(encoding='utf-8')
    assert 'pull_request:' not in android.split('jobs:')[0], (
        'the Android workflow already builds on a pull request, so the patch '
        'is not needed any more')
    windows = (ROOT / '.github/workflows/windows-integration.yml').read_text(encoding='utf-8')
    assert "branches: ['**']" not in windows, (
        'the Windows workflow already builds for any branch, so the patch is '
        'not needed any more')
