# JARVIS AI architecture — 0.2.0 foundation

## Runnable release boundary
A native Qt desktop owns the approval UI. Background chat workers call fixed HTTPS provider endpoints. SQLite stores conversation and task history. Windows Credential Manager stores provider secrets; there is no plaintext fallback. A single action gateway mediates app launches and workspace writes. Model text has no execution privileges. No HTTP listener or remote control is enabled.

User → Qt UI → permission gateway → registered action → result → SQLite history.
Chat: user → explicit Send → provider adapter → streamed text → conversation history.

## Components and trust boundaries
| Component | v0.2 responsibility | Expansion |
|---|---|---|
| desktop | Chat, settings, history, editor, automation, stop | Voice and dashboard panels |
| providers | OpenAI-compatible streaming for OpenAI/MiniMax/Gemini | Native Claude, other providers, opt-in fallback, evaluations |
| security | OS credential vault, one-action approvals, stop latch | Policy-bound workflow grants, signed updates |
| core | SQLite tasks/messages/config/jobs/usage, upgrade backup and interrupted-run recovery | Versioned migrations, cost/health metrics |
| automation | Fixed Windows Calculator/Notepad launches | UI Automation, window inspection, browser tools |
| developer_studio | UTF-8 workspace editor, backups, syntax check | Isolated test/build runner and Git integration |
| agents | Single-action gateway and durable manual app-launch queue | Durable planner, queue, verifier, scheduler |
| remaining directories | Explicitly planned extension boundaries | No pretend implementations |

Permissions are evaluated outside the model. Approval is bound to an immutable action and consumed once. An emergency-stop generation invalidates outstanding work even after Resume. Existing applications are not forcibly killed. Chat cancellation stops accepting output and requests interruption; a network read can take up to its timeout to return and provider billing may already have occurred.

Data: local per-user app directory contains history.sqlite3 and workspace/. History and code are plaintext user data, not encrypted memory. Credential storage is Windows Credential Manager only. No telemetry. Prompts/history are sent only to the selected provider when Send is clicked; no automatic cross-provider fallback. API errors are sanitized, never raw response bodies.

## Prioritized roadmap and acceptance gates
1. **Foundation (this release):** desktop, secure keys, three chat adapters, app launch approvals, editor, history, stop. Pass unit/security tests and Qt smoke; Windows acceptance remains required.
2. **Windows validation + intelligence:** Windows CI recipe, manual live-provider test, token ledger and chat reopening implemented in v0.2. Still pending: executed Windows CI, signed packaging, live account validation, costs, fallback consent and summarization.
3. **Automation:** accessibility-first inspection, verified actions, process ownership, scoped file actions; never arbitrary model shell execution.
4. **Development:** sandboxed runners, command approval, Git diffs/PR preparation, build tool detection; unfamiliar code only in isolation.
5. **Voice + memory:** push-to-talk first; Tamil/English/French STT/TTS; opt-in microphone and wake word; indexed, editable/deletable memory.
6. **Durable agents:** persistent queues, schedules, cancellation, checkpoints, idempotency, approvals tied to exact workflow/version. Add supervised/trusted modes only after enforcement tests.
7. **Quantum research:** optional Qiskit simulation, circuit visualization and benchmarks; label simulated versus authorized hardware.
8. **Vision + defense:** OCR/accessibility, permissioned screenshots, local audit and dependency checks.
9. **Remote:** authenticated FastAPI service behind private network/TLS; device pairing, revocation and approval channels before enabling any listener.
10. **Maintenance:** patch branches, regression suite, human-reviewed deployment, rollback; security modules cannot self-edit silently.
11. **Release engineering:** Windows installer, dependency hashes/SBOM, signing, resource benchmarks, recovery tests.
12. **Plugins:** declared capabilities, versioning, process isolation and explicit activation. No arbitrary plugin auto-loading.

Architecture targets Python 3.12 and PySide6. FastAPI, FAISS/Chroma, Qiskit and voice frameworks are future optional dependencies, not unnecessary requirements for this release.


## v0.2 additions and execution guarantees
Queue rows are claimed with a conditional SQLite update; only queued rows can be claimed. A claim enters reviewing before approval and running immediately before a launch. App names are allowlisted again at execution. Cancelled, denied, failed, completed and interrupted jobs are terminal. The user can deliberately create a new job; there is no automatic retry or persistent approval grant. This avoids replaying a possibly executed side effect after a crash. It is not an autonomous planner or exactly-once external execution guarantee.

Usage is provider-reported, nullable and separate from billing. One worker handles either a chat or a short, explicitly authorized provider check. Checks never attach history. Emergency stop invalidates its ticket and discards late results. No credentials or raw error bodies are included in health records.

Schema version 2 adds jobs and usage tables without altering v0.1 message/task/config tables. SQLite backup precedes the first migration; the app rejects unknown newer schema versions. Provider keys retain the original vault namespace.
