param(
    [ValidateSet('icarus','verilator')][string]$Simulator='icarus',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('full_controls_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_application.py') --rtl (Join-Path $workspacePath 'rtl\parser\top\http2_bidirectional_application.v') --harness (Join-Path $workspacePath 'sim\cocotb_bidirectional_application_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Baseline interface generation failed' }
foreach($generator in @('generate_two_fpga_application.py','generate_tokenizer_fpga_memory.py',
    'generate_rpc_grpc_parser_response.py','generate_leased_stream_store.py',
    'generate_rpc_grpc_leased_return.py','generate_controlled_hpack.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
& $referencePython (Join-Path $workspacePath 'tools\generate_http2_framed_parser.py') --control-fork
if($LASTEXITCODE -ne 0) { throw 'Full-control Parser wiring failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_harness.py') --tokenizer-memory --controlled-parser
if($LASTEXITCODE -ne 0) { throw 'Full-control two-FPGA fixture wiring failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_vectors.py') --output (Join-Path $workspacePath 'build\bidirectional-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native bidirectional references failed' }
& $referencePython (Join-Path $workspacePath 'tools\verify_http2_prefill_references.py') --fixtures (Join-Path $workspacePath 'build\bidirectional-fixtures') --output (Join-Path $workspacePath 'build\bidirectional-reference-validation.json')
if($LASTEXITCODE -ne 0) { throw 'Independent wire/reference verification failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_framed_vectors.py')
if($LASTEXITCODE -ne 0) { throw 'Native framed-return references failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL workspace path conversion failed' }
$linuxWorkspace=$linuxWorkspace.Trim()
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace+'/scripts/run_cocotb_snapshot.py') --suite two_fpga_controlled --name $SnapshotName --simulator $Simulator
if($LASTEXITCODE -ne 0) { throw 'Full-control two-FPGA regression failed; see its immutable snapshot and archived reports' }
