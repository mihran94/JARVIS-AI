# JARVIS AI — MARK LVII assistant-first integration

This branch integrates an **original** minimal holographic assistant UI with
the **existing JARVIS AI services**. This is not a separate MARK application.

## Present in this branch
- Main chat-first screen with a shared animated holo-reactor, not ten feature buttons.
- Direct Settings and Plugins; the existing settings and plugin switches are preserved.
- Omega, Island and Stealth retain the same voice and chat backend.
- The advanced dock is hidden on ordinary startup but accessible via Ctrl+D
  and Omega Settings; smoke tests preserve the legacy visible-dock flow.
- A `/capabilities` command and plain-language synonyms report live provider
  selection, voice permission, bridge readiness, Emergency Stop and plugin
  switches, without claiming that an untested provider or physical phone works.
- The independent Phase 1 source base already contains MARK-derived protections
  against reading/writing secret files, and optional GPU/temperature telemetry.


## Practical PC task executor — first verified source implementation
- JARVIS accepts **explicit, complete** commands such as
  `Open Notepad and type: Welcome` or `Type into Notepad: Hello`.
- JARVIS shows the full text and exact SHA-256 before owner approval.
- It can open Notepad, wait up to seven seconds for Windows to report
  Notepad as the foreground process, then send Unicode text (including Tamil).
- It does not type into an unknown/changed window; it does not run shell
  commands from text. Emergency Stop cancels a pending task.
- The task report distinguishes input events accepted from **content verified**
  or **saved**. The current code cannot assert those latter outcomes.
- These actions are currently limited to **Notepad**. The rest of the installed
  apps, UI navigation, browser forms, file workflows, cross-app chains and
  actual end-to-end hardware verification still need individual integrations.
- Tests cover parser constraints, Unicode events, Win32 layout, review/denial,
  and cancellation. These are source tests; no Windows device acceptance is
  implied.

## MARK functionality that still needs independent work
- Full human holographic avatar, viseme-based lip sync and gaze/facial acting.
- Native full-duplex Gemini Live audio, faster-Whisper and Piper/ElevenLabs
  integration with correct consent and language switching.
- Wake-word interruption while speaking and echo suppression.
- Broad Windows desktop control (screen understanding, clicks, app-specific
  operation and robust completion checking), undo, safe plugin loader and
  verified application open/close outcomes. Each needs the JARVIS approval gate.
- Hardware acceptance: Windows installer, microphone and Tamil speech,
  secure Android pairing and signed release build.

## Security and licensing
Keep one-use action approvals, Windows Credential Manager, Emergency Stop,
backup provider consent and the local Ollama hands-free restriction.
Never copy credentials, user memory or personal data into the repository.

The upstream FatihMakes MARK LVI README specifies CC BY-NC 4.0
(personal / non-commercial) for its code. Review licensing before
commercially redistributing any previously ported MARK source; avoid copying
MARK's licensed graphics, assets or source into proprietary JARVIS binaries
without the necessary permission.

No installer or physical-device test is implied by this source commit.
