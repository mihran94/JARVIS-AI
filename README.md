# JARVIS BLUE MOBILE

**A private, voice-controlled Android AI assistant that can actually do things on
your phone — under a permission and risk gate you control.**

Kotlin · Jetpack Compose · Clean Architecture · Room + SQLCipher · Android Keystore ·
OpenAI / Gemini / minimax / Ollama · Tamil, English, French · **minSdk 31 (Android 12)**

---

## What it is

JARVIS BLUE MOBILE is a *system-integrated* assistant, not a chat wrapper. It can
launch apps, read notifications you allow it to read, set alarms, draft messages
for you to send, organise files you grant it access to, inspect TLS on networks
you own, run a quantum-circuit simulation, and monitor your always-on Windows
JARVIS BLUE desktop over a private tunnel.

Every one of those actions goes through a single gate that validates the
arguments, checks your grants, evaluates the risk and asks you to confirm when
it matters. The AI can *request* an action; it can never perform one.

---

## Quick start

```bash
# 0. After a fresh clone (see docs/BUILD.md §0)
bash gradle/wrapper/restore-wrapper.sh && chmod +x gradlew

# 1. Toolchain: JDK 17 + Android SDK 35 (see docs/BUILD.md)
export ANDROID_HOME="$HOME/Android/sdk"
echo "sdk.dir=$ANDROID_HOME" > local.properties

# 2. Build
./gradlew :app:assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:assembleRelease      # app/build/outputs/apk/release/app-release.apk

# 3. Install
adb install -r app/build/outputs/apk/release/app-release.apk
```

Then open the app, go to **Settings → AI providers**, paste an API key, and
start talking. Full walkthrough in [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Architecture at a glance

```
        ┌──────────────┐   requests only   ┌──────────────┐
        │  AI provider │ ────────────────▶ │  ToolExecutor│
        │  (OpenAI,    │                   │  ★ THE GATE  │
        │   Gemini,    │                   └──────┬───────┘
        │   minimax,   │                          │
        │   Ollama)    │        schema · risk · permission · confirmation
        └──────────────┘                          │
                                                  ▼
                                   Android intents · SAF files · alarms
                                   media keys · diagnostics · Windows bridge
```

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Modules

| Module | What it holds |
|--------|---------------|
| `core:model` | Pure Kotlin domain models — no Android dependency |
| `core:common` | Result types, credential redaction, fuzzy text matching |
| `core:security` | Android Keystore, secret vault, grants, biometrics, app lock, emergency stop |
| `core:database` | Room + SQLCipher, encrypted at rest |
| `core:ai` | 5 providers, routing, health, budgets, tool schemas, offline fallback |
| `core:tools` | Tool registry, schema validation, risk gate, device control, security scanner, quantum simulator |
| `core:voice` | Wake-phrase matcher, on-device-first STT, TTS, language detection |
| `core:windows` | Signed HTTPS/WebSocket client for the desktop bridge |
| `core:ui` | The blue-and-black Compose design system |
| `feature:chat` | Conversation + live tool-call trace |
| `feature:assistant` | Orb, waveform, wake word, push-to-talk |
| `feature:studio` | Coding studio · cyber lab · quantum lab |
| `feature:command` | Permissions · tasks · memory · Windows · settings |
| `app` | Manifest, services, DI wiring, navigation |
| `windows-bridge/` | Reference Python desktop server |

---

## Feature status — what works, what is limited, what is absent

### ✅ Working

* **AI chat** with OpenAI, Gemini, minimax, any OpenAI-compatible gateway and
  your own Ollama server; automatic failover; provider health checks; daily
  token budget.
* **Tool calling** with schema validation — the model cannot smuggle extra
  parameters.
* **Tamil, English and French** with automatic language detection, per-language
  TTS and an honest *On-device ASR* vs *Cloud ASR* badge.
* **Wake phrase** "Hey Jarvis Blue" with fuzzy matching and Tamil/French
  variants.
* **Default-assistant integration** (`VoiceInteractionService` + system
  `RecognitionService`).
* **23 registered tools**: app launch, settings deep-links, alarms, dialler,
  message drafts, media transport, share, device diagnostics, notification
  summaries, screen text, file listing/organising, network inspection, security
  review, code quality checks, quantum simulation, memory, and the Windows
  bridge.
* **Encrypted everything**: SQLCipher database, Keystore-backed key vault,
  `allowBackup=false`.
* **Permission dashboard** with 18 capability buckets and per-tool switches.
* **Emergency stop** that survives restarts and blocks every tool.
* **Audit log** — every call, permission change and confirmation, exportable.
* **Windows bridge** with HMAC-signed requests and replay protection, plus a
  reference desktop server.
* **Quantum laboratory** — a classical state-vector simulator that is honest
  about being a simulation.

### 🟠 Limited, and the app says so

* **Background wake word** — Android 14+ forbids starting a microphone
  foreground service from the background. The service is implemented; it must be
  started from the visible app.
* **On-device ASR** — needs an on-device language pack for the locale.
* **Screen reading** — MediaProjection consent is required every time; the
  bundled analyser reports frame statistics rather than running OCR.
* **Code execution** — static analysis only. Generated code is never executed
  on-device; real builds are delegated to your Windows machine.
* **TTS** — falls back to English when a language pack is missing rather than
  reading gibberish.

### ⬜ Not included

* Acoustic hotword model (the seam is `WakeWordEngine`).
* On-device LLM (the seam is `ProviderRegistry`).
* Git operations on-device.
* Quick-settings tile / home-screen widget.
* An unrestricted remote desktop (deliberately — use a separate approved tool).

Full table with the platform reasoning: [`docs/ANDROID_COMPATIBILITY.md`](docs/ANDROID_COMPATIBILITY.md).

---

## Security properties

* **Deny by default.** 18 capability buckets, 18 in-app grants and 12 runtime
  permissions — all independent, all revocable.
* **The model never acts.** `ToolExecutor` is the only path to an effect and
  the only place that can grant or refuse one.
* **Arguments are validated.** Unknown properties, wrong types, out-of-range
  values and non-enum values are all rejected.
* **Risk is argument-aware.** A message body mentioning OTPs or bank details is
  escalated to CRITICAL regardless of the model's framing.
* **Fresh confirmations.** High-risk tools require a decision for *that* call.
* **Secrets never leak.** `Redactor` scrubs credentials on every write path —
  logs, audit rows and exports.
* **Data is encrypted.** Room + SQLCipher, keys in the Android Keystore, cloud
  backup disabled.
* **Remote access is signed.** HMAC-SHA256 over method, path, timestamp, nonce
  and body hash, with replay protection. No remote shell, ever.

Threat model: [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Module map, the execution gate, the reasoning loop, data-at-rest table |
| [`docs/PERMISSIONS_MATRIX.md`](docs/PERMISSIONS_MATRIX.md) | Every bucket, every tool, every manifest permission and why |
| [`docs/ANDROID_COMPATIBILITY.md`](docs/ANDROID_COMPATIBILITY.md) | Per-feature platform reality and Samsung/Xiaomi/OnePlus/Pixel notes |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) | Trust boundaries, 12 threats with mitigations, residual risks |
| [`docs/MILESTONES.md`](docs/MILESTONES.md) | Stage-by-stage status and the defect log |
| [`docs/BUILD.md`](docs/BUILD.md) | Toolchain, signing, low-memory hosts, troubleshooting |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Sideload installation, first-run setup, pairing, upgrade, uninstall |
| [`docs/TESTING.md`](docs/TESTING.md) | Test inventory, results, device test plan |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Everyday use of every screen |

---

## Windows bridge

```powershell
cd windows-bridge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m jarvis_bridge.server --generate-secret
$env:JARVIS_BRIDGE_SECRET = "<paste>"
python -m jarvis_bridge.server --host 127.0.0.1 --port 8765
```

Pair from the phone with the same secret. Reach it over Tailscale, WireGuard or
an SSH tunnel — **never** by opening the port on your router. The bridge
signing scheme is verified byte-for-byte against the Android client by a
cross-implementation test.

---

## Licence

Private project. Not published to any store. The bundled signing key is for
your own device only — generate your own before sharing the APK.
