# JARVIS BLUE — Windows 10 installer (development)
This is a **build recipe**, not a tested or released installer. Source branch: `dev/windows10-installer-20261113`.

## Requirements
- Windows 10 x64; Python 3.12 x64 installed with the `py` launcher.
- Internet access to install pinned dependencies and PyInstaller.
- Inno Setup 6 for the final setup EXE (install it separately).
- Build as a normal Windows user, not administrator.

## Build
From the repository root, double-click `installer\build-windows.cmd` or run it from Command Prompt.
The script builds `dist\JARVIS-BLUE\JARVIS-BLUE.exe` with PyInstaller.
When Inno Setup is available, it also creates `dist\installer\JARVIS-BLUE-Setup.exe`.
If Inno Setup is missing, the script exits with code 2 after producing the app bundle (not the Setup.exe). If ISCC is installed in a custom path, open `installer\jarvis-blue.iss` in Inno Setup and click Compile.

## Acceptance checks (must be completed on the user's Windows PC)
1. Confirm bundle EXE launches and Chat/Voice/Provider pages open without a console.
2. Confirm API keys stay in Windows Credential Manager and no keys are bundled.
3. Confirm emergency stop and per-action approvals still work.
4. Run the installer as a standard user; confirm desktop shortcut and uninstall.
5. Verify uninstall leaves the user's `%LOCALAPPDATA%\JarvisAI` history/data intact.
6. Check mobile pairing and provider integrations separately; do not assume they are working merely because the app launches.

No GitHub Actions. No automatic signing. Never upload API keys or credentials.
The bundled app uses the existing `main.py` entrypoint; no new capabilities are implied.

## Important limitations
- This build recipe has not been executed on the owner's Windows 10 PC. A successful GitHub commit is not a successful installer build.
- The source ZIP update workflow is not automatically compatible with a frozen PyInstaller installation; use a fresh installer build for updates until a separately tested update path is available.
- The package does not yet merge the PyQt6 Jarvis-Blue HUD into the PySide6 Windows UI. Voice and mobile functionality need end-to-end testing.
- Do not publish the generated unsigned executable as a verified release until Windows acceptance tests pass.

## Preflight validation
The build script now runs `installer\\preflight.py` before packaging. This parses Python source files and checks PySide6, httpx, and keyring availability. It does not run the application or test Windows functionality. You can also run `.venv\\Scripts\\python.exe installer\\preflight.py` manually after setup.

## Futuristic Blue UI (development)
The Windows Command Center now imports `desktop/blue_theme.py` and `desktop/blue_orb.py`. The orb is decorative and animated, not connected to AI requests, voice listening, or device status. It stops its animation timer while hidden. Validate the layout and animation on Windows 10 before treating it as finished.

## Orb activity states
The command-center orb now reflects the chat worker: idle, thinking (request in progress), responding (text chunks arriving), and stopped (emergency stop). These are UI indications only, not microphone listening, voice output, or proof of model reasoning. Confirm transitions and emergency stop behavior during Windows acceptance testing.

## CPU utilization monitoring
The read-only dashboard now uses Windows `GetSystemTimes` to compute CPU usage between samples, refreshing every five seconds. The first sample displays collecting/unavailable because a baseline is needed. CPU usage is system-wide, not per-process. Network throughput is not yet measured. Validate readings against Windows Task Manager on the target PC.
