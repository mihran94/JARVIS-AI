# Context-aware task assistant — review

**Section:** Context-aware task assistant (after Personal Codex Assistant Phase 1)
**Branch:** `development`
**Base:** `7ae2f12` (`main` @ `7a1ec8d` + video-editing-studio + chat-first (Ω) + personal-codex-assistant Phase 1)
**Status:** Ready for Review — nothing merged into `main`, nothing released.

---

## 1. What this section adds

JARVIS now **remembers the conversation it is in**. You can say one thing, and
then keep talking to the same task without repeating yourself.

```
JARVIS, website project-a VS Code-la open pannu. Contact form validation
fix panni tests run pannu. Enna change pannina nu Tamil-la sollu.
```

JARVIS understands the Tamil, the Tanglish and the English in that sentence,
picks the project, the editor, the change and the tests, asks your approval
for each action, and answers in Tamil — with the changed files, the diff you
can read, the test result, and where the work was saved.

Then, in the same conversation:

| You type | What happens |
|---|---|
| `show the diff` / `diff kaattu` | The diff is read back out of the saved worktree. |
| `run the tests again` / `tests run pannu` | The exact command is offered for approval, then run in the same worktree. |
| `continue that task` / `continue pannu` | The worktree and the starting commit are checked first, then the task comes back. |
| `stop this task` / `stop pannu` | That task stops. The assistant keeps running. |
| `also fix the logout validation` | The project from this conversation is used. |

---

## 2. The files

| File | Change | What it does |
|---|---|---|
| `developer_studio/context.py` | **new** | `ConversationMemory` — the remembered project, editor, language and last task, in the settings store. `TaskRecord`, `task_is_resumable()`, `describe_task()`. |
| `developer_studio/intents.py` | changed | Follow-up phrases (`continue` / `show_diff` / `run_tests` / `stop`) in English and Tanglish, reply-language detection, `match_projects()`, and the report labels in Tamil, English and French. |
| `developer_studio/codex_task.py` | changed | The task takes a language and reports in it; `reviewable_diff()` reads the diff back out of a worktree. |
| `developer_studio/editors.py` | changed | The "setup needed" instruction is written in the owner's language. |
| `desktop/app.py` | changed | The conversation memory, the follow-up handlers, the clarification question, the localised final report, and the reply language that goes to the model. |
| `tests/test_context_assistant.py` | **new** | 21 tests: the whole workflow, ambiguous names, a failed test, cancel and resume, missing tools, the preferences. |
| `tests/test_personal_codex_assistant.py` | changed | Two card assertions accept the Tamil wording too. |
| `tests/test_phase1_omega.py` | changed | One report assertion accepts the Tamil wording too. |
| `docs/SOURCE_INTEGRITY.sha256` | changed | Regenerated for the new files. |

---

## 3. How it works

### 3.1 The order of a message

`send()` now decides in this order:

1. **A follow-up?** `parse_follow_up()` only matches when the message is
   *essentially only* the follow-up phrase — "add a stopwatch to the project"
   is a new task, not a stop request.
2. **An answer to a question JARVIS asked?** If two projects matched, the
   answer picks the project and the task starts.
3. **A coding request?** A sentence that names a saved project and asks for an
   open, a change or the tests.
4. **A launch command or `/video`.**
5. **Ordinary chat**, which goes to the model.

### 3.2 When two projects could be meant

`match_projects()` returns **every** saved project whose name appears in the
sentence. More than one match produces a question, not a guess:

```
Which project do you mean? Choose one: website, project-a.
```

Answering with a project name starts the task. One match starts the task
straight away.

### 3.3 A request that names no project

The project this conversation is about is used. That is the whole point of the
memory, and it is why "also fix the logout validation" works.

### 3.4 The reply language

`detect_reply_language()` finds the language marker in the request
(`Tamil-la sollu`, `tell me in french`, …). It is remembered, it is passed to
the model as an instruction, and it chooses the labels of the final report —
the card, the steps and the report are all written in that language.

The app's saved language preference is the fallback, and the app's default is
Tamil, so an unadorned request is answered in Tamil.

### 3.5 The final report

The report always carries the same four things:

* the files that changed,
* the diff you can read (bounded to 8000 characters in the conversation; the
  **Review diff** button shows all of it),
* the test outcome — pass, fail or "not configured",
* where the work was saved: the isolated worktree path.

Nothing was pushed, merged or installed, and the report says so.

### 3.6 A resume checks first

`task_is_resumable()` confirms that the worktree folder is still there and
that the starting commit still exists (`git cat-file -e <sha>^{commit}`). If
either is gone, JARVIS says so instead of pretending:

```
The worktree for that task is gone (C:\...\worktrees\project-a-…). Start the
task again.
```

A resumed task never restarts work that already ran: the code is already
changed in the worktree, so "continue" brings the card back and waits for your
next instruction.

### 3.7 Approval still decides everything

The model's suggestion is a **proposed plan**. Every launch, write, test
command and transfer still goes through the existing approval gateway
(`security/policy.py` → `Policy.approve/execute`, `agents/gateway.py` →
`Gateway.run`), with a one-use token and the Emergency Stop check. Each
approval names the exact action and its target:

```
codex_task: project-a · C:\work\project-a · website - Contact form validation
run_project_tests: project-a: pytest -q
```

### 3.8 What is remembered

Only what is needed, and all of it editable:

* the preferred language (Settings & Plugins),
* the editor for each project,
* the saved projects,
* the permitted routines (open without asking / run tests without asking),
* the project and the last task of the current conversation.

---

## 4. Tests

```
$ python -m pytest -q
678 passed, 3 skipped, 12 subtests passed in 298.79s
```

* **657 passed, 3 skipped** before this section (base `7ae2f12`),
* **+21 new tests** in `tests/test_context_assistant.py`,
* **0 failures**, no new skips.

The new tests cover, in order:

| Test | What it proves |
|---|---|
| `test_the_demo_workflow_is_understood` | The exact demo sentence gives project-a, VS Code, the change, the tests and no question. |
| `test_the_demo_workflow_asks_for_the_answer_in_tamil` | `Tamil-la sollu` → Tamil, `tell me in french` → French. |
| `test_a_follow_up_is_recognised_in_three_languages` | All four follow-ups in English and Tanglish; a new request is **not** a follow-up. |
| `test_two_projects_named_in_one_sentence_are_both_found` | Both names are found, which is what triggers the question. |
| `test_the_complete_workflow_reports_files_diff_tests_and_where_it_saved` | The whole workflow, and all four parts of the report. |
| `test_a_failed_test_is_visible_in_the_final_report` | A failing test is in the report and in the history row. |
| `test_a_missing_editor_is_reported_as_setup_needed` | The card says what to do, not only that it is missing. |
| `test_ambiguous_project_names_ask_a_short_question` | JARVIS asks instead of guessing. |
| `test_answering_the_question_starts_the_task` | The answer starts the right project. |
| `test_one_matching_project_is_not_ambiguous` | One match is not a question. |
| `test_the_conversation_remembers_the_project_and_the_task` | The project, the language and the task are remembered. |
| `test_a_follow_up_without_a_project_still_knows_the_project` | The remembered project is used. |
| `test_show_the_diff_reads_the_diff_back` | The diff comes from the worktree, not from a cache. |
| `test_run_the_tests_again_asks_for_approval` | The test command asks again. |
| `test_stop_this_task_cancels_that_task_only` | The task is cancelled; the assistant is still running. |
| `test_continue_that_task_resumes_from_the_saved_state` | The task comes back with its project. |
| `test_continue_says_why_when_the_worktree_is_gone` | A missing worktree is explained, not ignored. |
| `test_a_resume_checks_the_starting_commit` | A task whose commit is gone cannot be continued. |
| `test_the_preferences_are_editable_and_survive_a_restart` | Language, project, launcher and permitted routines survive a new window. |
| `test_the_language_is_remembered_from_the_request` | The language from the request is stored. |
| `test_the_memory_module_survives_a_fresh_window` | The memory itself is persistent. |

### Two Phase-1 assertions were made language-tolerant

The task card and the report used to be English-only. They now follow the
owner's language, so two assertions that pinned the English wording accept the
Tamil wording too:

* `tests/test_personal_codex_assistant.py` — the card's step labels,
* `tests/test_phase1_omega.py` — the report's test line.

No Phase-1 behaviour was weakened: both assertions still require the card to
show the project, the change, the steps and the outcome.

---

## 5. What you must check on your own PC

This was built and tested on Linux, without a Windows machine, without an
installed editor and without a provider key. The behaviour is real, but these
parts have to be confirmed on your machine:

1. **The real editor opens.** `code` (or your chosen editor) has to be on
   `PATH`, or configured as a launcher in Settings & Plugins. Here it is not
   installed, so the card correctly showed "setup needed" and the open step
   failed — the change and the tests still ran.
2. **The real Codex CLI runs.** The Codex wrapper is unchanged from Phase 1,
   but `npm i -g @openai/codex` and `codex login` have to be done on your
   machine. The tests replace the CLI with a stub.
3. **The real test command runs.** `pytest -q` is a stand-in. Point it at your
   own command.
4. **The real approval dialog.** The tests approve programmatically; the
   dialog itself is Phase 1 behaviour, unchanged.
5. **The Tamil rendering on Windows.** The report and the card were rendered
   in the offscreen Linux build. The text is the same code path, but check the
   font and the line breaks on your display.
6. **The diff button on a big change.** The conversation shows the first
   8000 characters of the diff; **Review diff** shows all of it.

---

## 6. Known limitations

* **The parser is a phrase table, not a model.** "Fix the contact form
  validation in project-a" is understood; "you know that thing we talked
  about in project-a" is not. This is deliberate: a request that writes code
  must be certain what was asked, so the wording has to be explicit. The
  model is still used for ordinary chat.
* **One project at a time.** A sentence that names two projects asks which
  one; it does not do both.
* **The memory is per application, not per session.** The project and the last
  task stay remembered until you clear them. The preferences are editable; the
  remembered task is not a setting.
* **A cancelled task cannot be continued.** "Stop this task" cancels it for
  good; the worktree is left on disk for you to look at.
* **The tests ran in this sandbox are not your tests.** The test command came
  from the saved project; the result in the report is that command's result
  on your machine.
* **The Omega globe crash in offscreen mode is still there.** It is not ours
  and it is not fixed by this section (`desktop/omega_visuals.py:280`).
* **Phase 1 is still not merged into `main`.** This section sits on `development`
  on top of the Phase 1 patch.

---

## 7. What was not done

* No key was read, stored, logged, or put in a prompt, a diff or a screenshot.
* No PC action flow, approval dialog or security policy was changed.
* No Omega mode, setting or workflow was removed or renamed.
* No release was published and `main` was not touched.
* Nothing was installed, pushed, merged or deployed — except this section's
  files, pushed to `development` for your review.
