> **Latest beta status (14 November 2026):** the canonical product is **one Windows JARVIS with an Android remote**. Android startup crash repair PR #22 was merged (main `9313cb6`) and passed a real Android 15 emulator cold-launch gate; the installed phone and secure PC pairing still require hardware acceptance. Session-only hands-free voice uses **local Ollama only**, not paid cloud providers, and PC actions remain approval-gated. See [current development audit](docs/DEVELOPMENT_AUDIT_2026-11-14.md) and [Android remote setup](docs/ANDROID_REMOTE_QUICKSTART.md). Historic release instructions below may describe earlier source versions; do not treat them as evidence of completed production capabilities.

# JARVIS AI — Windows foundation v0.3.0

Independent source release for Mihran. Real PySide6 desktop and working provider request code; no API keys included. This is the third increment, **not the complete autonomous system**.

## Google Flow Video Editor

1. In **Settings & Safety → AI providers**, save your Gemini API configuration.
2. Open **Video Editor** and type a brief, or start an existing voice session and say “Hey Jarvis, video editor, …” followed by the brief.
3. Review the brief, then select **Generate with Gemini**. This sends the brief to Gemini. API charges may apply.
4. Copy the shot prompt into Google Flow. For an existing clip, select or attach the clip in Flow before pasting its edit prompt. Assemble and trim the clips in Flow's Scenebuilder using the shot times.
5. Save the shot plan or English subtitles from JARVIS when needed. Compare subtitle timings with the recorded Tamil voiceover before export.
6. Download the individual clips from Flow. Back in JARVIS, select **Assemble MP4 preview**, choose one clip per shot in timeline order, and optionally add your recorded Tamil narration. Choose an output path and approve the export. JARVIS creates a 30-second 1080 × 1920 MP4 with burned-in English captions. Clips start at their first frame, and shorter shots hold their last frame. Narration starts at time zero and lowers the clip audio.

MP4 export runs locally and requires an FFmpeg build with `ffmpeg` and `ffprobe` on PATH, plus the `libx264` encoder and libass subtitle filter. On Windows, restart JARVIS after updating PATH. You can cancel an export from Video Editor or use Emergency Stop. An interrupted or failed export leaves any existing destination file intact.

**CapCut Desktop.** Generate a shot plan and choose **Export for CapCut Desktop**. Select clips, optional narration and a destination folder. Import the new folder’s `video.mp4` at the start of the CapCut timeline and import `english.srt` under **Captions → Import captions**. The cuts and audio are assembled into one video. The captions stay editable in CapCut.

**After Effects render.** In Video Editor, select **Render After Effects**, or say “Hey Jarvis, render After Effects” to find the button. Choose Adobe's `aerender.exe` from the installed After Effects **Support Files** folder and your `.aep` project. Enter the exact composition and movie output module template names and choose an output extension that matches the template. Review the paths and approve the render. After Effects must be installed on that Windows PC. Start with a project and template you already trust.

**Editable After Effects timeline.** Open your project in After Effects. In JARVIS, generate a shot plan and select **Build After Effects timeline**. Choose one clip per shot, optional recorded narration, and the installed `AfterFX.exe`. Approve the handoff. After Effects imports the selected files and adds a 30-second vertical composition with separate clip and English caption layers. Short clips leave a gap. Check the result and save the project in After Effects.

## Fiverr and website drafts

Open **Business**, choose a task, enter a brief and select **Generate business draft**. The app uses the Gemini configuration from **AI providers**. It can draft Editopro gig packages, client replies, delivery and revision messages, or copy and SEO metadata for a named website page. For a Google AI Studio project, mention Build Mode to get a prompt you can paste there.

For voice input, start an existing voice session and say “Hey Jarvis, Fiverr gig, …”, “Hey Jarvis, Fiverr client reply, …”, “Hey Jarvis, Fiverr delivery, …”, or “Hey Jarvis, website update, …”. Review the recognized text before generating. Review the resulting draft before using it in the account dashboard.

## Start on Windows 10 / 11

1. Install **Python 3.12, 64-bit**, including its Python launcher, from https://www.python.org/downloads/windows/.
2. Extract this entire ZIP to a normal folder (for example Documents/JarvisAI). Do not run from inside the ZIP.
3. Double-click **setup.cmd**. It creates a local virtual environment and installs pinned direct dependencies. Internet access is needed.
4. Double-click **START_JARVIS.cmd**.
5. Open **API Providers**. Select MiniMax, OpenAI or Gemini, enter your own key locally, review the model ID, and click **Save provider configuration**.
6. Open **Chat**, choose that provider, type a message and click **Send to selected provider**. API usage can cost money.
7. Open **Windows Automation** to approve one Notepad or Calculator launch.

No administrator rights are required. Do not run JARVIS as administrator. A Python dependency install error stays visible in the command window. If Python cannot be found, confirm that the Python 3.12 launcher is installed.

A ChatGPT subscription is separate from provider API access. No keys are provisioned by this project. Credentials belong in the application's masked field, never in chat, source files or screenshots.

## Implemented

- Native Qt interface with command center, chat, app launcher, task queue, editor, history, provider manager, usage and permissions.
- Real streaming HTTPS chat adapter for OpenAI, MiniMax, DeepSeek, Groq, OpenRouter and Gemini's compatible chat endpoints, plus a native Anthropic Messages adapter for Claude and a loopback-only local adapter for Ollama. Configurable model IDs; no automatic fallback or hidden retries. A local model never receives a key and never leaves the computer.
- Windows Credential Manager key save/read/delete. Fixed provider endpoints and TLS verification; no plaintext key-storage fallback.
- Manual per-action confirmation for app launches and workspace saves; consumed approvals tied to exact arguments/content hash.
- Fixed Notepad/Calculator launch allowlist using the Windows system directory, with no shell.
- UTF-8 editor with Python syntax checking (no code execution), confined paths, atomic save and old-content backups.
- SQLite conversations/configuration/task history; recovery marks interrupted tasks; single-instance lock.
- Emergency stop and explicit resume; stale worker output remains cancelled after resume.
- Conversation deletion from the UI. New chat preserves old conversations in SQLite; the latest 100 saved conversations can be reopened from Chat.

## New in v0.3.0

- **Step Workflows:** enter 1–10 comma-separated actions from the fixed Notepad/Calculator allowlist. Each step shows a fresh, explicit approval prompt. Runs stop on denial, error or Emergency Stop; no automatic replay of failed/interrupted work.
- **Read-only window inventory:** click the inspection button under Windows Automation, approve access, then view up to 12 of the top-level visible Windows window titles and PIDs (the inspector caps collection at 30). Inspection runs in a separate subprocess with a three-second timeout and does not click/type into windows. Window titles may reveal private information and action results are logged locally.
- **Database migration v3:** on first upgrade from v0.2, a history-pre-v03-*.sqlite3 backup is created before adding workflow records. Existing provider keys remain in the original Windows vault namespace.
- **Manual safety only:** model responses cannot create workflows. Arbitrary app automation and autonomous planning are still not implemented. The wake phrase matcher and the mobile bridge arrived after this release; see the sections below.
- **Validation:** nine local workflow/inspection tests passed using the shared v0.2 gateway, policy and store interfaces; full suite and live Windows behavior still require validation.

## Voice

- **Voice page** in the desktop: allow the microphone, type the wake phrase, listen once or wait for the wake phrase, and let JARVIS speak. The wake phrase can be given in English, Tamil or French, and the matcher is a faithful port of the Android one, so a transcript is judged the same way on both platforms.
- **The microphone stays closed until you allow it.** The permission is shown on the page, unchecking the box withdraws it, and the stop button closes the microphone at once. Resuming does not silently reopen it: you allow it again yourself.
- **The recognition runs on a worker thread**, so the interface never freezes and a widget is never touched from another thread. The recognised text is shown, and a wake call is marked with the phrase that matched and the command that followed it.
- **On a machine that is not Windows** the speech adapters are not available, and the page says so instead of pretending. They have to be exercised on the owner's Windows machine before they are trusted.

## Mobile bridge

- **The phone never holds a provider key.** The chat is answered by the PC. A local provider needs no permission, a paid provider needs the owner's consent *and* the consent on the request itself, and the emergency stop stops the bridge too.
- **Pairing by QR.** The desktop shows a pairing code and a QR image; the phone scans it and the device is remembered. The pairing can be revoked from the desktop.
- **Ten endpoints** cover status, jobs, chat, memory, notifications and the device list. Every request is signed and audited, and only a short digest of the body is recorded, never the body itself.

## New in v0.2.0

- **Agent Task Queue:** add Notepad/Calculator jobs, select a job, then Review and run selected. Each launch needs approval. Waiting jobs survive restart; started/interrupted jobs are never replayed. Cancel selected or Emergency Stop cancels waiting jobs.
- **Test saved provider connection:** in API Providers, save your settings and click the test button. Confirm the short prompt and possible API charge. The test verifies a complete text response from the configured model; it does not send conversation history.
- **Usage & Health:** provider-reported input/output/total tokens, elapsed request time and outcome. Missing counts are shown as Unknown, including many interrupted requests. No currency estimates or billing guarantees.
- **Saved conversations:** choose one from the Chat dropdown and click Open saved chat.
- **Safe upgrade:** the old database is backed up automatically before adding the new tables. Existing history and Windows credentials are retained.
- **CI recipe:** .github/workflows/tests.yml runs tests on Windows and Linux when this source root is placed in a GitHub repository. It has not been run on GitHub here.

### Upgrade from v0.1.0

Close JARVIS first. Extract v0.2.0 into a new folder and run setup.cmd, then START_JARVIS.cmd. Do not merge Python environments. Both versions use %LOCALAPPDATA%/JarvisAI; the existing credential-vault service name remains JARVIS-AI-0.1 deliberately.

The first v0.2 startup backs up the original SQLite database as history-pre-v02-unique-id.sqlite3. Keep that file. To roll back user data, close JARVIS, back up the whole data folder, move the current history.sqlite3 and its -wal/-shm companions aside, and copy the pre-upgrade backup to history.sqlite3 before opening v0.1. Changes since the backup will not be present.

## Limits and security

This release has **manual mode only**. It does not implement autonomous planning, arbitrary computer control, shell execution, builds, RAG, quantum tools, cybersecurity scanning, self-updates or executable plugins. Voice is present as a permissioned adapter that still needs Windows acceptance, and the phone bridge is a supervised channel rather than remote control. Future directories contain boundary documentation, not mock features.

The **Mobile Bridge** page starts a listener for a paired phone. It refuses to start without TLS, refuses a non loopback address, authenticates every request with a signed HMAC, and keeps every job waiting for your approval in the desktop interface. The provider list, including Claude and the local Ollama model, is served by the unified router in `providers/`. The voice layer in `voice/` matches the wake phrase with the same rules as the Android client and holds the microphone behind an explicit permission and a stop control. All of this is covered by local tests; the Windows speech adapters still need to be exercised on your machine. See docs/BRIDGE_PROTOCOL.md and docs/UNIFIED_INTEGRATION.md.

Key storage works only on Windows. Chat UI and core were exercised on Linux with Qt offscreen. **No live provider request, Windows Credential Manager operation, Windows application launch or packaged EXE was tested here.** See docs/TEST_RESULTS.md for actual results and docs/WINDOWS_ACCEPTANCE.md for the remaining checks.

The selected conversation is sent to the selected provider when you click Send; sending the same conversation to another provider shares it with that provider. No system files or editor contents are automatically attached. Model responses are untrusted text and cannot launch tools.

Local chat/history/code are plaintext under **%LOCALAPPDATA%/JarvisAI**. Protect your Windows account and disk. The database contains task descriptions and conversation content, but never stores keys from the settings field. Do not type secrets into ordinary chat messages.

Emergency stop blocks new actions and invalidates approvals. It stops accepting streamed output and requests cancellation, but an in-flight network read may need up to 30 seconds to finish (total stream budget 180 seconds, checked between events). Already-sent requests may be billed. Already-launched applications remain open. It is not an OS-wide kill switch. Ctrl+Alt+J is an application shortcut while JARVIS has focus; other software may reserve this chord, so use the visible red button if necessary.

Editor confinement protects against accidental traversal and ordinary symlink escapes. It is not a sandbox against another process running as your Windows user racing filesystem changes. No unfamiliar code is executed by this release. History is not a tamper-proof enterprise audit log.

Chat input is limited to approximately 90,000 content characters; oversized serialized requests are rejected at 100,000 characters. There is no summarization yet. Output cap: 200,000 characters. Incomplete or filtered streams are reported as errors; partial output is not used as assistant context.

## Coding workspace and recovery

Workspace: **%LOCALAPPDATA%/JarvisAI/workspace**. Enter a relative filename such as src/main.py, then Open or Save. Editing supports text in any language; syntax checking is Python only. Existing contents are copied to .revisions/unique-id.bak before replacement. Revision filenames are opaque; inspect backup contents to select a revision.

To restore a file, close JARVIS, inspect the backup, and manually copy its contents to the intended workspace file. To back up all user data, close JARVIS and copy the JarvisAI data directory. API keys remain in Windows Credential Manager and are not included. For code rollback, retain the previous source folder before replacing it.

## v0.3 workflow usage and upgrade

Close JARVIS before upgrading. Save a copy of your existing source directory, extract the new v0.3 source to a separate directory, run setup.cmd and then START_JARVIS.cmd. The local SQLite database is upgraded in-place with an automatic v0.3 migration backup. Do not copy an old Python virtual environment into the new source.

Open **Step Workflows**. Enter a sequence such as `Notepad, Calculator`, click **Create workflow**, select the row, then click **Review and run selected**. Every launch gets its own confirmation; clicking No ends the whole workflow. Already launched apps are not closed on cancellation. This is a supervised sequence, not autonomous planning.

Under **Windows Automation**, use **Review visible window titles (read only)** to inspect visible top-level window titles and process IDs. Titles may include document names; approve only when comfortable. It does not type, click, record screens or inspect window contents.

## Tests and packaging

Run scripts/test.cmd on Windows. Or:
    python -m pip install -r requirements-dev.txt
    python -m pytest -q

Provider protocol tests use httpx.MockTransport with synthetic responses; they do not prove account/model access. Desktop smoke/integration tests use real Qt widgets and worker threads, with synthetic network responses.

Optional: installers/build.cmd builds an **unsigned PyInstaller folder** on Windows. Distribute the entire dist/JarvisAI folder. This is a build recipe, not a prebuilt installer, signed release, or claim of Windows verification. Direct dependencies are pinned; a full Windows transitive lock, SBOM and supply-chain review remain release-engineering work. Review Qt/PySide licensing before redistribution.

## Architecture and next phase

Read docs/ARCHITECTURE.md for trust boundaries and the complete prioritized 12-phase roadmap.

**Next phase:** validate v0.3 on Windows 10/11 and with your configured provider, execute Windows CI/acceptance checks, then add permissioned accessibility-based inspection and carefully scoped UI actions. Supervised/trusted modes must wait for policy and recovery tests.

## Official references checked while implementing

- Qt setup: https://doc.qt.io/qtforpython-6/gettingstarted.html
- OpenAI chat reference: https://developers.openai.com/api/reference/typescript/resources/chat
- MiniMax compatibility: https://platform.minimax.io/docs/api-reference/text-openai-api
- Gemini compatibility: https://ai.google.dev/gemini-api/docs/openai

Provider defaults are editable suggestions, not a guarantee of model availability. The request adapter uses the documented compatible chat format; native advanced provider capabilities are not included.

Provider usage references:
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events
- https://ai.google.dev/gemini-api/docs/openai?hl=fr
- https://platform.minimax.io/docs/api-reference/text-openai-api
