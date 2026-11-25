# JARVIS PC & Projects for Mark LVII

This installs a native plugin into an existing Mark LVII installation. Launch
Mark as usual. Its settings, voice engine, microphone controls and HUD stay in
its own process. The plugin uses the JARVIS Python environment for individual
operations and does not launch the JARVIS window.

From the JARVIS source folder in PowerShell:

```powershell
.\integrations\mark\Install-MarkPlugin.ps1 -MarkPath 'C:\path\to\Mark-LVII'
```

Add `-DevData` if the projects live in the JARVIS development profile
used by `START_JARVIS.cmd --dev-data`. Restart Mark to load the plugin.

Say “JARVIS PC plugin, list my saved projects” or “JARVIS PC plugin, calculate
17 times 23”. The plugin can open Calculator or Notepad, calculate two-integer
arithmetic in Calculator, insert approved text into Notepad, and show status,
open, statically inspect or run the saved tests for an existing JARVIS project.
Mark displays the exact action and target in its confirmation banner and records
the result in Communications. The project list can be read without a banner.
Project edits, new project registration, and arbitrary commands are outside
this plugin's operation list.
