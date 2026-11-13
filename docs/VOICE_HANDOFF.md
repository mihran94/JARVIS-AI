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

## Windows dependencies

- Local System.Speech recognition uses optional `pythonnet`, an available
  Windows audio-input device, and a *locally installed* Windows speech
  recognizer matching the selected language.
- Native SAPI speech output uses optional `pywin32` and an installed voice.
  Voice output is optional, disabled by default on the Chat page.
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
- Continuous back-and-forth hands-free AI dialogue is not completed by this
  draft handoff. The owner currently reviews and sends each new message.
- Mocked speech contract tests and CI do not substitute for a physical
  Windows microphone and speaker acceptance test.
