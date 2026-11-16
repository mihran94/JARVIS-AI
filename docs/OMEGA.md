# JARVIS Omega desktop

Omega runs inside the Windows desktop launcher. Install the project's pinned
dependencies with `setup.cmd`, then use `START_JARVIS.cmd`. An existing source
checkout can use `.venv\Scripts\python.exe main.py`. This branch preserves the
existing provider credentials, voice permission, phone pairing and approval flow.

## Modes and controls

| Mode | Use |
|---|---|
| Omega | Full-screen command center. **Window** or **F11** toggles normal size. Use the command field to submit through JARVIS Chat. |
| Island | Drag the core or title. **Expand** reveals microphone, quick command, alerts, Stop, and Dashboard. |
| Stealth | Click the small core to expand it. Drag it to reposition. **Dashboard** or **Esc** returns to Omega. |

Use **Settings** in the dock to select Midnight Blue, Apple Silver or Dark
Titanium, change backgrounds and dock order, disable animation, or turn on
always-on-top for the floating assistant. Startup speech uses the optional greeting you enter. **Ctrl+D** reveals or hides the dock.
Tab or the arrow keys move focus among dock tools. The current section has a
highlighted icon. The desktop remembers the theme, mode, dock and floating
position settings.

**Refresh weather and news** makes direct HTTPS requests to Open-Meteo and
the France and Sri Lanka sources already configured in the application.
You can change the weather label and coordinates under Omega Settings. The
dash displays the last returned reading time and marks unavailable feeds.
A displayed phone pairing count and last signed check-in are distinct from
an active Android connection.

The land grid is sampled from [Natural Earth public-domain 1:110m land polygons](https://www.naturalearthdata.com/about/terms-of-use/).
The animated Earth uses an orthographic projection. The reactor and backdrop
use a portable QPainter renderer. Rendering pauses when hidden and Reduce
Motion also stops the reactor and hover animations. Listening rings use
the existing Windows recognizer's audio level when available. Speaking rings
follow the voice worker's playback state.

## Validation

```powershell
.venv\Scripts\python.exe main.py --smoke-test
.venv\Scripts\python.exe -m pytest -q tests/test_omega.py tests/test_voice_panel.py tests/test_jarvis_main_window.py
```

A Windows candidate can be built with the repository's existing
`installers\build.cmd` on a Windows host.
