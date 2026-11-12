# Changelog

## Unreleased — 12 November 2026
- Provider registry and router covering OpenAI, Gemini, Claude, MiniMax, DeepSeek, Groq, OpenRouter and Ollama, with no implicit paid fallback and offline mode restricted to the local provider.
- Native Anthropic Messages API adapter and a loopback only local Ollama adapter. A local model never receives a key and never leaves the computer.
- The desktop provider list comes from the unified registry, so Claude and the local model are selectable from the interface. A local model never falls back to a paid endpoint.
- Versioned desktop/mobile bridge protocol: canonical HMAC-SHA256 signing shared with the JARVIS BLUE Android client, replay protection, pairing with revocation, job records and a request handler.
- The bridge listener refuses to start without TLS, refuses a non loopback address and authenticates every request.
- The Mobile Bridge page: start and stop the listener, pair a phone, revoke a phone, and approve or reject the jobs a phone sends through the existing one-use policy gateway.
- The voice layer: the wake phrase matcher and text scoring ported from the Android client, a microphone permission with a stop control, and Windows text to speech and speech recognition adapters.
- The provider selection policy and its test moved out of the repository root, where pytest never collected the test, into `providers/selection.py` and `tests/test_provider_selection.py`.
- A signing material checker and the Android release key rotation procedure.
- Release readiness record and a SHA-256 source integrity manifest for the branch, so the owner can verify the exact tree before building on Windows.
- The GitHub Actions runner fix as a ready to apply patch, because the connected App cannot write workflow files.
- The Windows application build and the Android debug APK build as workflow sources in `ci/`, with the matching patches in `patches/`. The Android build uses the automatic debug key and never the exposed release key.
- A release manifest writer that records the SHA-256 of every built file, so a distributed artefact can be verified.
- The Qt runtime preparation for Linux: `scripts/qt_runtime.py` installs `libEGL.so.1` when the machine does not have it, and the repository `conftest.py` calls it before the test modules are imported. This is what the GitHub Actions Linux runner was missing.
- Two test fixes that only fail on Windows: the update archive test now writes the member name unchanged, because the zip module turns a backslash into a path separator there, and the oversized input tests now carry short names, because pytest puts the test name in an environment variable and Windows refuses a value longer than 32767 characters.
- 286 local tests pass, 3 skipped.

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
