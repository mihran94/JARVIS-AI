# Personal Codex Assistant — Phase 1 review

**Section slug:** `personal-codex-assistant`
**Source baseline:** `954af152a263da7ece11b57f7c7ec3579e1663e6` ("Merge AI Brain & Voice, provider fixes, and manual release candidate workflow")
**Changes:** `develop/personal-codex-assistant/changes.patch`
**Status:** Ready for Review (revision 2 — the Phase 1 review findings are fixed)

---

## 1. Patch dependencies

This section was developed on top of two sections that are **submitted on
`development` and not yet merged into `main`**. Apply them in this order:

```cmd
git checkout 954af152a263da7ece11b57f7c7ec3579e1663e6
git apply develop\video-editing-studio\changes.patch
git apply develop\chat-first\changes.patch
git apply develop\personal-codex-assistant\changes.patch
python scripts\source_manifest.py
python scripts\source_manifest.py --check
```

| Order | Patch | Why it is needed |
|---|---|---|
| 1 | `develop/video-editing-studio/changes.patch` | the Video Editing Studio, on which the chat-first work builds |
| 2 | `develop/chat-first/changes.patch` | Chat as the home screen, the inline Approve/Decline row, Settings & Plugins |
| 3 | `develop/personal-codex-assistant/changes.patch` | **this section** |

If the first two are merged into `main` before this is reviewed, this patch
applies on its own.

## 2. The review findings, and how each one is fixed

| # | Finding | Fix |
|---|---|---|
| 1 | Task-card actions did not go through the approval gateway or the Emergency Stop checks | Every card action now goes through `coding_action_gate`, which takes a policy ticket, checks the stop, and runs the action through `self.gateway.run(...)` — the same one-use approval the rest of the application uses. |
| 2 | Untrusted test commands were approved together with the change | The Codex task no longer runs the tests. The test command is its **own step with its own approval**, shown with the exact command. A trusted routine still skips it. |
| 3 | Tests ran on the UI thread, and cancelling did not stop the test process | The tests run on `TestRunWorker`, a `QThread`. Emergency Stop interrupts the worker, which **terminates the test process** and waits for it to go. |
| 4 | The CapCut, DaVinci Resolve and After Effects launch commands were broken | The project editor launcher had taken the name `launch_editor` and shadowed the video-tool one, so those tools were being started with a project folder where an executable was expected. The project launcher is now `open_project_in_editor`. |
| 5 | The diff was taken against the worktree's HEAD, so a task that committed its own work hid those edits | The task captures the **starting commit** and reports `git diff --cached <starting commit>`, which includes committed and uncommitted edits and files the task created. |

Each one has a regression test in `tests/test_phase1_regressions.py`.

### 1. Every card action goes through the approval and the stop

The task card offers **Review diff**, **Run tests** and **Open project**. All
three now go through one gate:

* **Open project** launches a program, so it needs an approval unless the owner
  has trusted opening that project. It is then executed through
  `self.gateway.run(...)`, so the one-use approval token and the Emergency Stop
  checks apply.
* **Run tests** runs a command, so it needs an approval unless the owner has
  trusted that exact command.
* **Review diff** reads, so it needs no approval — but it still checks the
  stop, because an assistant that has been stopped should not quietly keep
  working.

After Emergency Stop, the card actions do nothing and say why.

### 2. A test command is approved on its own

The Codex task no longer runs the tests. The plan has a separate *Run the
configured tests* step, and when the owner has not trusted that command it
shows its own approval with the exact command:

```
run_project_tests: project-a: pytest -q
```

Trusting the saved command does not trust another one: `test_command_trusted`
compares the command as well as the routine, so a different command always
asks.

### 3. The tests run off the UI thread, and a stop kills the process

`TestRunWorker` runs the command on a worker thread, so the window stays
responsive while the tests run. `run_local_tests` polls a cancel callback while
the process is alive; when Emergency Stop raises through that callback the
process is **terminated** and waited for, not left running behind the owner's
back. The run is then reported as cancelled.

### 4. The video tool launches still work

`automation.windows.launch_editor` opens an *executable*. The project editor
launcher opens a *folder*. They are different things and must not share a
name, so the project one is now `open_project_in_editor`. The regression test
asserts that `desktop.app.launch_editor` is still the automation one, and that
each of CapCut, DaVinci Resolve and After Effects still has its launch phrase.

### 5. The diff is against the commit the task started from

The task records the commit it started from and reports the whole difference
against it:

```
2 file(s) changed against 7bf3fc69. The diff is below and the worktree is at ...
```

A task that commits its own work, and a task that leaves edits uncommitted, are
both fully visible in that diff — along with files the task created.

## 3. What Phase 1 does

1. **Saved projects in Settings.** Each project is a folder, an editor and a
   local test command. Five editors are known — VS Code, Visual Studio,
   Android Studio, IntelliJ IDEA and PyCharm — each showing its own
   capabilities individually. An editor that is not installed says
   **SETUP NEEDED** and what to do. Any other editor can be added as a launcher
   the owner configures, with its own capabilities.
2. **A chat request becomes a task card** showing the project, folder, editor,
   requested change and steps. It asks a short question only when the project
   or the scope is materially unclear.
3. **The task runs in an isolated Git worktree.** The owner's working folder is
   never edited, their uncommitted work is reported as protected, and the
   result is a real reviewable diff against the starting commit.
4. **Progress streams into Chat:** opening the project, creating the worktree,
   reading and editing, collecting the diff, running the tests, and the final
   completed-or-blocked line.
5. **The result stays in the conversation:** changed files, the diff, the test
   results and the decisions that are left, with **Review diff**, **Run tests**
   and **Open project**, and the task in the task history.
6. **Preferences and trusted routines** for projects, editors, the assistant
   language and the routines.
7. **Emergency Stop is preserved.** It cancels queued work, terminates a
   running test process, and requests cancellation of the running task. A
   cancelled task stays cancelled after Resume.

## 4. The acceptance test

> "JARVIS, my project-a VS Code-la open panni login page validation fix pannu.
> Tests run panni result sollu."

The request parser reads that sentence without a model, in Tanglish:

| | |
|---|---|
| Project | `project-a` |
| Editor | `VS Code` |
| Change | `login page validation` |
| Actions | open the project, make the change, run the tests, report the result |
| Question asked | none — nothing was materially unclear |

Then JARVIS opens the real folder in VS Code, asks for approval of the change
showing the exact target, creates an isolated worktree, runs Codex inside it,
collects the diff against the starting commit, asks for approval of the test
command, runs the tests off the UI thread and puts the result in the
conversation.

## 5. What changed

| File | Change |
|---|---|
| `developer_studio/editors.py` | **New.** The five known editors, what each can do, where to find them, the owner's configured launchers, and `open_project_in_editor`. |
| `developer_studio/projects.py` | **New.** Saved projects, the configured launchers, the trusted routines and the assistant language. |
| `developer_studio/intents.py` | **New.** The deterministic English/Tamil/Tanglish parser that reads a chat sentence as a coding request. |
| `developer_studio/codex_task.py` | **New.** The isolated-worktree task: open, isolate, edit, collect the diff against the starting commit, run the tests, report. |
| `developer_studio/codex_cli.py` | The existing wrapper is reused and extended: the sandbox, the approval mode and the working folder are now arguments. The default is unchanged — read-only, in the project. |
| `desktop/app.py` | The chat task card, the approval gate, the task controller, the test worker, and the saved-project settings inside Settings & Plugins. |
| `tests/test_personal_codex_assistant.py` | **New.** 17 tests. |
| `tests/test_phase1_regressions.py` | **New.** 17 regression tests, one for each review finding. |

### The parser is a table, not a model

A task that writes code must be certain what was asked for, so the request is
read by a strict local table — the same approach `desktop/voice_commands.py`
already uses for app launches. The Tanglish forms are the ones people actually
type: *open panni*, *fix pannu*, *tests run panni*, *result sollu*, plus Tamil
(*திற*, *செய்*, *மாற்று*).

A sentence it does not understand is **not** turned into a task. It stays
ordinary chat. A request that might be a coding task must never swallow a
question, and it must never start writing files.

### The work is isolated, and the isolation is the point

The change is made in a throwaway Git worktree created from the project's
`HEAD`, never in the owner's folder. So the owner's uncommitted work is
untouched, the diff is a real Git diff against their own history, and the
tests run against the changed code where the change was made.

A folder that is not a Git repository cannot be isolated and cannot give a
reviewable diff, so the task is **refused with a clear reason** instead of
editing the owner's files in place.

### What needs approval, and what does not

| Action | Needs approval? |
|---|---|
| Open a saved project | only if the owner has not trusted that routine |
| Run that project's configured tests | only if the owner has not trusted that exact command |
| Ask Codex to change the code | **always** — it writes code and sends project data to a provider |
| Install packages, overwrite work, push, merge, deploy, publish | **always**, and not implemented at all in this phase |

Declining one step declines the whole task. Nothing is left half done.

### Credentials

The Codex CLI reads its own credentials. No key is passed to the task, written
into a prompt, printed into a log, or put in a diff. The provider keys stay in
the Windows Credential Manager, and the task never sees them.

## 6. Test results

Measured on the same machine, same command, after the three patches in order:

| Tree | Result |
|---|---|
| Baseline `main` @ `954af15` | `577 passed, 3 skipped, 0 failed` |
| + video-editing-studio + chat-first | `604 passed, 3 skipped, 0 failed` |
| + this section | **`638 passed, 3 skipped, 0 failed`** |

34 new tests: 17 in `tests/test_personal_codex_assistant.py` and 17 regression
tests in `tests/test_phase1_regressions.py`.

### Results with mocks and test doubles

Everything below was proven **without** a Windows machine, a live provider or a
real Codex CLI. Nothing here is claimed as a live result.

| Check | What was replaced | Test |
|---|---|---|
| The acceptance sentence is read as project, editor, change and actions | nothing — the parser is deterministic | `test_the_acceptance_sentence_selects_the_project_the_editor_and_the_change` |
| A real Git worktree is created and the task runs inside it | the Codex call | `test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work` |
| The owner's uncommitted file is byte-for-byte unchanged | the Codex call | same test |
| Committed AND uncommitted edits are both in the diff | the Codex call | `test_committed_and_uncommitted_edits_are_both_reported` |
| The starting commit is captured and reported | the Codex call | `test_the_task_captures_the_starting_commit`, `test_the_starting_commit_is_reported_in_the_result` |
| A folder that is not a Git repository is refused | the Codex call | `test_a_task_in_a_folder_that_is_not_a_git_repository_is_refused` |
| A failed test is reported as failed | the Codex call and the test command | `test_a_failed_test_is_reported_as_failed` |
| The whole Qt flow: card, approval, worker, transcript | the Codex call and the test command | `test_the_conversation_keeps_the_result_visible` |
| The test command is approved separately from the change | the Codex call | `test_the_test_command_is_approved_separately_from_the_change` |
| A trusted test command does not ask again | the Codex call and the test command | `test_a_trusted_test_command_does_not_ask_again` |
| A different test command is never trusted | nothing | `test_a_different_test_command_is_never_trusted` |
| The card's Open project needs an approval | the editor launcher | `test_opening_the_project_from_the_card_needs_approval` |
| Emergency Stop stops the card actions | the editor launcher | `test_emergency_stop_stops_the_card_actions` |
| The stop is honoured when reading the diff | nothing | `test_reviewing_the_diff_honours_the_stop` |
| **The test process is really terminated by a stop** | the test command (a real sleeping interpreter) | `test_cancelling_the_tests_stops_the_test_process` |
| The UI thread is not blocked by the tests | the test command | `test_the_tests_run_off_the_ui_thread` |
| The video-tool launcher is not shadowed | nothing | `test_the_video_tool_launcher_is_not_shadowed` |
| The CapCut command still reaches the inline approval | the editor launcher | `test_the_capcut_command_still_reaches_the_inline_approval` |
| Every video tool still has its launch phrase | nothing | `test_every_video_tool_launch_command_is_still_known` |

Two of these are worth calling out because they are **not** mocks:

* `test_cancelling_the_tests_stops_the_test_process` starts a real sleeping
  interpreter, stops JARVIS, and then asserts the operating system process is
  gone and that its marker file was never written.
* `test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work`
  uses a real Git repository, a real worktree and a real `git diff`.

### Live Windows results

**None. No live Windows check was performed and no live result is claimed.**

This environment is Linux with no Windows machine, no installed editor, no
Codex CLI and no provider credentials. These need your PC:

| Check | What you do | What to look for |
|---|---|---|
| VS Code really opens the project | run the acceptance sentence in Chat | the real folder loads in the editor, and **Open project** opens it too |
| The **real** Codex CLI runs the task | `npm i -g @openai/codex`, then `codex login` | the diff is Codex's own work, not a scaffold |
| The project's **real** tests run | point the test command at your own suite | the result reaches the chat, and Emergency Stop kills the test process |
| Editor detection for your editors | open Settings & Plugins | each editor shows *installed* with its path, or **SETUP NEEDED** |
| Codex authentication | run a task without signing in | the message names `codex login` instead of failing obscurely |
| CapCut, DaVinci Resolve, After Effects | type `CapCut open pannu` in Chat | the inline approval still appears and the tool still launches |

## 7. Limitations

* **Only Codex can write code in this phase.** The Gemini and MiniMax coding
  paths in the Developer Studio still draft and repair code; they do not make a
  change inside a project. Wiring them to the same worktree is the obvious
  next step inside this section.
* **A project must be a Git repository.** Otherwise there is no reviewable
  diff and the task is refused.
* **The task runs the Codex CLI with `workspace-write` inside the worktree.** The
  CLI is told never to ask for approval, because the owner approves the whole
  task once, in the chat, before anything starts.
* **The test command is split into arguments, not run through a shell.** A
  compound command such as `a && b` will not work; point it at a script
  instead.
* **The worktree is left on disk after a task**, under the application data
  folder, so the owner can look at it. It is not cleaned up automatically.
* **No packages are installed and nothing is pushed, merged or published.** The
  approval path exists for those actions; the actions themselves are not
  implemented in Phase 1.
* **The request parser is a table.** A request phrased in a way it does not
  recognise stays ordinary chat rather than becoming a task. That is a
  deliberate limit, not an oversight.
* **Windows only** for the parts that need Windows: the credential manager,
  the editors, and the Codex CLI as it is installed.

## 8. Running it on Windows

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
   → choose the folder → name it → pick the editor → type the test command
   (`pytest -q`).
2. Check the editor list. An editor you have shows *installed* and its path; an
   editor you do not have shows **SETUP NEEDED**.
3. Tick **Open the selected project without asking** if you want that to stop
   asking.
4. Install and sign in to the coding CLI:
   `npm i -g @openai/codex` then `codex login`.
5. In **Chat**, type:
   `JARVIS, my project-a VS Code-la open panni login page validation fix pannu. Tests run panni result sollu.`
6. The task card appears. **Approve task** shows the exact project and change.
7. When the change is done, the test command asks for its own approval.
8. When it finishes, the transcript holds the changed files, the diff and the
   test results. **Review diff**, **Run tests** and **Open project** are below.

## 9. Applying and reverting

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

Expected: `638 passed, 3 skipped`, and no failures.

## 10. What was not done

* No key was read, stored, logged, or put in a prompt, a diff or a screenshot.
* No PC action flow, approval dialog or security policy was changed.
* No release was published and `main` was not touched. The owner merges and
  publishes.
* Nothing was installed, pushed, merged or deployed.
