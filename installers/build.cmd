@echo off
setlocal
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pip install pyinstaller==6.12.0
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name JarvisAI --hidden-import keyring.backends.Windows main.py
if errorlevel 1 exit /b 1
echo Unsigned folder build available at dist\JarvisAI. Windows testing is required before distribution.
pause
