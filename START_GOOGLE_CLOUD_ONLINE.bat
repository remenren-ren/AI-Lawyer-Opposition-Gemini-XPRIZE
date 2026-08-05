@echo off
cd /d "%~dp0"
if exist "C:\Program Files\Python310\pythonw.exe" (
  start "" "C:\Program Files\Python310\pythonw.exe" "Google_Cloud_Online_Launcher.py"
) else if exist "C:\ProgramData\anaconda3\pythonw.exe" (
  start "" "C:\ProgramData\anaconda3\pythonw.exe" "Google_Cloud_Online_Launcher.py"
) else (
  start "" /b pythonw "Google_Cloud_Online_Launcher.py"
)
exit /b
