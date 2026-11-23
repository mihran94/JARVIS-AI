# JARVIS AI — development coverage

**Base of this work:** `c4d3533602e432bbe6c757e2c8c6d15554d143f5` (`main`, the supplied baseline)
**Branch:** `dev/jarvis-complete-implementation-20261123`
**Scope of this document:** every requirement in the owner's master prompt and in the current
instruction, mapped to the implementation that reaches it.

## How to read the two statuses

| Column | Meaning |
|---|---|
| **Implementation** | The code exists, is wired to a real entry point, and is not a placeholder. |
| **Verification** | What has actually been *run*. `PASS` means a test in this repository ran it. `NOT RUN` means the code is written and tested in part, but the thing itself has not been executed on real hardware or against a live service. |

**Nothing in this document is marked verified because it looks right.** A file name, a TODO, a mock
response or a disconnected helper is not evidence. Where something is missing, it says so.

## The three outcomes, separately

1. **Coding completion** — see the table. Work that is implemented, with its tests.
2. **GitHub publication** — the branch is pushed and one draft pull request targets `main`. Merging
   waits for the owner.
3. **Runtime verification** — almost nothing in this document is runtime-verified, because this
   work was done on Linux with no Windows machine, no owner accounts and no paid API keys. The
   acceptance procedures in `docs/ACCEPTANCE_PROCEDURES.md` say exactly how each one is run.

## A limitation that affects the whole document

**The supplied archive `JARVIS-AI-all-source.zip` and the file `JARVIS-ALL-PROMPTS.md` were not
present on the machine this work was done on.** They were not in the workspace, not in the Drive
and not anywhere on the filesystem. The work was therefore carried out against the **real Git
repository** at the stated baseline, which is the better source anyway: it is the newer checkout,
it has the history, and it includes everything merged since the archive was cut.

Two files the archive was said to carry outside Git —
`desktop/history_backup_settings.py` and `memory/windows_backup.py` — were therefore **written from
scratch** to the specification in §9 and §10, rather than recovered. They are listed under §9 below.

---

## §1 Work order and authorisation

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| One development copy, commits on a branch | `dev/jarvis-complete-implementation-20261123` from `c4d3533` | `git log` | 11 commits, history preserved | Done | PASS (history inspected) |
| Push the branch, one draft PR against `main` | see §13 | GitHub | draft PR, `main` untouched | Done | PASS (SHA compared) |
| Regression tests beside the code | `tests/test_windows_backup.py`, `test_history_backup_settings.py`, `test_mission_conversation.py`, `test_downloads.py`, `test_cybersecurity.py`, `test_automation_uia.py` | pytest | 5 new files | Done | PASS |
| Do not merge into `main` | no merge performed | — | `main` still at `c4d3533` | Done | PASS |
| No trading features | none exist | — | — | Done | PASS (tree scan) |

## §2 The correct development copy

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| Fetch current remote `main`, record the full SHA | `c4d3533602e432bbe6c757e2c8c6d15554d143f5` | `git ls-remote` | SHA recorded here and in the PR | Done | PASS |
| Inspect open PRs and development branches | 19 open PRs and 101 branches listed; ancestry checked with `git merge-base` | — | list below | Done | PASS |
| Reuse earlier integration work with unique changes | **PR #88** (`dev/windows-verified-mission-launch`) merged into this branch as commit `1d67821` | `git log c4d3533..HEAD` | 6 commits carried forward | Done | PASS |
| Do not blindly merge a divergent legacy UI | the remaining open PRs are a stacked series targeting each other, not `main`; none was merged | — | only PR #88 was carried | Done | PASS |
| Keep historical files unless removal is approved | `legacy/` untouched (114 files) | — | — | Done | PASS |
| Preserve artwork, memories, migrations, backups, CMD launch | `START_JARVIS.cmd`, `setup.cmd`, `VERIFY_JARVIS.cmd`, `ROLLBACK_JARVIS.cmd`, `DIAGNOSE_JARVIS.cmd`, `docs/desktop-preview.png`, `iphone-pwa/icons/` all untouched | — | — | Done | PASS |
| Requirement coverage file | this document | — | — | Done | — |
| No trading features | none | — | — | Done | PASS |

**The open PRs that were inspected and what they hold:**

| PR | Base | Unique? | Decision |
|---|---|---|---|
| #88 `dev/windows-verified-mission-launch` | `main` | **Yes** — verified Windows mission launches, verified Notepad typing, text export, verified browser drafts, browser cleanup on cancel, owner-set mission budgets | **Merged** into this branch |
| #87 `integration/unify-approved-hud` | `main` | No — already in `main` at `c4d3533` | Nothing to do |
| #84 `feat/jarvis-suggestion-mode` | `main` | No — already merged | Nothing to do |
| #74, #72, #68, #66, #63…#46 | a chain of each other | Not against `main`; each depends on the one below it | Not merged; the chain is still in review by the owner |

## §3 One main assistant, one cybersecurity interface

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| One Main JARVIS conversation | `desktop/app.py` `send()` → the chat worker, one session | composer | one conversation | Done | PASS |
| One separate authorized Cybersecurity interface | **NEW** `cybersecurity/` + `desktop/cybersecurity_panel.py`, its own page and dock entry, no mission tool reaches it | Settings → dock → Cybersecurity | separate page | Done | PASS |
| Cyan M Guardian / M Signature Quantum HUD | `desktop/prime_ui.py`, `desktop/omega_visuals.py`, `fix/quantum-m-hologram` merged in #87 | window startup | the M and the hologram | Done | NOT RUN (no Windows machine) |
| Floating assistant and voice feedback | `desktop/omega.py` `FloatingAssistant`, `voice/voice_panel` | — | — | Done | NOT RUN |
| Actual application events for idle/listening/thinking/working/speaking/approval/completed/failed/stopped/disconnected | `desktop/app.py` `prime_state()`, `set_ai_visual_state()` | — | state drives the HUD | Done | PASS (unit) / NOT RUN (visual) |
| Restore conversation history at startup | `core/store.py` `messages()`, `render_chat()` | startup | the chat reopens | Done | PASS |
| Show the actual provider and model | `refresh_brain_label()` | top bar | provider and model shown | Done | PASS |
| Theme persistence, Dynamic Island, Suggestion Mode, readable errors, Windows scaling, emergency-stop visibility | `desktop/prime_theme.py`, `desktop/prime_ui.py` `PrimeShell`, `update_suggestion_mode()`, `desktop/app.py` `stop()` | — | — | Done | PASS (code) / NOT RUN (visual, scaling at 100/125/150/200 %) |
| Obsolete branding, duplicate orbs, retired dashboards out of the visible product | `legacy/` is kept on disk but not mounted; `fix/retire-legacy-hud` merged | — | one visible interface | Done | PASS |
| One startup and fallback route uses the approved interface | `main.py` → `desktop.app.main()` → `enable_omega()` → `enable_prime()` | `START_JARVIS.cmd` | — | Done | PASS |

## §4 The main agent and AI routing

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| Goal → Understand → Plan → Select tool → Approve → Execute → Observe → Verify → Recover/Finish | `core/mission.py` `AgentRuntime.run()` — the loop is plan, validate, approve, execute, observe, verify | **NEW** `/mission <goal>` or the **Work on this** composer button → `desktop/app.py` `send()` → `start_mission_from_chat()` → `MissionController.start()` | the mission runs and the answer returns into the conversation | Done | PASS |
| Tamil, Tanglish, English, French | `core/conversation.py` `ASSISTANT_GUIDANCE`, `providers/task_brain.py`, `detect_reply_language()` | composer | the answer comes back in the owner's language | Done | PASS (unit) / NOT RUN (live) |
| Follow-up context | `core/store.py` `messages()` carried into every request | — | — | Done | PASS |
| Fast/Deep effort | `providers/task_brain.py` `effort_for()`, `providers/profiles.py` | — | — | Done | PASS |
| Multi-step decomposition | the mission runtime, up to six steps | — | — | Done | PASS |
| Persistent task history | `core/store.py` `tasks()`, `core/mission.py` `Mission` | — | — | Done | PASS |
| Configurable bounded batches | PR #88: `MissionController.max_steps` and the mission budget | Mission Control | — | Done | PASS |
| Checkpoints | PR #88: `checkpoint()` is checked after each approval, so a deadline that passes during an approval still ends the mission | `core/mission.py` | — | Done | PASS |
| Pause/resume | the Emergency Stop cancels a mission and it can be started again; an interrupted mission is never replayed by itself | `desktop/app.py` `stop()` | — | Partial | PASS (cancel) / NOT RUN (resume of the same mission) |
| Safe retries | a failed step is never re-run automatically; the owner starts again | `core/mission.py` | — | Done | PASS |
| Interrupted-task recovery | `core/store.py` marks running rows `interrupted` at startup and never replays them | startup | — | Done | PASS |
| A timeout or step limit produces an accurate state | `Mission.status` is `completed`, `failed`, `cancelled` or `running`; the limit ends it with a `failed` mission and the reason | — | — | Done | PASS |
| Never replay a consequential action because the process stopped | `agents/queue.py`, `agents/workflows.py` — interrupted rows are terminal | — | — | Done | PASS |
| Approval bound to the exact action, arguments, target and spending boundary | `core/mission.py` builds `Action('mission_tool', summary)` from the tool name and the exact arguments; the approval dialog shows that summary | `agents/gateway.py` | the dialog names the call | Done | PASS |
| Generated prose separate from executable calls | `core/mission.py` `parse_decision()` accepts one JSON envelope; prose is refused | — | — | Done | PASS |
| Task ID, timestamps, redacted result, observed evidence, verification outcome | `core/mission.py` `Mission` (id, created, `tools_used` with the redacted result, `events`) | — | — | Done | PASS |
| Approval, dispatch and completion distinct | `agents/gateway.py` `approve()` → `execute()` → the store records each state | — | — | Done | PASS |
| Emergency Stop reaches active workers and prevents queued follow-up actions | `desktop/app.py` `stop()` → `policy.stop()` → the mission's `check()` raises at the next step; `agents/queue.py` `cancel_pending()` | — | — | Done | PASS |
| Gemini as the preferred conversation/planning brain | `providers/registry.py`, `providers/task_brain.py` — Gemini is the default provider | — | — | Done | PASS (registry) / NOT RUN (live) |
| Development tasks routed to OpenAI or MiniMax | `providers/task_brain.py` `select_route()` | — | — | Done | PASS (unit) / NOT RUN (live) |
| Claude, DeepSeek, Groq and local integrations preserved | `providers/claude.py`, `providers/registry.py`, `providers/ollama.py` | — | — | Done | PASS |
| Validate credentials, discover models through official APIs | `providers/models.py` `list_models()`, `check_model()` | Settings → AI Providers | — | Done | PASS (unit) / NOT RUN (live API) |
| Respect custom settings, owner budgets and paid-fallback consent | `providers/selection.py`, `providers/stream_fallback.py`, `providers/pricing.py`, `backup_consent` | — | — | Done | PASS |
| Record measured reliability and latency | `core/store.py` `usage` table, `providers/task_brain.py` reads `usage_rows()` | — | — | Done | PASS |
| Estimated costs labelled | `providers/pricing.py` `estimate()`, `docs/` labels it an estimate | — | — | Done | PASS |
| Secrets in Windows credential facilities, out of history, logs and source | `security/vault.py` (Credential Manager only), `remote/secrets.py`, `core/protection.py` keeps secret-named files out of model context | — | — | Done | PASS |

## §5 Real Windows automation

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| Preserve the owner-reported ability to open Notepad | `automation/windows.py` `launch_app()` | mission tool `launch_app` | Notepad opens | Done | PASS (unit) / NOT RUN (Windows) |
| Installed-app discovery | PR #88: `automation/windows.py` `system_app_directory()`, `launch_editor()` | mission tool `launch_app` | — | Done | NOT RUN (Windows) |
| Process/window identification | `automation/win_controls.py` `foreground_process()`, `automation/inspection.py` | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| UI Automation, accessible controls, menus, dialogs | **NEW** `automation/uia.py` — reads the Windows accessibility tree through the .NET `UIAutomationClient` assembly and turns it into plain elements that can be found by the name the owner sees, by type or by automation id. `unexpected_dialogs()` finds a dialog that was not expected | mission tool `inspect_window` | the controls of a window are listed | Done (written) | PASS (the model and the dialog rule) / NOT RUN (the .NET binding, which needs Windows) |
| Keyboard, mouse, scrolling, shortcuts | **PARTIAL** — `automation/desktop_tasks.py` sends Unicode keystrokes (`KEYEVENTF_UNICODE`) into a validated target. There is no mouse, no scrolling and no shortcut layer | `parse_desktop_task()` | — | Partial | PASS (unit) / NOT RUN (Windows) |
| Approved screen observation | **GAP** — `computer_vision/` exists but the Windows screen-capture path for the assistant is not wired to a mission tool | — | — | **Not implemented** | — |
| Switching between applications | `automation/input.py` `activate_window()` brings one forward, and refuses when the process has more than one visible window, because the target would be ambiguous | — | — | Done (written) | PASS (the refusal) / NOT RUN (Windows) |
| Validate the intended window and process before every focus-dependent input | `automation/input.py` `validate_focus()` — the process in front is checked before every action, and the action stops when it moved. `automation/desktop_tasks.py` does the same for the editor it types into | `automation/input.py` | — | Done | PASS (unit) / NOT RUN (Windows) |
| Stop safely if focus changes, the target is ambiguous or a dialog appears | `automation/input.py` raises `FocusLost`, `AmbiguousTarget` and `UnexpectedDialog`, and sends nothing. `automation/win_controls.py` refuses a `#32770` dialog class and a focus that is not inside the foreground window | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| Approved open, edit, save and export | PR #88: mission tool `export_text` writes and reads back; `save` of an open document is **not** implemented | mission tools | — | Partial | PASS (unit) / NOT RUN (Windows) |
| Verify the result using application state or file contents | PR #88: `VerifiedEdit` (the editor's own contents) and `export_text` (the file read back) | — | — | Done | PASS |
| A click, keystroke or launch is evidence only for that action | PR #88: `launch_app` says "Windows confirmed its foreground process"; `type_notepad` says the editor returned the expected text | — | — | Done | PASS |
| Type a Tamil sentence in Notepad and verify the saved text | `automation/desktop_tasks.py` sends Unicode, `win_controls.py` reads it back; **saving the file is not implemented** | — | — | Partial | PASS (unit) / NOT RUN (Windows) |
| Calculator result into Notepad | **GAP** — there is no Calculator adapter; `automation/windows.py` can launch Calculator but cannot read its result | — | — | **Not implemented** | — |

## §6 Browser, website and business automation

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| Extend the existing Playwright/Edge implementation | `automation/browser.py` | `desktop/browser_control.py` | — | Done | PASS |
| Authorized persistent sessions, tabs, navigation, live inspection, form filling | `automation/browser.py` | — | — | Done | PASS (unit) / NOT RUN (live) |
| Drafts, approved uploads/downloads, bounded waits, cancellation | `automation/browser.py`; PR #88 adds a verified browser draft to the mission | mission tool | — | Done | PASS |
| Error recovery and outcome verification | PR #88: the draft is verified after it is written | — | — | Done | PASS |
| AI Creative Studio, Fiverr, Flow, Higgsfield, Canva, social | `business/drafting.py`, `business/studio_inbox.py`, `video_studio/planning.py`, `quantum_core/launcher.py` | — | drafts prepared, nothing sent | Done | PASS (unit) / NOT RUN (live) |
| Website inspection and approved source corrections | `developer_studio/inspection.py`, `core/development.py` | — | — | Done | PASS (unit) / NOT RUN (live) |
| Exact approval before sending, publishing, deploying or spending credits | `agents/gateway.py`; the business flow produces a draft for review and never sends | — | — | Done | PASS |
| Pause for login, CAPTCHA or manual intervention | `automation/browser.py` reports the state instead of guessing | — | — | Done | PASS |
| Webpage content is untrusted and cannot authorize another tool | `core/protection.py` keeps untrusted content out of the model context; `research/research.py` answers only from the fetched text | — | — | Done | PASS |
| No invented selectors, generation results or successful uploads | every browser result is read back from the page | — | — | Done | PASS |
| **Web Download Center** | **NEW** `core/downloads.py` — URL and redirect validation, private-network refusal, bounded streaming, safe Windows file names, progress, cancellation, history | `core/downloads.py` `download()` | a file is written and measured | Done | PASS (23 tests) |

## §7 Creative software and coding workflows

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| After Effects projects, composition changes, renders | `video_studio/after_effects.py`, `after_effects_timeline.py` | video page | — | Done | PASS (unit) / NOT RUN (After Effects) |
| Photoshop edits and saves | **GAP** — the plugin switch exists (`EDITOR_EXECUTABLES`), but there is no edit-and-save adapter | — | — | **Not implemented** | — |
| Documented DaVinci Resolve scripting | **GAP** — the executable switch exists; no scripting adapter | — | — | **Not implemented** | — |
| Feasible CapCut operations and the FFmpeg pipeline | `video_studio/capcut.py`, `video_studio/editing.py` | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| Detect installed capabilities | `core/assistant_capabilities.py` `snapshot()`, `plugin_enabled()` | — | — | Done | PASS |
| Distinguish launch, modification, export and verified output | the four states are separate in the store and the UI | — | — | Done | PASS |
| Propagate cancellation to the right worker | `desktop/app.py` `stop()` cancels each worker kind | — | — | Done | PASS |
| Verify output media before reporting success | `video_studio/preview.py` | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| Open VS Code or another configured editor | `developer_studio/editors.py`, `automation/windows.py` `launch_editor()` | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| Repository inspection, source search, code generation, controlled edits, patches | `developer_studio/inspection.py`, `context.py`, `generation.py`, `core/coding_agent.py` | — | — | Done | PASS |
| Dependency inspection, isolated worktrees | `developer_studio/projects.py`, `core/coding_tasks.py` | — | — | Done | PASS |
| Failure analysis, approved command execution, test/build output capture | `developer_studio/runner.py`, `core/development.py` | — | — | Done | PASS |
| Git diff review, branch preparation, PR preparation | `developer_studio/commands.py` | — | — | Done | PASS (unit) / NOT RUN (live Git) |
| Protected paths, backups, rollback and approvals effective | `core/protection.py` (secret files), `developer_studio/workspace.py` backups, `agents/gateway.py` | — | — | Done | PASS |
| Never expose an unrestricted shell to model text | `core/protection.py`, `developer_studio/runner.py` — commands are a fixed set, each approved | — | — | Done | PASS |

## §8 Multilingual voice, wake and audio settings

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| VoicePanel, main conversation and API Settings integration | `desktop/voice_panel.py`, `desktop/azure_voice_settings.py` | Settings → Voice | — | Done | PASS |
| Optional Azure neural TTS for Tamil, English, French | `voice/azure_tts.py` | — | — | Done | PASS (unit) / NOT RUN (no Azure key) |
| Language-aware Tanglish handling | `voice/text_tools.py`, `detect_reply_language()` | — | — | Done | PASS |
| Compatible voice discovery | `voice/azure_tts.py` | — | — | Done | PASS (unit) / NOT RUN (live) |
| Persistent "Read replies aloud" | `desktop/app.py` `read_replies` stored in the settings store | composer | — | Done | PASS |
| Azure key stored securely, region configurable, permission before sending text | `security/vault.py`, `desktop/azure_voice_settings.py` | — | — | Done | PASS |
| Estimated usage shown | `providers/pricing.py`; voice usage is **not** yet estimated | — | — | Partial | — |
| Local Windows speech as fallback | `voice/windows_tts.py`, `voice/windows_stt.py` | — | — | Done | PASS |
| Test Tamil / English / French Voice, microphone test, speaker test | `desktop/audio_test.py`, `desktop/azure_voice_settings.py` | Settings → Voice | — | Done | PASS (unit) / NOT RUN (no audio device) |
| Missing keys, unsupported voices, network failures, device changes, disconnections, cancellation, text fallback | `voice/errors.py`, `voice/azure_tts.py` | — | — | Done | PASS (unit) |
| Consent-based push-to-talk and wake behaviour | `voice/consent.py`, `voice/wake.py` | — | — | Done | PASS |
| The wake animation is driven by the actual wake event | `desktop/app.py` `on_wake_detected()` → `set_ai_visual_state()` | — | — | Done | PASS (code) / NOT RUN (visual) |
| Never open the microphone without consent; never advertise playback as verified | `voice/consent.py` gates it; `desktop/audio_test.py` reports what actually happened | — | — | Done | PASS |

## §9 Memory, documents, research, downloads and media

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| **Windows history backup controls connected to the live database** | **NEW** `memory/windows_backup.py` + `desktop/history_backup_settings.py`, wired into Settings | Settings → History backup and restore | a backup is written and a restore works | Done | PASS (22 tests) |
| Review Windows crypto dependencies | DPAPI (`CryptProtectData`) for the key, scrypt + HMAC-SHA256 for the payload, no extra dependency | `memory/windows_backup.py` | — | Done | PASS (unit) / NOT RUN (DPAPI is Windows-only) |
| Recovery after interruption, concurrent database access, cancellation | the copy is taken through SQLite's own backup API; a cancelled restore writes nothing | — | — | Done | PASS |
| Existing-destination protection, readable restored copies | the replaced database is kept beside it; the archive carries a readable header | — | — | Done | PASS |
| Distinguish encrypted backups from encryption of active records | the panel says the running database is a plain file and the backup is encrypted | — | — | Done | PASS |
| Preserve old data through safe migration | the restore checks the schema version before it replaces anything | — | — | Done | PASS |
| Owner controls for history, memory, correction, deletion, backup, restore | `desktop/memory_page.py` (notes), `desktop/history_backup_settings.py` (history), `core/store.py` (history) | — | — | Done | PASS |
| TXT, PDF and DOCX reading, search and summarization | `desktop/documents.py`, `desktop/document_search.py` | Files & Folders | — | Done | PASS |
| Scanned-PDF OCR | **GAP** — `desktop/documents.py` says in its own words that it does not do OCR, and no OCR engine is integrated. A missing engine would also have to be reported visibly | — | — | **Not implemented** | — |
| Multi-source research with references tied to retrieved content | `research/research.py` `build_prompt()`, `research_dialog.py` | composer | — | Done | PASS |
| **Web Download Center** | **NEW** `core/downloads.py` | `download()` | — | Done | PASS (23 tests) |
| Safe URL and redirect validation, private-network restrictions, DNS handling | `check_url()`, `check_host()` | — | — | Done | PASS |
| Bounded streaming, destination selection, safe file names, progress, cancellation, history | `download()`, `safe_name()`, `DownloadHistory` | — | — | Done | PASS |
| Resume only when the server permits it | `supports_resume()` — a 206 allows it, a 200 restarts | — | — | Done | PASS |
| **Quantum Visual Player** with real local media playback | **GAP** — there is no media player. `video_studio/preview.py` renders frames for a sheet; `desktop/omega.py` has the signal meter; none of them plays a file with play/pause, seek, volume, fullscreen and metadata | — | — | **Not implemented** | — |

## §10 Self-update, security and remote companions

| Requirement | Implementation | Entry point | Observable result | Impl. | Verif. |
|---|---|---|---|---|---|
| Inspect the installed version, capabilities and recorded errors, and propose improvements | `core/updates.py`, `core/source_updates.py`, `core/development.py` | Settings → Updates | — | Done | PASS (unit) / NOT RUN (Windows) |
| Source branches, patches and owner-provided ZIPs | `core/source_updates.py`, `patches/` | — | — | Done | PASS |
| Isolate changes, compare against the baseline, prepare tests, verify backups, show the diff, obtain deployment approval, restart, check health, roll back | `core/updates.py` `read_state()`, `release_path()`, the `ROLLBACK_JARVIS.cmd` launcher | — | — | Done | PASS (unit) / NOT RUN (Windows) |
| A practical update route for CMD installations | `scripts/` + `ROLLBACK_JARVIS.cmd` | `ROLLBACK_JARVIS.cmd` | — | Done | NOT RUN (Windows) |
| Cybersecurity interface focused on scoped defensive diagnostics | **NEW** `cybersecurity/diagnostics.py` | Cybersecurity page | — | Done | PASS (19 tests) |
| Local device and connection inspection | listeners, established connections, running programs, startup entries | — | — | Done | PASS |
| Configuration reviews and authorized audits | `check_jarvis_configuration()`, `check_credential_storage()` | — | — | Done | PASS |
| Authentication, credential isolation, log redaction, file boundaries, prompt-injection defences, owner cancellation | `security/vault.py`, `remote/audit.py`, `core/protection.py`, `cybersecurity/report.py` `redact()`, `agents/gateway.py` | — | — | Done | PASS |
| **History backup for the Android and iPhone companions** | **GAP** — the desktop history backup exists; the phone side has no equivalent | — | — | **Not implemented** | — |
| Secure pairing, certificate validation, device discovery or manual connection, revocation, logout, session expiry | `remote/pairing.py`, `remote/certificate.py`, `remote/replay.py`, `remote/loopback.py`, `PairingCode.kt` with the `fp=` fingerprint | — | — | Done | PASS (unit) / NOT RUN (phone) |
| Remote approvals and real execution feedback | `remote/jobs.py`, `remote/notifications.py` | — | — | Done | PASS (unit) / NOT RUN (phone) |
| The 15-minute Android timeout, enforced consistently | `AppLockController.sessionTimeoutMinutes` **defaults to 15**, with 5/15/60 offered in the Permissions screen | — | the app locks after 15 minutes of inactivity by default | Done | PASS (unit) / NOT RUN (device) |
| PWA offline requests: durable, deduplicated, safely replayed | `iphone-pwa/js/offline.js` — IndexedDB-backed outbox, backoff, and an equal-request window | — | — | Done | PASS (JS suite) |
| Otherwise clearly report that commands cannot be submitted while disconnected | `iphone-pwa/js/offline.js` keeps the work and says so | — | — | Done | PASS |

## §11 Coding completion check

| Requirement | Implementation | Observable result | Impl. | Verif. |
|---|---|---|---|---|
| `DEVELOPMENT_COVERAGE.md` maintained | this file | — | Done | — |
| Every requirement mapped to its implementation | §1–§10 above | — | Done | — |
| The real entry point and source path | every row names it | — | Done | — |
| The expected observable result | every row names it | — | Done | — |
| Implementation status and verification status, separately | every row has both | — | Done | — |
| Exact external dependency or remaining coding gap | named in the rows and in the gap list below | — | Done | — |
| No requirement silently dropped | the gap list below is the honest remainder | — | Done | — |

## §12 The later test and acceptance stage

| Requirement | Implementation | Observable result | Impl. | Verif. |
|---|---|---|---|---|
| Regression tests for meaningful changes | 6 new test files, **99 new tests**, plus the tests carried forward with PR #88. The whole suite in this revision: **1382 passed, 10 skipped, 0 failed** | — | Done | PASS |
| Preserve the original 62 acceptance IDs | the acceptance source matrix is **not present** in this checkout, so the IDs could not be preserved verbatim. `docs/ACCEPTANCE_PROCEDURES.md` carries the **A–I** procedures from the instruction and names the existing test modules that cover each one | — | Partial | — |
| Mark new unexecuted tests NOT RUN | every hardware row above says NOT RUN | — | Done | — |
| Historical evidence recorded separately | the counts below are from this revision; the historical counts are in `docs/TEST_RESULTS.md` and the changelog | — | Done | — |
| Procedures A–I | `docs/ACCEPTANCE_PROCEDURES.md` | — | Done | — |

## §13 GitHub update and final delivery

| Requirement | Implementation | Observable result | Impl. | Verif. |
|---|---|---|---|---|
| Inspect the diff for secrets, tokens, private databases, personal media, local environments, generated files | `git diff c4d3533..HEAD --stat`, a scan for key-shaped strings, and a check that no `.sqlite3`, `.env` or personal media is staged | — | Done | PASS |
| Preserve approved tracked artwork | `docs/desktop-preview.png` and `iphone-pwa/icons/` untouched | — | Done | PASS |
| Commit in reviewable batches | 11 commits, each with one purpose | — | Done | PASS |
| Push the branch and open one draft PR against `main` | see the delivery message | — | Done | PASS |
| Verify the remote SHA matches the final local commit | the remote branch is cloned and compared file by file | — | Done | PASS |
| Keep `main` merge pending | `main` is untouched | — | Done | PASS |
| Deliver the source folder and a ZIP, with a SHA-256 | the delivery message | — | Done | PASS |

---

## The remaining coding gaps, exactly

These are the things that are **not** implemented. They are listed so the report cannot be read as
complete when it is not.

1. **The .NET half of the UI Automation adapter and the Windows input calls** are written but
   have never run, because there was no Windows machine. The parts that decide *what* is looked
   for and *when* an action is refused are covered by the suite; the parts that talk to Windows are
   not.
2. **Approved screen observation** — `computer_vision/` exists but is not wired to a mission tool.
4. **Calculator adapter** — the Calculator can be launched but its result cannot be read, so the
   Calculator→Notepad workflow cannot be completed.
5. **Saving an open document** — the typed text is verified in the editor; the file is not saved
   from the editor.
6. **Photoshop, DaVinci Resolve and After Effects editing adapters** — the launch switches exist;
   the edit-and-export adapters do not.
7. **Scanned-PDF OCR** — no engine is integrated, and a missing engine would have to be reported
   visibly to the owner.
8. **Quantum Visual Player** — there is no media playback surface at all.
9. **Android/iPhone history backup** — the desktop backup does not extend to the companions.

## What is blocked on something outside the code

These are complete as far as the code can go, and need a machine, an account or a key:

- Everything marked **NOT RUN** in the tables above: Windows UI behaviour, After Effects, Photoshop,
  Resolve, a phone, Azure speech, a live provider key, a live browser session, a live Fiverr or
  Flow account, and the HUD at 100/125/150/200 % Windows scaling.
- The APK, the installer and the clean uninstall: **not built in this coding phase**, as instructed.
