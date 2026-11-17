# JARVIS source updates, prepared changes and rollback

Use the Windows Python source installation launched through `START_JARVIS.cmd`. Keep the original installation folder, including its virtual environment and startup scripts.

## The rule

A source update is **prepared**, **reviewed** and only then **approved**. Nothing about a prepared revision changes the code that is running. The version that runs changes when you approve one exact revision, and it changes at the next start.

## Prepare a revision for review

1. Open **Settings & Safety → Updates & rollback**.
2. Turn on **Automatically stage source updates from GitHub main** and approve the setting. JARVIS checks on enable and once a day while it is open. Use **Check and prepare a revision for review** to check immediately.
3. The check downloads the exact commit ZIP, verifies every source file against that commit's Git tree, runs the tests in the prepared copy and writes down the revision, the changed files and the test result. **The version that is running is not touched.**
4. Open **Settings & Safety → Review prepared changes**. You see the revision, the files it changes, the diff and the test result, with **Approve this exact revision** and **Reject**.
5. Approve. The approved revision is selected for the next start. Close JARVIS and start it again from the original `START_JARVIS.cmd`.

JARVIS checks `mihran94/JARVIS-AI` on GitHub over HTTPS. This uses public GitHub endpoints and sends no API keys, prompts or chat history. Turning the setting off cancels an in-progress check.

**The approval is bound to that revision.** If the prepared files change after you reviewed them, the approval is refused and the revision has to be reviewed again. A revision whose tests failed cannot be applied at all: the button stays disabled and the failure is shown.

## Prepare an improvement to JARVIS itself

JARVIS can prepare a change to its own source, in an isolated Git worktree under the local `development/` folder. The running installation is never the place where the change is made.

1. Open **Coding Assistant**, describe the improvement, and choose **Prepare this improvement**.
2. The coding provider makes the change inside the worktree and the tests are run there.
3. The diff, the test results and the exact revision are saved. Open **Review prepared changes** to read them and to approve or reject.

A change whose tests failed cannot be applied. A change that is edited after the review cannot be applied either: the approval has to be given again.

If the coding provider stops — a rate limit, an exhausted quota, a dropped connection — the task is saved and can be resumed. Using the other coding provider instead is an action you approve.

## Apply a reviewed ZIP manually

1. Download a source ZIP from your trusted repository and review its commit.
2. Select **Settings & Safety → Updates & rollback → Select GitHub ZIP**.
3. Review the file list and archive SHA-256, then select **Approve selected update for next startup**. The ZIP is re-read and its digest is checked after approval.
4. Close JARVIS and restart using the original installation's `START_JARVIS.cmd`.

Both paths back up the history database locally and stage the source in a separate directory. An atomic state file selects the code for the next startup. The bootstrap, virtual environment, credentials and data stay in their existing locations. A change to pinned dependencies or `core/store.py` requires a separate source installation. Changes to the bootstrap require a new installation as well. Keep SQLite backups private.

## Rollback and recovery

Select **Updates & rollback → Select previous code version (rollback)** and restart. If the UI fails to open, run `ROLLBACK_JARVIS.cmd` in the original source folder and type `YES`. Rollback selects retained code and leaves user data in place. The automatic checker remembers the last staged GitHub commit across rollback and waits for a different commit.

For damaged update state, run `.venv\Scripts\python.exe main.py` from the original folder. Retain `.updates/releases` to keep previous versions.

## Keep JARVIS running in the background

**Settings & Safety** has two settings for the always-on session:

* **Keep JARVIS in the system tray when the window is closed** — closing the window then leaves JARVIS running in the tray. The tray menu shows the window, pauses the background work and exits JARVIS.
* **Start JARVIS when Windows signs in** — Windows-only. It adds the same launcher you already use to your own Run key, and removes it again when you switch the setting off. No administrator rights are needed.

Pausing stops the automatic source check and the background preparation of changes. Nothing is closed and nothing is lost: the saved work stays in the task history and can be resumed from **Review prepared changes**.
