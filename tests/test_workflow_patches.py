"""The workflows have to do what the owner expects, and the patches have to
keep applying.

WHY THIS FILE EXISTS
    The GitHub App that pushes this repository has no `workflows`
    permission, so it cannot write `.github/workflows/`. Every change to
    a workflow therefore travels as a patch file, and a patch that no
    longer applies is worse than no patch at all: the owner is told to
    run it and it fails.

    The older version of this file only looked at the text of the patch
    files. It passed while the workflows in the repository did not build
    the Android application on a pull request at all, and while the
    desktop matrix hid the Windows result behind a cancelled Linux job.
    A green test suite has to describe what the CI actually does, so the
    patches are applied here to a copy of the tree and the workflows
    that come out are read.

WHAT IS COVERED
    * The desktop workflow reports both operating systems, so a Linux
      only failure never hides the Windows result.
    * The Android application is built on a pull request, and the tests
      of `:core:common` run there, where the rules of the phone live.
    * The Windows installer is built for a pull request to any branch,
      because the work arrives as a stack of branches.
    * Every patch still applies, no two patches add the same line to the
      same file, and the whole set applies together.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / '.github' / 'workflows'
PATCHES = sorted((ROOT / 'patches').glob('*.patch'))

ANDROID_WORKFLOW = WORKFLOWS / 'android-integration.yml'
DESKTOP_WORKFLOW = WORKFLOWS / 'tests.yml'
WINDOWS_WORKFLOW = WORKFLOWS / 'windows-integration.yml'

#: The branch that carries the current work. The Android build used to run
#: only after a change reached main, so this branch was never compiled.
WORK_BRANCH = 'integration/jarvis-prime-final-review-20261119'


# --------------------------------------------------------------------------
# A small reader for the workflow files
#
# PyYAML is not installed here, and `on:` is a boolean key in YAML 1.1, so
# the workflows are read with a reader that follows the indentation and
# never guesses what a key means.
# --------------------------------------------------------------------------

def _indent(line):
    return len(line) - len(line.lstrip(' '))


def _is_skippable(line):
    stripped = line.strip()
    return not stripped or stripped.startswith('#')


def _next_content(lines, index):
    while index < len(lines) and _is_skippable(lines[index]):
        index += 1
    return index if index < len(lines) else None


def _scalar(text):
    """The value of a `key: value` line."""
    text = text.strip()
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('\'"') for item in inner.split(',')]
    if len(text) > 1 and text[0] == text[-1] and text[0] in '\'"':
        return text[1:-1]
    lowered = text.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    return text


def _parse_mapping(lines, index, indent):
    """A mapping whose keys are at `indent`."""
    node = {}
    while index < len(lines):
        found = _next_content(lines, index)
        if found is None:
            break
        line = lines[found]
        current = _indent(line)
        if current < indent:
            break
        assert current == indent, f'unexpected indentation in {line!r}'
        key, separator, value = line.strip().partition(':')
        assert separator, f'not a mapping line: {line!r}'
        key = key.strip()
        value = value.strip()
        index = found + 1
        if value in ('|', '>', '|-', '>-', '|+', '>+'):
            # A block of text. The lines under it are not a mapping.
            block = []
            while index < len(lines):
                if lines[index].strip() and _indent(lines[index]) <= indent:
                    break
                block.append(lines[index])
                index += 1
            node[key] = '\n'.join(block)
            continue
        if value:
            node[key] = _scalar(value)
            continue
        child, index = _parse_node(lines, index, indent + 1)
        node[key] = child
    return node, index


def _parse_sequence(lines, index, indent):
    """A sequence whose items are at `indent`."""
    node = []
    while index < len(lines):
        found = _next_content(lines, index)
        if found is None:
            break
        line = lines[found]
        current = _indent(line)
        if current < indent:
            break
        stripped = line.strip()
        if not stripped.startswith('- '):
            break
        text = stripped[2:]
        index = found + 1
        if ':' in text:
            key, _, value = text.partition(':')
            child, index = _parse_node(lines, index, indent + 2)
            child[key.strip()] = _scalar(value.strip())
            node.append(child)
        else:
            node.append(_scalar(text))
    return node, index


def _parse_node(lines, index, indent):
    """The node that starts at `index`, indented by at least `indent`."""
    found = _next_content(lines, index)
    if found is None:
        return {}, index
    current = _indent(lines[found])
    if current < indent:
        return {}, index
    if lines[found].strip().startswith('- '):
        return _parse_sequence(lines, found, current)
    return _parse_mapping(lines, found, current)


def _workflow(path):
    """The workflow file as a nested structure."""
    document, _ = _parse_node(path.read_text(encoding='utf-8').splitlines(), 0, 0)
    return document


def _steps(workflow, job):
    return workflow['jobs'][job]['steps']


def _command_with(workflow, job, needle):
    for step in _steps(workflow, job):
        command = step.get('run', '')
        if needle in command:
            return command
    raise AssertionError(f'no step of {job} runs {needle!r}')


def _branch_matches(pattern, branch):
    if pattern == '**':
        return True
    if pattern.endswith('/**'):
        return branch.startswith(pattern[:-2])
    return pattern == branch


# --------------------------------------------------------------------------
# The workflow the owner ends up with
#
# The workflow files in the repository cannot hold the changes, because
# the App that pushes this repository cannot write them. The owner
# applies the patches once, and what comes out is what the build servers
# run. These tests read that result.
# --------------------------------------------------------------------------

def _patch_targets(patch):
    """The files a patch touches, and whether the patch creates them."""
    targets = []
    for line in patch.read_text(encoding='utf-8').splitlines():
        if line.startswith('diff --git '):
            targets.append([line.split(' ')[-1][2:], False])
        elif line.startswith('--- /dev/null') and targets:
            targets[-1][1] = True
    return [(path, created) for path, created in targets]


def _apply_the_whole_set(tmp_path):
    """Apply every patch to a copy of the tree and return the copy."""
    for patch in PATCHES:
        for path, created in _patch_targets(patch):
            source = ROOT / path
            if created or not source.is_file():
                continue
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for patch in PATCHES:
        result = subprocess.run(
            ['git', 'apply', str(patch)], cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0, (
            f'{patch.name} does not apply to the tree: {result.stderr.strip()}')
    return tmp_path


@pytest.fixture(scope='module')
def patched(tmp_path_factory):
    """The tree with every patch applied, as the owner will have it."""
    return _apply_the_whole_set(tmp_path_factory.mktemp('patched'))


def test_the_workflows_are_in_the_repository(patched):
    """The owner has a workflow file for every recipe."""
    for name in ('tests.yml', 'android-integration.yml', 'windows-integration.yml'):
        assert (patched / '.github' / 'workflows' / name).is_file(), (
            f'{name} is missing from the tree')


def test_the_desktop_matrix_reports_both_operating_systems(patched):
    """A Linux only failure must never hide the Windows result.

    The matrix had no `fail-fast: false`, and GitHub cancels the other
    job of the matrix when one of them fails, so the result of the second
    operating system was never reported.
    """
    workflow = _workflow(patched / '.github' / 'workflows' / 'tests.yml')
    strategy = workflow['jobs']['test']['strategy']
    assert strategy.get('fail-fast') is False, (
        'the matrix strategy does not turn fail-fast off, so a failing job '
        'cancels the other one and hides its result')
    assert set(strategy['matrix']['os']) == {'ubuntu-latest', 'windows-latest'}, (
        'the matrix does not run on both operating systems any more')


def test_the_linux_runner_gets_the_qt_runtime(patched):
    """The Linux runner has no `libEGL.so.1`, so the suite cannot import PySide6."""
    workflow = _workflow(patched / '.github' / 'workflows' / 'tests.yml')
    steps = '\n'.join(step.get('run', '') for step in _steps(workflow, 'test'))
    assert 'libegl1' in steps, (
        'the Linux job does not install the Qt runtime libraries, so the '
        'whole suite stops with an ImportError')


def test_the_android_build_runs_on_a_pull_request(patched):
    """The phone was never compiled before it was merged.

    Five of the eight workflows had no pull request trigger at all, and
    the Android one only ran for a push to an allow list of branches that
    the work does not use. A change to the phone was therefore never
    built before it reached main.
    """
    workflow = _workflow(patched / '.github' / 'workflows' / 'android-integration.yml')
    triggers = workflow['on']
    assert 'pull_request' in triggers, (
        'the Android workflow has no pull_request trigger, so a pull '
        'request that touches the phone never builds it')


def test_the_android_pull_request_covers_the_branch_that_carries_the_work(patched):
    workflow = _workflow(patched / '.github' / 'workflows' / 'android-integration.yml')
    branches = workflow['on']['pull_request'].get('branches')
    assert branches is None or any(
        _branch_matches(pattern, WORK_BRANCH) for pattern in branches), (
        f'no pull request trigger covers {WORK_BRANCH}')


def test_the_android_build_runs_when_the_phone_is_touched(patched):
    """A pull request that touches the phone builds the phone."""
    workflow = _workflow(patched / '.github' / 'workflows' / 'android-integration.yml')
    paths = workflow['on']['pull_request'].get('paths')
    assert paths is None or 'android/**' in paths, (
        'the pull request trigger of the Android workflow does not watch '
        'the phone, so a change to the phone never builds it')


def test_the_android_build_runs_the_rules_of_the_phone(patched):
    """The rules of the phone live in `:core:common`.

    Without that module in the command, 91 of the 105 Android unit tests
    never run, and the `CertificatePinTest` and `PairingCodeTest` suites,
    the most valuable ones in the tree, are never run at all. With it, the
    38 tests of that module run before the APK is assembled.
    """
    workflow = _workflow(patched / '.github' / 'workflows' / 'android-integration.yml')
    command = _command_with(workflow, 'android-build', './gradlew')
    assert ':core:common:test' in command, (
        'the Android build does not run the tests of :core:common')
    assert ':app:assembleDebug' in command, (
        'the Android build does not assemble the debug APK')


def test_the_windows_installer_is_built_for_any_branch(patched):
    """The work arrives as a stack of branches.

    Every one of them is a pull request to the branch below it, so the
    Windows installer was never built for the stack.
    """
    workflow = _workflow(patched / '.github' / 'workflows' / 'windows-integration.yml')
    branches = workflow['on']['pull_request'].get('branches')
    assert branches is None or any(
        _branch_matches(pattern, WORK_BRANCH) for pattern in branches), (
        f'the Windows installer is not built for a pull request to {WORK_BRANCH}')


# --------------------------------------------------------------------------
# The patch files
# --------------------------------------------------------------------------

def test_there_are_patches_to_check():
    assert PATCHES, 'the patch directory is empty, so nothing would be checked'


@pytest.mark.parametrize('patch', PATCHES, ids=lambda path: path.name)
def test_the_patch_applies_to_the_tree_as_it_is(patch):
    """A patch applies, or it is already applied. Never neither."""
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


def _added_lines(patch):
    """The lines a patch adds, with the file they are added to."""
    target = None
    for line in patch.read_text(encoding='utf-8').splitlines():
        if line.startswith('diff --git '):
            target = line.split(' ')[-1][2:]
        elif line.startswith('+++ '):
            continue
        elif line.startswith('+') and target:
            yield target, line[1:]


def test_no_two_patches_add_the_same_line_to_the_same_file():
    """Two patches that add the same line cannot both be applied.

    The two patches that changed the test workflow added the very same
    lines byte for byte, so `git apply --check` passed for either of them
    and applying both of them failed. They now carry different halves of
    the same change.
    """
    seen = {}
    for patch in PATCHES:
        for path, line in _added_lines(patch):
            key = (path, line)
            other = seen.get(key)
            assert other is None or other == patch.name, (
                f'{patch.name} adds a line to {path} that '
                f'{other} adds as well, so only one of them can be '
                f'applied')
            seen[key] = patch.name


def test_the_whole_patch_set_applies_to_the_tree(tmp_path):
    """The owner applies the patches one after the other, so they have to
    work together and not only one by one."""
    for patch in PATCHES:
        for path, created in _patch_targets(patch):
            source = ROOT / path
            if created or not source.is_file():
                continue
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for patch in PATCHES:
        forward = subprocess.run(
            ['git', 'apply', str(patch)],
            cwd=tmp_path, capture_output=True, text=True)
        if forward.returncode == 0:
            continue
        reverse = subprocess.run(
            ['git', 'apply', '--reverse', '--check', str(patch)],
            cwd=tmp_path, capture_output=True, text=True)
        assert reverse.returncode == 0, (
            f'{patch.name} does not apply to the tree, and it is not '
            f'applied either: {forward.stderr.strip()}')
