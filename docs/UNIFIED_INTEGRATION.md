# JARVIS Unified AI — integration contract (draft)

This document is the first non-runtime integration artifact. The existing JARVIS-AI Windows application remains the foundation. No source project is deleted, renamed or overwritten by this plan.

## Source ownership

| Source | Intended contribution | Integration condition |
| --- | --- | --- |
| JARVIS-AI | PySide6 Windows shell, task queue, credential vault and permission policy | Preserve existing safety tests and manual approvals |
| Jarvis-Blue | Voice/wake word and optional provider/assistant adapters | Isolate PyQt6 UI from PySide6; review license and attribution before copying code |
| jarvis-blue-android | Kotlin Android client, on-device permissions and signed Windows bridge | Pair only with explicit consent; validate protocol and replay protection |
| JARVIS-Mobile-Beta | UI/protocol ideas only | Do not ship its demo gateway as production authentication |

## MVP sequence

1. Establish this integration contract and record source revisions.
2. Add a pure-Python provider router with mock-only tests. Providers: OpenAI, Gemini, Claude, MiniMax, DeepSeek, Groq, OpenRouter and Ollama. No implicit paid fallback or retries on authentication errors.
3. Define a versioned desktop/mobile protocol with authenticated pairing, replay protection, revocation and no public unauthenticated ports.
4. Integrate voice as an optional adapter behind explicit microphone consent and a stop control.
5. Preserve per-action Windows confirmation, argument binding and emergency stop for all local/remote requests.
6. Run unit and integration tests, then Windows and Android acceptance builds on the owner's PC.

## Safety and release gates

- Never commit API keys, tokens, signing material or personal databases.
- Never claim a provider, voice, mobile bridge or installer works until tested.
- Source merge requires passing relevant tests, license review and rollback plan.
- Do not execute AI-generated commands without a user-approved, constrained policy.
- Do not expose Ollama or a desktop control endpoint directly to the public internet.
- Existing repositories remain intact; the integration branch is isolated from main until review.

## Verification status

- Repository README and requirements for four projects were inspected through GitHub access.
- JARVIS-AI base commit: `7c18e83f66caae4e15be7c6580fa9c65e31fd228`.
- No runtime integration, automated tests, Windows execution or Android build has been verified for this document.
