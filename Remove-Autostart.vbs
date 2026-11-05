Option Explicit
Dim shell, fso, shortcutPath
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
shortcutPath = shell.SpecialFolders("Startup") & "\Telegram Theme Maker.lnk"

If fso.FileExists(shortcutPath) Then
    fso.DeleteFile shortcutPath, True
    MsgBox "Автозапуск отключён. Уже работающий бот не остановлен.", vbInformation, "Theme Maker"
Else
    MsgBox "Ярлык автозапуска не найден. Автозапуск уже отключён.", vbInformation, "Theme Maker"
End If
