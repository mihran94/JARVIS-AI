# Android JARVIS Remote — safe setup and crash diagnostics

**Current tested binary:** PR #22 crash repair, source `d38076bfa00337b140df9cc17dc210daa9b3321c`, [Android CI run 43528444985](https://github.com/mihran94/JARVIS-AI/actions/runs/43528444985). That exact debug APK passed Gradle unit tests, final merged permission audit, installation and Android 15 emulator cold launch, and remained alive long enough for a screenshot. The patch is merged to `main` as `9313cb6`. A physical owner's phone is **not yet** tested.

- Android requirement: Android 12/API 31 or later. Package in the CI **debug** artifact is `com.jarvisblue.mobile.debug`, not a native iOS app.
- The phone is a **remote** to Windows AI. It has no standalone AI/chat/microphone assistant. The opening screen says **JARVIS Remote / Not paired**.
- The previously observed immediate launch crash was `InvalidAlgorithmParameterException: Caller-provided IV not permitted`. A Keystore AES-GCM key configured for random IVs now generates the encryption IV itself; the authenticated IV remains stored with ciphertext. Do not disable Android security features.

## Starting on the phone

1. Get the APK from the exact successful GitHub Actions run, verify its SHA-256 (the archive contains `app-debug.apk.sha256`) and install using your phone's normal supported installer. Do not bypass Play Protect or other protections for a file you cannot verify.
2. If the package refuses an update, a previous **debug APK signed with a different CI certificate** may already be installed. Back up and record any existing remote pairing details before considering removal; uninstalling normally deletes that app's private data. Production updates need a stable owner-managed signing key.
3. Open **JARVIS Remote**. The default first screen lets you enter an **HTTPS host**, **port** and 32+ character one-time pairing secret, generated on Windows. It will not control a PC until you configure a valid private HTTPS endpoint and pair it.
4. If it installs but closes immediately, obtain Android logcat for package `com.jarvisblue.mobile.debug` without passwords, secrets or private messages. An unverified or unsupported phone-specific issue cannot be diagnosed from the APK digest alone.

## Connection to Windows — private HTTPS only

1. On the Windows JARVIS app open **Phone Remote**, choose **Pair a phone** and copy the unique pairing secret. Never paste it into support chats or source code.
2. The bridge listener is **off by default** and binds `127.0.0.1:8765` unless changed. Android requires HTTPS. The safe documented pattern is a trusted, *private* HTTPS tunnel/reverse proxy that terminates TLS and forwards requests to the loopback PC listener. On the PC only, explicitly check the option **My private tunnel terminates TLS** for the loopback listener if appropriate. Never expose the raw HTTP port publicly.
3. Enter the actual **HTTPS hostname** and matching public-facing HTTPS port in Android, e.g. port `443` if your private HTTPS reverse proxy accepts 443. Do not copy `127.0.0.1` into a phone: that means the *phone itself*.
4. Paste the unique secret from Windows JARVIS; press **Pair** and **Refresh**. An address being saved is not proof of a live connection. Expect a signed status result and reachable Windows screen before attempting jobs.
5. An expired/revoked secret or TLS certificate mismatch must fail closed. Do not disable certificate verification, use HTTP for the phone, or open a public router port.

## Actual limitations

- Windows pairing and a production TLS/tunnel have **not** passed a real Android-to-PC field acceptance test.
- A remote request may enter a review queue. Windows job approvals are not general purpose, autonomous execution. PC actions still require local owner's specific approval and Emergency Stop remains authoritative.
- The emulator CI gate checks APK permissions, Android process liveness and a rendered screen. It does **not** test a real network, fingerprint, signed release upgrade or Android 12/13/14 device behavior.
- An unsigned/beta app or Windows installer should not be treated as a production-certified release.
