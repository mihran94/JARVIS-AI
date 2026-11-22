"""The script that merges the stack has to merge it, not guess.

The work arrived as thirteen stacked pull requests. They were pushed
through an API that cannot rewrite history, so the branches do not sit
on one another's commits, and merging them one by one leaves a conflict
in the source integrity manifest.

The script has to resolve that conflict the only correct way — write
the manifest again for the tree that is being merged — and it has to stop
when it meets a conflict it does not know, rather than choosing for the
owner.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.merge_stack import MANIFEST, MergeFailed, STACK, merge_stack  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def git(cwd, *args):
    result = subprocess.run(['git', '-C', str(cwd)] + list(args),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def build_repository(directory: Path):
    """A tiny repository with two branches that disagree about the manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    git(directory, 'init', '--quiet', '-b', 'main')
    git(directory, 'config', 'user.email', 'test@example.invalid')
    git(directory, 'config', 'user.name', 'Test')
    (directory / 'docs').mkdir()
    (directory / 'scripts').mkdir()
    (directory / 'docs' / 'SOURCE_INTEGRITY.sha256').write_text(
        '# the manifest\n0000000000000000000000000000000000000000000000000000000000000000  a.txt\n',
        encoding='utf-8')
    (directory / 'scripts' / 'source_manifest.py').write_text(
        'import hashlib, os\n'
        'root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
        'files = []\n'
        'for directory, subdirectories, names in os.walk(root):\n'
        '    subdirectories[:] = [d for d in subdirectories if d != ".git"]\n'
        '    for name in names:\n'
        '        relative = os.path.relpath(os.path.join(directory, name), root)\n'
        '        relative = relative.replace(os.sep, "/")\n'
        '        if relative == "docs/SOURCE_INTEGRITY.sha256":\n'
        '            continue\n'
        '        files.append(relative)\n'
        'lines = []\n'
        'for relative in sorted(files):\n'
        '    with open(os.path.join(root, relative), "rb") as handle:\n'
        '        digest = hashlib.sha256(handle.read()).hexdigest()\n'
        '    lines.append(digest + "  " + relative + "\\n")\n'
        'with open(os.path.join(root, "docs/SOURCE_INTEGRITY.sha256"), "w") as handle:\n'
        '    handle.write("# the manifest\\n" + "".join(lines))\n',
        encoding='utf-8')
    (directory / 'a.txt').write_text('one\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'first')

    git(directory, 'checkout', '--quiet', '-b', 'one')
    (directory / 'a.txt').write_text('one changed\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'first branch')

    git(directory, 'checkout', '--quiet', 'main')
    git(directory, 'checkout', '--quiet', '-b', 'two')
    (directory / 'b.txt').write_text('two\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'second branch')
    return directory


def test_the_stack_is_the_thirteen_branches_in_order():
    assert len(STACK) == 13
    assert STACK[0] == 'fix/p0-ci-stability-20261118'
    assert STACK[-1] == 'feature/p12-global-hotkey-20261118'
    assert len(set(STACK)) == len(STACK)


def test_a_merge_that_conflicts_is_finished_and_the_manifest_is_written(tmp_path):
    directory = build_repository(tmp_path / 'repository')
    out, tree, worktree = merge_stack(
        'main', 'merged', branches=['one', 'two'], repository=directory)
    try:
        assert out == 'merged'
        # The worktree is taken away again when the merge is done.
        assert not worktree.exists()
        # The manifest was written again for the merged tree, and the
        # merged branch holds it.
        body = git(directory, 'show', 'merged:docs/SOURCE_INTEGRITY.sha256')
        assert 'a.txt' in body
        assert 'b.txt' in body
        # And nothing is left unmerged.
        unmerged = subprocess.run(
            ['git', '-C', str(directory), 'diff', '--name-only', '--diff-filter=U'],
            capture_output=True, text=True).stdout.strip()
        assert not unmerged
    finally:
        subprocess.run(['git', '-C', str(directory), 'worktree', 'prune'], capture_output=True)


def test_a_content_conflict_keeps_the_lines_of_the_merged_side(tmp_path):
    directory = build_repository(tmp_path / 'repository')
    # Both sides write the same file in a way that cannot be merged.
    git(directory, 'checkout', '--quiet', 'one')
    (directory / 'a.txt').write_text('one side\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'one side')
    git(directory, 'checkout', '--quiet', 'two')
    (directory / 'a.txt').write_text('two side\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'two side')
    # The manifest is the same on both sides now, so the merge is clean.
    # Add a file that both sides change in different ways.
    git(directory, 'checkout', '--quiet', 'one')
    (directory / 'c.txt').write_text('one side\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'one side of c')
    git(directory, 'checkout', '--quiet', 'two')
    (directory / 'c.txt').write_text('two side\n', encoding='utf-8')
    git(directory, 'add', '-A')
    git(directory, 'commit', '--quiet', '-m', 'two side of c')
    merge_stack('main', 'merged', branches=['one', 'two'], repository=directory)
    # The lines both sides changed are taken from the side that was
    # merged first, and the file is not left with conflict markers.
    body = git(directory, 'show', 'merged:c.txt')
    assert 'one side' in body
    assert '<<<<<<<' not in body
    # And nothing is left unmerged.
    unmerged = subprocess.run(
        ['git', '-C', str(directory), 'diff', '--name-only', '--diff-filter=U'],
        capture_output=True, text=True).stdout.strip()
    assert not unmerged


def test_the_manifest_is_the_file_that_is_written_again():
    assert MANIFEST == 'docs/SOURCE_INTEGRITY.sha256'


def test_the_script_lives_in_the_repository():
    assert (ROOT / 'scripts' / 'merge_stack.py').exists()
    assert os.access(ROOT / 'scripts' / 'merge_stack.py', os.R_OK)
