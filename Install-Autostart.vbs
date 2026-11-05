Option Explicit
Dim shell, fso, projectDir, pythonw, runner, envFile, startupDir
Dim shortcutPath, shortcut, target
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"
runner = projectDir & "\BackgroundRunner.py"
envFile = projectDir & "\.env"

If Not fso.FileExists(pythonw) Or Not fso.FileExists(runner) Or Not fso.FileExists(envFile) Then
    MsgBox "Сначала один раз настрой и успешно запусти бота через Start.bat." & vbCrLf & _
           "После этого снова открой Install-Autostart.vbs.", vbExclamation, "Theme Maker — автозапуск"
    WScript.Quit 1
End If

startupDir = shell.SpecialFolders("Startup")
shortcutPath = startupDir & "\Telegram Theme Maker.lnk"
target = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\wscript.exe"
Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = target
shortcut.Arguments = Chr(34) & projectDir & "\RunHidden.vbs" & Chr(34)
shortcut.WorkingDirectory = projectDir
shortcut.Description = "Запуск Telegram Theme Maker после входа в Windows"
shortcut.Save

' Start it now as well, so the user does not need to restart Windows to test it.
shell.Run Chr(34) & projectDir & "\RunHidden.vbs" & Chr(34), 0, False

MsgBox "Автозапуск настроен. Theme Maker запускается в фоне сейчас и будет запускаться после входа в Windows." & vbCrLf & vbCrLf & _
       "Окна CMD не будет." & vbCrLf & _
       "Лог запуска и ошибок: папка logs\bot.log внутри проекта." & vbCrLf & vbCrLf & _
       "Остановить бота: Stop-Bot.vbs. Отключить автозапуск: Remove-Autostart.vbs.", _
       vbInformation, "Theme Maker — автозапуск"
