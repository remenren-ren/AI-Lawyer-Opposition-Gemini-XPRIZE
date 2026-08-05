Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run """C:\ProgramData\anaconda3\pythonw.exe"" ""Nido_StrikeOver_Offline_EN.py""", 0, False
