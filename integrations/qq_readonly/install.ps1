$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Here '.venv'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $Venv
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv $Venv
} else {
    throw 'Install Python 3.11 or newer first.'
}
$VenvPython = Join-Path $Here '.venv\Scripts\python.exe'
& $VenvPython -m pip install -r (Join-Path $Here 'requirements.txt')

$Settings = Join-Path $Here 'settings.json'
if (-not (Test-Path $Settings)) {
    Copy-Item (Join-Path $Here 'settings.example.json') $Settings
}

Write-Host ''
Write-Host 'Dependencies installed. Next steps:'
Write-Host "1. Edit $Settings with the NapCat token and human-approved chats."
Write-Host '2. Enable NapCat OneBot HTTP at 127.0.0.1:3033.'
Write-Host '3. Add the mcp_servers.qq_readonly block from README.md to Codex, then restart Codex.'
