# Demo — the context-aware task assistant

A complete walk-through of the workflow this section adds, in the owner's own
words. Every line below is what you type in **Chat**, and what JARVIS does with
it.

---

## 0. Before the demo

1. **Settings & Plugins → Saved projects and editors → Add project folder**
   Choose the project folder, name it `project-a`, pick **VS Code**, and type
   the local test command (for example `pytest -q`).
2. Install and sign in to the coding CLI:
   `npm i -g @openai/codex` then `codex login`.

---

## 1. The workflow, in one message

Type this in **Chat**:

```
JARVIS, website project-a VS Code-la open pannu. Contact form validation
fix panni tests run pannu. Enna change pannina nu Tamil-la sollu.
```

JARVIS reads it as:

| | |
|---|---|
| Project | `project-a` |
| Tool | VS Code |
| Requested change | `website - Contact form validation` |
| Steps | open the project → change the code → run the tests → report |
| Answer language | Tamil (from `Tamil-la sollu`) |

**What happens next, step by step:**

1. **Opening the project** — JARVIS shows the task card: the project, the
   folder, the editor, the change and the steps. If the editor is not
   installed, the card says **SETUP NEEDED** and what to do about it.
2. **The change** — JARVIS asks for approval, showing the exact action and
   target:
   ```
   codex_task: project-a · C:\work\project-a · website - Contact form validation
   ```
   On approval, JARVIS creates an **isolated Git worktree** from the
   project's `HEAD` — your working folder and your uncommitted files are never
   touched — and runs Codex inside it.
3. **Collecting the diff** — JARVIS reads `git diff` against the commit the
   task started from, so committed edits, uncommitted edits and new files are
   all in it.
4. **The tests** — the test command gets **its own approval**, because it is a
   command that runs on your machine:
   ```
   run_project_tests: project-a: pytest -q
   ```
   The tests run off the interface thread, so the window stays responsive.
5. **The final report**, in Tamil because you asked for Tamil:

   ```
   1 file(s) changed against 7bf3fc69. The diff is below and the worktree is
   at C:\Users\...\JarvisAI\worktrees\project-a-…

   மாற்றப்பட்ட கோப்புகள்: app.py
   பரிட்சை முடிவு: passed
   பார்க்கக்கூடிய வேறுபாடு:
   diff --git a/app.py b/app.py
   …
   சேமிக்கப்பட்ட இடம்: C:\Users\...\JarvisAI\worktrees\project-a-…
   ```

---

## 2. Follow-ups, in the same conversation

The conversation remembers the project and the last task, so these need no
project name.

| You type | What JARVIS does |
|---|---|
| `show the diff` / `diff kaattu` | Reads the diff back out of the saved worktree and shows it. |
| `run the tests again` / `tests run pannu` | Asks for approval of the exact command, then runs it in the same worktree. |
| `continue that task` / `continue pannu` | Checks the worktree and the starting commit are still valid, then brings the task back so you can carry on. |
| `stop this task` / `stop pannu` | Stops that task only — the assistant keeps running. |
| `also fix the logout validation` | Uses `project-a`, because this conversation is about it. |

**If the worktree is gone**, JARVIS says so instead of pretending:

```
The worktree for that task is gone (C:\...\worktrees\project-a-…). Start the
task again.
```

---

## 3. When two projects could be meant

Save a second project also called `website`, then type:

```
website project-a fix the contact form validation
```

JARVIS does **not** guess. It asks:

```
Which project do you mean? Choose one: website, project-a.
```

Answer with the project name and the task starts.

---

## 4. When a test fails

The final report says so plainly, in the language you asked for, and the task
is recorded as **failed** in **Task History** — because the job was to make the
change *and prove it*:

```
பரிட்சை முடிவு: failed
```

The task row in the history keeps the whole story:

```
codex_task · failed · tests=failed · files=1 · worktree=C:\...\worktrees\project-a-… · from=7bf3fc69
```

---

## 5. Preferences

Saved, editable, and they survive closing the application:

| Preference | Where |
|---|---|
| Preferred language | **Settings & Plugins → Saved projects and editors → Assistant language** |
| Editor for each project | the project row in the same table |
| Projects | the same table |
| Permitted routines | **Open the selected project without asking** / **Run the selected project's tests without asking** |

---

## 6. Running the demo without a Windows machine

The repository ships an offline harness that replays the whole workflow with
the Codex CLI and the test command replaced, so you can watch the conversation
without a provider key, a Windows editor or a project:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_context_assistant.py -v
```

`test_the_complete_workflow_reports_files_diff_tests_and_where_it_saved`
replays the exact demo message and checks the report that comes back.
