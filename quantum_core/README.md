# J.A.R.V.I.S. // QUANTUM CORE

Extract this folder and open PowerShell in it. Python 3.12 and Chrome are the
default setup. Use `--browser edge` for Edge.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$key = Read-Host "Google AI Studio API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password
.\.venv\Scripts\python.exe launcher.py
```

Time and system status also work with an empty key. Try `/time`, `/status` or
`கணினி நிலை`. General questions go to Gemini and the chat retains context
until you exit. The default model is `gemini-2.5-flash`. Set `GEMINI_MODEL`
in PowerShell to use another model available to your key.

Spoken replies use local text-to-speech. Add `--no-voice` for text only. To
opt into continuous microphone input for a session, launch with
`--listen --language ta-IN`. Change the locale to `en-US` or `fr-FR` if needed.
Google speech recognition receives the recorded audio in this mode. General
questions are then sent to Gemini as text. Close the HUD or press Ctrl+C to
end the session.

The launcher serves the interface on `127.0.0.1:8766`. Use `--port` if that
port is occupied. For a manual browser launch, use `--browser none` and open
http://127.0.0.1:8766/index.html. Opening `web/index.html` directly runs the
visual preview with simulated readings.

## Creative and business workspaces

Use the HUD command bar with a brief after the command.

| Command | Output |
|---|---|
| `/flow` | A draft prompt to copy into Google Flow |
| `/higgsfield` | A draft prompt to copy into Higgsfield |
| `/fiverr` | A reply to review before sending to a client |
| `/website` | Draft copy for your website |
| `/app` | An HTML draft you can download and review in VS Code |

Drafts use Gemini without adding the briefs to general chat history. The HUD
shows the draft as text. For an app draft, **Download HTML draft** saves a file
for review. The coding model defaults to `gemini-2.5-pro`. Set
`GEMINI_CODING_MODEL` if your key uses another coding model.
