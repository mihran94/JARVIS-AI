# Changelog

## 0.3.0 — 8 November 2026
- Up to 10 manual allowlisted launch steps per workflow with per-step, one-use confirmations.
- Durable workflow statuses, restart interruption recovery and no replay after failure or cancellation.
- Read-only Win32 visible top-level window inventory in a 3-second bounded child process, only after owner approval.
- Desktop workflow tab and inspection button; global emergency stop cancels waiting workflow steps.
- Version-3 SQLite schema migration with a backup for previous version-2 databases.
- Nine new local regression tests passed against the workflow/store/policy integration harness. Windows/native UI suite remains unverified here.

## 0.2.0 — 8 November 2026
- Durable manual app-launch queue with one-use review, cancellation, atomic claim and interruption recovery.
- Provider response token metrics and request-duration ledger, with Unknown for missing counts.
- Explicit short provider connection test; no background polling or conversation attachment.
- Saved conversation picker.
- Schema backup before additive migration; original credentials retained.
- Emergency shortcut changed to Ctrl+Alt+J to avoid Windows Task Manager's standard shortcut.
- Windows/Linux GitHub Actions test recipe, not executed here.
- 57 passing Linux/offscreen tests; Windows/live provider validation still pending.

## 0.1.0
Initial Qt application, chat adapters, approved fixed app launches, local code editor, credential vault boundary, history and emergency stop.
