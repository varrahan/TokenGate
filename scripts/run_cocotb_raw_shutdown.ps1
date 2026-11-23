param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('raw_shutdown_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [ValidateSet('Directed','Faults','Full')][string]$Mode='Directed'
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$pythonPath=Join-Path $workspacePath '.venv312/Scripts/python.exe'
foreach($generator in @('generate_http2_shutdown_controls.py','generate_http2_shutdown_parser.py','generate_shutdown_vectors.py')) {
    & $pythonPath (Join-Path $workspacePath ('tools/'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Raw shutdown generation failed: $generator" }
}
& $pythonPath (Join-Path $workspacePath 'tools/generate_two_fpga_harness.py') --shutdown-parser --tokenizer-memory
if($LASTEXITCODE -ne 0) { throw 'Raw shutdown passive harness generation failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$arguments=@(($linuxWorkspace.Trim()+'/scripts/run_cocotb_snapshot.py'),'--suite','two_fpga_shutdown','--name',$SnapshotName)
if($Mode -eq 'Directed') { $arguments+=@('--test-module','test_raw_shutdown_controls') }
if($Mode -eq 'Faults') { $arguments+=@('--test-module','test_raw_shutdown_faults') }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python @arguments
if($LASTEXITCODE -ne 0) { throw 'Raw shutdown simulation failed' }
