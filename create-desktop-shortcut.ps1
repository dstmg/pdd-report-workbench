param([string]$DesktopDirectory)
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot 'start-workbench.ps1'
if (!(Test-Path -LiteralPath $launcher)) { throw 'Workbench launcher missing.' }
if (!$DesktopDirectory) { $DesktopDirectory = [Environment]::GetFolderPath('DesktopDirectory') }
if (!(Test-Path -LiteralPath $DesktopDirectory -PathType Container)) { throw 'Desktop directory unavailable.' }
$shortcutPath = Join-Path $DesktopDirectory 'PDD Workbench.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
if (Test-Path -LiteralPath $shortcutPath) {
    if ($shortcut.TargetPath -ne $powershellPath -or $shortcut.Arguments -ne $arguments) {
        throw 'A different PDD Workbench shortcut already exists. Rename it before creating this shortcut.'
    }
}
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Launch Pinduoduo local report workbench'
$shortcut.IconLocation = $powershellPath + ',0'
$shortcut.Save()
Write-Output 'Desktop shortcut ready: PDD Workbench'
