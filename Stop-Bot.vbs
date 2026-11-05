Option Explicit
Dim shell, fso, projectDir, runnerPath, service, processes, process
Dim found, result
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
runnerPath = LCase(projectDir & "\BackgroundRunner.py")
Set service = GetObject("winmgmts:\\.\root\cimv2")
Set processes = service.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe'")
found = False

For Each process In processes
    If Not IsNull(process.CommandLine) Then
        If InStr(1, LCase(CStr(process.CommandLine)), runnerPath, vbTextCompare) > 0 Then
            result = process.Terminate()
            If result = 0 Then found = True
        End If
    End If
Next

If found Then
    MsgBox "Фоновый процесс Theme Maker остановлен.", vbInformation, "Theme Maker"
Else
    MsgBox "Работающий фоновый процесс Theme Maker не найден.", vbInformation, "Theme Maker"
End If
