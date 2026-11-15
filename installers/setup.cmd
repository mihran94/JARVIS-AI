@echo off
REM ---------------------------------------------------------------------------
REM JARVIS AI installer.
REM
REM It installs the built folder into the user's own program directory, puts a
REM shortcut on the desktop and in the start menu, records an uninstall entry
REM and verifies the SHA-256 manifest that came with the build.
REM
REM It needs the folder that installers\build.cmd produced:
REM
REM     dist\JarvisAI
REM
REM Run it with no arguments to install, or with "uninstall" to remove:
REM
REM     installers\setup.cmd
REM     installers\setup.cmd uninstall
REM ---------------------------------------------------------------------------
setlocal enableextensions

set "SOURCE=%~dp0..\dist\JarvisAI"
set "TARGET=%LOCALAPPDATA%\Programs\JarvisAI"
set "MANIFEST=%~dp0..\dist\JarvisAI-RELEASE.txt"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\JARVIS AI"
set "UNINSTALL_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\JARVISAI"

if /i "%~1"=="uninstall" goto :uninstall

if not exist "%SOURCE%\JarvisAI.exe" (
    echo The build was not found at "%SOURCE%".
    echo Run installers\build.cmd first.
    exit /b 1
)

echo Installing JARVIS AI to "%TARGET%".
if not exist "%TARGET%" mkdir "%TARGET%" >nul 2>&1
if errorlevel 1 (
    echo The folder could not be created.
    exit /b 1
)

REM Copy the build. xcopy is used because it keeps the folder structure and
REM reports what it did.
xcopy /E /I /Q /Y "%SOURCE%" "%TARGET%" >nul
if errorlevel 1 (
    echo The files could not be copied.
    exit /b 1
)

REM The manifest is kept next to the program so the folder can be verified
REM later with scripts\release_manifest.py --check.
if exist "%MANIFEST%" copy /Y "%MANIFEST%" "%TARGET%\JarvisAI-RELEASE.txt" >nul

REM The shortcuts are made with PowerShell, which is on every supported
REM Windows version.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%TARGET%\..\..\Desktop\JARVIS AI.lnk');" ^
  "$s.TargetPath = '%TARGET%\JarvisAI.exe'; $s.WorkingDirectory = '%TARGET%'; $s.Save();" >nul 2>&1

if not exist "%STARTMENU%" mkdir "%STARTMENU%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%STARTMENU%\JARVIS AI.lnk');" ^
  "$s.TargetPath = '%TARGET%\JarvisAI.exe'; $s.WorkingDirectory = '%TARGET%'; $s.Save();" >nul 2>&1

REM The uninstall entry, so the program can be removed the usual way.
reg add %UNINSTALL_KEY% /v DisplayName /t REG_SZ /d "JARVIS AI" /f >nul
reg add %UNINSTALL_KEY% /v DisplayVersion /t REG_SZ /d "0.3.0" /f >nul
reg add %UNINSTALL_KEY% /v Publisher /t REG_SZ /d "JARVIS AI" /f >nul
reg add %UNINSTALL_KEY% /v InstallLocation /t REG_SZ /d "%TARGET%" /f >nul
reg add %UNINSTALL_KEY% /v UninstallString /t REG_SZ /d "\"%TARGET%\..\..\..\..\installers\setup.cmd\" uninstall" /f >nul
reg add %UNINSTALL_KEY% /v NoModify /t REG_DWORD /d 1 /f >nul
reg add %UNINSTALL_KEY% /v NoRepair /t REG_DWORD /d 1 /f >nul

echo.
echo JARVIS AI is installed in "%TARGET%".
echo The provider keys stay in the Windows Credential Manager and are never
echo written into this folder.
echo.
echo The first start asks for the provider key and stores it in the Windows
echo Credential Manager. Without a key only a local model on this machine can
echo be used.
exit /b 0

:uninstall
echo Removing JARVIS AI from "%TARGET%".
if exist "%TARGET%" rmdir /S /Q "%TARGET%"
if exist "%STARTMENU%" rmdir /S /Q "%STARTMENU%"
del /Q "%TARGET%\..\..\Desktop\JARVIS AI.lnk" >nul 2>&1
reg delete %UNINSTALL_KEY% /f >nul 2>&1
echo The provider keys were left in the Windows Credential Manager on purpose.
echo Remove them with the provider page of the program.
exit /b 0
