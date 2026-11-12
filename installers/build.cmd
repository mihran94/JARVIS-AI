@echo off
setlocal
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pip install pyinstaller==6.12.0
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name JarvisAI --hidden-import keyring.backends.Windows main.py
if errorlevel 1 exit /b 1

REM Record what was built, with the SHA-256 of every file, so the folder can
REM be verified later and the build can be traced back to its source.
set "REVISION=unknown"
for /f "delims=" %%r in ('git rev-parse HEAD 2^>nul') do set "REVISION=%%r"
.venv\Scripts\python.exe scripts\release_manifest.py dist\JarvisAI dist\JarvisAI-RELEASE.txt --version 0.3.0 --revision %REVISION% --channel beta
if errorlevel 1 exit /b 1

echo Unsigned folder build available at dist\JarvisAI.
echo The release manifest is at dist\JarvisAI-RELEASE.txt. Windows testing is required before distribution.
pause
