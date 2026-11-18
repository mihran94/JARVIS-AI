# JARVIS AI — source and system audit, and the JARVIS PRIME interface

**Audit date:** 2026-11-18
**Branch:** `feature/jarvis-prime-interface-20261118` → `main`
**Baseline:** `f379ce6` — *Merge MARK LVII chat and Island improvements (#38)*, the latest `main`.
**PR:** #40 — *JARVIS PRIME — the premium interface the application never showed*
**Status:** Ready for review. `main` is not touched, nothing is released.

---

## Part 1 — The audit (Phase 1 of the brief)

The repository was inspected as it is, not as the documentation describes it.
Three subsystems were read end to end, and the results are below.

### 1.1 What the application actually is today

* The **navigation sidebar is hidden** (`app.py:366-369`). Navigation is the
  toolbar buttons, the command system and the dock, which is hidden by default
  in command-first mode (`omega.py:692-697`).
* The **chat-first layout already exists** (`app.py:992-1126`): an orb, the
  holographic reactor, a transcript and one input. The provider and voice
  controls are re-parented into Settings (`app.py:2218`), so the chat page
  itself is already close to what the brief asks for.
* **The premium look was never applied.** `STYLE = PERSONAL_STYLE` was defined
  (`app.py:101`) and only the tests ever set it (`tests/test_desktop.py:9`). The
  shipping application rendered in the default light Qt theme — until the
  Omega controller replaced the window's stylesheet with a flat, fifteen-line
  sheet (`omega_visuals.py:27-75`).
* **The dock is already hidden by default** in command-first mode, and the
  brief's "no giant dock by default" is therefore already true.

### 1.2 The command system

`developer_studio/commands.py` is a **deterministic phrase and slash table**:
thirteen command kinds, addressed forms ("Jarvis, …"), a small Tamil/Tanglish
natural dictionary, and slash routing. Unknown slash commands are answered
locally and are never forwarded to a paid provider.

There is **no AI-assisted intent layer**. The brief asks for one; that is the
largest single piece of work still outstanding.

### 1.3 The provider router

Eight providers are registered. `providers/routing.py` already encodes the
brief's rule — the person-facing provider is Gemini by default, and only
MiniMax or Codex may write source code — but **the desktop never calls the
selection policy**: it reads the combo box directly (`app.py:4057`). The rule
is therefore documentation and a guard, not the routing that runs.

Approved fallback exists and is narrow: one backup attempt, only for
network/timeout/transient failures, and only before any text was emitted. A
rate limit is deliberately **not** backup-eligible. A local model never falls
back to a paid cloud provider — that is blocked in three places.

There is **no retry and no saved-pending-request queue** for a chat that
fails: the prompt is already in the history, and the owner is told to retry.

### 1.4 Voice, memory, mobile, developer tools, permissions, updates

| Area | What the code does |
|---|---|
| Voice | Three languages (en/ta/fr), SAPI for speech and Windows System.Speech for recognition. A wake phrase, three explicit talk modes, an echo guard, and interruption. The microphone is **never** opened without the owner's checkbox. Whisper/Piper/ElevenLabs exist only in `legacy/` and are listed as unverified. |
| Memory | Local SQLite, BM25 search over title, body and tags. Notes reach a provider only through the per-message "Include notes once" box. There is **no edit button and no export** in the UI. |
| Mobile | HTTPS only (plaintext is refused unless explicitly allowed), HMAC-SHA256 request signing with a nonce replay guard, a secret in Windows Credential Manager, revocation, and a signed WebSocket for the phone. **There is no certificate pinning.** The Android release build needs a keystore that is not in the repository, and cannot be built here — no JDK. |
| Developer Studio | Project registration, five editors with real launchers, a detached Git worktree so the owner's uncommitted files are never touched, a diff against the starting commit, and secret-named files restored and excluded from the diff. |
| Automation | App launch from an allowlist, the three creative editors, typing into Notepad only with the foreground window verified, file reads and writes inside a confined workspace, and read-only window inspection. **No screenshot capability.** No arbitrary shell, ever. |
| Permissions | Every action goes through `Gateway.run` → a one-use token bound to (ticket, action); Emergency Stop bumps the generation and clears every grant. Read-only actions check the stop but need no token. |
| Updates | The download verifies every file against the commit's Git tree. A candidate is prepared and tested, the running version is not touched, the approval is bound to one exact revision, and the previous release is kept for rollback. |

### 1.5 The capability inventory

| Capability | State |
|---|---|
| Chat with eight providers, streaming, cancellation | **Working** |
| Gemini as the person-facing default | **Working** (routing policy written; not yet the path the desktop takes) |
| Source work limited to MiniMax or Codex | **Working** (guard present; the desktop still takes the combo box) |
| Approved provider fallback, never local → paid | **Working** |
| Conversation memory, follow-ups, clarification, reply language | **Working on PR #39**, not in `main` |
| Tamil/Tanglish/English understanding | **Working** (deterministic table, no AI layer) |
| Multi-step conversation plans with per-step approval | **Working** (results are not verified) |
| Developer Studio: projects, editors, tests, worktree, diff | **Working** |
| PC automation: launch, type, files, window inspection | **Working** |
| Permission gateway, one-use approvals, Emergency Stop | **Working** |
| Source updates: verify, prepare, test, approve, roll back | **Working** |
| Memory search, notes with consent | **Working** |
| Voice: STT, TTS, wake phrase, echo guard, consent | **Working** (needs the hardware) |
| Android remote: HTTPS, HMAC, pairing, revocation | **Working** (certificate pinning missing) |
| Premium interface, light and dark themes | **Working on this branch** |
| AI-assisted intent interpretation | **Missing** |
| Per-task-type provider routing in the running path | **Missing** |
| Saved pending request, automatic resume after a rate limit | **Missing** |
| Result verification for conversation plans | **Missing** |
| Memory edit and export | **Missing** |
| Screenshot capability | **Missing** |
| Certificate pinning for the Android client | **Missing** (PR #27 is open) |
| Document intelligence (PDF and document reading) | **Missing** |
| Command history and reuse | **Missing** |
| Smart task planner with visible checkpoints | **Partial** (conversation plans, up to six steps) |
| Settings search | **Missing** |
| Microphone, Tamil speech quality, phone pairing, Emergency Stop on real hardware | **Requires PC hardware testing** |
| Windows installer and signed release | **Requires PC hardware testing** |
| Android APK | **Requires PC hardware testing** (no JDK here) |

---

## Part 2 — What this branch delivers

### 2.1 JARVIS PRIME: the premium interface the application never showed

The interface was plain, and the premium stylesheet in the repository was
never applied to the running application. This branch builds one visual
system and puts it in front of the owner.

* **A palette-driven premium stylesheet** (`desktop/prime_theme.py`). The
  Omega palette the owner already chooses — MARK LVII, Midnight Blue, Apple
  Silver, Dark Titanium — still decides the colours, so nothing about the
  accepted theme behaviour changes. What is new is the quality: glass
  surfaces, rounded corners, one accent, and one set of hover, focus,
  disabled and pressed states for every control.
* **The surfaces are genuinely translucent.** Qt's stylesheet engine ignores
  the alpha of `rgba()` when it paints a widget background, so the panels use
  the alpha-first eight-digit form Qt does honour. This was found by
  rendering the real window, not by reading the code.
* **The composer belongs to the window.** It was inside the scrolling chat
  page, so at a normal window size the input and its buttons fell below the
  fold. The composer is now the window's own bottom bar: the conversation
  scrolls, the input never leaves the screen.
* **The Emergency Stop is readable.** It had no visible label in the new
  sheet.
* **The interface theme is in Settings.** One control, the owner's palette,
  with a light one and three dark ones.
* **The chat surface is named.** The transcript, the composer, the task card
  and the approval card carry object names, so the sheet can style them as
  cards instead of leaving them as flat rectangles.

Nothing was removed. No module was rewritten for looks alone: the Omega
controller still paints the window with the palette, and the dock, the Island,
the pages and every command behave exactly as before.

### 2.2 Before and after

| | |
|---|---|
| Before | The composer and its buttons below the fold, a flat black page, an Emergency Stop with no visible label, and a stylesheet that only the tests ever applied. |
| After | The composer pinned to the window, glass cards with luminous edges, a readable Emergency Stop, and the premium stylesheet applied to the running application. |

Both screenshots are of the **real application** — the same window, the same
data folder, the same launch path (`enable_omega` with the normal, non-smoke
start). The "before" is `main` at `f379ce6`; the "after" is this branch.

They are delivered with the hand-back rather than committed, because the
repository's push path carries text only. To reproduce them:

```python
from pathlib import Path
from PySide6.QtWidgets import QApplication
from core.store import Store
from desktop import prime_theme
from desktop.app import Window

app = QApplication.instance() or QApplication([])
base = Path('/tmp/jarvis-shot'); base.mkdir(parents=True, exist_ok=True)
prime_theme.apply_theme(app, Store(base / 'history.sqlite3'))
window = Window(base)
window.enable_omega(smoke=False)
app.processEvents()
window.resize(1180, 800); window.show()
app.processEvents()
window.grab().save('/tmp/jarvis-prime-after.png')
```

### 2.3 Tests

```
$ python -m pytest -q
795 passed, 3 skipped, 12 subtests passed
```

`main` at `f379ce6` gives 786 passed, 3 skipped, so the nine new tests in
`tests/test_prime_theme.py` are the whole difference. Two accepted tests were
adjusted, both for the same reason and both keeping their intent:

* `tests/test_one_jarvis_dashboard.py` asserted the stylesheet was the old
  personal theme; it now asserts it is the premium dark theme.
* `tests/test_omega.py` asserted one literal stylesheet rule; it now asserts
  that the palette the owner chose decides the ground and the ink.

### 2.4 What is still open

Phase by phase against the brief:

| Phase | State |
|---|---|
| 1 — audit | **Done**, in this document. |
| 2 — premium interface | **This branch**: the visual system, the chat surface, the light and dark themes. Still open: 125/150/200 % scaling is not handled explicitly, and the settings are not searchable. |
| 3 — Dynamic Island | Already real: drag, persisted position, expansion to an input, real worker state, no fake percentages. Still open: a global hotkey. |
| 4 — universal command centre | The deterministic parser and the conversation plans exist. **The AI-assisted intent layer is still missing** — that is the next piece of work. |
| 5 — advanced AI | The routing policy exists; the desktop does not use it yet. **No saved-pending-request resume.** |
| 6 — developer studio | Already working, including the isolated worktree and the diff. The conversation memory that ties it together is on PR #39. |
| 7 — safe PC assistant | Already working, with the permission gateway and the Emergency Stop. No screenshot capability. |
| 8 — memory and context | The search works; **edit and export are missing**. |
| 9 — voice | Already working; the hardware acceptance is still pending. |
| 10 — mobile remote | Already working; certificate pinning is missing and PR #27 is open. The APK cannot be built here. |
| 11 — productivity features | The conversation plan is the beginning of a task planner. Document intelligence, command reuse and smart recovery are missing. |
| 12 — settings | The theme control is added here. The sections are one page; there is no search. |
| 13 — architecture | The layering is already reasonable; this branch adds a module and does not move any. |
| 14 — testing | Done here to the extent this environment allows; the hardware rows are marked unverified. |
| 15 — delivery | The branch, the PR, the tests and the screenshots are here. |

### 2.5 What the owner has to check on a real machine

1. The interface at 125 %, 150 % and 200 % scaling.
2. The Tamil text in the interface on a real display.
3. The microphone permission, the Tamil speech input and the spoken reply.
4. The Android pairing, a remote job, the revocation and the reconnection.
5. The Emergency Stop during a real task.
6. The Windows installer: install, launch, restart, uninstall.
7. The Android APK — it needs a signing keystore that is not in the repository.
