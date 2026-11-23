param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('rpc_cancel_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$Directed
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
foreach($generator in @('generate_cancel_send_windows.py','generate_cancellable_frame_arbiter.py',
    'generate_fenced_frame_grants.py','generate_registered_input_framer.py','generate_pipelined_cancel_framer.py',
    'generate_rpc_cancel_return.py')) {
    & (Join-Path $workspacePath '.venv312/Scripts/python.exe') (Join-Path $workspacePath ('tools/'+$generator))
    if($LASTEXITCODE -ne 0) { throw "RPC cancellation generation failed: $generator" }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$arguments=@(($linuxWorkspace.Trim()+'/scripts/run_rpc_cancel_tests.py'),'--name',$SnapshotName)
if($Directed) { $arguments+='--directed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python @arguments
if($LASTEXITCODE -ne 0) { throw 'Actual RPC cancellation regression failed' }
