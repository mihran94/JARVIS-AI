# Jarvis-Blue Quantum — Development Blueprint
Date: 6 November 2026

## Direction and boundaries
Jarvis-Blue remains the application/repository name. Quantum is the proposed development direction and a future Lab section, not a claim that the laptop is quantum hardware. Build a reliable Windows desktop assistant, then add bounded local quantum-circuit simulations and learning tools. Hardware quantum execution is optional later work with separately reviewed access, data, cost and job permissions. No hardware backend is selected or provisioned in this phase.

User experience: English interface by default; automatic conversation language detection and same-language replies; preferred female voice when available. Blue hologram styling, balanced animations, accessible keyboard controls and a clear microphone state. Always-listening should be an explicit setting with a visible mute control. Keep main navigation to Home, Tasks, Memory, Quantum Lab and Settings. Advanced controls stay inside Settings.

## Evidence and present status
The supplied Mark LVI source forms the foundation. Jarvis-Blue branding, source-updater UI, signed-manifest verification and signing tools have been developed. Production signing activation is pending owner public-key setup and an actual Windows publisher certificate. The HTTPS updater currently cannot authenticate to private GitHub releases. The source has not passed a full Windows GUI/audio acceptance test. Current development environment lacks the app's GUI/audio dependencies. Module presence or source parsing does not establish a working desktop session.

## Phases and exit criteria
| Phase | Deliverable | Implementation scope | Exit criterion | Status |
|---|---|---|---|---|
| 1 | Windows foundation | Python 3.12-first setup; project .venv; setup/start commands; import/DLL diagnosis; visible failures | Fresh and existing installs launch; mic/speaker and restart checked on user's laptop | Launcher development implemented; Windows acceptance pending |
| 2 | Main UI | Home/chat/task state; simple Settings; blue theme; keyboard navigation; reduced motion | Readable resize/scaling; state accurately follows listening, thinking, speaking and errors | Proposed |
| 3 | Tamil–English voice | Auto language detection; same-language reply; interruption; silence handling; device recovery | Tamil, English and mixed-script conversation with headset and speakers | Proposed |
| 4 | AI engine reliability | Local/cloud selection; capabilities/readiness; bounded timeouts; no silent cloud fallback | Offline local scenario and provider failure recover without crashing | Proposed |
| 5 | Memory and documents | Editable facts; expiry/delete/export; selected-folder document index and file references | Restart persistence, actual deletion and grounded answers | Proposed |
| 6 | Tasks and computer actions | Queue; cancel; permissions; scoped files; outcome verification; undo | Actions report checked outcomes; cancellation and restoration demonstrated | Proposed |
| 7 | Signed-update activation | Owner public trust; signed release delivery; restore; later installer updater | Valid signed release installs; altered/expired/unknown-signer release rejected | Verification developed; owner setup/delivery pending |
| 8 | Quantum Lab basics | Qubit visualizer; H/X/Z gates; circuit view; exact probabilities and measurement sampling | Deterministic math checks; normalized state; labelled simulation | Proposed |
| 9 | Quantum experiments | Multi-qubit gates, CNOT; Bell state; interference; small educational algorithms | Bell distribution and gate identities match expected results | Proposed |
| 10 | Connected Jarvis | Phone pairing/revocation; job lifecycle; optional reviewed remote quantum adapter | Revocation, network loss, timeout/cancel and job result provenance | Proposed |

Phases are delivery order, not deadlines. Existing partial features are improved rather than automatically replaced. A phase is complete only when its exit criteria have evidence; a commit alone does not complete it.

## Phase 1 tasks now
- [x] Add SETUP_JARVIS.cmd: prefer installed Python 3.12, then 3.11/3.13; use or create project .venv.
- [x] Add START_JARVIS.cmd and launcher.py: never install packages on normal launch; keep startup failure visible.
- [x] Add real import checks in child processes for Qt, audio, numpy, Gemini SDK, psutil and cryptography; import success is not an audio or network test.
- [x] Make setup independent of the caller's working directory; preserve child installer output and error code.
- [x] Document Windows acceptance and the subsequent phases.
- [ ] Run the CMD scripts on Windows with Python 3.12, including a folder whose path has spaces.
- [ ] Run setup and launch on the owner's laptop; record actual failure messages without secrets.
- [ ] Check microphone, speakers, Tamil/English interaction, Settings and close/reopen.
- [ ] Resolve issues found before claiming Phase 1 complete.

## Quantum Lab scope in detail
First implement a pure numeric statevector simulator using the project's existing numpy dependency. Start at one qubit, then expand to a hard maximum of eight qubits for the first educational release. Do not add a large quantum framework just to draw a qubit. Exponential state growth must be explained and enforced with a clear size limit.

1. Qubit state display: amplitudes, phase, normalization and probabilities; label measurement versus underlying state.
2. Gate playground: H, X, Z and reset. Define basis ordering and verify reversibility/normalization.
3. Circuit execution: CNOT and a two-qubit Bell-state example. Display exact theoretical probabilities separately from seeded, finite-shot samples.
4. Learn mode: Tamil explanations with English technical terms, diagrams and reproducible examples. A model may explain the results, but numeric probabilities come from simulator code.
5. Experiment history: circuit, seed, shot count and simulator version. No credentials or raw user documents in exports.
6. Optional later hardware adapter: provider/job provenance, explicit submission, cost estimate, cancellation, quotas and result errors. Never present simulation as a real hardware run.

Quantum Lab must not claim to speed up general chat, break encryption, remove normal hardware limits or stay online when the laptop is off. Remote reminders would need a separately running service; desktop control still needs a powered-on connected PC.

## Development workflow
For each bounded change: inspect source and AGENTS.md → implement → run relevant isolated checks → review behavior/limitations → push GitHub. Build only when the user asks. A release is separately prepared; ordinary pushes do not trigger update installs. Keep public-key verification, checked action outcomes, the existing config_manager and Qt-thread rules intact. Never put credentials, owner private keys or user memory into commits, update packages or logs.

## Windows acceptance checklist
1. Extract all files; double-click SETUP_JARVIS.cmd. Verify it selects the installed 3.12 environment and leaves installation errors visible.
2. Double-click START_JARVIS.cmd. Verify the app opens without installing anything.
3. Run `.venv\Scripts\python.exe launcher.py --check` to check imports only. This does not open the UI, record audio or contact a model.
4. Confirm Home, settings, audio selection, mute and voice output; test Tamil and English. Use the app's local configuration for credentials; do not paste keys into screenshots.
5. Close/reopen the app and verify settings remain. Try a missing dependency or moved environment only in a disposable copy and verify repair guidance.
6. Open Updates: signing setup and missing feed must be reported accurately. Do not promise automatic update delivery until activated.

## Later packaging
Windows EXE and installer, Authenticode signature, uninstall behavior and installer-compatible updates remain separate work. Source launch scripts are convenience entry points, not an installer and not a build. No release timetable or hosted-service cost is assumed.
