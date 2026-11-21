# Windows acceptance checklist

Run on non-administrator Windows 10 and Windows 11 with Python 3.12 x64.

1. Extract, run setup.cmd, launch START_JARVIS.cmd. Confirm the JARVIS AI conversation, its task panels and the separate diagnostics window render at 125% and 150% scale. Confirm a second assistant window does not appear at startup.
2. Start a second instance; confirm it is rejected without corrupting history.
3. Save a provider key. Restart the app. Verify it remains available; inspect Windows Credential Manager for JARVIS-AI-0.1. Confirm no API key is present in config/database/source. Remove the key and confirm it no longer works.
4. For each authorized provider, configure a model available to your account, Send a small message, verify streamed answer and task status. Repeat with an invalid key and confirm sanitized error, then restore the valid key.
5. During streaming click STOP. Confirm no further text is accepted, task ends cancelled, new actions are blocked. Resume and confirm old output does not reappear.
6. Decline Notepad launch; confirm no new app. Approve it; confirm app window opens. Repeat Calculator. Missing apps must report failure, not success.
7. Save a workspace Python file twice; check current file and prior-content backup. Try ../escape.py, C:/outside.py and a Windows junction outside the workspace; all must be blocked.
8. Close with unsaved edits; decline discard and verify editor remains. Accept discard and verify exit. Close during streaming and verify safe exit after cancellation.
9. Restart after a forced test crash with an in-progress task; confirm interrupted status.
10. Run scripts/test.cmd. Windows symlink tests may skip without developer mode; test junction confinement manually.
11. Build with installers/build.cmd and repeat checks using the EXE on a clean test machine.

Record OS build, Python/dependency versions, provider/model (never key), exact pass/fail and any crash. Do not call the build a validated release until these checks pass.


## Additional v0.2 acceptance
12. Upgrade an existing v0.1 profile and verify the pre-upgrade database backup, saved chats and stored keys.
13. Queue two launch jobs. Restart: queued jobs should remain. Approve one once; repeat Run must not launch it again. Decline the other.
14. Queue more jobs and click STOP, then Resume. They must remain cancelled. Force-close during a reviewing/running test job; it must be interrupted on restart with no replay.
15. Test each saved provider connection. Confirm no chat history is sent; verify last check status and usage table. Missing usage must say Unknown.
16. Reopen an older saved conversation and continue it. Delete it with confirmation and verify it disappears from the archive list.
17. Check Ctrl+Alt+J while JARVIS has focus, plus the red stop button.

## Installer lifecycle and HUD

- Run the installer on a disposable Windows account, then open the installed assistant. The automation entry point is `installers/Test-WindowsInstaller.ps1`. It checks installation, startup, packaged speech imports, uninstallation and retention of the temporary profile.
- Confirm the JARVIS AI title and the provider and model line. Try Emergency stop and Resume in the same window. Switch to Island mode and return to the main window.
- Close and reopen the app. Confirm the current conversation and selected theme return. For the legacy default theme, confirm its existing palette appears as Quantum Dark.
- Configure Photoshop in Settings and approve an Open Photoshop request in chat. Confirm the app launches. Record this as launch evidence only.

## Recovery

- Before updating, exit JARVIS and back up the per-user data folder at `%LOCALAPPDATA%\JarvisAI` to a protected location. Windows Credential Manager credentials are separate from the profile copy.
- To restore data, exit JARVIS, move the current profile aside and restore the backed-up folder. Retain both copies until chat history, settings and task history are verified. The existing profile database is not encrypted by this procedure.
- Use the rollback instructions in [UPDATES.md](UPDATES.md) for source-managed installations. Test installer upgrade and rollback in a disposable profile before using either with production data.
