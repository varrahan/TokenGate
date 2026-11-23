param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('rpc_envelope_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$Raw,
    [ValidateSet('native','shutdown-faults','return-faults','workload','duplex','duplex-faults','receive-flow')][string]$Profile='native'
)
$ErrorActionPreference='Stop'
if(-not $Raw -and $Profile -ne 'native') { throw 'Raw test profiles require -Raw' }
$workspacePath=Split-Path -Parent $PSScriptRoot
$pythonPath=Join-Path $workspacePath '.venv312/Scripts/python.exe'
foreach($generator in @('generate_grpc_header_vectors.py','generate_rpc_http2_progress.py','generate_rpc_http2_return.py')) {
    & $pythonPath (Join-Path $workspacePath ('tools/'+$generator))
    if($LASTEXITCODE -ne 0) { throw "RPC envelope generation failed: $generator" }
}
if($Raw) {
    & $pythonPath (Join-Path $workspacePath 'tools/generate_http2_enveloped_parser.py')
    if($LASTEXITCODE -ne 0) { throw 'Raw envelope generation failed' }
    & $pythonPath (Join-Path $workspacePath 'tools/generate_two_fpga_harness.py') --enveloped-parser --tokenizer-memory
    if($LASTEXITCODE -ne 0) { throw 'Passive two-FPGA envelope harness generation failed' }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$runner=if($Raw){'run_raw_envelope_tests.py'}else{'run_rpc_http2_tests.py'}
$runnerArguments=@(($linuxWorkspace.Trim()+'/scripts/'+$runner),'--name',$SnapshotName)
if($Raw) { $runnerArguments+=@('--profile',$Profile) }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python @runnerArguments
if($LASTEXITCODE -ne 0) { throw 'Actual RPC envelope regression failed' }
