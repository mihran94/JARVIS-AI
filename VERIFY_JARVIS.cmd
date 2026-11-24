@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo FAIL: Python environment not found. Run setup.cmd first.
  exit /b 1
)
"%PY%" scripts\verify_windows.py %*
exit /b %errorlevel%
