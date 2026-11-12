# JARVIS AI architecture — 0.3.0 foundation

## Runnable release boundary
A native Qt desktop owns the approval UI. Background chat workers call fixed HTTPS provider endpoints. SQLite stores conversation and task history. Windows Credential Manager stores provider secrets; there is no plaintext fallback. A single action gateway mediates app launches and workspace writes. Model text has no execution privileges. No HTTP listener or remote control is enabled.

User → Qt UI → permission gateway → registered action → result → SQLite history.
Chat: user → explicit Send → provider adapter → streamed text → conversation history.

## Components and trust boundaries
| Component | v0.2 responsibility | Expansion |
|---|---|---|
| desktop | Chat, settings, history, editor, automation, stop, mobile bridge | Dashboard panels |
| providers | Registry and router over eight providers: OpenAI, Gemini, Claude, MiniMax, DeepSeek, Groq, OpenRouter and a local Ollama model | Evaluations, cost ledger |
| security | OS credential vault, one-action approvals, stop latch | Policy-bound workflow grants, signed updates |
| core | SQLite tasks/messages/config/jobs/usage, upgrade backup and interrupted-run recovery | Versioned migrations, cost/health metrics |
| automation | Approved Notepad/Calculator launch and read-only window title inventory | Accessibility tree, verified UI actions, browser tools |
| developer_studio | UTF-8 workspace editor, backups, syntax check | Isolated test/build runner and Git integration |
| agents | Single-action gateway, manual queue and up to 10 sequential approved steps | Durable planner, scheduler and verifier |
| voice | Wake phrase matching, microphone consent and stop control, Windows speech adapters | Windows acceptance of the speech adapters |
| remote | Versioned bridge protocol, listener, pairing with revocation, owner approved jobs | A real phone on a private tunnel |
| remaining directories | Explicitly planned extension boundaries | No pretend implementations |

Permissions are evaluated outside the model. Approval is bound to an immutable action and consumed once. An emergency-stop generation invalidates outstanding work even after Resume. Existing applications are not forcibly killed. Chat cancellation stops accepting output and requests interruption; a network read can take up to its timeout to return and provider billing may already have occurred.

Data: local per-user app directory contains history.sqlite3 and workspace/. History and code are plaintext user data, not encrypted memory. Credential storage is Windows Credential Manager only. No telemetry. Prompts/history are sent only to the selected provider when Send is clicked; no automatic cross-provider fallback. API errors are sanitized, never raw response bodies.

## Prioritized roadmap and acceptance gates
1. **Foundation (this release):** desktop, secure keys, three chat adapters, app launch approvals, editor, history, stop. Pass unit/security tests and Qt smoke; Windows acceptance remains required.
2. **Windows validation + intelligence:** Windows CI recipe, manual live-provider test, token ledger and chat reopening implemented in v0.2. Still pending: executed Windows CI, signed packaging, live account validation, costs, fallback consent and summarization.
3. **Automation:** accessibility-first inspection, verified actions, process ownership, scoped file actions; never arbitrary model shell execution.
4. **Development:** sandboxed runners, command approval, Git diffs/PR preparation, build tool detection; unfamiliar code only in isolation.
5. **Voice + memory:** the wake phrase matcher, the microphone permission and the Windows speech adapters exist; the adapters still need Windows acceptance. Push to talk first, then indexed, editable/deletable memory.
6. **Durable agents:** persistent queues, schedules, cancellation, checkpoints, idempotency, approvals tied to exact workflow/version. Add supervised/trusted modes only after enforcement tests.
7. **Quantum research:** optional Qiskit simulation, circuit visualization and benchmarks; label simulated versus authorized hardware.
8. **Vision + defense:** OCR/accessibility, permissioned screenshots, local audit and dependency checks.
9. **Remote:** the authenticated protocol, pairing, revocation and the owner approval channel are implemented, and the listener refuses to start without TLS or on a public address. It still needs a real phone over a private tunnel, and the Windows job executors are not written.
10. **Maintenance:** patch branches, regression suite, human-reviewed deployment, rollback; security modules cannot self-edit silently.
11. **Release engineering:** Windows installer, dependency hashes/SBOM, signing, resource benchmarks, recovery tests.
12. **Plugins:** declared capabilities, versioning, process isolation and explicit activation. No arbitrary plugin auto-loading.

Architecture targets Python 3.12 and PySide6. FastAPI, FAISS/Chroma, Qiskit and voice frameworks are future optional dependencies, not unnecessary requirements for this release.


## v0.2 additions and execution guarantees
Queue rows are claimed with a conditional SQLite update; only queued rows can be claimed. A claim enters reviewing before approval and running immediately before a launch. App names are allowlisted again at execution. Cancelled, denied, failed, completed and interrupted jobs are terminal. The user can deliberately create a new job; there is no automatic retry or persistent approval grant. This avoids replaying a possibly executed side effect after a crash. It is not an autonomous planner or exactly-once external execution guarantee.

Usage is provider-reported, nullable and separate from billing. One worker handles either a chat or a short, explicitly authorized provider check. Checks never attach history. Emergency stop invalidates its ticket and discards late results. No credentials or raw error bodies are included in health records.

Schema version 2 adds jobs and usage tables without altering v0.1 message/task/config tables. SQLite backup precedes the first migration; the app rejects unknown newer schema versions. Provider keys retain the original vault namespace.

## v0.3 manual workflow and observation boundaries

Workflow definitions are authored by the person using the Qt interface, not by provider responses. Each action is re-checked against the fixed app allowlist, individually confirmed, and dispatched through the same one-use policy gateway. The workflow database uses conditional state transitions; a workflow that was cancelled, denied, failed, completed or interrupted cannot be run again. A new workflow must be created. SQLite v3 records each step and marks mid-execution rows as interrupted at the next startup.

A workflow runs synchronously in the owner-controlled UI; the step count is limited to 10. No scheduler, replay engine, operating-system process supervisor, UI automation scripting or autonomous planning has been added.

The read-only inspector runs as a separate Python process with a strict timeout. It enumerates only top-level visible window titles and process IDs, never keystrokes, focus changes, screenshots or child controls. Windows titles can contain personal information. The inspector is Windows-only and has not yet been manually validated on an actual Windows desktop. The global Emergency Stop prevents new workflows and invalidates outstanding grants; it cannot undo an already launched application or forcibly terminate a running native process.
