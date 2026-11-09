# Reviewed source updates and rollback

This updater supports the Python source installation launched through START_JARVIS.cmd. It is not a signed release feed, automatic downloader, frozen-EXE updater or autonomous self-modification system.

## Install this milestone

Download and extract the current GitHub source ZIP into a permanent folder, install Python 3.12 64-bit, run setup.cmd, then DIAGNOSE_JARVIS.cmd and START_JARVIS.cmd. Keep the extracted folder: its virtual environment, original source and bootstrap are retained for recovery. Do not overwrite this folder with future ZIPs.

## Apply a subsequent update

1. Download a source ZIP from your trusted repository while signed into GitHub. Inspect the commit/diff before trusting it.
2. Open Permissions & Roadmap → Updates & rollback → Select GitHub ZIP.
3. Review the file list and archive SHA-256. Changes in security, orchestration, core, UI and scripts are highlighted. Files absent from the new ZIP will be absent in the selected snapshot; they remain in the retained old source.
4. Approve selected update for next startup. A consistent history SQLite backup is created alongside history.sqlite3. The ZIP is re-read and its digest checked after approval.
5. Close JARVIS and restart using the ORIGINAL installation's START_JARVIS.cmd.

The new source is extracted into a separate release directory; the old source is not overwritten. An atomic state file selects the next startup. No code from the ZIP runs during staging; no dependency installation or network request occurs. The original virtual environment and bootstrap remain in use. Bootstrap/updater-launcher changes in later ZIPs do not replace that retained bootstrap; such changes require a separate installation.

Dependencies and core/store.py must exactly match the original installation (apart from surrounding whitespace in requirements.txt). Dependency or database-code changes require a separate installation, preventing this updater from claiming general schema rollback support. Your existing Credential Manager keys, chat/history and workspace remain in their existing user data location. Backups contain private history; do not upload them.

## Rollback and recovery

Use Updates & rollback → Select previous code version, then restart. If the new UI will not open, run ROLLBACK_JARVIS.cmd from the original folder and type YES. Rollback selects retained code; it does not restore or overwrite user data. For damaged update state, run `.venv\Scripts\python.exe main.py` from the original folder to open the retained base version. Do not delete .updates/releases if you need previous versions.

## Verification and boundaries

175 local tests passed, 3 Docker tests skipped. Offscreen Qt tests exercise ZIP selection and approval, consistent database backup and cancellation of update approval. Tests also cover traversal, links, reserved Windows paths, case collisions, changed archives, dependency/database incompatibility, rollback, failed state writes and bootstrap target selection. Compilation passed. Actual Windows startup/CMD behavior remains unverified.

A ZIP hash protects the reviewed bytes against later changes; it does NOT authenticate the publisher. There is no signing key or signature verification in this milestone. Only import source you independently trust. Updates may change permissions/security code only after the explicit review and approval. No background or silent updates are enabled.
