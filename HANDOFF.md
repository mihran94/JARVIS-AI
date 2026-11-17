# JARVIS OMEGA — handoff

**Cycle:** Windows install and verification, and the Personal Codex Assistant review.
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

## 3. Changed files in this cycle

| File | Change |
|---|---|
| `desktop/app.py` | `closeEvent` waits for the coding and test workers; `on_coding_finished` and `on_test_finished` close the window when the last worker is gone; `open_website_project` goes through the approval gateway; `open_video_tool` documented as the preserved one-click handoff. |
| `tests/test_phase1_gap_fixes.py` | **new** — 6 tests for the gaps above. |
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
709 passed, 3 skipped, 12 subtests passed in 220.68s
```

| Run | Result |
|---|---|
| Baseline of the applied tree, before the fixes | 657 passed, 3 skipped |
| After the fixes, before `main` moved | 663 passed, 3 skipped, 0 failed (+6 new tests) |
| After merging the new `main` (PR #30 and its follow-up) | **709 passed, 3 skipped, 0 failed** |

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
| 2 | Full Python regression suite | **PASS** | 709 passed, 3 skipped, 0 failed |
| 3 | Source integrity manifest | **PASS** | `scripts/source_manifest.py --check` → *matches the tree*; `tests/test_source_manifest.py` — 2 passed |
| 4 | CapCut / DaVinci Resolve / After Effects launch commands preserved | **PASS** | `test_the_software_launch_commands_still_work[CapCut|DaVinci Resolve|After Effects]` — 3 passed |
| 5 | Approval gate on the task card | **PASS** | `test_every_task_card_action_goes_through_the_approval` (phase 1 regressions) |
| 6 | Emergency Stop cancels the task and Resume does not restart it | **PASS** | `test_stop_cancels_the_task_and_resume_does_not_restart_it` |
| 7 | Tests run off the interface thread | **PASS** | `test_the_test_command_runs_off_the_interface_thread` (new) + the Phase 1 regression test |
| 8 | Android pairing protocol, revocation and reconnection (server side) | **PASS** | 61 passed across the five bridge test modules |
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
6. Start the Video Studio handoff and confirm the browser opens with the
   prompt on the clipboard.

On an Android phone, with the APK built there:

7. Install the debug APK, pair it, and repeat check 4.

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
