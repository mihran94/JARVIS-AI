# JARVIS AI — தொடங்குவது எப்படி

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
