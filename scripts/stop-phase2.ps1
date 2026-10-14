# Stop only JARVIS services/helpers whose identity matches our recorded PID.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$runtimeFile=Join-Path $root '.local/runtime.pid'
if(Test-Path -LiteralPath $runtimeFile) {
    $runtimeId=Get-Content -LiteralPath $runtimeFile
    if($runtimeId -match '^\d+$') {
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$runtimeId"
        if($process -and $process.Name -eq 'python.exe' -and $process.CommandLine -match 'jarvis.runtime.client.*serve') {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$runtimeId" |
                Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'jarvis.runtime.worker' } |
                ForEach-Object { Stop-Process -Id $_.ProcessId }
            Stop-Process -Id $runtimeId
        }
    }
}
& (Join-Path $PSScriptRoot 'wsl-compose.ps1') --profile desktop stop broker
$helperFile=Join-Path $root '.local/wsl-helper.pid'
if(Test-Path -LiteralPath $helperFile) {
    $helperId=Get-Content -LiteralPath $helperFile
    if($helperId -match '^\d+$') {
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$helperId"
        if($process -and $process.Name -eq 'wsl.exe' -and $process.CommandLine -match 'JARVIS_WSL_KEEPALIVE=jarvis-ai') {
            Stop-Process -Id $helperId
        }
    }
}
