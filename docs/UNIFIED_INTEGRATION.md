# JARVIS BLUE unified development — integration contract

## Source projects reviewed
- **JARVIS-AI**: Python/PySide6 Windows assistant, provider gateway, security policy, local data, task queue, and existing `jarvis_unified/protocol.py`.
- **Jarvis-Blue**: separate Mark LVI-derived assistant and holographic HUD. Preserve original attribution and licensing; do not copy PyQt6 objects directly into PySide6.
- **jarvis-blue-android**: Kotlin/Compose mobile app, encrypted storage, device permission gate, and Windows bridge design.

## One architecture, no duplicate brain
1. **Windows host**: JARVIS-AI is the primary local brain, user approval gate, provider router, and task/memory authority.
2. **Windows visual layer**: adapt compatible HUD ideas from Jarvis-Blue into the PySide6 desktop without mixing Qt bindings.
3. **Android client**: retain native Android permission/security APIs; do not run Windows automation on the phone.
4. **iPhone client**: browser-based secure remote dashboard; no unsupported native iOS APK claim.
5. **Shared protocol**: existing `jarvis_unified/protocol.py` is the current Windows request schema: `version`, `request_id`, `capability`, `payload`. It supports `status.read`, `tasks.read`, `chat.send`, `automation.request`. Its validator is not a transport, authentication mechanism, or execution authorization.
6. **Pairing and transport**: require explicit device pairing, authenticated encrypted channel, replay prevention, per-device revocation, and per-action approval. These must be verified end-to-end before remote automation is enabled.
7. **Memory**: specify sync ownership, conflict handling, encryption, and deletion semantics before implementing cross-device replication.
8. **MiniMax**: use a provider adapter in the main brain rather than shipping a second independent assistant process.

## Acceptance gates
- Desktop launches on Windows 10 x64; installer, uninstaller, microphone, and GUI tested on real hardware.
- Android APK installs and opens without crashes; secure pairing and disconnect/revoke tested.
- iPhone dashboard shows only approved data through authenticated private connectivity.
- Device loss, invalid requests, replays, and Emergency Stop prevent remote actions.
- No API keys in Git, logs, client payloads, or device-sync messages.
- No GitHub Actions: local/manual test and build scripts only.

**Status:** This document is an integration plan, not proof of completed merge or working device sync.
