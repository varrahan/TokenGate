param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('initialized_parser_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$BootstrapOnly
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
& $referencePython (Join-Path $workspacePath 'tools/generate_http2_initialized_parser.py')
if($LASTEXITCODE -ne 0) { throw 'Actual initialized Parser generation failed' }
& $referencePython (Join-Path $workspacePath 'tools/generate_two_fpga_harness.py') --tokenizer-memory --initialized-parser
if($LASTEXITCODE -ne 0) { throw 'Two-bank initialized Parser harness generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$runArguments=@('-d','Ubuntu','--','/home/varrahan/development/hardware/parser/.venv-sim/bin/python',
    ($linuxWorkspace.Trim()+'/scripts/run_cocotb_snapshot.py'),'--suite','two_fpga_initialized','--name',$SnapshotName)
if($BootstrapOnly) { $runArguments+=@('--test-module','test_two_fpga_bootstrap') }
& wsl.exe @runArguments
if($LASTEXITCODE -ne 0) { throw 'Initialized Parser simulation failed' }
