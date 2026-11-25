@echo off
setlocal
call "%~dp0START_JARVIS.cmd" %*
exit /b %errorlevel%
