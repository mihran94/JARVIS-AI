# Jarvis-Blue test report — 6 November 2026

Tested development source from commit fe89cba8e6ae96d0e588f5812e37e6acfa0473fe in an isolated Linux copy, Python 3.12. Owner laptop was not used. No executable build, release, production key generation or real model-provider call was performed.

| Check | Observed result |
|---|---|
| Launcher and signed updater tests | 19 passed, 0 failed |
| Existing provider self-test (`python -m providers._tests`) | 99 checks passed, 0 failed; local mock services |
| Actual Qt Updates dialog, offscreen | Opened successfully; initial Download/Install/Restore disabled; empty history rendered; missing feed produced an error and controls recovered |
| Full JarvisUI startup, offscreen | Failed: process exited 139 with native segmentation fault; PipeWire audio configuration errors were emitted immediately beforehand. Exact cause not established. This is not evidence that Windows startup passes or fails. |
| Windows CMD scripts, Windows GUI, microphone/speakers | Not tested: no Windows host or owner laptop available |
| Real provider connection, private release delivery, Authenticode signing | Not tested; credentials/certificate/delivery configuration are not activated |
| Quantum Lab | Blueprint only; no simulator exists to test yet |

Additional dependencies were installed into a separate scratch test directory, not into the owner laptop or project environment: PyQt6 6.12.0, Qt 6.12.0, google-genai 2.34.0, sounddevice 0.5.6 and cryptography 49.0.0. Existing runtime packages supply remaining test dependencies. Cryptography 49.0.0 satisfies the app's >=42,<50 requirement; the 19-test suite was rerun successfully using that version.

The standalone dialog check used an actual QApplication and actual UpdateDialog, without mocking widgets. It does not verify the main window integration, visual behavior on Windows, restart helper or physical devices. The full UI crash remains an unresolved environment/native-backend investigation; no application fix is claimed.

Phase 1 remains open until Windows setup/start and audio acceptance checks pass. Next useful checks are reproducing the native startup crash with an available supported audio backend and running the existing acceptance checklist on a Windows test host. Do not treat the 118 automated checks as certification of all application features.

## Follow-up: startup isolation fix
The native crash was reproduced with Python faulthandler: the active main-thread frame was MainWindow.__init__ at QAudioOutput() for optional video playback. This identifies the triggering call; the underlying Qt/PipeWire native defect has not been fixed.

Changed video backend initialization to happen on the Qt thread only when video playback is requested. Main-window construction now leaves QAudioOutput and QMediaPlayer uninitialized. The actual full JarvisUI now constructs, displays and processes events successfully in the same Linux/offscreen environment. No multimedia factory was mocked for that reproduction check.

Added five real-widget regression tests covering startup without eager media factories, mute/resize, the Settings button opening the actual Updates dialog, unavailable-video handling, and a simulated Python multimedia-constructor error. Tests use one QApplication, no model credentials, and mock only the multimedia error/factory probes and first-run credential gate. All 24 launcher/updater/UI tests pass using cryptography 49.0.0. The existing provider self-test was rerun with the changed UI: 99 passed, 0 failed. Total: 123 passing checks across the 24-test suite and 99 provider checks.

Video playback is deferred, not certified safe on the broken native backend: requesting video there may still cause a native crash. A Python exception is reported in the activity log, but a native segmentation fault cannot be caught this way. Actual playback, sound devices, Windows setup/CMD execution, Windows UI and production model calls remain unverified. Phase 1 remains open for Windows acceptance. No build or release.

## Phase 2 navigation increment
Actual Qt widget coverage now includes Home/Tasks/Quantum Lab navigation, retained Home results, live activity snapshots, automatic return to Home for arriving tool content, existing Memory/Settings panels and engine-driven status labels. All 28 tests pass and the existing provider suite reports 99 passed, 0 failed (127 checks total). Home and Quantum Lab rendered successfully at 1280×800 in the isolated Qt offscreen environment. Physical audio/video and Windows tests remain deferred. No build, release, persistent task queue or quantum simulator was produced.

## Coding workspace increment
- 37 tests pass (`python -m unittest discover -s tests -q`) in the isolated Linux/Qt-offscreen environment: previous 28 plus 8 workspace/diagnostic cases and 1 real-widget integration case.
- Verified project selection, preview, background result delivery, missing-folder recovery, root traversal rejection, symlink rejection, common credential exclusions, 128 KiB/UTF-8/binary preview limits and 500-entry directory cap.
- Rendered and visually inspected the real Coding panel at 1280×800. No production provider request, build, installer or Windows test was performed. The previously passing 99 provider checks were not rerun for this independent read-only feature.
- Error guidance is heuristic and requires developer review. Project code is never imported/executed by these new tools. Other existing app coding actions are unchanged.
- Scope checks do not defend against concurrent malicious filesystem replacement; secret filename filtering is intentionally not represented as complete secret detection.

## AI connections / Codex review
46 unit/widget tests and 99 provider checks pass in isolated Linux/offscreen runs. New HTTP mock coverage checks Gemini/OpenAI/MiniMax endpoint, bearer key and model separation; no real key is used. Command tests cover read-only policy, stdin, missing CLI and Windows npm entry-point resolution. Real QProcess widget tests use harmless Python subprocesses to verify output, nonzero exit and cancellation; they do not execute Codex model requests.

Codex CLI help was inspected locally without logging in or calling a model. Windows execution, real provider authentication and provider-specific tool/reasoning compatibility remain unverified. No new API key was created, no credentials committed, no build run.
