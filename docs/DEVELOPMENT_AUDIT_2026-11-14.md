# JARVIS One — development folders and integration audit (2026-11-14)

Canonical source: [mihran94/JARVIS-AI](https://github.com/mihran94/JARVIS-AI), `main` at `9313cb6dd503b286bebc56f100e76e2c82500bea`. This is a **tested beta**, not a completed self-governing assistant. This inventory concerns GitHub source, not any private folders on the owner's Windows disk. Never delete old repositories or source directories before preserving all branch refs and private user data.

## Production and historical folder boundaries

| Folder / component | Actual status and work remaining |
| --- | --- |
| `desktop/`, `main.py` | One Windows PySide6 interface with six primary pages, task history, policy approvals and optional background controls. Physical Windows acceptance and signed release remain outstanding. |
| `providers/`, `core/` | OpenAI, Gemini, Claude, MiniMax, DeepSeek, Groq, OpenRouter and local Ollama adapters, SQLite history and local usage records. Live-key/provider-account compatibility not verified across all eight services. |
| `voice/` | Opt-in Windows microphone, wake recognition, dictation, interruptible SAPI speaker. Session-only hands-free **local Ollama** loop merged in PR #21. Installed speech engines, microphone and Tamil speech remain hardware-dependent. |
| `security/`, `automation/`, `agents/` | One-use owner-approved actions, Emergency Stop, allowlisted Notepad/Calculator, read-only window inspection and bounded manual workflows. No unrestricted PC agent, autonomous shell or unreviewed job execution. |
| `developer_studio/` | Code drafts, syntax checks, confined workspace backups; experimental restricted Docker Python runner exists as source. No verified end-to-end autonomous project repair/build/installer workflow. |
| `remote/` and `desktop/bridge_*.py` | Signed PC-side HTTP bridge, secrets, jobs, phone pairing and optional chat. Listener OFF by default, loopback-only by default; actual private HTTPS tunnel and owner/phone end-to-end pairing not accepted. Remote job approval does not imply execution. |
| `android/` | Android 12+ **remote only**. Main launch goes to Windows remote pairing. PR #22 repairs AndroidKeyStore AES-GCM IV crash. Android 15 emulator cold-launch pass in [workflow 43528444985](https://github.com/mihran94/JARVIS-AI/actions/runs/43528444985); physical device and remote PC pairing still required. |
| `iphone-pwa/` | Browser PWA source present, **not** a native iPhone app or evidence of deployment. Requires HTTPS PC bridge and owner pairing. |
| `legacy/` | 144 historical files from Jarvis-Blue, JARVIS-Mobile-Beta and unified-build material. Preserve for comparison; do not run as independent production agents. |
| `tests/`, `.github/workflows/` | Python/Qt Windows and Ubuntu tests, bridge protocol tests, Android unit/APK permissions and emulator cold-launch CI. Hardware tests, production signing and release certification are not replaced by CI. |

Repository tree inspected on 2026-11-14 contained 556 tracked file entries: 201 under `android/`, 144 under `legacy/`, 49 under `tests/`, 28 under `iphone-pwa/`, 24 under `docs/` and smaller modules elsewhere. Counts exclude any inaccessible local PC copies.

## Development branches — safe migration review

- `dev/unified-jarvis-windows-android-20261109` and `dev/windows10-installer-20261113` are fully **behind** canonical `main` (no unique commits ahead in the GitHub compare at audit time).
- `dev/minimax-disk-monitor-review-20261109` has one unique patch, `review/minimax_disk_snapshot_fix.patch`. It targets an older `jarvis/automation/system_monitor.py` path, not the active desktop system-metrics source. Port only after verifying the target actually exists and passing tests; do not apply the patch blindly.
- `dev/advanced-security-review-20261110` has five unique review/security-gate files. Its `remote_execution_gate.py` is a **policy prototype**, not an OS sandbox; it must not be wired to autonomous remote shell/code execution without independent isolation and approval verification.
- The original `Jarvis-Blue` and `jarvis-blue-android` repositories have independent development branches, including diagnostics, UI experiments and trading-related code. Preserve and review their history before retiring source. **Exclude trading, Exness, XAUUSD and broker control** from the unified product.
- The full separate MiniMax v0.2.0 and MARK LVI source trees were **not verified in the canonical repository** as of this audit. A handoff/plan or copied blueprint is not evidence of actual merged runnable code.

## Immediate acceptance gates

1. **Android owner device:** install the debug APK from the verified crash-fixed run, confirm JARVIS Remote screen opens and survives background/foreground. Each CI debug artifact may have a different signing key; Android can refuse an in-place upgrade. Preserve data and pairing details before considering uninstall.
2. **Windows owner machine:** install unsigned beta only after verifying source/digest, test app launch, Ollama local model, voice microphone, spoken reply, Emergency Stop, explicit approval and saved conversations.
3. **Phone-to-PC connection:** deploy a trusted private HTTPS reverse proxy/tunnel to a PC listener on `127.0.0.1`; verify HMAC pairing, status, job queue, one-time approval and revocation with a real device. Do not expose the control port to the internet, disable certificate validation or use plaintext Android transport.
4. **Developer workflow:** isolate requested code execution with a verified sandbox, preserve backup/undo, require scoped human review, prove rollback and job cancellation on actual Windows. Do not claim self-healing or fully autonomous coding until tests demonstrate it.
5. **Release:** owner-controlled keystore and Windows code signing, app-update signing continuity, reproducible binaries, attribution/SBOM, installer rollback and physical acceptance.
6. **Source retirement:** archive unique Git branches/repositories as bare mirrors and compare the remaining local development folders with canonical source before any deletion.

The source monorepo is consolidated; **a product is not finished simply because its sources are consolidated**. Normal build/test CI can run when code changes. Do **not** create hourly GitHub Actions development jobs or trading automation.
