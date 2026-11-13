"""Import full upstream JARVIS repositories into a local JARVIS-AI monorepo.

Safe by default: prints commands only. Never deletes repositories, pushes, or
merges to main. Run from a clean JARVIS-AI checkout with git-subtree available.
This imports each upstream source tree and its history, including licenses,\ninto a dedicated directory.
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("legacy/jarvis-blue", "https://github.com/mihran94/Jarvis-Blue.git", "main"),
    ("android", "https://github.com/mihran94/jarvis-blue-android.git", "main"),
)


def commands(source=None):
    if source is not None and source not in {item[0] for item in SOURCES}:
        raise ValueError("Unknown upstream source")
    selected = [item for item in SOURCES if source is None or item[0] == source]
    return [
        ["git", "subtree", "add", f"--prefix={prefix}", url, ref]
        for prefix, url, ref in selected
    ]


def verify_checkout(source=None):
    if not (ROOT / ".git").exists():
        raise RuntimeError("Run inside a full git checkout of JARVIS-AI")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    if not branch or branch in {"main", "master"}:
        raise RuntimeError("Use a named integration branch, never main/master")
    changes = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    if changes.strip():
        raise RuntimeError("Working tree must be clean")
    remotes = subprocess.check_output(
        ["git", "remote", "-v"], cwd=ROOT, text=True
    )
    if "mihran94/JARVIS-AI" not in remotes:
        raise RuntimeError("This checkout does not identify the expected JARVIS-AI origin")
    for prefix, _, _ in SOURCES:
        if (source is None or prefix == source) and (ROOT / prefix).exists():
            raise RuntimeError(f"Import destination already exists: {prefix}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually import upstream trees into this local branch")
    parser.add_argument("--source", choices=[item[0] for item in SOURCES],
                        help="Import one upstream at a time for safer review")
    args = parser.parse_args(argv)
    for cmd in commands(args.source):
        print(" ".join(cmd), flush=True)
    if not args.apply:
        print("DRY RUN: no files changed. Add --apply after reviewing sources and licenses.")
        return 0
    verify_checkout(args.source)
    for cmd in commands(args.source):
        subprocess.run(cmd, cwd=ROOT, check=True)
    print("Local subtree imports complete. Run tests and review diffs before pushing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
