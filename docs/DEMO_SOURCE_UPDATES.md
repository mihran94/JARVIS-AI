# Demo — prepared source updates, and JARVIS improving its own source

Every step below is something you can do in the running application.

---

## 1. Which provider does what

Open **Coding Assistant**.

```
Coding AI   [ MiniMax ▾ ]
```

Only **MiniMax** and **Codex** are in the list. Gemini answers you, reads the
proposed change and explains it; it never edits a file. The choice is kept,
so it is still there the next time you start JARVIS.

**AI Providers** still offers every provider for your own conversations, and
**Gemini** is the default.

---

## 2. Prepare a source revision for review

1. **Settings & Safety → Updates & rollback**.
2. Turn on **Automatically stage source updates from GitHub main** and approve
   it. Or press **Check and prepare a revision for review** to check once.
3. The status bar says the revision is being prepared.

While it runs, the version that is running does not change. Nothing is
selected, nothing is staged.

---

## 3. Read it before you approve it

**Settings & Safety → Review prepared changes**.

```
Prepared            Kind              Revision    Tests     Changed
2026-01-01 00:00    GitHub source     458b0139    passed    3 file(s)
```

Below it:

* the **diff**, so you can read what changed,
* the **test results**, with the summary line of the run,
* **Approve this exact revision** and **Reject**.

If the tests failed, the button stays disabled and the screen says why:

> *Tests: failed — Apply is disabled because the tests did not pass. Read the
> failure and prepare the change again.*

**Reject** leaves the running version exactly as it was.

---

## 4. Approve, and start it

1. **Approve this exact revision** — the approval dialog names the revision
   and its digest, so you know exactly what you are approving.
2. Close JARVIS and start it again from your original `START_JARVIS.cmd`.

The approved revision is the one that runs. The version it replaced is kept:
**Updates & rollback → Select previous code version (rollback)** brings it
back.

**If the prepared files changed after you looked at them**, the approval is
refused and you are asked to review it again. The approval is bound to one
exact revision.

---

## 5. Let JARVIS improve its own source

1. **Coding Assistant**, in the box at the bottom:
   *Describe an improvement to JARVIS itself…*
2. **Prepare this improvement**, and approve it.

JARVIS then:

1. makes a Git worktree for the change under the local `development/` folder,
   from the current commit,
2. asks the coding provider (MiniMax or Codex) for the change,
3. writes the changed files inside that worktree,
4. runs the tests there,
5. saves the diff, the test results and the exact revision.

The result waits for you in **Review prepared changes**, with the same Approve
and Reject.

Your working folder and your uncommitted files are never touched: the change
is made in the worktree, and the running installation is not the place where
it is made.

---

## 6. When the coding provider is rate limited

Say MiniMax is rate limiting your key while it is preparing a change:

```
MiniMax is rate limiting this key (HTTP 429). The task was saved and can be
resumed. Using Codex instead needs your approval.
```

* The task is **saved**. The goal, the provider, the reason and the worktree
  are in the task history, so it can be picked up again later.
* JARVIS does **not** quietly use Codex. If you want the other provider, you
  approve it, and the approval names the provider and the goal.

---

## 7. Keep JARVIS running in the background

**Settings & Safety** has two settings:

* **Keep JARVIS in the system tray when the window is closed** — close the
  window and JARVIS stays in the tray. The tray menu has:

  ```
  Show JARVIS
  Run in background
  Pause JARVIS
  ─────────────
  Exit JARVIS
  ```

  **Pause JARVIS** stops the automatic source check and the background
  preparation of changes. Nothing is closed and nothing is lost: the saved
  work stays in the task history, and **Resume JARVIS** starts it again.

* **Start JARVIS when Windows signs in** — Windows only. It writes your own
  Run key entry, using the same launcher `START_JARVIS.cmd` uses, and removes
  it again when you switch the setting off.

---

## 8. Running the checks without Windows

The tests replay the whole workflow with the GitHub download, the provider
call and the test command replaced, so the behaviour can be checked without a
Windows machine, a key or an editor:

```cmd
.venv\Scripts\python.exe -m pytest -q tests\test_source_updates.py tests\test_provider_routing.py tests\test_development_workflow.py tests\test_review_panel.py -v
```
