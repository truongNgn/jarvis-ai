param([ValidateSet('init','serve','call','cancel')][string]$Action='serve',
      [string]$Tool, [string]$Arguments='{}', [switch]$AllowDesktop)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$oldPythonPath=$env:PYTHONPATH
try {
    $env:PYTHONPATH=Join-Path $root 'src'
    if($Action -eq 'init') { & python -m jarvis.security.credentials }
    elseif($Action -eq 'serve') {
        $runtimeArgs=@('-m','jarvis.runtime.client','serve','--config',(Join-Path $root 'config/runtime.example.json'))
        if($AllowDesktop) { $runtimeArgs+= '--allow-desktop' }
        & python @runtimeArgs
    }
    elseif($Action -eq 'call') { & python -m jarvis.runtime.client call $Tool --args $Arguments }
    else { & python -m jarvis.runtime.client cancel $Tool }
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH=$oldPythonPath
}
