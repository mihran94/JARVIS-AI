@echo off
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "PY_CHECK=import struct, sys; sys.exit(not (sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8))"
if exist "%PY%" goto check_venv
py -3.12-64 -c "%PY_CHECK%" >nul 2>&1
if errorlevel 1 goto try_path
py -3.12-64 -m venv .venv
if errorlevel 1 goto venv_failed
goto check_venv

:try_path
python -c "%PY_CHECK%" >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 64-bit is required. Install it and enable the Python launcher or add Python to PATH.
  exit /b 1
)
python -m venv .venv
if errorlevel 1 goto venv_failed

:check_venv
"%PY%" -c "%PY_CHECK%" >nul 2>&1
if errorlevel 1 goto venv_failed
"%PY%" -m pip install -r requirements.txt pythonnet==3.2.1 pywin32==312
if errorlevel 1 (
  echo Dependency installation failed. Check the pip error above and rerun setup.cmd.
  exit /b 1
)
echo Setup complete.
echo To open JARVIS M, run START_JARVIS_M.cmd
exit /b 0

:venv_failed
echo Could not use .venv with Python 3.12 64-bit. Fix the Python installation or rename the existing .venv and retry.
exit /b 1
