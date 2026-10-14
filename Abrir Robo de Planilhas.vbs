' =====================================================================
'  Abre o Robo de Planilhas: liga o robo e mostra o painel numa janela.
'  Se ja estiver aberto, apenas mostra a janela de novo.
'  Com o argumento /oculto (usado na inicializacao do Windows) so liga o robo,
'  sem abrir janela.
' =====================================================================
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = pasta

pythonw = pasta & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
  MsgBox "O robo ainda nao foi instalado." & vbCrLf & vbCrLf & _
         "De dois cliques em instalar.bat (na pasta " & pasta & ") e tente de novo.", 48, "Robo de Planilhas"
  WScript.Quit 1
End If

argumentos = " -m robo app"
If WScript.Arguments.Count > 0 Then
  If LCase(WScript.Arguments(0)) = "/oculto" Then argumentos = argumentos & " --sem-janela"
End If

sh.Run """" & pythonw & """" & argumentos, 0, False
