' Liga o robo em segundo plano (sem janela). Para desligar use parar_robo.bat
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = pasta
sh.Run """" & pasta & "\.venv\Scripts\pythonw.exe"" -m robo monitorar", 0, False
