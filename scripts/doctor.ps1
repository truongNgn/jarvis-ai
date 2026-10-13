# Read-only Phase 0 check. Does not start Docker, install libraries, or download models.
param([int]$TimeoutSeconds = 20)
$ErrorActionPreference = 'Stop'
$computer = Get-CimInstance Win32_ComputerSystem
$report = [ordered]@{
    machine = $computer.Model
    ramBytes = $computer.TotalPhysicalMemory
    vscodePresent = Test-Path 'C:\Users\nguye\AppData\Local\Programs\Microsoft VS Code\Code.exe'
    dockerCliPresent = [bool](Get-Command docker -ErrorAction SilentlyContinue)
    wslPresent = [bool](Get-Command wsl -ErrorAction SilentlyContinue)
}
if ($report.wslPresent) {
    $probe = Start-Job {
        & wsl -d Ubuntu -u root -- bash -lc 'uname -r; docker -H unix:///run/persona-docker.sock version --format "{{.Server.Version}}"; docker -H unix:///run/persona-docker.sock compose version; nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv'
        if ($LASTEXITCODE -ne 0) { throw 'WSL infrastructure probe failed' }
    }
    try {
        $finished = Wait-Job $probe -Timeout $TimeoutSeconds
        if ($finished) {
            $report.infrastructure = @(Receive-Job $probe -ErrorAction Stop | ForEach-Object { "$_" })
            $report.probeStatus = 'passed'
        } else {
            $report.probeStatus = 'timeout'
        }
    } catch {
        $report.probeStatus = 'failed'
        $report.error = $_.Exception.Message
    } finally {
        if ($probe.State -eq 'Running') { Stop-Job $probe }
        Remove-Job $probe
    }
}
$report | ConvertTo-Json -Depth 4
if ($report.probeStatus -ne 'passed') { exit 1 }
