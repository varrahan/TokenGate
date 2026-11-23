param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('windowed_admission_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')))
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
foreach($generator in @('generate_windowed_rpc_admission.py','generate_cocotb_windowed_admission.py',
    'generate_http2_send_window_vectors.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') --admission --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Actual admission/window commit regression failed' }
