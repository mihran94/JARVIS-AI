> **14 நவம்பர் 2026 — தற்போதைய நிலை:** JARVIS AI ஒரு Windows **Beta**, அதன் Android செயலி Windows PC-ஐக் கட்டுப்படுத்தும் **Remote**. Android app திறந்தவுடன் crash ஆன Android Keystore பிழை GitHub PR #22-ல் சரிசெய்யப்பட்டு Android 15 emulator-ல் சோதிக்கப்பட்டது. புதிய Android வழிமுறை: [Android Remote setup](docs/ANDROID_REMOTE_QUICKSTART.md). என்ன முடிந்துள்ளது / எது இன்னும் முடியவில்லை: [Development Audit](docs/DEVELOPMENT_AUDIT_2026-11-14.md). உங்கள் PC-யில் உண்மையான microphone, AI connection, mobile pairing, signing ஆகியவை இன்னும் சோதிக்கப்படவேண்டும். முழு autonomous JARVIS தயாராகிவிட்டதாக இதனால் பொருள் இல்லை.

# JARVIS AI — தொடங்குவது எப்படி

## ஒரே personal Windows build

1. பழைய JARVIS app-ஐ மூடுங்கள். Windows 10/11 x64 PC-ல் Python 3.12 (64-bit) மற்றும் Python Launcher இருக்க வேண்டும்.
2. இந்த ZIP-ஐ ஒரு தனி folder-ல் extract செய்து `setup.cmd` இயக்குங்கள். அதன் பிறகு அந்த folder-ல் உள்ள `START_JARVIS.cmd` shortcut-ஐ மட்டும் பயன்படுத்துங்கள்.
3. **Settings & Safety → AI providers** பகுதியில் Gemini model மற்றும் API key-ஐச் save செய்து **Test saved provider connection** அழுத்துங்கள்.
4. **Voice / Hey Jarvis** பகுதியில் microphone permission கொடுத்து **Talk once** மூலம் தமிழ் brief பேசிப் பாருங்கள். Windows-ல் கிடைக்கும் speech recognizer மற்றும் மொழி ஆதரவைப் பொறுத்தே recognition இருக்கும்.
5. **Video Editor**-ல் shot plan தயார் செய்து, Flow clips மற்றும் விருப்பப்பட்டால் பதிவு செய்த Tamil narration-ஐத் தேர்ந்தெடுத்து captions உடன் MP4 export செய்யுங்கள். FFmpeg, ffprobe மற்றும் subtitle filter தேவை.
6. **Business** பகுதியில் Editopro reply அல்லது website update draft உருவாக்கிப் பாருங்கள். அனுப்புதல் மற்றும் publish செய்வதை account dashboard-ல் செய்யுங்கள்.
7. Android Remote தேவைப்பட்டால் மட்டும் தனியாக Windows app-உடன் pair செய்யுங்கள். [Android Remote setup](docs/ANDROID_REMOTE_QUICKSTART.md)

**CapCut Desktop:** Video Editor-ல் **Export for CapCut Desktop** தேர்வு செய்யுங்கள். JARVIS உருவாக்கும் `video.mp4` மற்றும் `english.srt` files-ஐ CapCut-ல் import செய்யுங்கள். Subtitle text-ஐ CapCut-ல் திருத்தலாம்.

**iPhone:** Windows-ல் **Phone Remote → Pair this iPhone** மூலம் pairing code எடுக்கவும். இந்த package-ல் உள்ள `iphone-pwa` folder-ஐ private HTTPS வழியாக Windows bridge-உடன் இணைத்த பிறகு, அந்த URL-ஐ Safari-ல் திறந்து **Share → Add to Home Screen** தேர்வு செய்யலாம். [iPhone setup](iphone-pwa/README.md)

Windows PC இயங்கும்போது phone remote-ல் PC status, chat மற்றும் request queue பயன்படுத்தலாம். Video clips தேர்வு, After Effects handoff மற்றும் CapCut import ஆகியவை Windows-ல் செய்யப்படுகின்றன.

இந்த ZIP என்பது ஒரே Windows source build. Windows installer மற்றும் உங்கள் PC-ல் live microphone, Gemini, FFmpeg மற்றும் phone pairing சோதனைகள் முடிந்த பிறகு v1.0 என்று குறிக்கலாம்.

## Google Flow மற்றும் Business update

- **Video Editor:** 30-second vertical video-க்கான Google Flow prompts, Tamil voiceover draft, English SRT மற்றும் cut instructions.
- **MP4 preview:** Flow-ல் download செய்த clips-ஐ **Assemble MP4 preview** மூலம் ஒவ்வொரு shot-க்கும் தேர்வு செய்யுங்கள். விரும்பினால் பதிவு செய்த Tamil narration-ஐச் சேர்க்கலாம். English subtitles உடன் 1080 × 1920 MP4 export ஆகும். FFmpeg மற்றும் ffprobe Windows PATH-ல் இருக்க வேண்டும்.
- **After Effects:** **Video Editor → Render After Effects** திறந்து, நிறுவிய After Effects-ன் `aerender.exe`, உங்கள் `.aep` project, composition பெயர், output module template பெயர், save location ஆகியவற்றைத் தேர்வு செய்யுங்கள். Review செய்து approve செய்ததும் JARVIS render தொடங்கும்.
- **Editable timeline:** After Effects project-ஐத் திறந்து, JARVIS-ல் shot plan உருவாக்கி **Build After Effects timeline** தேர்வு செய்யுங்கள். ஒவ்வொரு clip, விருப்பப்பட்டால் narration, மற்றும் `AfterFX.exe` ஆகியவற்றைத் தேர்ந்தெடுத்து approve செய்யுங்கள். உருவான composition-ஐ After Effects-ல் பார்த்து project-ஐ save செய்யுங்கள்.
- **Business:** Editopro Fiverr gig, client reply, delivery/revision drafts, website copy மற்றும் SEO drafts.
- இரண்டு tabs-க்கும் **Settings & Safety → AI providers → Gemini** பகுதியில் உங்கள் Gemini API configuration-ஐ save செய்யுங்கள். Chat-ல் OpenAI-யும் தேர்வு செய்யலாம்.
- Voice session-ல் “Hey Jarvis, video editor, …” அல்லது “Hey Jarvis, Fiverr gig, …” என்று சொல்லலாம். Brief-ஐ review செய்து Generate அழுத்துங்கள். Fiverr மற்றும் website drafts-ஐ அந்தந்த dashboard-ல் பயன்படுத்தலாம்.
- Source installation இருந்தால் **Settings & Safety → Updates & rollback → Select GitHub ZIP** வழியாக ZIP-ஐத் தேர்ந்தெடுத்து review செய்யலாம். Approve செய்த பிறகு JARVIS-ஐ மூடி `START_JARVIS.cmd` மூலம் மீண்டும் திறக்கவும். Installer build பயன்படுத்தினால் இந்த ZIP-ஐ தனி folder-ல் extract செய்து source setup வழிமுறையைப் பின்பற்றுங்கள்.

இது முதல் வேலை செய்யக்கூடிய source version (v0.2). முழுமையான autonomous JARVIS இன்னும் இல்லை.

1. Windows கணினியில் Python 3.12 (64-bit) மற்றும் Python Launcher நிறுவுங்கள்.
2. ZIP கோப்பை Extract All செய்து ஒரு சாதாரண folder-ல் வையுங்கள்.
3. setup.cmd திறந்து dependencies நிறுவி முடிக்கவும்.
4. START_JARVIS.cmd திறக்கவும்.
5. API Providers பகுதியில் MiniMax / OpenAI / Gemini தேர்வு செய்யவும்.
6. உங்கள் API key-ஐ அந்த app-ல் மட்டும் உள்ளிட்டு Save provider configuration அழுத்தவும்.
7. Chat பகுதியில் அதே provider-ஐத் தேர்வு செய்து message அனுப்பவும்.

API key-ஐ இந்த ChatGPT உரையாடலுக்கு அனுப்ப வேண்டாம். API பயன்பாட்டிற்குக் கட்டணம் இருக்கலாம்.

இந்த version-ல்:
- Desktop interface மற்றும் streaming AI chat code.
- அனுமதி கொடுத்த பிறகு Notepad / Calculator திறப்பது.
- Code editor, Python syntax check, file backup.
- Task history மற்றும் Emergency Stop.

சிவப்பு EMERGENCY STOP button புதிய செயல்களைத் தடுக்கும். ஏற்கெனவே திறந்த programs மூடப்படாது. நடந்து கொண்டிருக்கும் API request முடிவடைய 30 seconds வரை ஆகலாம்.

இங்கே 57 tests pass ஆனது. Windows app launch, Windows Credential Manager மற்றும் உண்மையான API response உங்கள் PC-ல் இன்னும் சோதிக்கப்பட வேண்டும். முழு வழிமுறை README.md-ல் உள்ளது.


புதிய வசதிகள்:
- Agent Task Queue: வேலைகளைச் சேர்த்து, ஒவ்வொன்றையும் அனுமதித்த பிறகு இயக்கலாம்.
- API Providers: உங்கள் key-ஐ save செய்த பிறகு Test saved provider connection மூலம் சோதிக்கலாம். API கட்டணம் இருக்கலாம்.
- Usage & Health: token பயன்பாடு மற்றும் request நேரம் தெரியும். Unknown என்பது இலவசம் என்று பொருள் அல்ல.
- Chat: முன்பு சேமித்த உரையாடலை மீண்டும் திறக்கலாம்.

பழைய version இருந்தால் அதை மூடி, புதிய ZIP-ஐ தனி folder-ல் extract செய்யுங்கள். setup.cmd மீண்டும் இயக்கவும். பழைய history மற்றும் keys இருக்கும். முதல் startup-ல் database backup உருவாகும்.

## v0.3 புதிதாக சேர்த்தவை

- **Step Workflows:** `Notepad, Calculator` என்று கொடுத்து Create Workflow தேர்வு செய்யுங்கள். ஒவ்வொரு படிக்கும் தனியாக உங்கள் அனுமதி அவசியம் (அதிகபட்சம் 10).
- **Window inspection:** Windows Automation → Review visible window titles (read only). நீங்கள் ஒப்புதல் அளித்த பின்னரே திறந்துள்ள Windows தலைப்புகளையும் process ID-களையும் பார்க்கலாம். எந்த window-வையும் கட்டுப்படுத்தாது.
- **Emergency Stop:** காத்திருக்கும் workflows-ஐ நிறுத்தும். ஏற்கெனவே திறந்த app-களை மூடாது.
- API keys இப்போது தேவையில்லை; பின்னர் உங்கள் Windows PC-யில் மட்டும் சேர்க்கலாம்.
- இது முழு autonomous AI அல்லது mobile remote-control final version அல்ல.


## Installation பிரச்சினைகளைச் சோதிக்க

`DIAGNOSE_JARVIS.cmd`-ஐ double-click செய்யுங்கள். Python 3.12, 64-bit, package versions மற்றும் Qt imports ஆகியவை சரிபார்க்கப்படும். Missing package அல்லது version mismatch இருந்தால் `setup.cmd` மீண்டும் இயக்குங்கள்.

API key, chat history எதையும் இந்தச் சோதனை படிக்காது; internet request அனுப்பாது. இது installation check மட்டுமே; உண்மையான Windows automation அல்லது provider connection வெற்றியை உறுதிப்படுத்தாது.

## அடுத்த updates: app மூலமாக

முதல் installation-க்குப் பிறகு புதிய GitHub ZIP-ஐ பழைய folder மீது extract செய்ய வேண்டாம். App-ல் **Permissions & Roadmap → Updates & rollback → Select GitHub ZIP** செல்லுங்கள். மாற்றங்களைப் பார்த்து approve செய்யுங்கள். App-ஐ மூடி, பழைய installation folder-ல் இருக்கும் `START_JARVIS.cmd` மூலம் மீண்டும் திறக்கவும்.

பழைய code பாதுகாக்கப்படும்; history database backup எடுக்கப்படும். பிரச்சினை வந்தால் `ROLLBACK_JARVIS.cmd` இயக்கி YES கொடுத்து பழைய code-க்கு திரும்பலாம். Dependencies அல்லது database code மாறிய update-ஐ இது ஏற்காது; அந்த release-ஐ தனியாக install செய்ய வேண்டும்.

இது signed auto-update அல்ல. நீங்கள் நம்பும் GitHub ZIP மட்டும் தேர்வு செய்யுங்கள். Update தானாக download/install ஆகாது. Windows PC சோதனை இன்னும் நிலுவையில் உள்ளது.
