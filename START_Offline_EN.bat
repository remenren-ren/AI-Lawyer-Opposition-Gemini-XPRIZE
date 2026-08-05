@echo off
cd /d "%~dp0"
if exist "C:\ProgramData\anaconda3\pythonw.exe" (
  start "" "C:\ProgramData\anaconda3\pythonw.exe" "Nido_StrikeOver_Offline_EN.py"
) else (
  start "" /b pythonw "Nido_StrikeOver_Offline_EN.py"
)
exit /b
pause
