# Explicitly target the existing native Ubuntu engine, never Docker Desktop.
$ComposeArgs = @($args)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$linuxRoot = & wsl -d Ubuntu -- wslpath -a $root.Replace('\', '/')
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve workspace in WSL' }
& wsl -d Ubuntu -u root --cd $linuxRoot.Trim() -- docker -H unix:///run/persona-docker.sock compose @ComposeArgs
exit $LASTEXITCODE
