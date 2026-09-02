# ==============================================================================
# Video Converter - Windows Desktop Shortcut & Environment Setup
# ==============================================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopDir "Video Converter.lnk"
$TargetBat = Join-Path $ScriptDir "vid-gui.bat"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetBat
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "High-Quality Video Converter (WebM, MP4, MOV)"
$Shortcut.Save()
Write-Host "[*] Created Desktop Shortcut: $ShortcutPath"
