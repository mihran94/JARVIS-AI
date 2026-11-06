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
