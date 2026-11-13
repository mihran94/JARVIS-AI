# One JARVIS — consolidated source and safe retirement plan

The canonical maintained repository is **mihran94/JARVIS-AI**, with one Windows
entry point (`main.py`), one Android application (`android/`) and one
supervised Windows-to-mobile protocol (`remote/`). The iPhone frontend remains
a browser PWA, not a native iPhone app.

## Incorporated sources

| Original | Location in the canonical repository | Status |
| --- | --- | --- |
| `mihran94/JARVIS-AI` | root | Main Python/PySide6 app, eight-provider router, safety policy |
| `mihran94/Jarvis-Blue` | `legacy/jarvis-blue/` | Whole original main branch, matching file blobs and Git subtree history |
| `mihran94/jarvis-blue-android` | `android/` | Whole original main-branch file set; secure endpoint fixes intentionally differ from upstream |
| `mihran94/JARVIS-Mobile-Beta` | `legacy/jarvis-mobile-beta/` | Whole original main branch and subtree history |
| `mihran94/jarvis-unified-builds` | `legacy/jarvis-unified-builds/` | Archived earlier workflow definitions; **not active workflows** |
| `dev/windows10-installer-20261113` | `desktop/`, `tests/`; history as additional merge parent | Blue HUD, system/network metrics, optional local dictation/speech utilities and tests; duplicate installers not activated |

The visual dashboard shares the *existing* PySide6 Window, provider router,
voice consent UI, mobile bridge and emergency stop. The new themed orb reflects
only the state of a chat worker; it does **not** start the microphone or claim
that an AI provider is reachable. System/network metrics read local counters
without opening connections. The existing native voice controls are primary.
The imported Vosk and pyttsx3 adapters are **optional source modules** and not
automatically installed or enabled.

The canonical CI workflows are in `.github/workflows/`. Files under
`legacy/` are historical code and must not be shipped as additional apps.
No other production entrypoint, duplicate Windows installer or active
background listener is introduced by consolidation.

## Unmerged source and verification work — do not delete yet

Branches on original repositories may contain commits not reachable from
their `main`. Their branch references must be preserved and reviewed before
**permanent repository deletion**:

- `mihran94/jarvis-blue-android`:
  `security/minimal-permission-diagnostic-20261112` (33 commits ahead of main,
  diagnostic work); `feature/responsive-smart-updates-v119-20261109`
  (14 unique commits, gold/Exness and update experiments);
  `feat/jarvis-blue-mobile-1.0.0` (16 divergent commits);
  the `fix/gemini-voice-android12-v118-20261109` branch is behind main.
- `mihran94/Jarvis-Blue`:
  `development/nov-beta-v73-1` (4 divergent commits),
  `development/windows-native-tests` (one independent commit),
  `feature/v72-mobile-remote-command-center` (one independent commit).
  Other branches were identical to or behind main at audit time.
- MiniMax v0.2.0 and MARK LVI full sources have **not** been obtained from the
  earlier handoff and cannot be claimed as incorporated.

Until each unique branch is exported or its changes have been reviewed,
deleting original repositories risks losing source. Neither a repository
deletion nor an uninstall from the user's PC is performed by these commits.
For the final retirement, take a full bare mirror/backups of original refs and
Git history, validate hashes, ensure CI and physical installs pass, then remove
old repositories using authorized GitHub administration and remove older local
installations with a backup of `%LOCALAPPDATA%/JarvisAI` and credential vault
before touching user data. The GitHub connection used here does not expose
repository deletion.

## Security and operational boundaries

- The Windows listener remains OFF by default; HTTPS, explicit user pairing
  and per-action confirmation continue to apply.
- Pairing secrets are stored in Windows Credential Manager; device metadata
  and chat history are private local SQLite data, not encrypted by this app.
- No automatic shell execution, remote desktop control or trading is enabled.
- The Android APK is a debug beta, Windows installer unsigned beta, and phone
  hardware pairing has not yet passed an end-to-end field acceptance test.
