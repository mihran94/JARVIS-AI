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
If ISCC is not on PATH or at the default install path, open `installer\jarvis-blue.iss` in Inno Setup and click Compile.

## Acceptance checks (must be completed on the user's Windows PC)
1. Confirm bundle EXE launches and Chat/Voice/Provider pages open without a console.
2. Confirm API keys stay in Windows Credential Manager and no keys are bundled.
3. Confirm emergency stop and per-action approvals still work.
4. Run the installer as a standard user; confirm desktop shortcut and uninstall.
5. Verify uninstall leaves the user's `%LOCALAPPDATA%\JarvisAI` history/data intact.
6. Check mobile pairing and provider integrations separately; do not assume they are working merely because the app launches.

No GitHub Actions. No automatic signing. Never upload API keys or credentials.
The bundled app uses the existing `main.py` entrypoint; no new capabilities are implied.
