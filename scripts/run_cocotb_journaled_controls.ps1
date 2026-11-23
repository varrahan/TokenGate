param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('journaled_controls_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')))
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools/generate_journaled_controls.py')
if($LASTEXITCODE -ne 0) { throw 'Journal/executor generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') --journaled-controls --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Actual journaled window/ACK regression failed' }
