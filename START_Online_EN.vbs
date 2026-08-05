Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run """C:\Program Files\Python310\pythonw.exe"" ""Nido_StrikeOver_Online_EN.py""", 0, False
