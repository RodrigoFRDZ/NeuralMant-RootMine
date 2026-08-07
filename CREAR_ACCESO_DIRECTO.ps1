$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Join-Path $Project "INICIAR_ROOTMINE.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "NeuralMant - RootMine.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $Project
$Shortcut.Description = "Abrir NeuralMant RootMine"
$Shortcut.Save()
Write-Host "Acceso directo creado en el Escritorio."
Pause
