# JARVIS BLUE MOBILE — Architecture

> Private, sideload-installed Android personal AI assistant.
> Kotlin · Jetpack Compose · Clean Architecture · minSdk 31 (Android 12) · targetSdk 35 (Android 15)

---

## 1. Design goals

1. **The model proposes, the app disposes.** A language model may only *request*
   an action. Every request passes a single execution gate that validates the
   schema, checks the permission grants, evaluates the risk and collects a fresh
   user confirmation. The model never touches the Android framework.
2. **Deny by default.** Every capability starts denied. Nothing is granted
   implicitly by installing the app, and the runtime Android permission is
   *additional* to the in-app grant, never a substitute for it.
3. **Honest about limits.** The UI states plainly when a feature is blocked by
   the platform (Android 14 microphone FGS rules, missing Tamil voice pack,
   unavailable on-device ASR) instead of silently degrading.
4. **Everything is auditable.** Each tool call, permission change and
   confirmation lands in an encrypted audit table the user can export.

---

## 2. Module structure

```
jarvis-blue-mobile/
├── app/                      Application module — manifest, services, DI wiring, navigation
│
├── core/
│   ├── model/                PURE KOTLIN — domain models only, zero Android dependencies
│   │   ├── ToolSpec.kt         Tool contract + JSON-Schema parameter descriptors
│   │   ├── Permission.kt       18 fine-grained capability buckets
│   │   ├── Action.kt           Plan / step / result / execution verdict
│   │   ├── Conversation.kt      Messages, roles, attachments, token usage
│   │   ├── Provider.kt         Provider ids, health, model descriptors, budgets
│   │   ├── Task.kt             Automation tasks, triggers, statuses
│   │   ├── Memory.kt           Personal memory items
│   │   ├── Security.kt         Findings, severities, authorisation grants
│   │   ├── Quantum.kt          Circuits, gates, simulation results
│   │   ├── WindowsBridge.kt    PC status, bridge jobs, peers
│   │   └── Audit.kt            Audit events and categories
│   │
│   ├── common/              PURE KOTLIN — cross-cutting utilities
│   │   ├── Outcome.kt           Result type + AppError taxonomy
│   │   ├── Redactor.kt          Credential scrubbing for logs and audit rows
│   │   ├── TextTools.kt         Normalisation, tokenisation, fuzzy similarity
│   │   ├── AuditSink.kt         Write-only audit channel
│   │   └── Clock.kt / Dispatchers.kt / Logger.kt
│   │
│   ├── security/            Android — Keystore, vault, biometrics, app lock
│   │   ├── KeystoreKeyManager.kt  AES-256-GCM key; StrongBox when available
│   │   ├── CipherBox.kt           Envelope encryption (v1.iv.ciphertext.tag)
│   │   ├── SecretVault.kt         Provider API keys, encrypted at rest
│   │   ├── PermissionGrantStore.kt Per-capability and per-tool grants
│   │   ├── BiometricGate.kt       BiometricPrompt wrapper (FragmentActivity)
│   │   ├── AppLockController.kt   Lock state + session expiry
│   │   └── EmergencyStop.kt       Sticky global kill switch
│   │
│   ├── database/            Android — encrypted persistence
│   │   ├── JarvisDatabase.kt      Room + SQLCipher (32-byte random passphrase)
│   │   ├── Entities.kt            8 tables
│   │   ├── Daos.kt                Flow-based DAOs
│   │   ├── Repositories.kt        Conversation / Memory / Task / Provider / Peer
│   │   └── Mappers.kt             Entity ⇄ domain mapping
│   │
│   ├── ai/                  Android — multi-provider intelligence
│   │   ├── OpenAiProvider.kt      Chat Completions (also minimax, generic gateways)
│   │   ├── GeminiProvider.kt      generateContent + functionDeclarations
│   │   ├── OllamaProvider.kt      Self-hosted /api/chat
│   │   ├── OfflineProvider.kt     Honest offline fallback (no hallucination)
│   │   ├── AiRouter.kt            Routing, health, budget, fallback chain
│   │   ├── PromptBuilder.kt       System prompt + language detection
│   │   └── ToolSchema.kt          ToolSpec → provider-specific JSON schema
│   │
│   ├── tools/               Android — the capability surface
│   │   ├── ToolRegistry.kt        Registration + schema export
│   │   ├── SchemaValidator.kt     Argument validation (rejects unknown keys)
│   │   ├── RiskEvaluator.kt       Effective risk from declared risk + arguments
│   │   ├── ToolExecutor.kt        ★ THE GATE — the only path to an effect
│   │   ├── AssistantAgent.kt      Reasoning loop, tool-call iteration, confirmations
│   │   ├── IntentRouter.kt        Deterministic rule engine for spoken commands
│   │   ├── DeviceControlEngine.kt Intents, media keys, diagnostics
│   │   ├── FileTools.kt           SAF tree access, copy-first organisation
│   │   ├── NetworkDiagnostics.kt  DNS / TCP / TLS inspection
│   │   ├── SecurityScanner.kt     Defensive static analysis + OWASP mapping
│   │   ├── CodeQualityChecker.kt  On-device structural checks (no execution)
│   │   ├── QuantumSimulator.kt    Classical state-vector simulator
│   │   ├── ConfirmationCoordinator.kt  Single in-flight approval channel
│   │   └── MemoryTools.kt / JarvisTools.kt / ToolContextProvider.kt
│   │
│   ├── voice/               Android — speech
│   │   ├── WakePhraseMatcher.kt   Fuzzy multi-language wake-phrase matching
│   │   ├── SpeechRecognizerController.kt  On-device-first SpeechRecognizer
│   │   ├── TextToSpeechController.kt      Per-language TTS with voice-pack checks
│   │   ├── VoiceLanguageProfile.kt        Locale chains (ta-IN, en-US, en-IN, fr-FR)
│   │   └── WakeWordEngine.kt
│   │
│   ├── windows/             Android — desktop bridge client
│   │   ├── BridgeClient.kt        HTTPS + WebSocket, HMAC-SHA256 signed requests
│   │   └── WindowsModule.kt
│   │
│   └── ui/                  Android — design system
│       ├── theme/                 Colour, typography, Material 3 scheme
│       └── components/            JarvisOrb, VoiceWaveform, GlowCard, StatusPill,
│                                  MetricChip, SectionHeader, JarvisScaffold, …
│
├── feature/
│   ├── chat/                Conversation UI + agent ViewModel
│   ├── assistant/           Orb, waveform, wake word, push-to-talk
│   ├── studio/              Dev studio · Cyber lab · Quantum lab
│   └── command/             Permissions · Tasks · Memory · Windows · Settings
│
├── windows-bridge/         Reference Python desktop server (FastAPI + WebSocket)
└── docs/                    Architecture, permissions, compatibility, threat model, …
```

### Dependency direction

```
app ──▶ feature:* ──▶ core:*
                        core:model ◀── core:common
                        core:security ◀── core:database
                        core:ai ◀── core:tools
                        core:tools ◀── core:voice
                        core:windows
                        core:ui  (Compose design system, no domain logic)
```

`core:model` and `core:common` are pure Kotlin — they compile in milliseconds,
are unit-testable without an emulator, and cannot accidentally depend on the
Android framework.

---

## 3. The execution gate

`ToolExecutor.execute()` is the only code path that produces an effect. Its
checks run in a fixed order and each can only stop the action:

| # | Check | Failure verdict |
|---|-------|-----------------|
| 1 | Emergency stop engaged | `EMERGENCY_STOP` |
| 2 | Tool known **and** enabled by the user | `DENIED_PERMISSION` |
| 3 | Arguments valid against the tool schema | `INVALID_ARGUMENTS` |
| 4 | Every required permission bucket granted | `DENIED_PERMISSION` |
| 5 | Risk ≥ HIGH and no fresh confirmation | `NEEDS_CONFIRMATION` |
| 6 | Execute, then write an audit row | `COMPLETED` / `ERROR` |

The AI's tool call is a **request**. The result of the gate — including a
refusal — is fed back to the model as a tool result, so the assistant reports
what actually happened instead of claiming success.

### Schema validation

`SchemaValidator` rejects:
* unknown parameters (so a model cannot smuggle extra fields),
* wrong JSON types,
* out-of-range numbers,
* strings longer than the declared maximum,
* values outside a declared enum,
* missing required parameters.

### Risk evaluation

`RiskEvaluator` takes the tool's *declared* risk as a baseline and can only
raise it:

* `destructive = true` → at least HIGH.
* A `COMMUNICATION` tool whose body mentions payments, OTPs, PINs or bank
  details → CRITICAL.
* A `FILES` tool pointed at `.ssh`, `.aws`, wallet or credential paths → at
  least MEDIUM.
* Every `REMOTE` tool → at least HIGH.

---

## 4. AI reasoning loop

```
user text
   │
   ├─▶ IntentRouter.detect()          deterministic rule match (no AI)
   │       └─▶ shows the matched rule to the user before execution
   │
   └─▶ AssistantAgent.run()
          ├─ system prompt: language rule, memory, tool policy, platform facts
          ├─ AiRouter.route()          priority → health → task heuristic → budget
          ├─ model responds
          ├─ has tool calls?
          │     ├─ SchemaValidator → RiskEvaluator → permission → confirmation
          │     ├─ ToolExecutor executes
          │     └─ result (or refusal) is appended as a `tool` message
          ├─ loop (max 6 iterations) until the model answers without tools
          └─ final message + tool-call trace + token usage → encrypted DB
```

**Provider routing order**

1. Explicit user override for this conversation.
2. User-configured provider priority.
3. Task heuristic (coding → coder model, vision → multimodal model).
4. Live health: an unhealthy provider is demoted, not silently used.
5. Daily token budget.

If every cloud provider fails, the honest offline responder answers with an
explanation of what is missing. The app never fabricates an answer.

---

## 5. Data at rest

| Data | Storage | Protection |
|------|---------|-----------|
| Conversations, messages | Room + SQLCipher | AES-256, random 32-byte passphrase |
| SQLCipher passphrase | SharedPreferences | Encrypted by the Keystore master key |
| Master key | Android Keystore (TEE / StrongBox) | Non-exportable, hardware-bound |
| API keys, pairing secret | `SecretVault` (SharedPreferences) | Encrypted with the master key |
| Permission grants | `PermissionGrantStore` | Encrypted with the master key |
| Memory items, tasks, audit rows | Room + SQLCipher | Same database |
| Audit detail | `Redactor` applied before write | API keys are scrubbed, never stored |
| Backups | Disabled | `allowBackup="false"` + explicit data-extraction rules |

Losing the Keystore key makes the database permanently unreadable — which is
the intended behaviour: a forensic image of the app's data directory is
ciphertext without the hardware key.

---

## 6. Background execution

| Mechanism | Used for | Constraint honoured |
|-----------|----------|---------------------|
| `WorkManager` | Scheduled automation tasks | Runs under system-managed constraints |
| Microphone foreground service | Wake-word listening | Ongoing notification + system mic indicator; not started from the background on Android 14+ |
| MediaProjection foreground service | Optional screen capture | Requires fresh user consent every session |
| `AlarmManager` | Reminders | Exact alarms when permitted, inexact fallback otherwise |
| Boot receiver | Re-arms scheduled work | Deliberately does **not** restart the microphone service |

---

## 7. Extending the tool registry

```kotlin
registry.register(
    ToolSpec(
        name = "my_tool",                    // ^[a-z][a-z0-9_]{2,63}$
        displayName = "My tool",
        description = "What it does — the model reads this.",
        category = ToolCategory.DEVICE,
        parameters = listOf(
            ToolParameter("target", ParamType.STRING, "What to act on", required = true),
        ),
        riskLevel = RiskLevel.LOW,
        requiredPermissions = setOf(Permission.SYSTEM_SETTINGS),
    ),
) { context, arguments ->
    val target = arguments.string("target")
    ToolOutput(summary = "Did the thing to $target")
}
```

The tool is immediately visible in the Permissions dashboard, is exported to the
model as a JSON schema, and passes through the same gate as everything else.
There is no way to register a tool that skips the gate.

---

## 8. Threading

* `core:common.DispatcherProvider` abstracts `main` / `io` / `default`.
* All network and disk work runs on `Dispatchers.IO` inside the provider
  clients and repositories.
* The UI is Compose + `StateFlow`; every ViewModel exposes a single immutable
  UI-state object.
* Tool execution is sequential within a request: the model asks, the gate
  decides, the result is reported, the model asks again.
