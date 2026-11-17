# Owner review — prepared source updates and the coding route

**Branch:** `feature/automatic-source-updates` (draft PR #30)
**Base:** `7a1ec8d` (`main`)
**Status:** Ready for the owner's review. The PR stays a draft; `main` is not touched.

---

## 1. What this changes, and why

PR #30 had one opt-in setting that downloaded the latest commit on `main`,
verified it and **selected it for the next start on its own**. The owner
requirement in the draft says the opposite:

> "Automatic download and test preparation must leave the active version
> pointer alone." and "Bind one-time approval to the exact verified revision.
> Changes after approval require a fresh review."

So the automatic check now **prepares a candidate for review** and changes
nothing. The version that runs moves only when the owner approves that exact
revision.

On top of that, the draft asks for four things that did not exist yet:

| Requirement | What is there now |
|---|---|
| Gemini answers the owner | `providers/routing.py` — Gemini is the default for the chat, the spoken replies, the daily tasks and the explanation of a proposed update. Every other person-facing provider stays selectable. |
| Only MiniMax or Codex write code | `require_coding_provider()` refuses every other provider before a request is made. The choice is in **Coding Assistant**, and it is MiniMax until the owner picks Codex. |
| A coding provider that stops must not lose the task | The task is written to the task history before the provider is called. A rate limit, an exhausted quota or a dropped connection leaves it `waiting`, with the reason, so it can be resumed. Using the other coding provider is an approved action. |
| JARVIS improves its own source | `core/development.py` prepares the change in an isolated Git worktree under the local `development/` folder, runs the tests there and saves the diff, the test results and the exact revision. |
| The always-on session | An opt-in start-at-sign-in setting (Windows Run key) and a system tray with **Pause** and **Exit**. Closing the window can keep JARVIS in the tray. |

---

## 2. The files

| File | Change | What it does |
|---|---|---|
| `providers/routing.py` | **new** | The routing policy: the person-facing provider (Gemini by default) and the coding providers (MiniMax and Codex only). |
| `core/candidates.py` | **new** | The prepared revision: download, verify, test, review, approve, reject, activate. |
| `core/development.py` | **new** | The isolated worktree, the diff, the exact revision, and the approval that is bound to it. |
| `core/coding_tasks.py` | **new** | The saved coding task, so an interrupted one can be resumed. |
| `core/coding_agent.py` | **new** | Asks the coding provider for the files of a change and writes them into the worktree. |
| `core/verification.py` | **new** | Runs a test command in a prepared folder and keeps the result. |
| `core/source_updates.py` | changed | `stage_latest()` became `fetch_latest_source()`, which downloads and verifies without selecting anything. |
| `desktop/review_panel.py` | **new** | The review screen: the diff, the test results, Approve and Reject. |
| `desktop/background.py` | **new** | The background work: preparing an improvement, and preparing a source revision. |
| `desktop/startup.py` | **new** | The Windows start-at-sign-in setting. |
| `desktop/tray.py` | changed | **Pause JARVIS** next to **Show JARVIS** and **Exit JARVIS**. |
| `desktop/app.py` | changed | The coding provider is MiniMax or Codex, the review page, the always-on settings, and the improvement flow. |
| `desktop/update_dialog.py` | changed | The check prepares a revision for review instead of staging it. |
| `docs/UPDATES.md` | changed | The new flow, in the words the owner reads. |
| `tests/test_provider_routing.py` | **new** | 9 tests. |
| `tests/test_development_workflow.py` | **new** | 10 tests. |
| `tests/test_review_panel.py` | **new** | 9 tests. |
| `tests/test_source_updates.py` | changed | 12 tests, around the new approval gate. |
| `tests/test_code_generation.py` | changed | The coding provider is MiniMax or Codex now. |
| `tests/test_background_tray.py` | changed | The tray has **Pause**. |

---

## 3. How it works

### 3.1 Which provider does what

```
the owner  →  Gemini (default) or any other provider they choose
the code   →  MiniMax (default) or Codex, and nothing else
```

`providers/routing.py` is the only place that knows this. `require_coding_provider()`
is called before a request is made, so a new call site cannot forget the rule.
The Coding Assistant says it on screen: *"Only MiniMax and Codex may write or
fix source code."*

When Codex is the chosen coding provider, the draft and repair flows use the
Codex command line tool instead of the API. The draft still lands in the same
preview, and it is still applied to the editor only after the owner approves
it.

### 3.2 Preparing a revision

`core/candidates.py` does the work the old `stage_latest()` did, and stops
there:

1. download the exact commit ZIP from `mihran94/JARVIS-AI`,
2. verify every file against that commit's Git tree,
3. write the files into a prepared folder under `.updates/candidates/`,
4. run the tests there and keep the result,
5. record the revision, the changed files, the diff and the test result.

**The active version pointer is not touched.** The state file that selects the
version is only written by `stage_candidate()`, which runs after the approval.

### 3.3 The approval is bound to the revision

`stage_candidate()` re-reads the prepared files and compares their content
digest with the one that was reviewed. If a single byte changed after the
review, the approval is refused:

> *The prepared source changed after the review. Review it again.*

The approval itself is the existing one-use token from `security/policy.py`,
and the action names the exact revision and its digest, so the dialog shows
what is being approved.

### 3.4 A failed test disables Apply

`Candidate.appliable` is true only when the tests passed. The review screen
shows the failure and keeps the button disabled:

> *Tests: failed — Apply is disabled because the tests did not pass. Read the
> failure and prepare the change again.*

### 3.5 Only the approved revision is activated

`stage_candidate()` selects the approved revision and keeps the one it
replaces as `previous`, so **Select previous code version (rollback)** still
works. A revision that was prepared but never approved is never activated; the
review screen is the only way to reach that code path.

### 3.6 The isolated worktree

`core/development.py` prepares an improvement to JARVIS itself:

```
<installation>/development/<task id>/     a detached Git worktree
```

The worktree is made from the current commit, so the branch that is checked
out never moves. The coding provider proposes the files, JARVIS writes them
inside the worktree — a path that would leave it is refused — and the tests
run there. The diff, the test results and the exact revision are saved.

The folder is in `.gitignore`: it is a working area, not source.

### 3.7 When the coding provider stops

The task is written to the task history before the provider is called. A
failure that can pass — a rate limit, an exhausted quota, a dropped
connection, a timeout — leaves the task in the state `waiting`, with the
reason, and the worktree that holds the work so far.

The other coding provider is **offered**, not used. Switching is an action the
owner approves, with the provider and the goal in the approval text.

### 3.8 The always-on session

* **Keep JARVIS in the system tray when the window is closed** — closing the
  window hides it and the tray keeps it alive. The tray menu has **Show
  JARVIS**, **Pause JARVIS** and **Exit JARVIS**.
* **Start JARVIS when Windows signs in** — a per-user Run key entry holding the
  same launcher `START_JARVIS.cmd` uses. It is removed again when the setting
  is switched off, and no administrator rights are needed.

Pause stops the automatic source check and the background preparation of
changes. Nothing is closed and nothing is lost.

---

## 4. Tests

```
$ python -m pytest -q
624 passed, 3 skipped, 12 subtests passed
```

The branch had **589 passed, 3 skipped** before this work (its own PR body
says so). Now: **624 passed, 3 skipped, 0 failed**.

New and changed tests, by requirement:

| Requirement | Test |
|---|---|
| Gemini is the default | `test_provider_routing.py::test_gemini_answers_the_owner_by_default` |
| Other person-facing providers stay | `test_provider_routing.py::test_the_owner_can_choose_another_person_facing_provider` |
| MiniMax and Codex write code | `test_provider_routing.py::test_only_minimax_and_codex_may_write_code` |
| The chat provider cannot write code | `test_provider_routing.py::test_the_application_offers_only_the_coding_providers` |
| The coding provider defaults to MiniMax | `test_provider_routing.py::test_minimax_writes_code_until_the_owner_chooses_otherwise` |
| Rate-limit recovery | `test_development_workflow.py::test_a_rate_limited_provider_saves_the_task_and_asks_before_switching` |
| The switch needs approval | `test_development_workflow.py::test_the_switch_to_the_other_coding_provider_is_an_approved_action` |
| A task can be resumed | `test_development_workflow.py::test_a_stopped_task_is_saved_and_can_be_resumed` |
| The worktree is isolated | `test_development_workflow.py::test_the_change_is_prepared_in_a_worktree_under_development` |
| Failed tests | `test_development_workflow.py::test_a_failed_test_makes_the_change_not_applicable`, `test_source_updates.py::test_a_revision_whose_tests_failed_cannot_be_applied` |
| Rejection | `test_source_updates.py::test_a_rejected_revision_leaves_the_running_version_alone`, `test_review_panel.py::test_rejecting_leaves_the_running_version_alone` |
| Approval invalidation | `test_source_updates.py::test_a_prepared_revision_that_changed_after_the_review_cannot_be_applied`, `test_development_workflow.py::test_a_change_edited_after_the_review_cannot_be_applied` |
| Only the approved revision is activated | `test_source_updates.py::test_only_the_approved_revision_is_activated` |
| The running version is untouched by a check | `test_source_updates.py::test_preparing_a_revision_does_not_change_the_running_version` |
| The previous version is kept | `test_source_updates.py::test_approving_a_revision_selects_it_and_keeps_the_previous_one` |
| Apply is disabled on a failure | `test_review_panel.py::test_apply_is_disabled_when_the_tests_failed` |
| The tray keeps JARVIS alive | `test_review_panel.py::test_closing_the_window_keeps_jarvis_in_the_tray_when_it_is_asked` |
| Pause and Exit | `test_background_tray.py::test_pause_stops_the_background_work_without_closing_anything` |
| Start at sign-in | `test_review_panel.py::test_starting_at_sign_in_is_a_windows_setting_and_is_off_by_default` |

---

## 5. What is still to be checked on Windows

This was built and tested on Linux, with no Windows machine, no MiniMax key,
no Codex CLI and no provider credentials. These parts have to be confirmed on
the owner's PC:

1. **Start at sign-in.** The Run key entry is written to
   `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Check that the entry
   appears, that JARVIS starts after a sign-in, and that switching the setting
   off removes it. The code path is exercised on Linux only up to the point
   where it refuses, because it is a Windows setting.
2. **The system tray.** The tray icon, the **Pause** action and the
   **Exit** action need the real Windows notification area. The offscreen
   tests use a fake tray.
3. **Closing the window keeps JARVIS alive.** Check that the window closes,
   the tray icon remains, **Show JARVIS** brings it back and **Exit JARVIS**
   really exits.
4. **A real Codex CLI run.** `npm i -g @openai/codex` and `codex login`. The
   tests replace the CLI with a stub.
5. **A real MiniMax call.** The key comes from Windows Credential Manager; the
   tests never touch the real one.
6. **A real prepared revision.** The GitHub download and the tree verification
   are tested against a mocked transport. A live download from the desktop and
   a real test run in the prepared folder are still to be done.
7. **A real improvement.** Preparing a change to JARVIS itself, in a real
   worktree, with the real provider and the real test suite, has not been run
   on Windows.
8. **The next restart.** The staged revision is selected at the next
   `START_JARVIS.cmd`. The state file is tested; the restart itself is not.

---

## 6. Known limitations

* **The parser of what to prepare is a phrase table**, not a model. "Fix the
  contact form validation" is understood; "you know that thing we talked
  about" is not.
* **One improvement at a time.** The background worker refuses a second
  preparation while one is running.
* **The prepared folder is not cleaned up automatically.** A rejected or a
  failed candidate leaves its files under `.updates/candidates/` until the
  next preparation replaces them.
* **The worktree of a failed task is kept** when it holds a change, so the
  work is not lost. An empty one is removed.
* **The tests of a prepared revision use the project's own command.** The
  default is `python -m pytest -q`; it is configurable.
* **The start-at-sign-in setting is Windows only**, and it is off by default.
* **The draft PR is still a draft.** Nothing is merged into `main`, and no
  release is published.

---

## 7. What was not done

* No key was read, stored, logged, or put in a prompt, a diff or a screenshot.
* No PC action flow, approval dialog or security policy was changed. The
  approval gateway and the emergency stop still control every action.
* No Omega mode, setting or workflow was removed or renamed.
* No release was published and `main` was not touched.
* The provider registry was not changed: Gemini, OpenAI, Claude, Ollama and
  the rest still work exactly as before for the owner's own conversations.
