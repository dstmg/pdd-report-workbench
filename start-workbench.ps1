param([switch]$NoOpen, [switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
trap {
    $failureMessage = $_.Exception.Message + "`n`nSee README.md. Logs: " + (Join-Path $env:LOCALAPPDATA 'PddReportDownloader\workbench-logs')
    if (!$NoOpen -and !$ValidateOnly) {
        try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show($failureMessage, 'PDD Workbench - Startup failed', 'OK', 'Error') | Out-Null } catch { Write-Error $failureMessage -ErrorAction Continue }
    } else { Write-Error $failureMessage -ErrorAction Continue }
    exit 1
}
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $PSScriptRoot 'scripts\serve_workbench.py'
$url = 'http://127.0.0.1:5191/'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Python environment missing. See README.md.' }
if ($ValidateOnly) { Write-Output 'Launcher paths OK'; exit 0 }
$taskMutex = New-Object System.Threading.Mutex($false, 'Local\PddWorkbenchLauncher5191')
if (!$taskMutex.WaitOne(0)) { $taskMutex.Dispose(); exit 0 }
function Test-PddWorkbench {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200 -and $response.Content -match 'PINDUODUO / WORKBENCH'
    } catch { return $false }
}
try {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 5191 -ErrorAction SilentlyContinue
    if ($listener) {
        if (!(Test-PddWorkbench)) { throw 'Port 5191 is occupied by an unknown service. No process was stopped.' }
    } else {
        $logDir = Join-Path $env:LOCALAPPDATA 'PddReportDownloader\workbench-logs'
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $taskServer = Start-Process -FilePath $pythonPath -ArgumentList ('"' + $scriptPath + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir ($stamp + '.out.log')) -RedirectStandardError (Join-Path $logDir ($stamp + '.err.log'))
        $deadline = (Get-Date).AddSeconds(20)
        while (!(Test-PddWorkbench)) {
            $taskServer.Refresh()
            if ($taskServer.HasExited -or (Get-Date) -gt $deadline) { throw ('Workbench did not become ready. Logs: ' + $logDir) }
            Start-Sleep -Milliseconds 300
        }
    }
    if (!$NoOpen) { Start-Process $url }
    Write-Output $url
} finally { $taskMutex.ReleaseMutex(); $taskMutex.Dispose() }
