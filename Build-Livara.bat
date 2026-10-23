@echo off
setlocal
where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo Windows PowerShell 5.1 or later is required.
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Livara.ps1" %*
set "livara_result=%ERRORLEVEL%"
if "%~1"=="" (
  if not defined LIVARA_NO_PAUSE pause
)
exit /b %livara_result%
