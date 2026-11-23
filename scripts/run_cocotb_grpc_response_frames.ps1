param(
    [ValidateSet('icarus','verilator')][string]$Simulator='icarus',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('response_frames_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_grpc_response_frame_vectors.py') --output (Join-Path $workspacePath 'build\grpc-response-frame-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native gRPC/HTTP2 frame references failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL workspace path conversion failed' }
$linuxWorkspace=$linuxWorkspace.Trim()
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace+'/scripts/run_grpc_response_frames.py') --name $SnapshotName --simulator $Simulator
if($LASTEXITCODE -ne 0) { throw 'gRPC response-frame regression failed; see the frozen source archive' }
