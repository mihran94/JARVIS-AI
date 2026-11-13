@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project environment is missing. Double-click SETUP_JARVIS.cmd first.
    pause
    exit /b 1
)
if not exist "launcher.py" (
    echo Launcher is missing. Extract the complete ZIP before starting Jarvis.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "launcher.py"
set "JB_RESULT=%errorlevel%"
if not "%JB_RESULT%"=="0" pause
exit /b %JB_RESULT%
