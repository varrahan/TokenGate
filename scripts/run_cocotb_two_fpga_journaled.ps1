param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('journaled_parser_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$ControlsOnly
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
foreach($generator in @('generate_keyed_send_windows.py','generate_windowed_rpc_admission.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
& $referencePython (Join-Path $workspacePath 'tools/generate_rpc_durable_return.py') --keyed
if($LASTEXITCODE -ne 0) { throw 'Actual keyed return generation failed' }
foreach($generator in @('generate_http2_initialized_parser.py','generate_journaled_controls.py','generate_http2_journaled_parser.py','generate_raw_journal_control_vectors.py')) {
    & $referencePython (Join-Path $workspacePath ('tools\'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Generation failed: $generator" }
}
& $referencePython (Join-Path $workspacePath 'tools/generate_two_fpga_harness.py') --tokenizer-memory --journaled-parser
if($LASTEXITCODE -ne 0) { throw 'Two-bank journaled Parser harness generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$runArguments=@('-d','Ubuntu','--','/home/varrahan/development/hardware/parser/.venv-sim/bin/python',
    ($linuxWorkspace.Trim()+'/scripts/run_cocotb_snapshot.py'),'--suite','two_fpga_journaled','--name',$SnapshotName)
if($ControlsOnly) { $runArguments+=@('--test-module','test_raw_journaled_controls') }
& wsl.exe @runArguments
if($LASTEXITCODE -ne 0) { throw 'Journaled Parser simulation failed' }
