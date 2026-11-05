Option Explicit
Dim shell, fso, projectDir, pythonw, runner, command, logDir, logPath

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"
runner = projectDir & "\BackgroundRunner.py"
logDir = projectDir & "\logs"
logPath = logDir & "\autostart.log"

If Not fso.FolderExists(logDir) Then
    On Error Resume Next
    fso.CreateFolder(logDir)
    On Error GoTo 0
End If

' Keep this script ASCII-only: Windows Script Host may misread UTF-8
' source files without a Unicode signature.
WriteLog "RunHidden.vbs was started."

If Not fso.FileExists(pythonw) Then
    WriteLog "ERROR: .venv\Scripts\pythonw.exe was not found."
    WScript.Quit 2
End If

If Not fso.FileExists(runner) Then
    WriteLog "ERROR: BackgroundRunner.py was not found."
    WScript.Quit 2
End If

command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & runner & Chr(34)
shell.CurrentDirectory = projectDir

' Give Windows a moment to finish signing in and initialize the network.
WScript.Sleep 8000

On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    WriteLog "ERROR starting pythonw.exe: " & Err.Description
    Err.Clear
Else
    WriteLog "Background process launch command was sent."
End If
On Error GoTo 0

Sub WriteLog(message)
    On Error Resume Next
    Dim stream
    Set stream = fso.OpenTextFile(logPath, 8, True, -1)
    If Err.Number = 0 Then
        stream.WriteLine Now & " | " & message
        stream.Close
    End If
    Err.Clear
    On Error GoTo 0
End Sub
