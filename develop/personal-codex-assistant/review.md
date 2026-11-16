# Personal Codex Assistant — Phase 1 review

**Section slug:** `personal-codex-assistant`
**Source baseline:** `954af152a263da7ece11b57f7c7ec3579e1663e6` ("Merge AI Brain & Voice, provider fixes, and manual release candidate workflow")
**Changes:** `develop/personal-codex-assistant/changes.patch`
**Status:** Ready for Review

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

## 2. What Phase 1 does

The product goal is that opening an app is one step and the next step is doing
useful work **inside** the project and verifying the result. Phase 1 delivers
that path end to end:

1. **Saved projects in Settings.** Each project is a folder, an editor and a
   local test command. Five editors are known — VS Code, Visual Studio,
   Android Studio, IntelliJ IDEA and PyCharm — and each one shows its own
   capabilities individually. An editor that is not installed says
   **SETUP NEEDED** and says what to do. Any other editor can be added as a
   launcher the owner configures, with its own capabilities.
2. **A chat request becomes a task card.** The card shows the project, the
   folder, the editor, the requested change and the steps. It is a short
   question only when the project or the scope is materially unclear.
3. **The task runs in an isolated Git worktree.** The owner's working folder is
   never edited, their uncommitted work is reported as protected, and the
   result is a real reviewable `git diff`.
4. **Progress streams into Chat.** Opening the project, creating the worktree,
   reading and editing, collecting the diff, running the tests, and the final
   completed-or-blocked line.
5. **The result stays in the conversation.** Changed files, the diff, the test
   results and the decisions that are left, with **Review diff**, **Run tests**
   and **Open project** buttons, and the task in the task history.
6. **Preferences and trusted routines.** Projects, editors, the assistant
   language and the routines are saved. Opening a saved project and running its
   configured tests can be trusted so they do not ask every time. Everything
   else — installing packages, overwriting existing work, sending project data
   to a provider, pushing, merging, deploying, publishing — needs an explicit
   approval that shows the exact action and its target.
7. **Emergency Stop is preserved.** It cancels queued work and requests
   cancellation of the running task, and a cancelled task stays cancelled after
   Resume.

## 3. The acceptance test

> "JARVIS, my project-a VS Code-la open panni login page validation fix pannu.
> Tests run panni result sollu."

The request parser reads that sentence without a model, in Tanglish, and finds:

| | |
|---|---|
| Project | `project-a` (the saved project, matched loosely: "project a" finds "project-a") |
| Editor | `VS Code` |
| Change | `login page validation` |
| Actions | open the project, make the change, run the tests, report the result |
| Question asked | none — nothing was materially unclear |

Then JARVIS opens the real folder in VS Code, asks for approval of the change
showing the exact target, creates an isolated worktree, runs Codex inside it,
collects the diff, runs the project's tests and puts the result in the
conversation.

`tests/test_personal_codex_assistant.py` drives this through the real window:
the sentence is typed into the chat, the task card appears, the approval is
given, and the diff and the test results reach the transcript.

## 4. What changed

| File | Change |
|---|---|
| `developer_studio/editors.py` | **New.** The five known editors, what each can do, where to find them, and the owner's own configured launchers. |
| `developer_studio/projects.py` | **New.** Saved projects, the configured launchers, the trusted routines and the assistant language. |
| `developer_studio/intents.py` | **New.** The deterministic English/Tamil/Tanglish parser that reads a chat sentence as a coding request. |
| `developer_studio/codex_task.py` | **New.** The isolated-worktree task: open, isolate, edit, collect the diff, run the tests, report. |
| `developer_studio/codex_cli.py` | The existing wrapper is reused and extended: the sandbox, the approval mode and the working folder are now arguments. The default is unchanged — read-only, in the project. |
| `desktop/app.py` | The chat task card, the controller, and the saved-project settings inside Settings & Plugins. |
| `tests/test_personal_codex_assistant.py` | **New.** 17 tests. |

### The parser is a table, not a model

A task that writes code must be certain what was asked for, so the request is
read by a strict local table — the same approach `desktop/voice_commands.py`
already uses for app launches. The Tanglish forms are the ones people actually
type: *open panni*, *fix pannu*, *tests run panni*, *result sollu*, plus Tamil
(*திற*, *செய்*, *மாற்று*).

A sentence it does not understand is **not** turned into a task. It stays
ordinary chat. That matters: a request that might be a coding task must never
swallow a question, and it must never start writing files.

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
| Run that project's configured tests | only if the owner has not trusted that routine |
| Ask Codex to change the code | **always** — it writes code and sends project data to a provider |
| Install packages, overwrite work, push, merge, deploy, publish | **always**, and not implemented at all in this phase |

The approval shows the exact action and its target, for example:

```
codex_task: project-a · C:\work\project-a · login page validation
```

Declining one step declines the whole task. Nothing is left half done.

### Credentials

The Codex CLI reads its own credentials. No key is passed to the task, written
into a prompt, printed into a log, or put in a diff. The provider keys stay in
the Windows Credential Manager, and the task never sees them.

## 5. Test results

Measured on the same machine, same command, after the three patches in order:

| Tree | Result |
|---|---|
| Baseline `main` @ `954af15` | `577 passed, 3 skipped, 0 failed` |
| + video-editing-studio + chat-first | `604 passed, 3 skipped, 0 failed` |
| + this section | **`621 passed, 3 skipped, 0 failed`** |

The 17 extra passing tests are the new ones in
`tests/test_personal_codex_assistant.py`.

### Passed for real — no mock involved

| Check | Test |
|---|---|
| The acceptance sentence is read as project, editor, change and actions | `test_the_acceptance_sentence_selects_the_project_the_editor_and_the_change` |
| A real Git worktree is created and the task runs inside it, not in the project | `test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work` |
| The owner's uncommitted file is byte-for-byte unchanged afterwards | same test |
| The diff really is a Git diff, with the changed file listed | same test |
| A folder that is not a Git repository is refused | `test_a_task_in_a_folder_that_is_not_a_git_repository_is_refused` |
| A failed test is reported as failed, with its output | `test_a_failed_test_is_reported_as_failed` |
| The whole Qt flow: card, approval, worker, transcript | `test_the_conversation_keeps_the_result_visible` |
| Emergency Stop cancels, and the task stays cancelled after Resume | `test_emergency_stop_cancels_the_task_and_it_stays_cancelled` |
| A declined action changes nothing | `test_a_declined_action_changes_nothing` |
| A trusted routine opens the project without asking | `test_a_trusted_routine_opens_the_project_without_asking` |
| An untrusted routine asks first, with the exact target | `test_an_untrusted_routine_asks_first` |
| Each editor shows its capabilities individually | `test_each_editor_shows_its_capabilities_individually` |
| The settings page lists the projects, the editors and the launchers | `test_the_saved_projects_page_lists_the_projects_and_the_editors` |

### Passed with a test double

| Check | What was replaced | Why |
|---|---|---|
| The Codex CLI call | `run_codex` and `codex_executable` | the CLI is not installed on this Linux machine |
| The test command | `run_local_tests` | the project has no test suite here |
| Opening the editor | `launch_editor` | no editor is installed here |

### Blocked — needs your Windows PC

| Check | Why it is blocked | What you do |
|---|---|---|
| VS Code actually opening the project | no editor is installed here | open the project from the chat card and confirm the real folder loads |
| A **real** Codex CLI run | the CLI is not installed here | `npm i -g @openai/codex`, then `codex login`, then run the task |
| The project's **real** tests | the sample project has no suite | point the test command at your own suite |
| Editor detection for your installed editors | none are installed here | open Settings and check each shows *installed* with the right path |
| Codex authentication | no credentials here | confirm the task reports the sign-in instruction instead of failing obscurely |

## 6. Limitations

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
7. When it finishes, the transcript holds the changed files, the diff and the
   test results. **Review diff**, **Run tests** and **Open project** are below.

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

Expected: `621 passed, 3 skipped`, and no failures.

## 9. What was not done

* No key was read, stored, logged, or put in a prompt, a diff or a screenshot.
* No PC action flow, approval dialog or security policy was changed.
* No release was published and `main` was not touched. The owner merges and
  publishes.
* Nothing was installed, pushed, merged or deployed.
