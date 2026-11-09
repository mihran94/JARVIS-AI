@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Python environment missing. Run setup.cmd first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe scripts\diagnose.py
set "JARVIS_DIAG_EXIT=%errorlevel%"
pause
exit /b %JARVIS_DIAG_EXIT%
