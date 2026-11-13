# JARVIS AI unified beta — build verification and owner setup
Date: 2026-11-13. Work branch: `integration/main-preserving-20261113`.
This is an **integration test build**, not a production-certified release.

## Verified downloads (actual hosted workflow artifacts)

| Target | Built from | GitHub Actions run | File and size | SHA-256 |
|---|---|---|---|---|
| Windows x64 unsigned Inno Setup installer | `1d5e234154ba990e09364bf28137fcf5c9400d72` | [43446360859](https://github.com/mihran94/JARVIS-AI/actions/runs/43446360859) | `JarvisAI-Setup-Windows-x64.exe`, 38,446,995 bytes | `f04efdd3ac06027c1ee191fa99cc5de3fc35b59fdd657738eb519da31a74b1a2` |
| Android 12+ debug APK | `8e5d87fe6fd95cc3702a94192b30435ea3f7d264` | [43446656087](https://github.com/mihran94/JARVIS-AI/actions/runs/43446656087) | `app-debug.apk`, 79,795,623 bytes | `ac22019bf585a09cc72503e8c20d75977a33330ca8d40268404a5bce3b74acf5` |

The corresponding GitHub artifact ZIPs contain manifests. The installer and
APK were downloaded back from GitHub and SHA-256 verified against CI output.
The Windows artifact also includes the PyInstaller `JarvisAI/` folder and
per-file release manifest. The installer and desktop folder are **unsigned**;
the Android debug APK is signed by a temporary Android debug certificate,
not the owner's production signing certificate.

The binaries predate the additional Mobile Beta subtree import; that import
is isolated under `legacy/jarvis-mobile-beta/`, not executed by either app.
Release candidates must be rebuilt from a final reviewed integration SHA.

## What was actually tested

- Desktop/core Ubuntu: 397 passed, 3 skipped at `d1ac4589`.
- Desktop/core Windows: 395 passed, 5 skipped at `d1ac4589`.
- New explicit PySide6 background tray tests subsequently passed on Windows and Ubuntu CI at `1d5e234`.
- Windows installer workflow: desktop suite, PyInstaller folder creation,
  release-manifest generation, Inno Setup compilation and artifact upload passed.
- Android Gradle workflow: `:core:windows:testDebugUnitTest`,
  `:app:testDebugUnitTest`, `:app:assembleDebug`, APK nonempty check,
  SHA-256 digest and artifact upload passed (Gradle BUILD SUCCESSFUL).
- Source integrity workflow and initial imported source tests passed, and
  the Mobile Beta Git-history-preserving subtree import succeeded.

The Kotlin/Python signing test vectors are compatible in unit tests. **No
real Android-to-Windows pairing or encrypted network session was tested**;
passing two different platform test suites alone is not a live connection test.

## Windows beta setup (owner machine)

1. Download the installer from the linked Windows Actions run.
2. Use Windows PowerShell to verify the file's SHA-256:

   ```powershell
   (Get-FileHash .\JarvisAI-Setup-Windows-x64.exe -Algorithm SHA256).Hash.ToLower()
   ```

   Compare against the full digest in the table; reject if different.
3. Run the installer from your own account. Because it is unsigned, Windows
   may display a SmartScreen warning; do not override a warning for a file
   whose source or digest is uncertain.
4. Launch **JARVIS AI** from the Start menu. Set an AI provider/model and
   enter its key only through the app's secure key-storage settings.
5. Test a plain chat response and **Emergency Stop** before configuring
   automation. The tray menu allows optional background mode; close is not
   silently converted to background mode.

## Android debug APK setup

1. Verify the downloaded `app-debug.apk` SHA-256, ideally on your PC
   (`Get-FileHash` on Windows or `sha256sum` on Linux).
2. On a compatible Android 12+ phone, use the supported system package
   installer for an APK from a source you trust. No root and no disabling
   device security protections are needed. A workplace-managed device may
   prohibit sideloading.
3. The debug application ID is `com.jarvisblue.mobile.debug`, so it is
   separate from a regular release-signature install.
4. Open the app; enable only the permissions you want, configure an AI
   provider in the app's settings, and verify basic chat and microphone
   permission behavior. For crash reports, collect a sanitized Android
   logcat without API keys, tokens or personal messages.
5. This is a **debug build**; it must not replace a properly signed
   production APK.

## Windows ↔ Android secure pairing checklist

Pairing cannot be verified from hosted CI alone. On the Windows desktop open
**Mobile Bridge** and review its explicit controls:

- The listener is off by default. It uses 127.0.0.1 by default and rejects
  public network binding. To make the bridge reachable by a phone, configure
  a trusted TLS endpoint/private tunnel with appropriate private-network
  routing. **Never expose the desktop control port on a public router.**
- Generate a unique device pairing secret using **Pair a phone**. Transfer
  it out of band and store it only in the Android Keystore-backed vault.
  Never paste real secrets into repository files, issues, screenshots or CI.
- The Android bridge address must be **HTTPS** (no HTTP downgrade). The
  device must trust the server certificate and reach that endpoint through
  your approved private network.
- Test signed `GET /api/status`, replay rejection, revocation, a controlled
  job queue request and rejection without approval; then inspect the
  desktop audit log. Jobs are **queued**, not automatically executed.
- The desktop owner must separately allow memory synchronisation; pairing
  alone does not grant remote memory reads or writes. Restart persistence
  and conflict-free multi-device memory remain a future acceptance gate.
- Remove any temporary pairing secret after testing. Revoke the device if
  the phone is lost.

Do not enable a public HTTP listener or weaken TLS certificate validation
just to obtain a passing connection test.

## Release blockers / missing sources

1. No physical Windows install+launch acceptance, phone APK install+launch
   acceptance, or cross-device end-to-end pairing has yet been demonstrated.
2. The current Android release is debug signed; Windows EXE/installer is
   unsigned. Production signing and platform security review remain.
3. Complete separate **MiniMax JARVIS-AI v0.2.0 source** was not present in
   the accessible `JARVIS-MiniMax-Handoff.zip`; that ZIP contains instructions
   rather than code. **MARK LVI / Mark-LVI-main.zip** was not found in
   accessible sources. Do not pretend either was imported.
4. Some Windows voice modules need real microphone and Windows SAPI
   acceptance. The iPhone PWA is future-ready design, not a native signed IPA.
5. Full persistent multi-device settings/memory sync, remote execution
   dispatch, live AI provider billing/fallback and application update
   safety need end-to-end validation. Trading/orders remain prohibited
   unless separately authorised.

**Merge rule:** Do not merge to `main` without verified acceptance tests and
explicit owner approval. Preserve the original repositories and source histories.
