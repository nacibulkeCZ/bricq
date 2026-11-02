@echo off
powershell.exe -NoProfile -File "%~dp0bricq-cli.ps1" %*
exit /b %errorlevel%
