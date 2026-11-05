Option Explicit
Dim shell, fso, projectDir, pythonw, runner, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"
runner = projectDir & "\BackgroundRunner.py"

If Not fso.FileExists(pythonw) Or Not fso.FileExists(runner) Then
    WScript.Quit 2
End If

command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & runner & Chr(34)
shell.CurrentDirectory = projectDir
shell.Run command, 0, False
