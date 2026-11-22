# JARVIS AI — Windows-ல் தொடங்குவது எப்படி

முதலில் PC-ல் மூன்று விஷயங்களைச் சரிபாருங்கள். JARVIS திறக்கிறதா, அனுமதித்த Windows action-ஐச் செய்கிறதா, நீங்கள் தேர்ந்தெடுத்த AI provider பதில் தருகிறதா என்று பாருங்கள்.

## முதல் முறை setup

[GitHub main ZIP](https://github.com/mihran94/JARVIS-AI/archive/refs/heads/main.zip)-ஐ download செய்து புதிய folder-ல் extract செய்யுங்கள். Python 3.12 (64-bit) மற்றும் Python Launcher தேவை. Extract செய்த folder-ல் Windows CMD திறந்து இயக்குங்கள்.

```bat
setup.cmd
```

`Setup complete` வந்ததும், அதே CMD-ல் இயக்குங்கள்.

```bat
START_JARVIS.cmd
```

அடுத்த முறை `START_JARVIS.cmd` மட்டும் போதும். ஏற்கெனவே மற்றொரு JARVIS window திறந்திருந்தால் அதை மூடிவிட்டு தொடங்குங்கள்.

## முதல் சோதனை

1. **Local check** — Chat-ல் `/status` என்று type செய்யுங்கள். Provider key இல்லாமலே PC status வர வேண்டும்.
2. **PC Control** — `Open Notepad` என்று type செய்யுங்கள். முதலில் **Decline** அழுத்தி app திறக்கவில்லை என்று பாருங்கள். மீண்டும் கேட்டு **Approve** அழுத்துங்கள். Notepad window திறந்ததா என்று பாருங்கள். **Activity**-ல் `Verified` அல்லது `Unverified` என்ற முடிவு தெரியும். Windows ஏற்கெனவே திறந்த window-ஐப் பயன்படுத்தினால் `Unverified` வரலாம்.
3. **AI chat** — **Settings & Safety → AI providers** சென்று ஒரு provider, உதாரணமாக Gemini, configure செய்யுங்கள். **Test saved provider connection (uses API)** அழுத்துங்கள். Settings-ல் chat provider-ஆக அதையே தேர்ந்தெடுத்து, தமிழில் ஒரு message அனுப்புங்கள். API key-ஐ app Settings-ல் மட்டும் உள்ளிடுங்கள். Provider கட்டணம் இருக்கலாம்.
4. **Voice மற்றும் Stop** — **Voice / Hey Jarvis** பகுதியில் microphone permission கொடுத்து குறுகிய வாசகத்தைச் சொல்லிப் பாருங்கள். விருப்பப்பட்டால் **Read replies aloud** இயக்குங்கள். இயங்கும் plan-ஐ நிறுத்த **Emergency Stop** அழுத்துங்கள். ஏற்கெனவே திறந்த apps திறந்தபடியே இருக்கும்.

இந்தச் சோதனைகள் முடிந்ததும் உங்களுக்கு அடிக்கடி தேவைப்படும் ஒரு வேலையை முயற்சி செய்யுங்கள். உதாரணமாக, ஒரு Editopro client message-க்கு Tamil மற்றும் English reply draft தயார் செய்து, நீங்கள் பார்த்த பிறகு அனுப்பலாம்.

## மற்ற வசதிகள்

- **Files & Folders** — `/files` மூலம் local file அல்லது folder தேர்ந்தெடுத்து preview செய்யலாம்.
- **Video Editor** — `/video` மூலம் shot plan திறக்கலாம். உங்கள் Flow clips-ஐ subtitles உடன் MP4 preview ஆகச் சேர்க்க FFmpeg மற்றும் ffprobe தேவை. CapCut handoff மற்றும் After Effects render தனித்தனி controls மூலம் கிடைக்கும்.
- **Phone Remote** — PC-ல் chat மற்றும் supported remote tasks வேலை செய்வதை உறுதிசெய்த பிறகு pair செய்யுங்கள். [Android வழிமுறை](docs/ANDROID_REMOTE_QUICKSTART.md) · [iPhone PWA வழிமுறை](iphone-pwa/README.md)

## பிரச்சினை வந்தால்

JARVIS-ஐ மூடி `VERIFY_JARVIS.cmd` run செய்யுங்கள். இது installed runtime மற்றும் offline startup-ஐச் சோதிக்கும். `DIAGNOSE_JARVIS.cmd` missing dependencies-ஐக் கண்டுபிடிக்க உதவும். உண்மையான voice, provider, camera மற்றும் Windows automation சோதனைகளை உங்கள் PC-ல் செய்ய வேண்டும். [Windows acceptance checklist](docs/WINDOWS_ACCEPTANCE.md)

Source update-ஐ **Settings & Safety → Updates & rollback** வழியாக review செய்யலாம். Update அல்லது reinstall செய்வதற்கு முன் `%LOCALAPPDATA%\JarvisAI` profile-ஐ backup எடுக்கவும். [Backup மற்றும் rollback வழிமுறை](docs/WINDOWS_ACCEPTANCE.md#recovery)
