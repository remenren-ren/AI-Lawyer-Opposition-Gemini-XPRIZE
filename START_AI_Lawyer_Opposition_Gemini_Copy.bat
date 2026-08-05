@echo off
cd /d "%~dp0"
if exist "C:\Program Files\Python310\pythonw.exe" (
  start "" "C:\Program Files\Python310\pythonw.exe" "ai_law_firm_reception_launcher.py"
) else if exist "C:\ProgramData\anaconda3\pythonw.exe" (
  start "" "C:\ProgramData\anaconda3\pythonw.exe" "ai_law_firm_reception_launcher.py"
) else (
  start "" /b pythonw "ai_law_firm_reception_launcher.py"
)
exit /b
