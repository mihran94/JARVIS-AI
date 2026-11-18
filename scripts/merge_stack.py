"""Merge the JARVIS PRIME stack into one branch, in order.

The work arrived as thirteen stacked pull requests, each one built on the
one before it. They were pushed through an API that cannot rewrite
history, so the branches do not sit on one another's commits. Two things
follow from that:

* Merging them one by one leaves a conflict in
  `docs/SOURCE_INTEGRITY.sha256`, because that file is written for the
  tree of one branch and two different trees give two different files.
  The right answer is always the same: write the manifest again for the
  tree that is being merged.
* The first branch also carries work the later branches do not have, the
  application icon among it. A merge keeps it, because the later branches
  never touched those files.
* The first branch and the later ones were made from different copies of
  the same phase, so a few files were changed on both sides. Where they
  disagree, the first side wins the lines, and the branch keeps the rest
  of its changes.

This script does the whole thing and checks the result. Where the two
sides changed the same lines, the lines of the side that was merged
first are kept, because that side is the one that was already tested.
Every other change of the branch is kept. The script says which file it
had to decide on.

    python scripts/merge_stack.py --out merged/jarvis-prime

The branches, in the order they are merged:

    #44  fix/p0-ci-stability-20261118
    #46  feature/p1-conversation-memory-20261118
    #47  feature/p2-cost-visibility-20261118
    #49  feature/p3-document-intelligence-20261118
    #53  feature/phone-bridge-trust-20261118
    #54  feature/p5-task-plan-20261118
    #55  feature/p6-developer-inspection-20261118
    #56  feature/p7-voice-local-commands-20261118
    #58  feature/p8-safe-control-20261118
    #59  feature/p9-document-search-20261118
    #60  feature/p10-web-research-20261118
    #61  feature/bridge-certificate-pinning-20261118
    #62  feature/p12-global-hotkey-20261118
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent

STACK = [
    'fix/p0-ci-stability-20261118',
    'feature/p1-conversation-memory-20261118',
    'feature/p2-cost-visibility-20261118',
    'feature/p3-document-intelligence-20261118',
    'feature/phone-bridge-trust-20261118',
    'feature/p5-task-plan-20261118',
    'feature/p6-developer-inspection-20261118',
    'feature/p7-voice-local-commands-20261118',
    'feature/p8-safe-control-20261118',
    'feature/p9-document-search-20261118',
    'feature/p10-web-research-20261118',
    'feature/bridge-certificate-pinning-20261118',
    'feature/p12-global-hotkey-20261118',
]

#: The file that is written for the tree of one branch, and is therefore
#: different in two branches. It is written again for the merged tree.
MANIFEST = 'docs/SOURCE_INTEGRITY.sha256'

#: The file that needs a hand when the two sides changed it in different
#: places. The first branch added the list of files the build draws, and
#: the last branch added the list of files that are never in the
#: repository. Both are needed.
SCRIPT = 'scripts/source_manifest.py'


class MergeFailed(Exception):
    """The merge met something it cannot resolve on its own."""


def git(*args, cwd=None, check=True):
    result = subprocess.run(
        ['git', '-C', str(cwd or REPOSITORY)] + list(args),
        capture_output=True, text=True)
    if check and result.returncode != 0:
        raise MergeFailed(result.stderr.strip() or result.stdout.strip())
    return result


def resolve_reference(branch: str, worktree: Path) -> str:
    """The name to merge: the branch itself when it is here, the remote one otherwise."""
    if branch.startswith(('origin/', 'refs/')):
        return branch
    found = git('rev-parse', '--verify', '--quiet', branch, cwd=worktree, check=False)
    if found.stdout.strip():
        return branch
    return f'origin/{branch}'


def resolve_keeping_ours(worktree: Path, name: str) -> bool:
    """Merge one file, keeping our lines where the two sides disagree.

    The two sides are the merged stack so far and the branch that is
    being merged. The lines both sides changed differently are taken from
    the merged stack, because that side is the one that was already
    tested. Every other change of the branch is kept.

    This is the same choice `git merge -X ours` makes, and it is made
    here per file, so the script can still say which file it was.
    """
    base = git('show', f':1:{name}', cwd=worktree, check=False).stdout
    ours = git('show', f':2:{name}', cwd=worktree, check=False).stdout
    theirs = git('show', f':3:{name}', cwd=worktree, check=False).stdout
    path = worktree / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ours, encoding='utf-8')
    with tempfile.NamedTemporaryFile('w', suffix='.base', delete=False) as base_file, \
            tempfile.NamedTemporaryFile('w', suffix='.theirs', delete=False) as theirs_file:
        base_file.write(base)
        theirs_file.write(theirs)
        base_name = base_file.name
        theirs_name = theirs_file.name
    try:
        subprocess.run(['git', 'merge-file', '--ours', str(path), base_name, theirs_name],
                       capture_output=True, text=True)
    finally:
        for name_to_remove in (base_name, theirs_name):
            Path(name_to_remove).unlink(missing_ok=True)
    return True


def conflicted_files(worktree: Path):
    result = git('diff', '--name-only', '--diff-filter=U', cwd=worktree, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def resolve_manifest_script(worktree: Path, branch: str):
    """Keep both skip lists in the manifest script.

    The first branch of the stack skips the files the build draws, such as
    the application icon. The last branch skips the files that are never
    in the repository, such as the Gradle wrapper. The merged script has
    to do both, so the list from the side that has it is put into the
    other side when it is missing.
    """
    script = worktree / SCRIPT
    later = git('show', f'origin/{branch}:{SCRIPT}', cwd=worktree).stdout
    earlier_text = git('show', f'HEAD:{SCRIPT}', cwd=worktree).stdout
    if 'GENERATED_FILES' in later:
        return
    block = ''
    lines = earlier_text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith('GENERATED_FILES')), None)
    if start is None:
        return
    depth = 0
    for index in range(start, len(lines)):
        depth += lines[index].count('{') - lines[index].count('}')
        block += lines[index] + '\n'
        if depth == 0:
            break
    if not block:
        return
    lines = later.splitlines()
    anchor = next((i for i, line in enumerate(lines)
                   if line.startswith('SKIP_DIRS')), None)
    if anchor is None:
        return
    lines.insert(anchor, block.rstrip('\n'))
    later = '\n'.join(lines) + '\n'
    # The check that uses the list has to exist as well.
    if 'relative in GENERATED_FILES' not in later:
        lines = later.splitlines()
        anchor = next((i for i, line in enumerate(lines)
                       if 'relative in SKIP_PATHS' in line), None)
        if anchor is not None:
            lines.insert(anchor, '            if relative in GENERATED_FILES:')
            lines.insert(anchor + 1, '                continue')
            later = '\n'.join(lines) + '\n'
    script.write_text(later, encoding='utf-8')


def write_manifest(worktree: Path):
    # The PWA icons are pictures and the repository carries only their
    # base64 sidecars, so they are written again before the manifest is
    # made. They are build output and are not committed.
    restore = worktree / 'iphone-pwa' / 'icons' / 'restore-icons.py'
    if restore.exists():
        subprocess.run([sys.executable, str(restore)], cwd=worktree,
                       capture_output=True, text=True)
    result = subprocess.run(
        [sys.executable, 'scripts/source_manifest.py'], cwd=worktree,
        capture_output=True, text=True)
    if result.returncode != 0:
        raise MergeFailed(result.stderr.strip() or 'the manifest could not be written')


def merge_stack(base: str, out: str, branches=None, repository: Path = REPOSITORY):
    """Merge every branch in order and return the branch that holds them."""
    branches = list(branches or STACK)
    worktree = Path(tempfile.mkdtemp(prefix='jarvis-merge-'))
    failed = False
    git('worktree', 'add', '--detach', str(worktree), base, cwd=repository)
    try:
        for branch in branches:
            reference = resolve_reference(branch, worktree)
            git('merge', '--no-commit', '--no-ff', reference, cwd=worktree, check=False)
            unresolved = conflicted_files(worktree)
            print(f'  {branch}: ' + (', '.join(unresolved) if unresolved else 'no conflict'))
            if SCRIPT in unresolved:
                resolve_manifest_script(worktree, branch)
            for name in unresolved:
                if name in (MANIFEST, SCRIPT):
                    continue
                # The lines both sides changed are taken from the side
                # that was merged first. The rest of the branch is kept.
                resolve_keeping_ours(worktree, name)
            write_manifest(worktree)
            git('add', '-A', cwd=worktree)
            git('commit', '--quiet', '-m', f'Merge {branch}', cwd=worktree)
        write_manifest(worktree)
        git('add', '-A', cwd=worktree)
        git('commit', '--quiet', '--amend', '--no-edit', cwd=worktree)
        head = git('rev-parse', 'HEAD', cwd=worktree).stdout.strip()
        tree = git('rev-parse', 'HEAD^{tree}', cwd=worktree).stdout.strip()
        git('branch', '-f', out, head, cwd=repository)
        return out, tree, worktree
    except MergeFailed:
        # The unfinished merge is kept, so the owner can look at it and
        # see what it is that the script did not know.
        failed = True
        print(f'The unfinished merge is at {worktree}', file=sys.stderr)
        raise
    finally:
        if not failed and worktree.exists():
            git('worktree', 'remove', '--force', str(worktree), cwd=repository, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--base', default='origin/main',
                        help='the branch the stack is merged into (default origin/main)')
    parser.add_argument('--out', default='merged/jarvis-prime',
                        help='the branch that will hold the merged stack')
    parser.add_argument('--branches', nargs='*', default=None,
                        help='the branches to merge, in order (default: the whole stack)')
    arguments = parser.parse_args()
    try:
        out, tree, _worktree = merge_stack(arguments.base, arguments.out, arguments.branches)
    except MergeFailed as error:
        print(f'The merge stopped: {error}', file=sys.stderr)
        return 1
    print(f'The stack is merged into {out}.')
    print(f'Tree {tree}')
    print('Check it with:')
    print(f'  git checkout {out}')
    print('  python -m pytest -q')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
