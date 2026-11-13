"""Fail closed until required upstream source trees are actually present.

This is a structural pre-merge gate, not a substitute for application,
Windows installer, Android device, or security integration tests.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "Windows desktop": "desktop",
    "Windows provider router": "providers",
    "Shared device protocol": "jarvis_unified",
    "Original Jarvis-Blue source": "legacy/jarvis-blue",
    "Android source": "android",
}


def missing_sources(root=ROOT):
    return [label for label, relative in REQUIRED.items()
            if not (root / relative).is_dir()
            or not any((root / relative).iterdir())]


def main():
    if not (ROOT / '.git').exists():
        print('MERGE BLOCKED: full git checkout required to verify main history')
        return 1
    try:
        subprocess.run(['git', 'fetch', '--no-tags', 'origin', 'main'],
                       cwd=ROOT, check=True, capture_output=True, timeout=120)
        result = subprocess.run(['git', 'merge-base', '--is-ancestor',
                                 'refs/remotes/origin/main', 'HEAD'],
                                cwd=ROOT, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        print('MERGE BLOCKED: unable to verify origin/main ancestry')
        return 1
    if result.returncode != 0:
        print('MERGE BLOCKED: current branch has not integrated origin/main')
        return 1

    missing = missing_sources()
    if missing:
        print("MERGE BLOCKED: required source trees missing:")
        for name in missing:
            print(" - " + name)
        return 1
    print("Structural source presence passed; functional testing still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
