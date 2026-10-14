$ErrorActionPreference = 'Stop'
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (!$python) { throw 'Install Python 3.12 with the Windows Python launcher first.' }
$runtime = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $runtime)) {
    & py.exe -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Creating Python 3.12 environment failed.' }
}
& $runtime -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Existing files were retained.' }
Write-Output 'Environment ready. Run start-workbench.cmd. Google Chrome must be installed separately.'
