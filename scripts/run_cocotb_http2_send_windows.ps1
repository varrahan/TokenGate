param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('send_windows_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')))
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_http2_send_window_vectors.py')
if($LASTEXITCODE -ne 0) { throw 'Native send-window reference generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Durable send-window regression failed' }
