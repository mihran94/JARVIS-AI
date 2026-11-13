# JARVIS AI — one friendly desktop, one secure mobile remote

The **Windows PySide6 app is the main AI assistant**. Mobile is a remote
client for that PC, not a second independent assistant. Development changes
are reviewed in a branch before they reach `main`.

## Main Windows window

The primary navigation deliberately has only six destinations:

1. JARVIS Chat (opens by default) — Tamil, English, French and other text
2. PC Control — allowlisted Windows apps and read-only window inspection
3. Coding Assistant — draft, repair, review and explicit approval before saving
4. Voice / Hey Jarvis — Windows speech recognition and local speech output
5. Phone Remote — pair, monitor and revoke access
6. Settings & Safety — emergency stop, providers, historical/advanced tools

Task queues, workflows, task history, provider key configuration and usage
remain reachable from Settings so old records and capabilities aren't lost.
All twelve underlying page widgets are still instantiated. The command
center's blue orb and passive local system metrics now sit on the chat screen.

## Voice and ongoing listening

The **owner has to grant microphone permission** first. A new opt-in
"Keep listening for Hey Jarvis" mode continues recognition while JARVIS is
running. Audio recognition requires Windows plus the optional `pythonnet`
adapter and working System.Speech language recognition; no OS-level
always-on activation is guaranteed. Voice recognition is not started at login,
at launch, or when the window is sent to background. Stop Voice, Emergency
Stop and closing JARVIS revoke consent. Incoming spoken words are **drafted**
in the main chat window; voice alone never launches apps, changes files or
spends paid-model API credits. The user must explicitly press Ask JARVIS.

Reading AI replies aloud is a separate opt-in checkbox and uses the Windows
text-to-speech adapter. The backend cannot autonomously execute tool calls.

## Permission boundaries

Every PC launch, workspace save, destructive chat action and approved
workflow step still passes through the one-use `security.policy.Policy`
gateway. Rejected permissions cause no action. Emergency stop invalidates
approvals and stops voice. Remote jobs remain queued until separately
approved on Windows. The bridge listener stays off by default; mobile must
be paired and reached over a private HTTPS connection.

## Limits and scope

This release does **not** provide arbitrary full-PC operation, autonomous
coding/execution, guaranteed offline multilingual voice recognition, or
continuous voice while Windows/JARVIS is closed. All trading, Exness,
XAUUSD, buy/sell signal and broker-order features are **excluded** at the
owner's request. Duplicate/legacy source archives are kept for lossless
recovery until independently verified and safely retired.

## Android application is now remote only

The Compose launcher opens `WindowsRoute()` directly; it no longer exposes
standalone mobile chat, studio, Android task execution, wake services, screen
capture, accessibility or background receivers. The app keeps Android biometric
lock and HTTPS bridge pairing. The release manifest requests only network and
biometric permissions and disables sensitive data backups. Old Android source
files remain in Git history but are not registered by the launcher.

The phone may view Windows status, submit **approval-required** job requests,
cancel queued jobs and see logs. It cannot execute arbitrary PC actions and
cannot override the Windows emergency stop. An owner must explicitly pair the
phone, configure the private HTTPS bridge and approve actions on Windows.
Plain HTTP origins, embedded credentials, paths and conflicting ports are
rejected. The shared secret is stored in the phone's Keystore-backed vault and
is not printed or embedded in the APK.

The remote-only Android privacy audit runs during the Gradle pre-build; it is
not a substitute for validating the final merged manifest and device hardware.
Existing installed APKs are not upgraded or uninstalled by merging source.
