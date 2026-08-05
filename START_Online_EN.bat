@echo off
cd /d "%~dp0"
if exist "C:\Program Files\Python310\pythonw.exe" (
  start "" "C:\Program Files\Python310\pythonw.exe" "Nido_StrikeOver_Online_EN.py"
) else if exist "C:\ProgramData\anaconda3\pythonw.exe" (
  start "" "C:\ProgramData\anaconda3\pythonw.exe" "Nido_StrikeOver_Online_EN.py"
) else (
  start "" /b pythonw "Nido_StrikeOver_Online_EN.py"
)
exit /b
pause
