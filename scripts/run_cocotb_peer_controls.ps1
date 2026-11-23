param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('peer_controls_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$StateOnly
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
if(-not $StateOnly) {
    & (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools/generate_peer_controls.py')
    if($LASTEXITCODE -ne 0) { throw 'Peer-control generation failed' }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$suiteFlag=if($StateOnly) {'--peer-state'} else {'--peer-controls'}
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') $suiteFlag --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Actual peer-state regression failed' }
