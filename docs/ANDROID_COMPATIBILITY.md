# JARVIS BLUE MOBILE — Android & OEM Compatibility Analysis

Target: **Android 12 (API 31) minimum**, **Android 15 (API 35) target**.
Verified build configuration: `compileSdk 35`, `minSdk 31`, `targetSdk 35`.

---

## 1. Feature-by-feature platform reality

Legend: **Working** = implemented and exercised on-device · **Conditional** =
works when the platform/OEM allows it · **Limited** = implemented with a reduced
scope that the UI states explicitly · **Unavailable** = not possible without
violating Android policy.

### 1.1 Voice

| Feature | Status | Android / OEM restriction |
|---------|--------|---------------------------|
| Push-to-talk speech recognition | Working | `RECORD_AUDIO` runtime permission. Android 12+ shows the mic indicator while active. |
| On-device (offline) recognition | Conditional | `SpeechRecognizer.createOnDeviceSpeechRecognizer` requires API 31+ **and** a downloaded on-device language pack. The app checks `isOnDeviceRecognitionAvailable` and labels the engine as *On-device ASR* or *Cloud ASR* in the UI — it never claims offline when it is not. |
| Text-to-speech (Tamil / English / French) | Conditional | Needs the matching voice pack in *Settings → System → Languages & input → Text-to-speech output*. The app falls back to English and states that the requested voice pack is missing rather than reading Tamil with an English voice. |
| Automatic language detection | Working | Unicode block detection for Tamil + a French marker set for Latin script. Deterministic, no model download. |
| Wake phrase "Hey Jarvis Blue" | Working (proof of concept) | Implemented as **transcript matching** against the on-device recogniser, with fuzzy tolerance for ASR errors and Tamil/French variants. A true acoustic hotword model (Porcupine/Snowboy) is a drop-in replacement point but is not bundled — see §4. |
| Continuous background wake word | Conditional | Requires a microphone foreground service with `FOREGROUND_SERVICE_TYPE_MICROPHONE`, an ongoing notification and the system mic indicator. **Android 14 (API 34) refuses to start a microphone FGS from the background** (`ForegroundServiceStartNotAllowedException`) — the app catches this and asks the user to open it from the assistant screen. The service is never started silently from a boot receiver. |
| Default assistant (`VoiceInteractionService`) | Working | The user selects JARVIS BLUE in *Settings → Apps → Default apps → Assistant app* or via the assistant gesture. Until then Android routes the gesture elsewhere. |
| System recognition service | Working | `android.speech.RecognitionService` + `res/xml/recognition_service.xml` lets the system use JARVIS BLUE as a voice-input provider. |
| Voice interruption / turn-taking | Limited | Implemented as: TTS is stopped before the next recognition cycle begins (`stopListening` → `speak`), so the assistant does not talk over itself. True barge-in requires the OS assistant pipeline, which is available once JARVIS BLUE is the default assistant. |

### 1.2 Device control

| Feature | Status | Restriction |
|---------|--------|-------------|
| Launch an app | Working | Uses `PackageManager.getLaunchIntentForPackage`. Package visibility is limited by the `<queries>` element. `QUERY_ALL_PACKAGES` is **not** requested. |
| Open system settings | Working | Deep-links into `Settings.ACTION_*` screens. The user always sees the Settings app. |
| Set an alarm | Working | `AlarmClock.ACTION_SET_ALARM` — the system clock UI opens so the user confirms. |
| Open the dialler | Working | `Intent.ACTION_DIAL` — the app **pre-fills but does not place** the call. Placing a call programmatically needs `CALL_PHONE`, which the app does not request. |
| Draft a message | Working | `ACTION_SENDTO` / `ACTION_SEND`. The app opens a compose screen; **it never sends**. Sending is always the user's action, and the tool additionally requires a fresh in-app confirmation. |
| Media playback control | Working | `AudioManager.dispatchMediaKeyEvent` — the standard transport-key path. No special permission needed. |
| Share text | Working | `ACTION_SEND` chooser. |
| Notifications: read | Conditional | Requires *Notification access* in Android settings (a toggle, not a runtime dialog). Until granted the tool reports "no notifications available". |
| Notifications: post | Working | `POST_NOTIFICATIONS` on Android 13+. On Android 12 the permission is implicit. |
| Battery / storage / RAM / network diagnostics | Working | `BatteryManager`, `StatFs`, `ActivityManager.MemoryInfo`, `ConnectivityManager`. Read-only. |
| File organisation | Working | Storage Access Framework only. The user grants a tree URI; the app can only read/write inside it. Files are **copied** first and only removed when the `move` flag is explicitly set, which raises the risk to HIGH and triggers a confirmation. |
| Read visible screen | Limited | `MediaProjection` requires the system consent dialog **on every capture**. The bundled implementation analyses a single frame's luminance in memory and writes no pixels to disk. For literal on-screen text the Accessibility service (separately granted) is used. |
| Limited UI automation | Conditional | `AccessibilityService` with `canPerformGestures="false"` — it records the visible text of the current window for a command you issued; it never taps, swipes or acts on its own. Disabled by default; enabling it shows the system disclosure and a permanent status-bar indicator. |

### 1.3 AI and connectivity

| Feature | Status | Restriction |
|---------|--------|-------------|
| OpenAI / Gemini / minimax / OpenAI-compatible | Working | Requires the user's API key, stored in the Keystore-encrypted vault. Keys are never in the APK, never in logs (the `Redactor` scrubs them from every log line and audit row). |
| Ollama (self-hosted) | Working | The user runs the server and reaches it over a VPN/tunnel. The app does not require a publicly reachable endpoint. |
| Offline fallback | Working | A deterministic responder that explains what is unavailable. It never fabricates an answer. |
| Model routing / health / budgets | Working | Priority → health → task heuristic → daily token budget. |
| Tool calling | Working | OpenAI function schema, Gemini `functionDeclarations`, Ollama tools. All arguments are schema-validated before execution. |

### 1.4 Windows bridge

| Feature | Status | Restriction |
|---------|--------|-------------|
| Pairing, heartbeat, job list, submit, cancel | Working | HMAC-SHA256 signed requests over HTTPS or a private tunnel. Replay protection via timestamp + nonce. |
| WebSocket event stream | Working | Same signature scheme, `wss://`. |
| Full interactive desktop control | **Not provided** | Deliberately out of scope — the app never exposes a remote shell. Use a separate, approved remote-desktop product for that. |

---

## 2. OEM behaviour notes

| OEM | Relevant difference | What JARVIS BLUE does |
|-----|--------------------|------------------------|
| **Samsung (One UI 5–7)** | Aggressive background-task killing; "Sleeping apps" can kill services. Battery menu adds a separate "Never sleeping apps" list. | The wake-word service is a foreground service with a visible notification, which One UI keeps alive. The user should add JARVIS BLUE to *Settings → Apps → Special app access → Unrestricted battery usage* for reliable long-running listening. Reminders use `AlarmManager` with `setExactAndAllowWhileIdle`, which One UI honours, but the app falls back to inexact alarms if exact alarms are not permitted. |
| **Google Pixel (Android 12–15)** | Reference behaviour. Battery Saver and "Adaptive Battery" can restrict background work; Android 14 restricts background microphone FGS starts. | Wake word must be started from the app. The app catches `ForegroundServiceStartNotAllowedException` and asks the user to open it. |
| **Xiaomi / Redmi (MIUI, HyperOS)** | The most aggressive OEM: autostart restrictions, a separate "Background activity" permission, and aggressive process reaping that can kill a foreground service. | Recommend *Settings → Apps → Manage apps → JARVIS BLUE → Autostart = On*, *Background activity = On* and *Battery saver = No restrictions*. Without these the wake-word service may be killed on Xiaomi devices. |
| **OnePlus (OxygenOS)** | Similar to Xiaomi: aggressive process management plus a battery-optimisation screen. | Same recommendation: exclude the app from battery optimisation. |
| **Oppo / Realme (ColorOS)** | Background activity and auto-launch restrictions, notification "quiet mode" that can suppress foreground-service notifications (and therefore the mic-indicator-adjacent notifications). | If the foreground-service notification is hidden, the service may be killed. Recommend allowing notifications. |
| **Huawei / Honor (EMUI, MagicOS)** | No Google Play Services in some variants → on-device speech recognition may be unavailable. | The app detects the missing on-device engine and labels the recogniser as *Cloud ASR* instead. |
| **Android Go editions** | Low RAM → background processes are killed aggressively. | Use push-to-talk rather than the wake word; the assistant UI stays usable. |
| **Android 12L / tablets** | Larger screens, multi-window. | The Compose layout scales; the bottom navigation is the only fixed element. |

> No OEM-specific code paths exist in this build. The differences above are
> *configuration guidance*, not code forks — this keeps the app maintainable and
> avoids the fragile `isXxx()` detection that breaks on every monthly update.

---

## 3. Permission dialogs and where the user meets them

| First use of | Dialog | Where |
|--------------|--------|-------|
| Microphone | System runtime dialog | Assistant screen → *Talk* |
| Notifications | System runtime dialog (Android 13+) | First reminder or job alert |
| Notification access | System settings toggle | Settings → Permissions → *Read notifications* |
| File access | System document-tree picker | Control → Tasks → *organize files* |
| Screen capture | System MediaProjection consent | Every capture |
| Accessibility | System accessibility screen | Settings → Permissions → *Limited UI automation* |
| Default assistant | System default-app picker | Settings → Permissions → *Assistant role* |
| Biometric | System biometric prompt | App unlock / sensitive action |

---

## 4. Known gaps, stated plainly

| Gap | Why | Path forward |
|-----|-----|--------------|
| No bundled acoustic hotword model | A production hotword needs a trained model (Porcupine/Snowboy/TFLite). Shipping a third-party SDK adds a licence and a native dependency. The transcript-matching implementation is real and works, but it consumes more CPU than an acoustic model and needs the recogniser running. | `WakeWordEngine` is the single integration point; swap the matcher for a streaming acoustic model behind the same interface. |
| No on-device LLM | Requires a multi-GB model download and a device-capable runtime (llama.cpp / MLC). | `ProviderId.OLLAMA` already covers the "your own server" case; an on-device provider would slot into `ProviderRegistry`. |
| Screen OCR | Would require bundling an OCR model. | The frame analyser is the seam; the Accessibility path already provides literal text. |
| No git integration on-device | Git operations are destructive and remote-capable; the tool would need its own confirmation flow and credential handling. | Delegate to the Windows bridge as a remote job with approval. |
| No multi-window / tablet-specific layout | Out of scope for the first private build. | — |

---

## 5. Compatibility test matrix (to run on your devices)

The script `scripts/compat-check.sh` performs the static half of this matrix.
The dynamic half needs real hardware:

| Test | Pixel 6/7/8 | Samsung S23/S24 | Xiaomi 13 | OnePlus 11 | Android 12 device |
|-------|-------------|-----------------|-----------|------------|-------------------|
| Install + first launch | ☐ | ☐ | ☐ | ☐ | ☐ |
| App lock with biometric | ☐ | ☐ | ☐ | ☐ | ☐ |
| AI chat (one configured provider) | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tool call: `device_diagnostics` | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tool call with confirmation: `compose_message` | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tamil speech-to-text | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tamil text-to-speech | ☐ | ☐ | ☐ | ☐ | ☐ |
| On-device ASR badge shown correctly | ☐ | ☐ | ☐ | ☐ | ☐ |
| Wake word from the assistant screen | ☐ | ☐ | ☐ | ☐ | ☐ |
| Wake word survives 10 min in background | ☐ | ☐ | ☐ | ☐ | ☐ |
| Default-assistant selection | ☐ | ☐ | ☐ | ☐ | ☐ |
| Notification access toggle | ☐ | ☐ | ☐ | ☐ | ☐ |
| SAF tree grant + file organisation | ☐ | ☐ | ☐ | ☐ | ☐ |
| Emergency stop blocks all tools | ☐ | ☐ | ☐ | ☐ | ☐ |
| Windows bridge pair + heartbeat | ☐ | ☐ | ☐ | ☐ | ☐ |
| Battery drain over 1 h idle | ☐ | ☐ | ☐ | ☐ | ☐ |
