# Windows acceptance checklist

Run on non-administrator Windows 10 and Windows 11 with Python 3.12 x64.

1. Extract, run setup.cmd, launch START_JARVIS.cmd. Confirm the JARVIS AI conversation, its task panels and the separate diagnostics window render at 125% and 150% scale. Confirm a second assistant window does not appear at startup.
2. Start a second instance; confirm it is rejected without corrupting history.
3. Save a provider key. Restart the app. Verify it remains available; inspect Windows Credential Manager for JARVIS-AI-0.1. Confirm no API key is present in config/database/source. Remove the key and confirm it no longer works.
4. For each authorized provider, configure a model available to your account, Send a small message, verify streamed answer and task status. Repeat with an invalid key and confirm sanitized error, then restore the valid key.
5. During streaming click STOP. Confirm no further text is accepted, task ends cancelled, new actions are blocked. Resume and confirm old output does not reappear.
6. From the chat, decline a Notepad launch and confirm no new window. Approve it and inspect Activity. The entry should show `Verified` only when the new foreground window belongs to the dispatched process. Repeat with Calculator. Windows can hand off to another process or reuse an open window. In those cases expect `Unverified`. Type `/cancel` during a pending check and confirm that it stops the check without closing an already opened app.
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
- Open Activity during an approved task. Check the current state, recorded outcome, and task history at 125% and 150% scaling. Check the Revision label against the release manifest.
- Close and reopen the app. Confirm the current conversation and selected theme return. For the legacy default theme, confirm its existing palette appears as Quantum Dark.
- Configure Photoshop in Settings and approve an Open Photoshop request in chat. Confirm the app launches. Record this as launch evidence only.

## Recovery

- Before updating, exit JARVIS and back up the per-user data folder at `%LOCALAPPDATA%\JarvisAI` to a protected location. Windows Credential Manager credentials are separate from the profile copy.
- To restore data, exit JARVIS, move the current profile aside and restore the backed-up folder. Retain both copies until chat history, settings and task history are verified. The existing profile database is not encrypted by this procedure.
- Use the rollback instructions in [UPDATES.md](UPDATES.md) for source-managed installations. Test installer upgrade and rollback in a disposable profile before using either with production data.

## Local audio and wake phrase

- Open **Settings & Safety → Audio devices and testing**. Check the detected input and output, change the Windows default audio device, then use **Refresh**.
- Grant microphone permission in **Voice**, select **Test microphone** and speak. The level should respond for five seconds and stop. Select **Test speaker** and confirm you actually hear the tone. Test missing devices and **Stop test**.
- Under **Voice**, enable **Keep listening for Hey Jarvis**, minimize the window, and say the configured wake phrase. Check that Chat is restored and the M pulses when reduced motion is off. Confirm Emergency Stop silences the test and disables listening.

## Optional Azure neural voice

1. In **Settings and safety → AI providers → Azure Speech**, save the region and Speech resource key. The key is kept in Windows Credential Manager and the region is saved in JARVIS settings.
2. Enable **Allow JARVIS to send spoken text to Microsoft Azure** and approve the dialog. Revoking this permission cancels queued speech and requests cancellation of in-flight cloud speech. A request Azure already received may still be billed.
3. Use **Test Tamil Voice**, **Test English Voice** and **Test French Voice**. Confirm the complete sample is audible on the Windows default output. Verify the voice and session character count in settings. The count is an estimate based on successful synthesis and is not an Azure billing total.
4. Enable **Read replies aloud** and try Tamil script, English, French and Tanglish. Recognition is local and based on script, vocabulary and the existing language preference. Common Romanized Tamil words are converted to Tamil script. Unrecognized Romanized words keep their spelling and may sound unnatural.
5. Test mute and Emergency Stop during playback. Test a wrong key or unavailable network. Ordinary read-aloud should try the installed Windows voice after a cloud synthesis failure. A failed cloud voice sample should report the error.
6. For opt-in live acceptance from source on the target Windows machine, set PowerShell variables `$env:JARVIS_AZURE_LIVE_AUDIO = '1'` and `$env:JARVIS_AZURE_REGION` to the resource region, then run `python -m pytest -q tests/test_azure_tts.py -k live_windows`. This uses the saved key and sends only the three fixed samples. Listen to each sample and record what you hear. The automated assertion verifies playback dispatch.

## Suggestion Mode

- Configure a chat AI. In JARVIS Chat, turn on **Suggestion Mode** and send `Open Notepad`. Confirm a plan appears in the chat, with no task approval card or new Notepad window. Try a Tamil or Tanglish goal and confirm the reply follows the language of the request.
- Try an actionable voice request with Suggestion Mode on. With ordinary dictation, confirm it appears in the composer for review. If local hands-free chat is enabled, confirm the reply comes from Ollama and no task workflow is opened.
- Turn off Suggestion Mode. Send `/suggest Create a promotional Reel`, then send `Open Notepad`. Confirm the first message returns advice and the second returns to the normal app approval flow.

- Send `/suggest Open Notepad and type: Hello`. Confirm the exact text is shown locally. Select **Review suggested steps**, then **Approve**. Confirm the text was entered in the verified Notepad window and no file was saved. Repeat with **Decline** and confirm no text was entered.


### Tamil and Tanglish voice review

- With a compatible speech recognizer and microphone permission enabled, say “Calculator open pannu” or “Notepad open panni ezhuthu நாளைக்கு promo video” using chat dictation. Repeat after “Hey Jarvis” with local hands-free enabled.
- Check that the recognized command appears in the editable composer. Correct any recognition errors before sending. Sending should show a task preview, with no launch or typing until you choose **Review suggested steps** and **Approve**. Repeat with **Decline**.
- Repeat while an unsent draft is in the composer. Confirm the current draft is preserved and read the status prompt before repeating the command.
