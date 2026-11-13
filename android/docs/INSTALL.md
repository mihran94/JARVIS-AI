# JARVIS BLUE MOBILE — APK Installation Guide

Private sideload installation. No Google Play Store involvement, no root, no
security settings are weakened.

---

## 1. What you are installing

| Artefact | Path | Signing |
|----------|------|---------|
| Debug APK | `app/build/outputs/apk/debug/app-debug.apk` | Android debug key, id `com.jarvisblue.mobile.debug` |
| Release APK | `app/build/outputs/apk/release/app-release.apk` | `jarvisblue` key (PKCS#12), id `com.jarvisblue.mobile` |

Both are **sideloaded** — Android will warn you about an unknown source. That
warning is expected and correct.

---

## 2. Install the release APK (recommended)

### Option A — install from your computer over USB

```bash
# 1. Enable Developer options on the phone
#    Settings → About phone → tap "Build number" 7 times
# 2. Settings → System → Developer options → USB debugging = ON
# 3. Connect the phone, accept the "Allow USB debugging?" prompt

adb devices                       # the phone must be listed
adb install -r app/build/outputs/apk/release/app-release.apk
```

`-r` reinstalls over an existing copy **with the same signature**. Without it,
or with a different signature, uninstall first:

```bash
adb uninstall com.jarvisblue.mobile
adb install app/build/outputs/apk/release/app-release.apk
```

### Option B — install from the phone itself

1. Copy `app-release.apk` to the phone (USB cable, cloud drive, SD card…).
2. Open **Files** on the phone → tap the APK.
3. Android asks which app should open it → choose **Package Installer**.
4. You will see **"This app was built for an older version of Android"** — no,
   you will see *"For your security, your phone is not allowed to install
   unknown apps from this source"* → tap **Settings** → allow **Files** (or
   whichever app you used) to install unknown apps → go back → **Install**.

> Allowing "install unknown apps" is scoped to that one file manager app. You
> can revoke it immediately afterwards in *Settings → Apps → Special app
> access → Install unknown apps*.

### Option C — from the phone's file manager over local HTTP

```bash
cd app/build/outputs/apk/release
python3 -m http.server 8000
```

Open `http://<your-computer-ip>:8000` on the phone and download the APK.

---

## 3. Verify what you installed

```bash
$ANDROID_HOME/build-tools/35.0.0/apksigner verify --verbose --print-certs \
  app/build/outputs/apk/release/app-release.apk
```

You should see:

```
Verified using v1 scheme: true
Verified using v2 scheme: true
Verified using v3 scheme: true
```

And the SHA-256 of the signing certificate — write it down. If you ever
rebuild the APK with the same keystore, the certificate hash must match; if it
does not, the phone will refuse the update.

```bash
sha256sum app/build/outputs/apk/release/app-release.apk
```

---

## 4. First-run setup

### 4.1 AI provider (required for live intelligence)

1. Open **Settings → AI providers**.
2. Pick a provider (OpenAI, Gemini, minimax, Ollama, or any OpenAI-compatible
   gateway).
3. Enter the base URL (leave the default unless you know otherwise) and the
   model id.
4. Paste the API key → **Save key**.
5. Switch the provider **on**, then tap **Health check**.

The key is encrypted with the Android Keystore before it touches the disk. It
is never written into the APK and never appears in a log or in the audit trail.

For a fully local setup, run Ollama on your own machine and reach it over a
VPN/tunnel:

```
Base URL: http://100.x.y.z:11434      # your Tailscale/WireGuard address
Model id: llama3.1
```

### 4.2 Permissions

Open **Control → Permissions** and switch on only what you want. The dashboard
lists every capability bucket and every individual tool. Everything starts
**off**.

Suggested minimum for a first run:

- ✅ **AI providers** (cloud AI) — if you configured a provider
- ✅ **Package inventory** — so "open WhatsApp" works
- ✅ **System settings** — so "open Wi-Fi settings" works
- ✅ **Automation** — so "set an alarm" works
- ✅ **Personal memory** — if you want the assistant to remember things
- ⬜ Microphone — only when you want to talk to it
- ⬜ Screen capture, Accessibility, Notifications, Files, Remote — until you
  actually need them

### 4.3 App lock (recommended)

**Control → Permissions → App lock → Require unlock on launch**. The app then
requires a biometric confirmation after the session timeout (5 / 15 / 60
minutes).

### 4.4 Voice

**Assistant → Talk** triggers the microphone runtime permission on first use.
The language chips select Tamil, English or French.

For Tamil text-to-speech, install the Tamil voice pack:
*Settings → System → Languages & input → Text-to-speech output → Tamil →
install the "Google Text-to-Speech" language data.*

### 4.5 Make it the default assistant (optional)

*Settings → Apps → Default apps → Assistant app → JARVIS BLUE.*
(or long-press the assistant gesture / press-and-hold the home button and pick
JARVIS BLUE). Then the assistant gesture and "Hey assistant" route to the app.

### 4.6 Optional system grants

| What | Where |
|------|-------|
| Notification access | *Settings → Notifications → Device & app notifications → Notification access → JARVIS BLUE* |
| Accessibility | *Settings → Accessibility → Downloaded apps → JARVIS BLUE* (read the disclosure first) |
| Exact alarms | *Settings → Apps → Special app access → Alarms & reminders → JARVIS BLUE* |
| Battery (Xiaomi/OnePlus/Oppo) | *Settings → Apps → JARVIS BLUE → Battery → No restrictions* and allow *Autostart* / *Background activity* |

---

## 5. Windows pairing

1. On the Windows machine:

   ```powershell
   cd windows-bridge
   .\.venv\Scripts\activate
   python -m jarvis_bridge.server --generate-secret
   python -m jarvis_bridge.server --host 127.0.0.1 --port 8765
   ```

2. Reach it through Tailscale / WireGuard / an SSH tunnel — **do not open the
   port on your router**.
3. In the app: **Control → Windows**, enter the host and port, paste the
   secret, tap **Pair**.
4. Tap **Refresh** — the dashboard shows the PC state, CPU, RAM, disk and job
   counts.

The secret is stored in the Keystore-encrypted vault. **Unpair** deletes it.

---

## 6. Upgrading

```bash
adb install -r app/build/outputs/apk/release/app-release.apk
```

`adb install -r` preserves the app data, so your grants, memories and audit
log survive the update.

---

## 7. Uninstalling

```bash
adb uninstall com.jarvisblue.mobile
```

or long-press the icon → Uninstall.

Because the database passphrase is derived from a Keystore key that belongs to
the app, uninstalling makes the encrypted database permanently unreadable.
There is no recovery path — that is intentional.

Before uninstalling, export anything you want to keep:
**Settings → Audit trail** (copy the exported text) and **Control → Memory**.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "App not installed" | Signature mismatch with the previously installed copy | `adb uninstall com.jarvisblue.mobile` then install again |
| Install blocked | "Install unknown apps" not granted for the source app | Grant it in *Settings → Apps → Special app access → Install unknown apps* |
| Chat replies "Offline mode" | No provider enabled or the key is wrong | Settings → enable the provider → **Health check** |
| "Missing permission: …" in a reply | The capability bucket is off | Control → Permissions → enable it |
| A tool says it needs confirmation | It is HIGH risk by design | Read the payload in the dialog, then Approve |
| Wake word never triggers | The service is not running, or the device killed it | Open the Assistant screen and start it there; on Xiaomi/OnePlus exempt the app from battery optimisation |
| Wake word does nothing on Android 14+ | Background microphone FGS starts are forbidden | The service must be started while the app is visible — this is an Android rule, not a bug |
| Tamil voice sounds wrong | The Tamil voice pack is missing | Install it in *Settings → System → Languages & input → TTS output* |
| Windows shows "Paired but offline" | The bridge is not running or the tunnel is down | Start the bridge; check the host/port; the app only accepts private addresses |
| Nothing works at all | The emergency stop is engaged | Control → Permissions → Emergency stop → **Release** |

---

## 9. Security notes for this install

* The APK is signed with a key that is in the repository. Keep the repository
  private, and generate your own key before sharing the APK with anyone.
* The app requests **no** dangerous permissions it does not use. In particular
  it never asks for `READ_SMS`, `READ_CONTACTS`, `CAMERA`, `LOCATION` or
  `MANAGE_EXTERNAL_STORAGE`.
* The app never auto-grants a permission, never roots the device, never
  disables a security setting and never bypasses the lock screen.
* If you later want to remove every trace: uninstall, and on the desktop stop
  the bridge and rotate `JARVIS_BRIDGE_SECRET`.
