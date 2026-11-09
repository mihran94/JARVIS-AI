# Unified JARVIS — integration baseline (work in progress)

## Verified source projects
- Windows foundation: `mihran94/JARVIS-AI` (v0.3.0 README).
- MiniMax Windows source: user-provided `JARVIS-AI-MiniMax-source-clean.zip` (0.2.0 package; not yet merged or Windows-validated).
- JARVIS Blue desktop: `mihran94/Jarvis-Blue` (Mark LVI-derived; preserve original attribution and license).
- JARVIS Blue Android: `mihran94/jarvis-blue-android` (Kotlin/Compose; Android 12+).

## Target product
One product identity and update policy, but two installables: **Windows desktop** and **Android APK**. Windows is the host for desktop automation, local tools and optional private remote server; Android is a companion client with its own local permission gate. Do not combine Python and Kotlin into one executable.

## Safe merge sequence
1. Audit licenses, dependencies, source provenance and security for all three repositories plus the MiniMax ZIP; retain attribution and notices.
2. Choose the canonical Windows host and migrate *tested* MiniMax modules into it behind adapters, preserving v0.3.0 functionality. Do not overwrite existing main.
3. Implement a versioned shared protocol: authenticated device pairing, scoped capabilities, explicit user approval for each sensitive action, request IDs, replay protection, timeout, revocation, emergency stop, audit log. No exposed unauthenticated control endpoint.
4. Adapt JARVIS Blue desktop voice/vision components after license and compatibility review; preserve only working tested modules.
5. Adapt Android to the shared protocol; never bypass Android permissions, biometric/OS security, or desktop approval. No silent execution of high-risk tasks.
6. Build and test Windows installer and Android APK separately; CI should require unit, security, integration and platform smoke tests before merge/release.

## Hard rules
- No API keys or personal data in Git. Configure keys locally.
- No unattended shell/desktop control from phone; require local policy and approval.
- No auto fallback to paid providers without consent.
- No force push or replacing `main`.
- The MiniMax ZIP's Linux tests do not prove Windows/Android compatibility.

## Status (2026-11-09)
Integration plan committed to development branch. **Codebases not yet merged; no unified installer/APK built.** Next action: inspect cross-project licenses and protocol endpoints, then implement the first tested adapter.
