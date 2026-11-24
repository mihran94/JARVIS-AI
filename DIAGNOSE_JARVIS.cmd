@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Python environment missing. Run setup.cmd first.
 exit /b 1
)
".venv\Scripts\python.exe" scripts\diagnose.py %*
exit /b %errorlevel%
