# JARVIS M-CORE 1.0.0 — release plan

Prepared on 27 November 2026 (Europe/Paris). Baseline: GitHub main
`d0c2910bf27b36fe227e18a561d922e6dda7b539`, weather animation and native M icon.

This is the next-release plan, not a declaration that version 1.0.0 has shipped.
The application remains version 0.3.0 until the release gates below pass.

## Product contract

- One desktop JARVIS window, existing dark navy/black and cyan appearance.
- English interface; natural Tamil replies, with English words when useful.
- Keep M hologram, Communications/Command, Terminal, compact system status,
  and combined Time / Weather. Settings remain an owned popup.
- Chat history, Heard, attachment selection and composer stay together.
- Main Brain: Gemini recommended. Coding Agent: separately configured OpenAI
  or MiniMax. Never require a coding key for ordinary conversation.
- Use saved audio devices; chat mic icon controls mute. Camera state and optional
  preview must agree with actual capture/sharing. No repeated personal-name greeting.
- Automation runs from chat and reports the action and verified result in Terminal.
- Emergency Stop interrupts work, audio and sharing; stale approvals cannot resume it.

## Current audit scope

The initial source pass enumerated 675 Git-tracked files and parsed/byte-compiled
all 347 tracked Python files. No Python syntax errors or duplicate definitions
within module/class scopes were found. Source-integrity verification passed.
This structural scan does not prove every feature works or replace a security review.
Automated regression and hardware acceptance are recorded separately in the audit report.

## Work order

| Stage | Changes | Completion gate |
| --- | --- | --- |
| 1. Reliability baseline | Resolve reproducible suite failures, dependency/runtime differences, worker cleanup and interrupted-task recovery. Keep the current UI stable. | Entire runnable regression suite passes; every skip has a reason; no unexplained crashes or thread leaks. |
| 2. Voice and vision | One Gemini speech path; complete Tamil/Tanglish Heard text; reliable barge-in, device reconnect and stale-camera-frame refusal. Measure response latency before tuning buffering/frame delivery. | Recorded input fixtures pass; user confirms real Tamil speech, interruption and object recognition on this PC. Camera Off sends no frames. |
| 3. Verified desktop control | One action dispatcher for voice, text and buttons. Persist the user's control preference. Verify target window, mouse/keyboard result and completion before reporting success. | Calculator click/readback, Tamil Notepad typing/readback, wrong-window refusal, stop-during-action and restart persistence pass. Take control alone launches no editor. |
| 4. Remote experience | Keep one device-pairing popup, expiring QR/code and revocation. Make connection/call state honest. Implement actual continuous audio/video conversation if call parity is required. | Real phone pairs over private HTTPS; Tamil voice/chat replies, shown-object recognition, reconnect and revoked-device refusal pass on the phone. |
| 5. Setup and update | ZIP → setup → first-run Main Brain/Coding Agent → vault save → restart. Preserve profile, memories and paired-device state. Use short update worktree paths and verified rollback. Unify native, shortcut and packaged M icons. | Clean Windows setup, subsequent launch without re-entry, failed-update rollback and successful approved-update restart pass. Verify macOS on a real Mac before claiming support. |
| 6. Release candidate | Version/product naming, changelog, installer/ZIP contents and dependency inventory. Consolidate outdated acceptance documents around one current report. | CI passes on Windows and Linux; owner acceptance complete; release candidate installs/runs and rolls back. Then set M-CORE 1.0.0 and publish artifacts. |

## Internal structure

Stage 1's first production batch is tracked in
[MCORE_STAGE1_RELIABILITY.md](MCORE_STAGE1_RELIABILITY.md): interrupted-task retry,
safe camera-preference fallback and voice-session callback/stop isolation.
This is progress toward the reliability gate, not a declaration of version 1.0.0.

`desktop/app.py` has 7,699 lines and `desktop/prime_ui.py` has 1,691 lines at
this baseline. Gradually extract voice/vision coordination, desktop-action dispatch,
remote sessions, settings and update orchestration behind existing entry points.
Do one subsystem per change with behavior tests; avoid a simultaneous rewrite.

Keep the existing boundaries: `security/policy.py` for approval/stop state,
`automation/` for validated desktop operations, `remote/` for authenticated
device requests, and `core/development.py` / `core/source_updates.py` for updates.
Model text must describe proposed actions rather than bypass those boundaries.

## Acceptance matrix

| Area | Automated evidence required | Physical acceptance required |
| --- | --- | --- |
| UI | Popup dismissal, alignment, attachment close, weather fallback/reduced motion, single instance, native icon | Display scaling, visible taskbar icon, one window after shortcut/restart |
| Audio | PCM conversion, echo guard, partial/full transcripts, interruption, disconnect/retry limits | Real microphone, speaker, friendly Tamil response, no duplicate voice |
| Camera | Fresh-frame checks, On/Off state, stop/close teardown | Show several objects in different lighting and verify Tamil answers |
| Automation | Intent routing, exact target, input/readback, cancellation, refusal and persistent control | Calculator 7 click, calculation readback, Notepad typing, intended app only |
| Coding/update | Separate provider selection, review/reject/approve, tests, restart, rollback | One small requested change survives restart and profile is preserved |
| Remote | Signing, replay/revocation, HTTPS/static-asset boundaries, QR parsing and call state | Real phone QR pairing, mic/camera permission, Tamil voice/chat, reconnect |
| Memory | Explicit remember/forget, persistence, no secret leakage into prompts/export | User's correction and subsequent forget request honored |

## Known acceptance gaps to close before 1.0.0

- A real phone audio/video call and camera-to-Tamil answer have not been verified
  in this audit. Existing browser speech is browser-provided, and turn-based capture
  must not be advertised as a continuous Gemini call.
- A controlled WebSocket disconnect has been tested previously; an actual physical
  Internet outage/recovery is separate and remains to be verified.
- A physical Mac setup, Keychain round trip and microphone/camera session are unverified.
- Real microphone accuracy, voice identity and live object recognition cannot be certified
  from mocked inputs, text transcripts or offscreen UI tests alone.
- Historical docs refer to older names/layouts and earlier test totals. Preserve them as
  historical records; use the new dated audit as current release evidence.

## Release rule

Fix blockers first, finish the acceptance matrix, then name a release candidate.
Do not change the user's profile, erase memories, rotate keys, publish a new installer,
or label the current build 1.0.0 merely because the plan exists.
