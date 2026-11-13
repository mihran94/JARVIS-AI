# JARVIS voice → main Chat (owner-controlled)

This release keeps **one Windows JARVIS window**. Its **Speak to JARVIS**
button starts *one* speech-recognition request. The phone remains a remote
control for the Windows process, not another AI brain.

1. On **Voice / Hey Jarvis**, enable **Allow the microphone** explicitly.
2. In **JARVIS Chat**, click **Speak to JARVIS**. The transcribed utterance
   appears in the main Chat draft and is never sent automatically.
3. Review/edit the draft and click **Ask JARVIS** to query the selected AI
   provider. Cloud models may cost money. No voice transcript can directly
   execute a PC command; all PC actions use their own per-action approval.
   Alternatively, **Review PC action** recognizes only exact allowlisted
   utterances (`open notepad`, `open calculator` or matching Tamil phrases).
   It shows the same one-use Windows confirmation before launching the app;
   longer, mixed or unknown commands are refused without execution.
4. **Wait for the wake phrase** or **Keep listening for Hey Jarvis** can
   detect the wake phrase while the microphone is allowed. A wake phrase
   switches to Chat; instructions are drafted, not executed.
5. **Stop voice** revokes microphone permission and requests cancellation
   of the listening thread. If Windows is already inside a synchronous
   recognition call, it may finish the current bounded recognition timeout
   before the microphone fully closes. **EMERGENCY STOP** additionally
   invalidates outstanding PC action approvals.

## Hands-free conversation (opt-in, LOCAL Ollama only)

This optional mode lets JARVIS rearm the wake listener after each local-model
answer, without cloud API costs:

1. Install and start **Ollama** on the Windows PC and download the model ID
   selected in JARVIS (the default is `llama3.2`). JARVIS does not silently
   download models or run installers.
2. Visit **Voice / Hey Jarvis**, enable **Allow the microphone**. Make sure
   your Windows speech recognition and output voices work on this PC.
3. In **JARVIS Chat**, choose **Ollama** and check
   **Hands-free Hey Jarvis (LOCAL Ollama only, session opt-in)**. This turns on
   **Read replies aloud** and starts a bounded offline wake listener.
4. Say **Hey Jarvis**, wait for recognition, then speak one question within
   the eight-second dictation window. The recognized text goes only to
   loopback Ollama. The optional Windows SAPI voice speaks its reply; once
   speaking finishes, JARVIS resumes waiting for another wake phrase.
5. Uncheck hands-free, uncheck microphone permission, close the app or press
   **EMERGENCY STOP** to stop listening. Microphone consent and local
   hands-free are OFF at startup and never persist across sessions.

**Important boundaries**: Hands-free requests are never routed to a paid
cloud model. Switching provider, enabling backup fallback, losing microphone
consent, or invoking Emergency Stop immediately disables the automatic
conversation path. If a draft already exists or an AI request is running,
the spoken phrase cannot send that draft automatically. Spoken commands do
not execute Windows actions: the user must press **Review PC action**, and
the existing one-use owner approval remains mandatory.

The speaker now runs in its own initialized Windows COM thread. SAPI output
is interruptible by **Stop voice** and Emergency Stop without blocking the
main Qt interface. A running Windows recognition timeout is bounded; stopping
the microphone can still take until the current recognition call returns.
No system-wide always-on listening, wake-word recognition with the app closed,
unsupervised cloud spending, or automatic external application control is
claimed. A real PC/phone hardware acceptance test is still required.

## Windows dependencies

- Local System.Speech recognition uses optional `pythonnet`, an available
  Windows audio-input device, and a *locally installed* Windows speech
  recognizer matching the selected language.
- Native SAPI speech output uses optional `pywin32` and an installed voice.
  Voice output is optional, disabled by default on the Chat page.
- The Windows installer build installs pinned `pythonnet` and `pywin32`
  dependencies, then retrieves Microsoft's MIT-licensed `System.Speech`
  **10.0.14** from the official NuGet feed at build time. It bundles the
  `netstandard2.0` assembly beside the packaged executable, because the
  Windows Server 2025 CI runner does not ship that assembly. No packages
  or assemblies are fetched when a user speaks or launches JARVIS.
  The optional CLR loader first checks native System.Speech availability,
  then explicitly loads only the bundled Microsoft DLL if needed.
  PyInstaller includes CLR and COM support. The built EXE must pass
  `--check-voice-runtime` in CI. This checks imports and creation of a
  SAPI object, never microphone capture, installed languages, wake-word
  accuracy, or physical audio output. The installer also carries the
  System.Speech **MIT attribution** copied from `licenses/System.Speech.MIT.txt`
  as `System.Speech.LICENSE.txt` beside the installed executable; CI refuses
  to package the binary without that notice.
  Diagnostic codes: 31 = CLR import, 32 = assembly loading, 33 = speech
  grammar import, 34 = win32com import, 35 = SAPI COM object. These do not
  disclose local file paths or credentials.
- The .NET System.Speech integration uses `Grammar(GrammarBuilder)`,
  `SetInputToDefaultAudioDevice()` and `Recognize(TimeSpan)`.
- Tamil and French support **depend on installed Windows recognizers and
  voices**. The program must not silently claim that a language works
  without its installed speech pack.

## What this does not do

- No unsupervised AI requests, automatic billing, AI-driven shell execution,
  auto-trading, or microphone permission on boot.
- No guarantee of 24/7 recognition while Windows is asleep, JARVIS is closed,
  the microphone is unavailable, or an unsupported speech pack is selected.
- An optional, explicitly enabled **local Ollama** wake/dictation/reply
  loop is implemented. Cloud providers still require reviewed manual Send.
  A physical Windows microphone/speaker and model test remains outstanding.
- Mocked speech contract tests and CI do not substitute for a physical
  Windows microphone and speaker acceptance test.
