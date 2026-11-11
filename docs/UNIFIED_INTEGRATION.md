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

### Progress recorded on the integration branch

Step 2 and step 3 of the MVP sequence now have a first implementation. The
work is additive and does not change the existing desktop chat flow.

Step 2, provider router:

- `providers/registry.py` lists the eight agreed providers. The six cloud
  providers already used by the desktop are taken from `providers.chat`, so the
  existing behaviour is unchanged. Claude and Ollama are added because they
  need a different request shape or a different trust level.
- `providers/selection.py` holds the selection policy. It used to live in the
  repository root as `unified_provider_policy.py`, where `pytest.ini` never
  collected its test. The module and its test now live in `providers/` and
  `tests/`, so the policy is covered by the normal suite.
- `providers/claude.py` is the native Anthropic Messages API adapter, and
  `providers/ollama.py` is the loopback only local adapter.
- `providers/router.py` selects one provider and dispatches to the adapter
  that matches its shape. Offline mode can only select a local provider, so an
  offline request cannot reach a paid endpoint.
- The router is not wired into the desktop interface yet. The desktop still
  uses `providers.chat` directly.

Step 3, desktop/mobile protocol:

- `remote/` implements the desktop half of the bridge protocol: the canonical
  signing scheme, replay protection, pairing with revocation, the job records
  and the request handler. `docs/BRIDGE_PROTOCOL.md` is the shared contract.
- The cross implementation vectors are pinned on both sides, so the desktop and
  the Android client cannot drift apart silently.
- Nothing binds a socket and the desktop interface does not expose the bridge,
  so no phone can reach a JARVIS installation yet.

Validation performed for the work above:

    QT_QPA_PLATFORM=offscreen python -m pytest -q
    239 passed, 3 skipped in 6.06s

The baseline before the change was 175 passed, 3 skipped; the skipped tests are
the Windows only ones. The suite uses synthetic HTTP transports and real Qt
widgets in offscreen mode. No API key was used, no provider was called and no
Android build was made. Windows behaviour, live provider access and the APK
remain unverified.
