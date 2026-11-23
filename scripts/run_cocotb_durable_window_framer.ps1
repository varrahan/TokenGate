param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('durable_framer_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')))
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
foreach($generator in @('generate_leased_stream_store.py','generate_pool_locked_store.py','generate_owned_send_windows.py','generate_lifecycle_send_windows.py','generate_durable_window_framer.py','generate_http2_send_window_vectors.py','generate_durable_framer_vectors.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') --durable-framer --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Actual durable-credit framing regression failed' }
