param(
    [ValidateSet('icarus','verilator')][string]$Simulator='icarus',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('rpc_durable_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$Keyed
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
foreach($generator in @('generate_rpc_grpc_parser_response.py','generate_leased_stream_store.py',
    'generate_rpc_grpc_leased_return.py','generate_pool_locked_store.py','generate_owned_send_windows.py',
    'generate_lifecycle_send_windows.py','generate_durable_window_framer.py','generate_rpc_durable_return.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
$suiteName=if($Keyed){'rpc_keyed'}else{'rpc_durable'}
if($Keyed) {
    & $referencePython (Join-Path $workspacePath 'tools\generate_keyed_send_windows.py')
    if($LASTEXITCODE -ne 0) { throw 'Keyed window generation failed' }
    & $referencePython (Join-Path $workspacePath 'tools\generate_rpc_durable_return.py') --keyed
    if($LASTEXITCODE -ne 0) { throw 'Keyed RPC generation failed' }
}
$harnessArguments=@('--output',(Join-Path $workspacePath 'sim\cocotb_rpc_durable_top.sv'))
& $referencePython (Join-Path $workspacePath 'tools\generate_cocotb_rpc_durable_harness.py') @harnessArguments
if($LASTEXITCODE -ne 0) { throw 'RPC durable harness generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_rpc_grpc_vectors.py') --output (Join-Path $workspacePath 'build\rpc-grpc-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native RPC/framing fixture generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_cocotb_snapshot.py') --suite $suiteName --name $SnapshotName --simulator $Simulator
if($LASTEXITCODE -ne 0) { throw 'Actual progress-authorized durable RPC regression failed' }
