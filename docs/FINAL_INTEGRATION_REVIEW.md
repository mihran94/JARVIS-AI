# JARVIS PRIME — final integration review and release gates

**Integration branch:** `integration/jarvis-prime-final-review-20261119`  
**Source baseline:** `feature/p13-workflow-20261119` at `0d4da4fd256729ac6f3f63b98b19efc6d789cea4`  
**Main at preparation:** `c450fe8ee89604a9ff1643c31ec6e5bfee5516d4`

This is a **review candidate**, not a final release and not a Git
merge of all 14 separate historical branch commit graphs.

## What is integrated

The latest P13 branch already carries cumulative code for context, routing
costs, PDF/DOCX reading, task planning, approved project inspection, Tamil
local commands, PC controls, document search, safe web research, phone
certificate pinning, and a global hotkey.

A source-tree comparison across the 13 earlier phase-branch tips identified
three unique P0 additions absent from P13:

- `patches/windows-app-icon.patch`
- `tools/make_icon.py`
- `tests/test_app_icon.py`

These three files are brought into this integration candidate unchanged
from P0, and `scripts/source_manifest.py` now includes both exclusions:
the P0-generated Windows icon and the Android-specific generated paths
introduced in later phases. Tests for icon and CI patch applicability accept
either the original untouched workflows or fully applied patches; partial
workflow changes must fail.

**Important:** Unlike a local `scripts/merge_stack.py` run, this branch does
not claim conflict-by-conflict semantic reconciliation of every historical
branch. The previous P13 desktop CI pass is not validation of this new tree.

## Evidence already available (prior branch only)

On `0d4da4fd`, automated desktop jobs passed:

- Ubuntu: 1,060 passed, 9 skipped
- Windows: 1,056 passed, 13 skipped

GitHub desktop CI:
https://github.com/mihran94/JARVIS-AI/actions/runs/44420140351

The reported **1,060 passed, 5 skipped** for MiniMax's local merged tree
is a separate reported result and is not independently verified against
this GitHub branch.

## Required before merging this PR to main

1. Run `python scripts/source_manifest.py --check` against this exact tree.
2. Run `python -m pytest -q` on Windows and Ubuntu; retain both job links.
3. Independently validate the three workflow patches in
   `docs/OWNER_ACCEPTANCE.md` section 0. They have **not** been applied by
   the GitHub App (which lacks permission to write `.github/workflows/`).
   The owner can apply them on a trusted clone and push their committed
   changes. Do not claim Android/installer CI covers these changes until
   that has been performed.
4. Ensure no features were overwritten by conflict resolution, especially
   the P0 layout and security fixes, Android certificate trust, and the
   single JARVIS PRIME UI.
5. Run a full debug Android build with its security tests. Provide a real APK
   artifact and SHA-256.
6. Build the actual unsigned Windows installer and publish its checksums.
7. Perform the manual PC/phone acceptance checks listed in
   `docs/OWNER_ACCEPTANCE.md`, including microphones, DPI scaling, remote
   pairing/revocation and Emergency Stop.
8. Keep credentials, conversation history, projects and backups intact.
9. Only merge to `main` after required validation; do not publish a final
   signed release without signing credentials and tested hardware.

## Status

**Integration review prepared.** Source contents and previously passing
tests are inspectable, but all release gates above are still open until
the exact integration commit is verified. No GitHub Actions workflows
were manually dispatched.
