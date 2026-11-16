# Personal Codex Assistant — Phase 1 review

**Section slug:** `personal-codex-assistant`
**Source baseline:** `7a1ec8d` ("Merge JARVIS Omega desktop presentation (#29)") — the latest `main`, which includes JARVIS Omega.
**Changes:** `develop/personal-codex-assistant/changes.patch`
**Status:** Ready for Review (revision 3 — the Phase 1 blockers are fixed, on the Omega tree)

---

## 1. Baseline and required patches

The baseline is the current `main`, `7a1ec8d`, which includes **JARVIS Omega**
(`desktop/omega.py`, `desktop/omega_visuals.py`, `desktop/omega_geography.py`).

None of the three submitted sections has landed in `main`, so all three are
applied, in order:

```cmd
git checkout 7a1ec8d
git apply develop\video-editing-studio\changes.patch
git apply develop\chat-first\changes.patch
git apply develop\personal-codex-assistant\changes.patch
python scripts\source_manifest.py
python scripts\source_manifest.py --check
```

| Order | Patch | State |
|---|---|---|
| 1 | `develop/video-editing-studio/changes.patch` | unchanged, applies cleanly to `main` |
| 2 | `develop/chat-first/changes.patch` | **re-exported for Omega** — see below |
| 3 | `develop/personal-codex-assistant/changes.patch` | this section |

### The chat-first patch had to be re-exported

The submitted chat-first patch was written against `main` **before** JARVIS
Omega landed. Its `desktop/app.py` hunks no longer applied: Omega moved the
navigation, rewrote `confirm()`, `stop()` and `resume()`, and changed how the
window is shown.

Rather than drop the chat-first work, it was **ported onto the Omega tree** and
re-exported, so the dependency chain still resolves. Nothing was lost:

* Omega keeps all three of its modes — **Omega, Island, Stealth** — and its
  saved preferences.
* `confirm()` still brackets the approval dialog with Omega's approval state.
* `stop()` still calls `omega.on_stop()`, and `resume()` still restores Omega's
  feed and state.
* The chat-first navigation, the inline Approve/Decline row, the plugin
  switches, the chosen executables, the chat commands and `/video` are all
  present.

The port is scripted in `scripts/port_chat_first_omega.py` so it is auditable
and repeatable rather than a pile of hand-edited hunks.

## 2. The Phase 1 blockers, and how each is fixed

### Blocker 1 — every task-card action goes through the approval and the stop

`Open project`, `Run tests` and `Review diff` now all go through one gate,
`coding_action_gate`:

* a policy ticket is taken and the Emergency Stop is checked;
* an action that changes something needs an approval unless the owner has
  trusted that exact routine, and it is then executed through
  `self.gateway.run(...)` — the same one-use approval token the rest of the
  application uses;
* a read-only action needs no approval but still honours the stop.

**A test command the owner has not trusted is approved on its own.** The Codex
task no longer runs the tests at all: the plan has a separate *Run the
configured tests* step with its own approval, and the exact command is shown:

```
run_project_tests: project-a: pytest -q
```

`test_command_trusted` compares the command as well as the routine, so
trusting `pytest -q` never trusts `npm test`.

### Blocker 2 — the tests run off the UI thread, and Stop ends the process

`TestRunWorker` runs the command on a `QThread`, so the window stays
responsive. `run_local_tests` polls a cancel callback while the process is
alive; when Emergency Stop raises through that callback the test process is
**terminated and waited for**, not left running behind the owner's back.

`stop()` now interrupts the test worker **and** the coding worker, and still
calls Omega's `on_stop()`. **Resume does not restart the job**: Emergency Stop
bumps the policy generation, so the cancelled worker's ticket is dead and the
task stays cancelled.

### Blocker 3 — the diff is against the commit the task started from

The task captures the commit it started from and reports
`git diff --cached <starting commit>`, which includes **committed edits,
uncommitted edits and new files**. A task that commits its own work no longer
hides behind its own commit. The original checkout and its dirty files are
untouched: the work happens in a separate worktree.

### Blocker 4 — the task is in the history, and a failed test is visible

* The task is recorded in the **task history** the moment it starts
  (`codex_task`), and the row is updated as it goes, so an interrupted task
  still leaves a trace.
* The history row carries the **status**, the **test result**
  (`tests=passed` / `tests=failed`), the **worktree path** and the **starting
  commit** (`from=7bf3fc69`).
* A **failed test is visible in the final result**: the chat summary always
  states `Tests: failed`, and the history row's status becomes `failed`,
  because the job was to make the change *and prove it*.
* An **active task and a pending approval are protected** from being
  overwritten by a new chat request. A second request while a task is running
  is refused with a sentence saying so, and `New chat` will not change the
  conversation under a running task.

### Blocker 5 — the software launchers and the coding editors stay separate

The project editor launcher had taken the name `launch_editor` and **shadowed**
`automation.windows.launch_editor`, so CapCut, DaVinci Resolve and After
Effects were being started with a project folder where an executable was
expected. The project launcher is now `open_project_in_editor`.

Verified: `desktop.launch_editor is automation.windows.launch_editor`,
`desktop.open_project_in_editor is developers_studio.editors.open_project_in_editor`,
and the two are different objects. `CapCut open pannu`, `DaVinci Resolve` and
`After Effects` still reach their inline approval, and **VS Code** and the
owner's **configured coding editors** still open the saved project folder — the
configured launcher is now used in the task step as well as in the card button,
which was a second, smaller instance of the same bug.

## 3. What changed

| File | Change |
|---|---|
| `developer_studio/editors.py` | **New.** The five known editors, their capabilities, where to find them, the owner's configured launchers, and `open_project_in_editor`. |
| `developer_studio/projects.py` | **New.** Saved projects, configured launchers, trusted routines, the assistant language. |
| `developer_studio/intents.py` | **New.** The deterministic English/Tamil/Tanglish request parser. |
| `developer_studio/codex_task.py` | **New.** The isolated-worktree task: open, isolate, edit, collect the diff against the starting commit, run the tests, report. |
| `developer_studio/codex_cli.py` | The existing wrapper is reused and extended with the sandbox, the approval mode and the working folder. The default is unchanged — read-only, in the project. |
| `desktop/app.py` | The chat task card, the approval gate, the task controller, the test worker, the history recording and the saved-project settings inside Settings & Plugins. |
| `desktop/omega.py` | Four lines: the Omega presentation recognises the personal coding worker, so the modes still show coding work in progress. |
| `tests/test_personal_codex_assistant.py` | **New.** 17 tests. |
| `tests/test_phase1_regressions.py` | **New.** 17 regression tests for the first review round. |
| `tests/test_phase1_omega.py` | **New.** 17 tests for this round, on the Omega tree. |

### The parser is a table, not a model

A task that writes code must be certain what was asked for, so the request is
read by a strict local table — the same approach `desktop/voice_commands.py`
uses for app launches. The Tanglish forms are the ones people actually type:
*open panni*, *fix pannu*, *tests run panni*, *result sollu*, plus Tamil
(*திற*, *செய்*, *மாற்று*).

A sentence it does not understand is **not** turned into a task. It stays
ordinary chat. A request that might be a coding task must never swallow a
question, and it must never start writing files.

### The acceptance sentence

> "JARVIS, my project-a VS Code-la open panni login page validation fix pannu.
> Tests run panni result sollu."

is read as: project `project-a`, editor `VS Code`, change
`login page validation`, actions open + change + tests + report, and **no
question asked**.

## 4. Test results

Measured on the same machine, same command, after the three patches in order
from a clean `main`:

| Tree | Result |
|---|---|
| Baseline `main` @ `7a1ec8d` (with JARVIS Omega) | `604 passed, 3 skipped, 0 failed` |
| + video-editing-studio | `620 passed, 3 skipped, 0 failed` |
| + chat-first (Ω-resolved) | `637 passed, 3 skipped, 0 failed` |
| + this section | **`657 passed, 3 skipped, 0 failed`** |

34 new tests in this section: 17 functional, 17 first-round regression tests,
17 Omega-tree tests — each review finding has a test that reproduces it
**through its normal entry point**.

### Results with mocks and test doubles

Everything below was proven **without** a Windows machine, a live provider or a
real Codex CLI. Nothing here is claimed as a live result.

| Check | What was replaced | Test |
|---|---|---|
| The acceptance sentence is read as project, editor, change and actions | nothing — the parser is deterministic | `test_the_acceptance_sentence_selects_the_project_the_editor_and_the_change` |
| A real Git worktree is created and the task runs inside it | the Codex call | `test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work` |
| The owner's uncommitted file is byte-for-byte unchanged | the Codex call | same test |
| Committed AND uncommitted edits are both in the diff | the Codex call | `test_committed_and_uncommitted_edits_are_both_reported` |
| The starting commit is captured and reported | the Codex call | `test_the_task_captures_the_starting_commit` |
| A non-Git folder is refused | the Codex call | `test_a_task_in_a_folder_that_is_not_a_git_repository_is_refused` |
| A failed test is reported as failed | the Codex call and the test command | `test_a_failed_test_is_reported_as_failed` |
| The task is recorded in the task history with its status, tests and worktree | the Codex call and the test command | `test_the_task_is_recorded_in_the_task_history` |
| The history row exists while the task is still running | nothing | `test_the_history_row_is_written_while_the_task_runs` |
| A failed test is visible in the final result | the Codex call and the test command | `test_a_failed_test_is_visible_in_the_final_result` |
| A new request cannot overwrite a running task | the Codex call | `test_a_new_request_does_not_overwrite_a_running_task` |
| A new request cannot lose a pending approval | nothing | `test_a_pending_approval_is_not_overwritten_by_a_new_request` |
| `New chat` cannot orphan a running task | nothing | `test_a_new_chat_does_not_orphan_a_running_task` |
| Stop cancels the task and Resume does not restart it | the Codex call | `test_stop_cancels_the_task_and_resume_does_not_restart_it` |
| The card actions go through the approval | the editor launcher | `test_opening_the_project_from_the_card_needs_approval` |
| Emergency Stop stops the card actions | the editor launcher | `test_emergency_stop_stops_the_card_actions` |
| The stop is honoured when reading the diff | nothing | `test_reviewing_the_diff_honours_the_stop` |
| The test command is approved separately from the change | the Codex call | `test_the_test_command_is_approved_separately_from_the_change` |
| A trusted test command does not ask again | the Codex call and the test command | `test_a_trusted_test_command_does_not_ask_again` |
| A different test command is never trusted | nothing | `test_a_different_test_command_is_never_trusted` |
| **The test process is really terminated by a stop** | the test command (a real sleeping interpreter) | `test_cancelling_the_tests_stops_the_test_process` |
| The UI thread is not blocked by the tests | the test command | `test_the_tests_run_off_the_ui_thread` |
| The software launcher is not shadowed | nothing | `test_the_software_and_coding_launchers_are_separate` |
| CapCut, DaVinci Resolve and After Effects still have their commands | nothing | `test_every_video_tool_launch_command_is_still_known` |
| VS Code opens the saved project | the editor launcher | `test_vs_code_still_opens_the_saved_project` |
| A configured coding editor opens the saved project | the editor launcher | `test_a_configured_coding_editor_opens_the_saved_project` |
| The Omega modes still exist and work | nothing | `test_the_omega_modes_are_still_there` |
| Omega shows the coding work in progress | the Codex call | `test_omega_still_shows_the_coding_work` |
| Emergency Stop still reaches Omega | nothing | `test_omega_still_receives_the_stop` |

Three of these are **not** mocks at all:

* `test_cancelling_the_tests_stops_the_test_process` starts a real sleeping
  interpreter, stops JARVIS, then asserts the operating system process is gone
  and that its marker file was never written.
* `test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work`
  uses a real Git repository, a real worktree and a real `git diff`.
* `test_the_tests_run_off_the_ui_thread` runs a real interpreter while a QTimer
  must keep firing, which fails if the UI thread is blocked.

### Live Windows results

**None. No live Windows check was performed and no live result is claimed.**

This environment is Linux with no Windows machine, no installed editor, no
Codex CLI and no provider credentials. These need your PC:

| Check | What you do | What to look for |
|---|---|---|
| VS Code really opens the project | run the acceptance sentence in Chat | the real folder loads, and **Open project** opens it too |
| A configured coding editor opens the project | save a project with that editor | the project opens in YOUR editor |
| The **real** Codex CLI runs the task | `npm i -g @openai/codex`, then `codex login` | the diff is Codex's own work |
| The project's **real** tests run | point the test command at your own suite | the result reaches the chat, and a failure is visible |
| The test process really stops | start a long test suite and press Emergency Stop | the suite stops, not just the window |
| CapCut, DaVinci Resolve, After Effects | type `CapCut open pannu` in Chat | the inline approval still appears and the tool still launches |
| The Omega modes | switch between Omega, Island and Stealth | all three still work, and the saved preference is kept |
| **The Omega globe, sustained repainting** | leave the Omega Home page running for a minute | see the finding in §6 |

## 5. Limitations

* **Only Codex can write code in this phase.** The Gemini and MiniMax coding
  paths still draft and repair code; they do not change a project in place.
* **A project must be a Git repository.** Otherwise there is no reviewable
  diff and the task is refused.
* **The task runs the Codex CLI with `workspace-write` inside the worktree.**
  The CLI is told never to ask for approval, because the owner approves the
  whole task once, in the chat, before anything starts.
* **The test command is split into arguments, not run through a shell.** A
  compound command such as `a && b` will not work; point it at a script.
* **The worktree is left on disk after a task**, under the application data
  folder, so the owner can look at it. It is not cleaned up automatically.
* **No packages are installed and nothing is pushed, merged or published.**
* **The request parser is a table.** A request phrased in a way it does not
  recognise stays ordinary chat rather than becoming a task.
* **Windows only** for the parts that need Windows: the credential manager,
  the editors, and the Codex CLI as it is installed.

## 6. One finding outside this section: the Omega globe

While testing I hit a crash that **is not from this section**. The Omega
reactor repaints every 48 ms, and after sustained repainting in a headless
environment it dies with a PySide6 refcount fault:

```
Fatal Python error: none_dealloc: deallocating None: bug likely caused by a refcount error in a C extension
  File "desktop/omega_visuals.py", line 280 in draw_globe
  File "desktop/omega_visuals.py", line 258 in paintEvent
```

It reproduces with **no coding task at all** — just `enable_omega()` and a
repaint loop — and the existing Omega tests miss it because they call
`processEvents()` only once. On a real Windows desktop the same code path
runs continuously, so it is worth a look on your machine: leave the Omega Home
page running for a minute and see whether it survives. I have not changed
Omega's painter, because I cannot verify a fix for it here.

## 7. Running it on Windows

```cmd
git clone https://github.com/mihran94/JARVIS-AI.git
cd JARVIS-AI
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pythonnet==3.2.1 pywin32==312
setup.cmd
START_JARVIS.cmd
```

1. **Settings & Plugins → Saved projects and editors** → **Add project folder**
   → choose the folder → name it → pick the editor → type the test command.
2. Check the editor list. An editor you have shows *installed* with its path;
   an editor you do not have shows **SETUP NEEDED**.
3. Tick **Open the selected project without asking** if you want that to stop
   asking.
4. Install and sign in to the coding CLI:
   `npm i -g @openai/codex` then `codex login`.
5. In **Chat**, type:
   `JARVIS, my project-a VS Code-la open panni login page validation fix pannu. Tests run panni result sollu.`
6. The task card appears. **Approve task** shows the exact project and change.
7. When the change is done, the test command asks for its own approval.
8. When it finishes, the transcript holds the changed files, the diff, the test
   result and the worktree path. **Review diff**, **Run tests** and
   **Open project** are below, and the task is in **Task History**.

## 8. Applying and reverting

See §1 for the apply order. The manifest step is required: the patch leaves
`docs/SOURCE_INTEGRITY.sha256` out because it is a generated file.

**Revert**

```cmd
git revert <the commit that applied the patch>
```

or, before committing:

```cmd
git apply -R develop\personal-codex-assistant\changes.patch
```

**Verify after applying**

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Expected: `657 passed, 3 skipped`, and no failures.

## 9. What was not done

* No key was read, stored, logged, or put in a prompt, a diff or a screenshot.
* No PC action flow, approval dialog or security policy was changed.
* No Omega mode, setting or workflow was removed or renamed.
* No release was published and `main` was not touched.
* Nothing was installed, pushed, merged or deployed.
