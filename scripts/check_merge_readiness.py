"""Fail closed until required upstream source trees are actually present.

This is a structural pre-merge gate, not a substitute for application,
Windows installer, Android device, or security integration tests.
"""
from pathlib import Path

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
