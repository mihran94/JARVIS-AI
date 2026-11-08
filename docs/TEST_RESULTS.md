# Verification report — v0.2.0, 8 November 2026

Environment: Linux; Python 3.12.14; PySide6 6.8.3; httpx 0.28.1; keyring 25.6.0; pytest 8.3.5.

Command: QT_QPA_PLATFORM=offscreen python -m pytest -q

Actual final output:

    .........................................................                [100%]
    57 passed in 0.56s

python -m compileall -q . completed with exit code 0.

The 39-test v0.1 regression suite still passes (updated to navigate nine pages). Eighteen additional cases cover: queue persistence, fresh approvals after restart, duplicate-run rejection, atomic concurrent claims, cancellation while reviewing, emergency stop/resume, two interrupted job states, tampered app allowlist, launch failure without retry, v0.1 backup/migration, rejection of newer schemas, empty-choice usage chunks, missing/invalid counts, persistent archive/usage records, reopening chat, UI provider check, and UI queue cancellation.

Provider tests use synthetic HTTP responses with httpx.MockTransport; the Qt worker, widgets and SQLite paths are real. The provider-check test verifies no conversation messages are created and usage/health are recorded.

A real offscreen Qt screenshot of the task queue was captured and visually inspected (docs/desktop-preview.png). Qt emitted its benign offscreen propagateSizeHints warning.

NOT EXECUTED: Windows OS integration, Windows Credential Manager, real Notepad/Calculator launches, live provider requests, packaged EXE, or the supplied GitHub CI workflow. No API keys were configured or created. No claim of Windows certification or production security audit is made.

Windows acceptance steps are in WINDOWS_ACCEPTANCE.md. Historical v0.1 results are in TEST_RESULTS_v0.1.md.
