# JARVIS AI — owner acceptance procedures

**What this is.** A reproducible procedure for each acceptance item in the owner's order of work.
Each one says what to do, what a pass looks like, and what the state of that check is **today**.

**Two different things are called "a test" here, and they are not the same.**

| | Automated regression | Owner acceptance |
|---|---|---|
| Runs on | the development machine | the owner's Windows PC |
| Needs | nothing but Python and the source | Windows, a display, an audio device, provider keys, and the owner's own accounts |
| Proves | the code behaves as written | the product works on the owner's machine, with the owner's data |

Everything in the **Status** column below is the honest state today. **NOT RUN** means the
procedure has never been executed on the owner's PC, because no Windows machine, no owner account
and no provider key were available while this code was written. It does not mean the procedure is
missing — it means the *result* is unknown.

---

## Before you start

```cmd
cd path\to\JARVIS-AI-development
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
copy setup.cmd .venv\Scripts\python.exe 2>nul
```

`setup.cmd` prepares the runtime library the Qt binaries need on a fresh Windows machine.
Then:

```cmd
START_JARVIS.cmd
```

The launcher checks the runtime, starts the application and keeps a log in
`%LOCALAPPDATA%\JarvisAI`. `DIAGNOSE_JARVIS.cmd` reports what is missing without changing
anything, and `VERIFY_JARVIS.cmd` runs the local checks. `ROLLBACK_JARVIS.cmd` restores the
previous release.

**Required:** Windows 10 or 11, Python 3.12, one screen, and a provider key for at least one
provider. **Optional:** a microphone, speakers, Azure Speech (Tamil, English, French), Edge or
Chrome, After Effects / Photoshop / DaVinci Resolve / CapCut, a phone with the JARVIS BLUE app.

---

## A. Tamil Notepad save and exact file-content verification

**What it proves.** That JARVIS can type Tamil text into Notepad on this machine, and that what
landed on the disk is byte-for-byte what was asked for.

1. Open JARVIS. Put the cursor in the chat composer.
2. Turn on **Work on this** (the composer button beside *Send*).
3. Type: `தமிழில் ஒரு வரியை எழுதவும்` and press **Start the mission**.
4. Approve the Notepad action when the approval dialog appears. **Do not type in Notepad while
   the mission runs** — the check compares the foreground window before and after.
5. When the mission finishes, look at the answer in the conversation and the rail in Mission
   Control. The answer must name the text it verified, not "the text was typed".
6. Save the document in Notepad yourself (Ctrl+S) to a path you choose, then open that file.

**A pass is:** the mission's answer reports the exact string it read back from the editor, and
the saved file contains `தமிழில் ஒரு வரியை எழுதவும்` with no other characters.

**A fail is:** the answer says the text was typed without quoting what was read back, or the
saved file differs from the string that was asked for.

**Status: NOT RUN.** The Unicode keystroke path and the editor read-back are covered by the
automated suite (`tests/test_desktop_tasks.py`, `tests/test_safe_computer_control.py`), but no
Windows machine was available. **Saving the file from the editor is not implemented** — the
mission can write a text file directly (the `export_text` tool), but it cannot press Ctrl+S in
Notepad for you.

## B. Calculator to Notepad, multi-application

**What it proves.** That JARVIS can work across two applications and that the value it carried
across was the one the application actually produced.

1. Approve the Calculator launch.
2. Read the Calculator's display and check it against the value the mission reports.

**A pass is:** the value in the mission's evidence is the value on the Calculator's display.

**Status: NOT RUN, and the last step is not implemented.** There is **no Calculator adapter**:
JARVIS can launch the Calculator, but it cannot read its result, so it cannot carry that value
into Notepad. This is listed as a coding gap in `DEVELOPMENT_COVERAGE.md` §5.

## C. Developer project fix, diff and actual test/build output

**What it proves.** That a coding request produces a reviewable diff and a real test result.

1. Open the Coding Assistant page and choose the project you want worked on.
2. Ask for a change that the project's own tests can judge — for example: *fix the failing test in
   `tests/test_example.py`*.
3. Wait for the prepared changes.

**A pass is:** the review screen shows a diff that is only the files you expected, the protected
paths were not touched, and the test run below it shows the **actual** output of the project's
test command, including the pass/fail line. A failed test must be shown as failed.

**A fail is:** the diff touches a file that holds a secret, or the "test output" is a sentence
instead of the command's own output.

**Status: NOT RUN.** The review and the protection rules are covered by the automated suite
(`tests/test_code_generation.py`, `tests/test_code_repair.py`, `tests/test_mark_lvi_ports.py`).
A live project and a real Codex or MiniMax key were not available.

## D. After Effects project export and verified media

**What it proves.** That an After Effects export is really produced and really inspected.

1. Open the Video Editor page and point JARVIS at the `.aep` project.
2. Ask for a composition to render.
3. Approve the render when asked.

**A pass is:** the mission reports the output file, its size and its SHA-256, and the preview
sheet shows frames that came from that file. "Launch", "project modified", "export" and "verified
output" must be reported as four different things.

**Status: NOT RUN.** After Effects is not installed on the development machine. The timeline
handling is covered by `tests/test_after_effects_timeline.py`.

## E. Controlled browser draft, result inspection and authorized live-site follow-up

**What it proves.** That JARVIS can prepare and inspect a draft, and that it stops before
anything is published.

1. Open the browser control and have JARVIS open the page you want.
2. Ask it to fill the form and **stop before sending**.
3. Inspect the draft.

**A pass is:** the draft is visible in the browser, JARVIS describes what it actually read back
from the page, and it asks for approval before anything is sent. A login page, a CAPTCHA or a
missing control produces a clear "this needs you" message, not a guess.

**A fail is:** the message was sent without an approval, or a selector was invented.

**Status: NOT RUN.** The browser draft is verified in the mission path (`tests/test_browser_control.py`
and the PR #88 browser tests), but no live session with the owner's accounts was available.

## F. Flow or Higgsfield prompt preparation and explicit credit approval

**What it proves.** That a creative prompt can be prepared and that credits are never spent
without an explicit approval.

1. Ask for a shot prompt for a video.
2. Copy the prepared prompt into the service yourself, or let JARVIS prepare it.

**A pass is:** the prompt is prepared locally and shown to you in full. Nothing is submitted and
no credits are spent by the preparation step.

**Status: NOT RUN.** The drafting is covered by `tests/test_video_planning.py`. The credit step
itself belongs to the external service and needs the owner's account.

## G. Wake phrase, real microphone input, Notepad dispatch and Tamil speaker playback

**What it proves.** That the voice path works with the owner's own voice, in the owner's language.

1. Open **Settings → Voice / Hey Jarvis** and grant the microphone permission.
2. Press **Test English Voice**, then **Test Tamil Voice**. Each must say the test sentence out
   loud.
3. Switch the interface language to Tamil. The play button and the labels must be in Tamil.
4. Say the wake phrase, then a request that needs Notepad.

**A pass is:** the wake animation starts **when the wake word is actually recognised** and not
before, the microphone is only opened after the permission is granted, and the Tamil reply is
audible.

**A fail is:** the animation starts on a timer, or the microphone opens at startup.

**Status: NOT RUN.** There is no audio device on the development machine. The consent gate and the
wake matcher are covered by `tests/test_voice.py` and `tests/test_voice_echo_guard.py`.

## H. Isolated self-update, backup, restart health check and rollback

**What it proves.** That an update can be prepared, applied, checked and undone.

1. In **Settings → Updates and recovery**, choose **Updates & rollback**.
2. Let JARVIS prepare the update. It shows the diff before anything is applied.
3. Approve the deployment.
4. Start JARVIS again and check that it comes up and that the history is still there.

**A pass is:** the old release is still on disk, the new one starts, and the history survived the
restart.

**A fail is:** the update is applied without showing the diff, or the history did not survive.

**Status: NOT RUN.** The state machine is covered by `tests/test_source_updates.py`,
`tests/test_updates.py` and `tests/test_release_manifest.py`. `ROLLBACK_JARVIS.cmd` restores the
previous release and has not been executed on Windows.

## I. Emergency Stop, wrong-window prevention and zero unauthorised follow-up actions

**What it proves.** That the owner can stop everything, and that JARVIS cannot act on the wrong
window or keep working after a stop.

1. Start a mission that needs an approval, and approve it.
2. While it is running, press **Emergency Stop** (Ctrl+Alt+J).
3. Check that no further step ran and that no new approval appeared.

**A pass is:** the mission stops at the next step, no queued action follows it, and the
approvals that were waiting were thrown away rather than reused.

**A fail is:** a queued step runs after the stop, or an approval is reused.

**Status: NOT RUN.** The stop path is covered by `tests/test_mission_runtime.py`
(`test_an_emergency_stop_cancels_the_mission`) and by the queue and workflow tests. The
wrong-window check is covered by `tests/test_safe_computer_control.py`.

---

## Also in this order of work

| Item | Procedure | Status |
|---|---|---|
| History migration and restore | Settings → History backup and restore → *Back up now*, then *Restore from a backup file*. The archive's header is shown before it is opened. The database that was replaced is kept beside the new one | NOT RUN (the code path is covered by `tests/test_windows_backup.py` and `tests/test_history_backup_settings.py`) |
| Device switching | Open the Phone Remote page, pair the phone, and confirm the pairing is revoked when the phone is removed | NOT RUN |
| Provider fallback consent | In Settings → AI Providers, allow a backup provider, then make the first provider fail. The second provider must be used only after the consent, and the conversation must not be sent to it otherwise | NOT RUN (covered by `tests/test_provider_routing.py` and `tests/test_stream_fallback_http_integration.py`) |
| PWA offline behaviour | Open the iPhone PWA, switch the phone to airplane mode, ask for something, and bring the phone back | NOT RUN (the outbox is covered by the JavaScript suite) |
| Android expiry | Leave the Android app for 15 minutes and open it again. It must be locked and ask for the biometric again | NOT RUN (the default of 15 minutes is covered by the Kotlin tests) |
| HUD scaling at 100/125/150/200 % | Set the Windows display scale to each of the four values and open Mission Control and the main window. Nothing may be clipped and the rail must still be readable | NOT RUN |
| Windows CMD startup and shutdown | Run `START_JARVIS.cmd`, then close the window with the tray's **Exit**. The process must end and the lock file must be released | NOT RUN |
| Clean installer and uninstaller | **Not built in this coding phase.** The installer sources are in `installers/` | NOT RUN |

## Running the automated regression suite on the owner's PC

```cmd
.venv\Scripts\python.exe -m pytest -q
```

The suite is the regression record for this revision. The counts are in
`docs/TEST_RESULTS.md`; the historical counts from earlier cycles are kept there separately and
are not evidence about this revision.

## Where a failure should be reported

A failure in any of these procedures should be reported with:

1. the procedure letter (A–I) and the step number;
2. the exact text JARVIS said, copied in full;
3. the log from `%LOCALAPPDATA%\JarvisAI`;
4. what you expected and what happened instead.

Do not paste a provider key, a pairing code or a private file into a report. The redactor in
`cybersecurity/report.py` masks them in the cybersecurity report, but a message written by hand
is not redacted for you.
