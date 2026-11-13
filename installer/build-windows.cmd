@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if not "%OS%"=="Windows_NT" (
 echo Windows 10 or 11 is required.
 exit /b 1
)
where py >nul 2>&1
if errorlevel 1 (
 echo Python launcher missing. Install Python 3.12 64-bit.
 exit /b 1
)
py -3.12 -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
 echo Python 3.12 64-bit is required.
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 py -3.12 -m venv .venv
 if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Running offline dashboard regression tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_system_metrics.py
if errorlevel 1 exit /b 1
echo Running offline network regression tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_network_metrics.py
if errorlevel 1 exit /b 1
echo Running offline speech regression tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_speech.py
if errorlevel 1 exit /b 1
echo Running offline dictation model tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_dictation.py
if errorlevel 1 exit /b 1
echo Running offline voice command security tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_voice_commands.py
if errorlevel 1 exit /b 1
echo Running unified read-only bridge tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p test_unified_read_only.py
if errorlevel 1 exit /b 1
echo Running source and dependency preflight...
.venv\Scripts\python.exe installer\preflight.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install "pyinstaller==6.16.0"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name JARVIS-BLUE --paths . main.py
if errorlevel 1 exit /b 1
if not exist "dist\JARVIS-BLUE\JARVIS-BLUE.exe" (
 echo EXE missing. Build failed.
 exit /b 1
)
echo.
echo App bundle: dist\JARVIS-BLUE\JARVIS-BLUE.exe
where ISCC.exe >nul 2>&1
if not errorlevel 1 goto compile_on_path
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" goto compile_default
echo Inno Setup 6 not found. App bundle is ready but Setup.exe was not built.
echo Install Inno Setup 6, then compile installer\jarvis-blue.iss.
exit /b 2
:compile_on_path
ISCC.exe installer\jarvis-blue.iss
if errorlevel 1 exit /b 1
goto verify_installer
:compile_default
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\jarvis-blue.iss
if errorlevel 1 exit /b 1
:verify_installer
if not exist "dist\installer\JARVIS-BLUE-Setup.exe" (
 echo Inno Setup returned without creating the expected installer.
 exit /b 1
)
echo Installer created: dist\installer\JARVIS-BLUE-Setup.exe
exit /b 0
