# Explicitly target the existing native Ubuntu engine, never Docker Desktop.
$ComposeArgs = @($args)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (($ComposeArgs -contains 'up') -or ($ComposeArgs -contains 'run')) {
    $local = Join-Path $root '.local'
    New-Item -ItemType Directory -Force -Path $local | Out-Null
    $pidFile = Join-Path $local 'wsl-helper.pid'
    $existing = $null
    if (Test-Path -LiteralPath $pidFile) {
        $helperId = Get-Content -LiteralPath $pidFile
        if ($helperId -match '^\d+$') { $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$helperId" }
    }
    if (!$existing -or $existing.Name -ne 'wsl.exe' -or $existing.CommandLine -notmatch 'JARVIS_WSL_KEEPALIVE=jarvis-ai') {
        $helper = Start-Process wsl -ArgumentList @('-d','Ubuntu','--exec','/usr/bin/env',
            'JARVIS_WSL_KEEPALIVE=jarvis-ai','/usr/bin/sleep','infinity') -WindowStyle Hidden -PassThru
        $helper.Id | Set-Content -LiteralPath $pidFile
    }
}
$linuxRoot = & wsl -d Ubuntu -- wslpath -a $root.Replace('\', '/')
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve workspace in WSL' }
& wsl -d Ubuntu -u root --cd $linuxRoot.Trim() -- docker -H unix:///run/persona-docker.sock compose @ComposeArgs
exit $LASTEXITCODE
