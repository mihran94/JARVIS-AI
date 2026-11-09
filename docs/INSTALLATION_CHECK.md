# Offline installation diagnostics

Run DIAGNOSE_JARVIS.cmd after setup.cmd, or run `.venv\Scripts\python.exe scripts\diagnose.py` from the extracted project directory. Output is JSON on the terminal, not automatically saved. Exit code 0 means every installation check passed; 1 means at least one failed.

Checks: Windows platform, Python 3.12, 64-bit interpreter, exact pinned package versions, and dependency imports plus an in-memory SQLite query. Native imports run in an isolated child process with a 20-second timeout. Child output is suppressed to avoid exposing local paths or exception data. No API calls, credential reads, application launches, or user history access occur.

Missing environment: run setup.cmd. Missing or mismatched packages: rerun setup.cmd. Import failures: inspect the Python installation and native Qt dependencies. Extract all project files before running. Passing this check does not establish that display rendering, credential storage, network access or automation works.

Verification: 105 local tests passed; actual diagnostic passed dependency checks and correctly failed the Windows check on Linux. Native Windows execution of the CMD wrapper remains unverified.
