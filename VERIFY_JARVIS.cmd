@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
echo JARVIS AI - offline Windows verification
echo Close any running JARVIS app before this check.
echo This script does not trigger GitHub Actions or request an AI response.
echo It uses a temporary data folder for the UI smoke test.
echo.
if not exist "%PY%" (
  echo FAIL: Python environment not found. Run setup.cmd first.
  goto failed
)
echo [1/3] Checking installed runtime and Qt imports...
"%PY%" scripts\diagnose.py
if errorlevel 1 goto failed
echo.
echo [2/3] Starting short offline UI smoke test...
set "JARVIS_CHECK_HOME=%TEMP%\Jarvis-Offline-Check-%RANDOM%-%RANDOM%"
mkdir "%JARVIS_CHECK_HOME%" >nul 2>&1
if not exist "%JARVIS_CHECK_HOME%" goto failed
set "LOCALAPPDATA=%JARVIS_CHECK_HOME%"
set "QT_QPA_PLATFORM=offscreen"
"%PY%" main.py --smoke-test
if errorlevel 1 goto failed
echo.
echo [3/3] Checking for local pytest installation...
"%PY%" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pytest') else 1)"
if errorlevel 1 (
  echo SKIP: pytest not installed. Install requirements-dev.txt separately to run UI tests.
) else (
  "%PY%" -m pytest -q tests/test_omega.py tests/test_mark_lvii_assistant.py
  if errorlevel 1 goto failed
)
echo.
echo OFFLINE CHECKS COMPLETE. Real microphone, AI account, and phone pairing still need manual tests.
if defined JARVIS_CHECK_HOME if exist "%JARVIS_CHECK_HOME%" rmdir /s /q "%JARVIS_CHECK_HOME%" >nul 2>&1
pause
exit /b 0
:failed
echo.
echo LOCAL VERIFICATION FAILED. Copy the output above, excluding personal data, for diagnosis.
if defined JARVIS_CHECK_HOME if exist "%JARVIS_CHECK_HOME%" rmdir /s /q "%JARVIS_CHECK_HOME%" >nul 2>&1
pause
exit /b 1
