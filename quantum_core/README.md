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
until you exit. The default model is `gemini-3.5-flash-lite`. Set `GEMINI_MODEL`
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
| `/studio` | Prepare a prompt to update AI Creative Studio in Google AI Studio Build |
| `/app` | An HTML draft you can download and review in VS Code |

The workspace also links to the AI Creative Studio Build project. Copy the
`/studio` prompt into Build mode and review the resulting preview. JARVIS
formats this prompt locally.

The other drafts use Gemini without adding the briefs to general chat history. The HUD
shows the draft as text. For an app draft, **Download HTML draft** saves a file
for review. The coding model defaults to `gemini-2.5-pro`. Set
`GEMINI_CODING_MODEL` if your key uses another coding model.

## Camera and Windows devices

Open **Camera & Windows devices** in the HUD. Camera preview and brightness
control have optional dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-device.txt
```

- **Face preview** opens the selected camera for about eight seconds. Q or Esc
  closes it early. Frames are processed locally and discarded. A result reports
  face presence only.
- **Brightness** accepts 10–100%. The HUD displays values reported by the
  connected displays.
- **Power plan** switches among Balanced, Power Saver and High Performance if
  available. The HUD verifies the active Windows plan.
- **Kali WSL** opens the installed `kali-linux` console for manual use.
- **WhatsApp** and **Phone Link** ask Windows to open the installed app.
  Choose the contact and start the call there.


### Use an iPhone as the camera on a Windows PC

1. Install [Camo Camera on the iPhone and Camo Studio on the PC](https://camo.com/studio).
2. Connect the iPhone directly to the PC with a USB data cable. Open both Camo
   apps and select your iPhone in Camo Studio. Verify the live feed there.
3. In JARVIS, open **Camera & Windows devices** and select **Refresh cameras**.
   Choose **Camo Camera**, preferably the DirectShow entry if two appear,
   then select **Face preview**.
4. If Camo Camera is missing, keep Camo Studio open and select **Refresh cameras**
   after reconnecting the phone. If one capture entry fails, try the other
   backend entry for the same camera.

An external USB webcam uses the same source selector once Windows detects it.

## Local network diagnostics and upgrade proposals

Under **Camera & Windows devices**, choose **Cached neighbors**, **TCP listeners**
or **Established TCP** to read the local operating system's tables. Reports stay
in the HUD.

Type `/upgrade` and a feature brief to draft a Gemini review plan with tests and
rollback notes. The proposal appears in **Creative & business workspaces**.


## Spatial Edition

From the full JARVIS source folder, run the HUD with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r quantum_core/requirements.txt
.\.venv\Scripts\python.exe main.py --hud
```

The dock switches between **Core**, **Creative**, **Business**, **Dev Lab**
and **Devices**. The HUD runs in a browser on the PC. Run `START_JARVIS.cmd`
to use the Windows desktop app, including Tamil news and its existing updater.
