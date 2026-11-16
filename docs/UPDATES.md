# JARVIS source updates and rollback

Use the Windows Python source installation launched through `START_JARVIS.cmd`. Keep the original installation folder, including its virtual environment and startup scripts.

## Enable automatic source updates

1. Open **Settings & Safety → Updates & rollback**.
2. Turn on **Automatically stage source updates from GitHub main** and approve the setting. JARVIS checks on enable and once a day while open. Use **Check and stage source update now** to check immediately.
3. When JARVIS reports that a commit is staged, start it again from the original `START_JARVIS.cmd` at your convenience.

JARVIS checks `mihran94/JARVIS-AI` on GitHub over HTTPS, downloads the exact commit ZIP and checks every source file against that commit's Git tree. This uses public GitHub endpoints and sends no API keys, prompts or chat history. Turning the setting off cancels an in-progress download or staging operation. Use **Select previous code version (rollback)** if an update was already staged.

An existing source installation can get this feature through one reviewed ZIP update if its original pinned dependencies and database code are compatible. The source-updater setting is unavailable in the frozen Windows EXE.

## Apply a reviewed ZIP manually

1. Download a source ZIP from your trusted repository and review its commit.
2. Select **Settings & Safety → Updates & rollback → Select GitHub ZIP**.
3. Review the file list and archive SHA-256, then select **Approve selected update for next startup**. The ZIP is re-read and its digest is checked after approval.
4. Close JARVIS and restart using the original installation's `START_JARVIS.cmd`.

Both paths back up the history database locally and stage the source in a separate directory. An atomic state file selects the code for the next startup. The bootstrap, virtual environment, credentials and data stay in their existing locations. A change to pinned dependencies or `core/store.py` requires a separate source installation. Changes to the bootstrap require a new installation as well. Keep SQLite backups private.

## Rollback and recovery

Select **Updates & rollback → Select previous code version (rollback)** and restart. If the UI fails to open, run `ROLLBACK_JARVIS.cmd` in the original source folder and type `YES`. Rollback selects retained code and leaves user data in place. The automatic checker remembers the last staged GitHub commit across rollback and waits for a different commit.

For damaged update state, run `.venv\Scripts\python.exe main.py` from the original folder. Retain `.updates/releases` to keep previous versions.
