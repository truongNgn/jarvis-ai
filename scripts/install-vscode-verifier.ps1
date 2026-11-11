$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& python (Join-Path $PSScriptRoot 'package_vscode_verifier.py')
if ($LASTEXITCODE -ne 0) { throw 'Verifier packaging failed' }
& "$env:LOCALAPPDATA/Programs/Microsoft VS Code/bin/code.cmd" --install-extension (Join-Path $root '.local/workspace-verifier.vsix')
if ($LASTEXITCODE -ne 0) { throw 'Verifier installation failed' }
