@echo off
setlocal
cd /d "%~dp0"
if not exist "tools\setup_environment.py" goto incomplete
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\setup_environment.py"
    goto done
)
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 "tools\setup_environment.py"
    goto done
)
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.11 "tools\setup_environment.py"
    goto done
)
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.13 "tools\setup_environment.py"
    goto done
)
echo Python 3.12 was not found. Run: py -0p
echo Install Python 3.12 with the Python launcher, then retry.
pause
exit /b 1
:incomplete
echo Project files are missing. Extract the complete ZIP before setup.
pause
exit /b 1
:done
set "JB_RESULT=%errorlevel%"
echo.
pause
exit /b %JB_RESULT%
