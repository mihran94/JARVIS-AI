# Jarvis-Blue — Complete Update Plan
Date: 6 November 2026

## Scope and evidence
Reviewed the supplied Mark-LVI-main.zip source, not a live GitHub checkout. This is a source-level inventory and proposed roadmap, not a runtime certification. The archive contains main.py, ui.py, actions, core, providers, memory, dashboard, config and plugins. Its README also describes items that are not necessarily included in this archive; the source inventory takes priority.

Implemented in this package: renamed the outer project folder, README heading, assistant fallback names, setup branding and dashboard page titles to Jarvis-Blue. Custom saved assistant names remain unchanged. Internal Python class names, wake phrase, config locations and dashboard storage keys remain compatible. Historical release notes, upstream links and original attribution are retained. This is a development package, not a new numbered release.

## Product direction
A Windows-first personal desktop assistant with a blue hologram interface, Tamil–English conversation, visible task progress and local processing when configured. Keep Home, Tasks, Memory and Settings as the main navigation. Put developer and device tools under Advanced. Use English interface labels, detect conversation language automatically and answer in the same language. Female voice is a preference subject to installed voice and language availability.

## Every section: existing source and proposed changes
| Section | Present in supplied source | Proposed update | Completion evidence |
|---|---|---|---|
| Identity and setup | setup.py, config, README | Centralize product name; add Windows setup/start scripts with clear environment errors; migrate old default names explicitly | Fresh install and existing-config launch both work |
| Home interface | ui.py, core/avatar.py, avatar_mesh.py, viseme.py | Blue hologram theme; compact chat; one microphone control; visible idle/listening/thinking/speaking/error state; reduced-motion option | Windows screenshots, resize and keyboard checks |
| Voice input | stt.py, wake_word.py, hotkey.py, audio_devices.py | Tamil/English auto-detection; selectable always-listening mode; mute indicator; hotkey fallback; interruption and headset recovery | Quiet/noisy room and headset unplug checks |
| Voice output | tts.py, providers/tts_* | Preferred female voice; Tamil pronunciation samples; speech queue cancellation; visible fallback when a voice lacks a language | Tamil/English and mixed-script recordings |
| AI routing | gemini.py, llm_client.py, providers/registry.py, engine_pipeline.py | Simplify local/cloud selection; display processing location, model readiness and capability limits; no silent cloud switch | Local mode works with network disabled; provider failure stays visible |
| Conversation engine | main.py, core/outcome.py, echo.py | Separate session/audio/tool coordination gradually; task IDs, cancellation and checked outcomes | Reconnect, timeout, interruption and duplicate-action checks |
| Memory | memory_manager.py, config_manager.py | User-editable facts, expiry, export, delete and conversation search; distinguish preferences from temporary context | Data survives restart; deleted facts stay deleted |
| Files and documents | file_controller.py, file_processor.py | Folder-scoped access; previews for bulk edits; backup/undo; OCR and document Q&A only after dependency review | Temporary-folder rename/delete/restore scenarios |
| Browser and research | browser_control.py, web_search.py, screen_processor.py | Clear source links; structured extraction; treat web text as untrusted; pause before purchases or submissions | Controlled pages and prompt-injection fixtures |
| Desktop and apps | desktop.py, computer_control.py, open_app.py, appidentity.py | Reliable focus, DPI and multi-monitor behavior; explain unavailable actions; verify resulting window state | Windows scaling and multi-monitor manual checks |
| System controls | computer_settings.py, system_monitor.py, background_monitor.py | Read-only health view first; explain each setting change; record before/after and rollback where available | Mock power/network operations before real-device trials |
| Tasks and reminders | reminder.py, proactive.py | Unified Tasks page; timezone-aware reminders; missed-task handling; quiet hours; restart recovery | Paris daylight-saving boundary and restart scenarios |
| Developer workspace | dev_agent.py, code_helper.py, code_checks.py | Show plan/diff/check results; isolate work; stop/cancel; separate development from build commands | Disposable repo tests; no build unless explicitly requested |
| Messaging | send_message.py | Draft preview, verified recipient and explicit send authorization; reliable delivery status | Mock adapters; no real messages during automated tests |
| Media and utilities | video_player.py, youtube_video.py, weather_report.py, flight_finder.py, game_updater.py | Consistent task status, cancellation and provider errors; optional modules loaded on demand | Offline, timeout, missing-app and media/mic checks |
| Phone dashboard | dashboard/server.py, static pages | Responsive blue theme; device list/revoke; session expiry; secure remote transport before internet exposure | Pair/revoke/expired-session tests and phone browser checks |
| Plugins | plugin_loader.py, action_loader.py, plugins/_template.py | Review new plugin permissions before execution; expose capabilities and disable controls; keep loader compatibility | Broken/slow/untrusted plugin fixtures; no Qt use from workers |
| Security and privacy | confirm.py, undo.py, outcome.py, dashboard auth | Central permissions and audit view; redact secrets; distinguish authorization from model text; show rollback limits | Forged approval, secret-redaction and denied-action scenarios |
| Performance and packaging | lazyimport.py, platform_support.py, requirements.txt | Startup profiling; lazy-load extras; hardware readout; dependency grouping; reproducible packaging later | Measured cold start, idle CPU/RAM and recovery on user's PC |
| Quality and documentation | _smoke_harness.py, providers/_tests.py, AGENTS.md | Maintain capability matrix, troubleshooting, migration notes and a Windows acceptance checklist | Source checks plus manual Windows run before release |

## Delivery order
1. Foundation: finish centralized identity, Windows setup/start reliability, config migration and baseline measurements. Exit: new and existing installations launch reliably.
2. Daily-use experience: simplified hologram UI, language behavior, voice device recovery, provider readiness and clear errors. Exit: complete Tamil/English conversations on target Windows PC.
3. Reliable actions: scoped files, task queue, checked outcomes, permission gates and undo. Exit: controlled action scenarios complete or explain failure accurately.
4. Personal workspace: memory controls, reminders, document search, optional media modules and developer workspace. Exit: persistence, deletion and cancellation behave correctly.
5. Connected devices: improve phone dashboard first, then paired-device and remote-service experiments. Exit: pairing, revocation and connection loss are handled before wider access.
6. Release preparation: Windows manual QA, dependency review, migration rehearsal and packaging. Build only when requested. No calendar promises until the baseline is measured.

## Future features worth prioritizing
- Search and ask questions about selected local documents, with file references and a way to remove indexed material.
- A task timeline showing requested, running, awaiting input, completed, failed and cancelled work.
- Offline daily routines using reminders and selected local apps, with clear permissions.
- A hardware-aware quality selector that measures resource use before recommending model settings.
- Paired phone handoff for drafts, notifications and continuing conversations.
- Optional VPS companion for reminders while the PC is off. Desktop actions require the PC to be powered on and connected; a VPS does not change that.
- Later experiments: owner-paired smart-home adapters, calling integrations and read-only security diagnostics. Start with mocks; verify provider access, cost and permissions before implementation.

## Development rules
Keep the single QApplication and all widgets on the Qt main thread; action/plugin workers use player signals. Keep model requests through the existing core.gemini abstraction until a reviewed routing migration exists. Keep secrets under config_manager and do not include them in exports. Preserve original LICENSE and attribution. No implicit package installs during normal app startup. No build or deployment was performed for this package.

## Verification and limits
All Python files were parsed after the branding edits. Expected branding strings and required files were checked. No packages were installed; no provider API requests, application launch, microphone test, dashboard pairing or Windows GUI tests were run. New roadmap features remain proposals. This ZIP has not been pushed or merged into GitHub.

## Updater implementation — 6 November 2026
Added Settings → Updates, optional startup notification, HTTPS source feed checks, notes, verified staging, restart helper, code backup, history and manual restore. See UPDATE_GUIDE.md for publication setup, source-only limits and validation. No feed is configured, no automatic installation is enabled, and no build or GitHub publication was performed.

## Digital signatures — 6 November 2026
Added Ed25519 manifest signing/verification, encrypted owner-side key setup, pinned public trust, expiry and downgrade checks, install-time archive verification, and a Windows Authenticode signing/verification script. Thirteen tests pass. Production keys and trusted Windows publisher certificate remain owner activation steps; no build, actual Authenticode signing or release was performed. See SIGNING_GUIDE.md.

## Quantum direction and Phase 1 startup — 6 November 2026
Added DEVELOPMENT_BLUEPRINT.md, Windows setup/start entry points, isolated startup import checks and working-directory-safe setup. Phase 1 Windows GUI/audio acceptance remains pending. Quantum Lab remains proposed. No build or release.
