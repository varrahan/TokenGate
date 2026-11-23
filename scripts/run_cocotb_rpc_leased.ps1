param(
    [ValidateSet('icarus','verilator')][string]$Simulator='icarus',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('rpc_leased_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
$generators=@(
    'generate_two_fpga_application.py',
    'generate_rpc_grpc_parser_response.py',
    'generate_leased_stream_store.py',
    'generate_rpc_grpc_leased_return.py'
)
foreach($generator in $generators) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
& $referencePython (Join-Path $workspacePath 'tools\generate_cocotb_rpc_leased_harness.py') --output (Join-Path $workspacePath 'sim\cocotb_rpc_leased_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Leased return fixture wiring failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_rpc_grpc_vectors.py') --output (Join-Path $workspacePath 'build\rpc-grpc-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native framed RPC references failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL workspace path conversion failed' }
$linuxWorkspace=$linuxWorkspace.Trim()
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace+'/scripts/run_cocotb_snapshot.py') --suite rpc_leased --name $SnapshotName --simulator $Simulator
if($LASTEXITCODE -ne 0) { throw 'Leased RPC return regression failed; see the frozen snapshot and reports' }
