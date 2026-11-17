# JARVIS OMEGA — handoff

**Cycle:** Windows install and verification, the Personal Codex Assistant review, and the port of the Mark LVI source that was supplied.
**Branch:** `feature/phase1-omega-verification-20261117`
**Baseline (starting commit):** `7a1ec8d` — *Merge JARVIS Omega desktop presentation (#29)*, the `main` at the start of the cycle.
**Current `main`:** `8450f51` — *Merge pull request #30 from mihran94/feature/automatic-source-updates*. PR #30 was merged into `main` **by the owner, not by this cycle**, and the branch now contains it. This branch merges that `main` in; see section 1.1.
**Status:** Ready for the owner's review. `main` is not touched by this cycle, nothing is merged, no release is published.

---

## 1. Where this branch starts

`main` did not have the three accepted sections, so the branch applies them in
order, exactly as the Personal Codex Assistant review says:

| Order | Patch | State |
|---|---|---|
| 1 | `develop/video-editing-studio/changes.patch` | applied unchanged |
| 2 | `develop/chat-first/changes.patch` | applied in its Omega port (`scripts/port_chat_first_omega.py`) |
| 3 | `develop/personal-codex-assistant/changes.patch` | the submission under review |

The worktree used for this cycle is **`/workspace/work/wt-omega-verify`**.

Baseline of that tree: **657 passed, 3 skipped** — the same number the section
reviews recorded.

### 1.1 `main` moved during the cycle

While this cycle was running, PR #30 was merged into `main` by the owner and a
further commit (*Make reviewed JARVIS improvements launchable and authorize
tests separately*) landed on that branch. This branch therefore **merges the
new `main`** (`8450f51`) instead of staying on the old `7a1ec8d`.

The merge touched `desktop/app.py` in three places. Each one was resolved by
keeping **both** sides:

| Place | Phase 1 side | PR #30 side | Resolution |
|---|---|---|---|
| Method block | the coding task, the task card and the approval gate | the review screen, the prepared changes, the maintenance timer | both, in full |
| `stop()` | interrupts the test worker, the coding worker and the chat launch | cancels the source check and interrupts the improvement worker | both |
| `closeEvent()` | waits for the coding and test workers | hides to the tray and waits for the source and improvement workers | both: the tray check first, then every worker |

The merged `Window` class has 192 methods and no duplicated one.

---

## 2. What was fixed in this cycle

### 2.1 The Emergency Stop gap: closing the window left the task running

**What was wrong.** `closeEvent` only waited for the chat worker. A coding
task runs the **Codex CLI** and the **test command** in their own processes.
Closing the window during a task closed the window immediately and left both
processes running behind the owner's back — the exact thing the Phase 1
review says it fixed ("the TEST PROCESS is terminated — not left running
while the owner believes it stopped"). The Emergency Stop button reached
them; closing the window did not.

**The fix.**

* `desktop/app.py` — `closeEvent` now waits for `self.coding_worker` and
  `self.test_worker` as well, calls `stop()` first, and shows
  *Waiting for the current task to exit safely…*.
* `on_coding_finished` and `on_test_finished` close the window once the last
  worker is gone, so the window never disappears while a process is still
  running.

### 2.2 The approval gap: the AI Studio project link opened a browser

**What was wrong.** `open_website_project` opened the owner's browser and
stored the URL with `self.policy.ticket()` only. A ticket checks that the
Emergency Stop is not active; it is not an approval. The handoff lists
*browser* under permission-gated PC automation, and every other file or
browser action in the application goes through `Gateway.run`.

**The fix.** `open_website_project` now goes through
`self.gateway.run(Action('open_website_project', url), self.confirm, operation)`.
The approval names the exact address that is about to be opened, the
one-use token applies, and the Emergency Stop is checked inside the gateway.
The URL is validated *before* the approval is asked for, so a bad address
never reaches a dialog.

### 2.3 What was deliberately NOT changed

* **The Video Studio one-click handoff.** `open_video_tool` opens Google Flow
  or Higgsfield in the browser and copies the shot prompt, without a dialog.
  That is what the accepted Video Studio section built and its test
  asserts, so it is preserved. The **chat** command for the same tool still
  asks for approval, because a chat command can be anything the owner typed.
  This inconsistency is noted in section 6 for the owner to decide.
* **The CapCut, DaVinci Resolve and After Effects launch commands.**
  `automation/windows.py` keeps `CapCut.exe`, `Resolve.exe` and
  `AfterFX.exe`, and
  `test_the_software_launch_commands_still_work[CapCut|DaVinci Resolve|After Effects]`
  passes.

---

## 2.4 What came from the Mark LVI source

The owner supplied `Mark-LVII-main.zip`. It is a full alternative assistant
(96 Python files, about 52,000 lines, PyQt6, its own asyncio voice session).
It was **inspected**, not copied: the whole archive is a second application
with a second daemon, a second GUI and its own config file, and the handoff
says to integrate the useful modules as optional modules, not as a second
background daemon.

Two things were worth porting, and both fill a real gap in JARVIS.

### 2.4.1 `core/protection.py` — the files a coding agent may not touch

Ported from the archive's `core/code_checks.py`. Its own comment explains
why:

> *"Learned from a real job: asked to add a plugin, the model also 'edited'
> config/api_keys.json to switch the plugin on — rewrote the whole file from
> memory, dropped the API keys and half the settings. Worse, that file had
> been read into the project context, so the keys in it went to the model
> with every request."*

That is exactly what JARVIS's own coding agent could do: `project_context()`
read every `.json` in the project into the request, so a `config/api_keys.json`
would have gone to MiniMax with the code.

The rule now lives in one place:

* a file that looks like a secret by name (`.env`, `*.pem`, `*secret*.json`,
  `*token*.yaml`, …) is off limits;
* a file the project's own `.gitignore` keeps out is off limits.

It is applied in four places:

| Where | What it does |
|---|---|
| `core/coding_agent.py` → `project_context()` | those files never enter the request, so a key never travels to a provider |
| `core/coding_agent.py` → `apply_files()` | a proposed change may not write one — the provider proposes, JARVIS decides |
| `developer_studio/codex_task.py` → `build_prompt()` | the Codex prompt names the files that are off limits |
| `developer_studio/codex_task.py` → `_collect_diff()` | a change to one is put back from `HEAD` and left out of the diff, so the review screen never shows a key |

`dropped_data()` came with it: an edit that silently drops keys from a
settings file is reported instead of being applied quietly.

Source code called `api_keys.py` is still editable — only DATA files with
those names are treated as secrets.

### 2.4.2 GPU load and CPU temperature

Ported from the archive's `actions/system_monitor.py`. JARVIS's system
readings had CPU, RAM and disk; they had no GPU load and no temperature.

The readings come from NVML through `ctypes` and from `psutil`, so no
subprocess is started. A value that cannot be read stays **Unavailable** —
the same honesty the rest of the HUD keeps.

### 2.4.3 What was NOT taken

The archive also contains a second GUI, its own asyncio voice session, its
own task engine, its own plugin loader, a Windows Startup VBS, a wake-word
listener and a second microphone listener. None of it was copied: it would
be a second daemon next to JARVIS, it would fight JARVIS for the microphone
and the TTS, and the handoff forbids exactly that. The archive stays where
it was, outside the repository.

Two things the handoff asked for were found **already done** in JARVIS, so
nothing was ported for them: the news briefing already reads real regional
RSS feeds with parsing tests (`news/briefing.py`), and the permission model
is already the approval gateway.

---

## 3. Changed files in this cycle

| File | Change |
|---|---|
| `desktop/app.py` | `closeEvent` waits for the coding and test workers; `on_coding_finished` and `on_test_finished` close the window when the last worker is gone; `open_website_project` goes through the approval gateway; `open_video_tool` documented as the preserved one-click handoff. |
| `tests/test_phase1_gap_fixes.py` | **new** — 6 tests for the gaps above. |
| `core/protection.py` | **new** — the secret and `.gitignore` protection, ported from the Mark LVI source. |
| `core/coding_agent.py` | The project context leaves protected files out; a proposed change may not write one. |
| `developer_studio/codex_task.py` | The prompt names the off-limits files; a change to one is put back and left out of the diff. |
| `desktop/system_metrics.py` | The GPU load and the CPU temperature, read with no subprocess. |
| `tests/test_mark_lvi_ports.py` | **new** — 17 tests for the ports. |
| `docs/SOURCE_INTEGRITY.sha256` | regenerated for the tree. |
| `HANDOFF.md` | **new** — this file. |

The reviewable diff against the starting commit is
`git diff 7a1ec8d..HEAD`. Because the branch now also contains the merged
`main`, `git diff origin/main..HEAD` shows only what this cycle added.

---

## 4. Test commands and results

```
$ cd /workspace/work/wt-omega-verify
$ QT_QPA_PLATFORM=offscreen python -m pytest -q
726 passed, 3 skipped, 12 subtests passed in 220.06s
```

| Run | Result |
|---|---|
| Baseline of the applied tree, before the fixes | 657 passed, 3 skipped |
| After the fixes, before `main` moved | 663 passed, 3 skipped, 0 failed (+6 new tests) |
| After merging the new `main` (PR #30 and its follow-up) | 709 passed, 3 skipped, 0 failed |
| After the Mark LVI ports | **726 passed, 3 skipped, 0 failed** (+17 new tests) |

Targeted runs used as evidence:

```
$ python -m pytest -v tests/test_omega.py tests/test_phase1_omega.py tests/test_source_manifest.py
24 passed
$ python -m pytest -q tests/test_bridge_listener.py tests/test_bridge_pairing.py \
      tests/test_bridge_protocol.py tests/test_persistent_pairing.py tests/test_bridge_chat.py
61 passed
$ python -m pytest -q tests/test_phase1_gap_fixes.py
6 passed
$ python scripts/source_manifest.py --check
docs/SOURCE_INTEGRITY.sha256 matches the tree.
```

The six new tests, and what each one holds in place:

| Test | Finding it holds |
|---|---|
| `test_the_video_tool_handoff_is_preserved` | The accepted one-click handoff still opens the tool. |
| `test_the_chat_command_for_the_same_tool_still_asks` | The chat path still asks for approval. |
| `test_the_website_project_link_needs_the_approval` | The AI Studio link needs an approval that names the URL. |
| `test_closing_the_window_during_a_task_stops_the_workers` | Closing the window waits and stops the task. |
| `test_the_window_closes_when_the_last_worker_is_gone` | The window goes away only when nothing is running. |
| `test_the_test_command_runs_off_the_interface_thread` | The test command runs on a worker thread. |

---

## 5. Verification matrix

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Startup smoke test (Omega modes, dock, approval, stop) | **PASS** | `tests/test_omega.py` — 6 passed, including `test_modes_return_to_same_window_and_keep_saved_preferences`, `test_live_activity_approval_and_emergency_stop` |
| 2 | Full Python regression suite | **PASS** | 726 passed, 3 skipped, 0 failed |
| 3 | Source integrity manifest | **PASS** | `scripts/source_manifest.py --check` → *matches the tree*; `tests/test_source_manifest.py` — 2 passed |
| 4 | CapCut / DaVinci Resolve / After Effects launch commands preserved | **PASS** | `test_the_software_launch_commands_still_work[CapCut|DaVinci Resolve|After Effects]` — 3 passed |
| 5 | Approval gate on the task card | **PASS** | `test_every_task_card_action_goes_through_the_approval` (phase 1 regressions) |
| 6 | Emergency Stop cancels the task and Resume does not restart it | **PASS** | `test_stop_cancels_the_task_and_resume_does_not_restart_it` |
| 7 | Tests run off the interface thread | **PASS** | `test_the_test_command_runs_off_the_interface_thread` (new) + the Phase 1 regression test |
| 8 | Android pairing protocol, revocation and reconnection (server side) | **PASS** | 61 passed across the five bridge test modules |
| 8b | A key never reaches a provider, and never the review screen | **PASS** | `tests/test_mark_lvi_ports.py` — 17 passed |
| 9 | Windows release candidate build | **BLOCKED** | No Windows in this environment: `wine`, `makensis`, `iscc` all absent; the build is a Windows-only step. **No artifact and no checksum are given, because no build succeeded.** |
| 10 | Clean install → launch → restart → uninstall on Windows 10/11 | **BLOCKED** | Needs a real Windows PC and the installer from check 9. |
| 11 | Microphone permission prompt | **BLOCKED** | No microphone and no audio stack here. The permission logic is covered by `tests/test_native_speech_contract.py` and the Omega floating-mic test, which report PASS for the *logic*, not the hardware. |
| 12 | Tamil voice input quality | **BLOCKED** | No speech engine and no microphone. No speech-quality claim is made. |
| 13 | Android pairing and reconnection **on the phone** | **BLOCKED** | No Android device and no build: `java`, `gradle`, `adb` and `ANDROID_HOME` are all absent. The phone-side protocol is covered by the server-side tests in check 8. |
| 14 | Emergency Stop on real hardware | **BLOCKED** | Needs the Windows PC from check 10. The behaviour itself is verified in check 6. |

**What the owner has to do on a real machine** is listed in section 7.

---

## 6. Known issues and blockers

1. **The Video Studio button and the chat command behave differently.**
   The button opens Google Flow or Higgsfield in one click; the chat command
   asks first. Both were accepted work. The owner may want them the same.
2. **The offscreen Qt teardown segfault.** A full suite run ends with a
   segmentation fault at interpreter shutdown, *after* the results are
   printed. It happens on the base commit too, so it is pre-existing and not
   caused by this work.
3. **No artifact and no checksum.** The build did not run, so none is given.
4. **Phase 1 is still not merged into `main`.** This branch carries the
   sections as patches, not as merged code.
5. **PR #30** (`feature/automatic-source-updates`) is a separate draft with
   the prepared-source-update work. It is not merged either.

---

## 7. What the owner has to check

On a Windows 10/11 PC, with the release candidate built there:

1. Install, launch, restart and uninstall; confirm the launcher and the
   uninstaller behave.
2. Give the microphone permission once; confirm the prompt appears and that
   the floating mic reports its state.
3. Speak Tamil into the microphone; confirm the transcript reaches the chat.
4. Pair the Android phone over the private HTTPS bridge; approve one job
   from the phone; revoke it; confirm the phone is refused afterwards; then
   restart the app and confirm the phone reconnects.
5. Press **Emergency Stop** during a coding task and confirm the Codex CLI
   and the test process really end, and that closing the window during a
   task waits instead of leaving the process running.
6. Give a project that has a `.env` or a `config/api_keys.json` to the
   coding assistant, and confirm the key is neither sent to the provider nor
   shown in the diff.
7. Check the HUD's GPU and CPU temperature lines on the real machine. They
   read **Unavailable** here because this sandbox has no GPU and no sensor.
8. Start the Video Studio handoff and confirm the browser opens with the
   prompt on the clipboard.

On an Android phone, with the APK built there:

9. Install the debug APK, pair it, and repeat check 4.

---

## 8. The exact next step

1. The owner reviews this branch and the diff `7a1ec8d..HEAD`.
2. The owner decides on the Video Studio button question in section 6, item 1.
3. The owner runs checks 1–6 on a real Windows PC and 7 on a real phone, and
   the results are added to section 5.
4. **Only after that approval** is the branch merged into `main`, and only
   then is the release candidate built and signed.

### 8.1 What this cycle did *not* do

* It did not merge PR #30 — the owner did that. This cycle only merged the
  resulting `main` into the feature branch.
* It did not merge anything into `main`.
* It did not build an installer or an APK, so there is no artifact and no
  checksum.
* It did not claim integration of any archive that was not inspected and
  tested: the `JARVIS-AI-visionOS.zip`, the Supreme OS source, MiniMax
  v0.2.0 and the MARK LVI source were **not** supplied to this environment,
  so nothing about them is claimed.
* It did not touch the provider registry, the credential store or the
  permission model.

Nothing is merged before the owner says so.
