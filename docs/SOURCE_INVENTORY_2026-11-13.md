# JARVIS AI — verified source inventory and phased integration plan
Date: 2026-11-13. Working branch: `integration/main-preserving-20261113`.

This document distinguishes **source present**, **source only identified**, and
**tested functionality**. A copied folder is not evidence that two applications
communicate. Never merge to `main` without separate owner approval.

## Sources directly inspected

| Source | Verified availability | Role / integration boundary |
|---|---|---|
| `mihran94/JARVIS-AI` | GitHub main + integration branch | Windows PySide6 UI, provider router, permissioned actions, bridge server, SQLite |
| `mihran94/Jarvis-Blue` | GitHub repository plus `legacy/jarvis-blue/` in monorepo | Voice, legacy UI, provider adapters; PyQt6 cannot be directly mixed with PySide6 |
| `mihran94/jarvis-blue-android` | GitHub repository plus `android/` | Kotlin/Compose app, Android Keystore and bridge client; build separately |
| `mihran94/JARVIS-Mobile-Beta` | Imported as `legacy/jarvis-mobile-beta/` by history-preserving subtree commit `bc34c525` | Review prototype, never reuse demo authentication as production security |
| `mihran94/jarvis-unified-builds` | GitHub repository, metadata accessible | Potential release/build repository; not a source-of-truth runtime |
| `JARVIS-MiniMax-Handoff.zip` | User Library | Three text/PowerShell instructions, **not** standalone MiniMax v0.2.0 source |
| `Jarvis-Blue-Development-Plan.zip` | User Library | 84 old source files; review differences against preserved `legacy/jarvis-blue/` |
| `JARVIS_BLUE_BACKGROUND_PATCH_01.zip` | User Library | PyQt6 system tray controls; adapted to PySide6 at `desktop/tray.py`, with tests |
| `JARVIS_BLUE_WINDOWS_TEST_FIX_01.zip` and `02.zip` | User Library | Project updater and Windows test patches; preserve as historical variants until diff reviewed |
| `JARVIS_BLUE_OFFLINE_WINDOWS_TESTS.zip` | User Library, identified | Separate Windows regression bundle; pending file-by-file review |
| MARK LVI / `Mark-LVI-main.zip` | Mentioned in earlier conversation, not found in accessible GitHub trees or Library results | **Source missing**: cannot accurately import or validate without archive |
| Separate MiniMax JARVIS-AI v0.2.0 | Mentioned, no complete standalone source archive verified | **Source missing**: handoff only points to repository clones and requests an extra archive |
| Local Windows folders | Not mounted from the user's PC in this chat | Inventory requires a user-connected Work desktop session or owner export |

Source import: `bc34c5251c756caca4f76cf30bd7d0c0ac12e965` has **two parents** and preserves the upstream Mobile Beta history; manifest commit `ed4b4793` follows. This source is present as a legacy prototype, not wired into production authentication.

GitHub branches reviewed include existing voice, Windows installer, PWA and
security branches in JARVIS-AI; Android security/voice branches; and several
Jarvis-Blue development branches. Their presence does not mean that all changes
are already merged into the currently tested branch.

## Consolidation decisions

1. Keep the `main` branch untouched. Require passing integration tests,
   Android debug build, Windows EXE + installer build, signed bridge contract
   tests, device acceptance and explicit owner approval before any merge.
2. Keep one **Python desktop provider router** under `providers/` with eight
   named providers. Keep Android's native Kotlin provider adapter as a
   platform client of the same documented feature contract, not Python copied
   into an APK. Paid fallback requires user consent.
3. Keep `remote/` as the PC bridge authority and the `android/core/windows`
   module and `iphone-pwa/` as clients. Pair each device independently,
   require TLS/tunnel, HMAC signing, nonce replay prevention, key revocation,
   and owner approval for actions.
4. Use `desktop/tray.py` for explicit background mode instead of loading
   the legacy PyQt6 UI inside the PySide6 process. Microphone stays opt-in.
5. Audit each source for license obligations, compatible dependencies,
   secrets, duplicate modules and tests before adopting it. Preserve original
   source trees and history until provenance review is complete.
6. A memory read or write must pass active owner permission, even for
   an already paired device. Never treat pairing as consent.
7. Do not enable automated trading or unsupervised shell execution.

## Remaining implementation phases and acceptance criteria

| Phase | Work | Evidence required |
|---|---|---|
| 1. Inventory + CI integrity | Complete archive diffs, eliminate hash drift, test both desktop OSes | Commit SHAs, CI logs, source manifest |
| 2. Real builds | Build monorepo Windows EXE + unsigned installer and Android debug APK | Artifacts, SHA-256, Windows smoke/Android install validation |
| 3. Device protocol | Pair Windows and Android via private TLS; authenticate, rotate/revoke, prevent replay | Real-device and Python/Kotlin integration tests |
| 4. Shared brain/memory | Settings/notes sync with conflict resolution, encryption, explicit owner permissions | Cross-client round-trip and restart persistence tests |
| 5. Voice + agents | Windows acceptance of STT/TTS, opt-in wake words, approved remote actions | Mic consent tests, native UI automation acceptance |
| 6. Sources + releases | Import only genuinely available MiniMax, MARK, mobile beta modules with attribution | Complete source manifest, license review, installer + APK release tests |

## Current limitations

Unit tests, bridge request tests and generated artifacts are distinct. A
successful simulated HMAC test proves no real Android device was paired; a
successful hosted APK compilation does not prove installation or launch.
Unsigned beta builds are for testing only. No API keys, signing keystores or
real device secrets belong in GitHub or public artifacts.
