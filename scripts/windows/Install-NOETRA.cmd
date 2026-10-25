@echo off
powershell.exe -NoProfile -File "%~dp0Install-NOETRA.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not finish. Review the message above. No existing Nexa app was changed.
)
pause
