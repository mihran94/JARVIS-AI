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
| 2 | Main UI | Home/chat/task state; simple Settings; blue theme; keyboard navigation; reduced motion | Readable resize/scaling; state accurately follows listening, thinking, speaking and errors | Navigation/status developed; accessibility and motion refinements pending |
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

## Phase 1 follow-up: UI startup
The full UI now opens in the isolated Linux/offscreen test environment after deferring optional video audio initialization until playback. Settings → Updates, mute and resize have regression coverage. Windows/device acceptance remains pending; Quantum Lab remains proposed. See QA_REPORT.md for the precise native-backend limitation.

## Phase 2 increment: main navigation and session state
Added Home, Tasks, Memory, Quantum Lab and Settings navigation with Alt+1 through Alt+5 shortcuts and accessible names. Home preserves current result content across navigation; arriving tool results return to Home. Tasks shows the existing activity log and existing interrupt action; it does not claim a persistent task queue. Memory and Settings open the existing panels. Quantum Lab is explicitly labelled planned, with no simulator/hardware claim. A visible status label follows engine state signals. Activity refresh runs once a second only while the Tasks page is selected.

Twenty-eight launcher/updater/widget tests and 99 provider checks pass in isolated Linux/offscreen testing. Full Windows testing and builds remain deferred by user request. Reduced motion, broader accessibility review and the later voice/provider phases remain open.

## Coding skills increment: Project Explorer and Error Doctor
Coding (Alt+6) provides a user-selected, read-only project browser with background directory/file reads and UTF-8 source previews. Parent navigation stays within the selected root; ordinary symlinks, common credential filenames and generated/environment directories are excluded. Preview limit is 128 KiB; directory results are capped at 500 visible entries. These filters are convenience protections, not a sandbox against another process changing the filesystem or a comprehensive secret detector.

Error Doctor analyzes pasted Python exception text locally using built-in guidance, including missing modules, syntax, names, permissions and file paths. It makes no model calls and neither runs nor edits code. Suggestions are not verified fixes. Diff editing, test execution, Git actions inside the app, Work Mode routines and automation scheduling remain future increments. Existing external development tools remain separate.

Validation: 37 unit/widget tests pass on Linux with Qt offscreen, including a real project-selection/preview/error-guidance flow. Windows testing and builds remain deferred.

## AI connections and Codex review increment
Gemini Live remains the native voice engine. The existing OpenAI and MiniMax Chat Completions connections are retained; Gemini's official OpenAI-compatible endpoint is now also available for background/coding and pipeline use. Each service uses its own saved settings through config_manager. Choose a model supported by the account; this does not imply support for every model or API modality (Responses-only models are not supported by this adapter).

Setup: Coding → AI connections (or Settings → ENGINE & PROVIDERS) → choose a service under CODING or BACKGROUND REQUESTS → enter its own API key and model → TEST → SAVE & APPLY. TEST sends a real provider request and may incur usage; model discovery can also contact the selected service. Gemini-compatible settings are separate from the existing Gemini Live key. Existing local configuration is ignored by git but is not an encrypted credential vault.

Coding → select project → Codex review opens a dedicated dialog. Only Run Codex review starts a process. This uses an installed, signed-in Codex CLI, not the Jarvis provider key fields, and may send project context to OpenAI. It requests a read-only sandbox, never approvals, ephemeral session, and ignored user config/rules. Prompt travels over stdin; commands use argument arrays without a shell. Windows npm shims resolve via Node.js. Unsupported CLI flags or sandbox/authentication errors fail visibly rather than retrying with weaker permissions.

Codex review is analysis/suggestions only; code application, builds and releases are not added. A five-minute deadline, 256 KiB output cap and Stop terminate the CLI process. Subprocess descendants may require separate cleanup; sandbox enforcement and credentials remain the CLI's responsibility. This is not a hard read boundary around the selected folder, and the Explorer's filename filters do not govern Codex reads. Review only projects appropriate to share.

Official references checked 2026-11-06:
- https://ai.google.dev/gemini-api/docs/openai
- https://platform.minimax.io/docs/api-reference/text-openai-api
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/developer-commands?surface=cli

Validation: 46 unit/widget tests and 99 provider regression checks pass using mocks and local processes. No live API/Codex review, Windows test or executable build performed. Provider-specific advanced tool loops (including reasoning metadata), account access, real latency and native Windows sandbox behavior still need acceptance testing.

## ZIP update increment
Coding → Update project ZIP imports a separate working copy. Select an existing UTF-8 source file, edit manually or request an AI draft using configured provider routing, preview diff, apply with backup, undo and export a new ZIP. AI sends only the selected editor text and request after confirmation. No automatic multi-file edits. Common credential/environment entries are excluded and counted. Python syntax checks do not run tests or builds. Backups remain alongside the working copy; undo history lasts for the dialog session. Imported archives are limited to 5000 entries/100 MiB. Windows acceptance and live AI drafts remain unverified.
