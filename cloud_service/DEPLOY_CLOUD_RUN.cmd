@echo off
cd /d "%~dp0"
title AI Lawyer Opposition - Deploy Cloud Run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0DEPLOY_CLOUD_RUN.ps1"
echo.
if errorlevel 1 (
  echo Deployment did not complete. Review the error above.
) else (
  echo Deployment finished successfully.
)
echo.
set /p NIDO_CLOSE_PROMPT=Press Enter to close this deployment window...
