param(
    [ValidateSet('icarus','verilator')][string]$Simulator='icarus',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('tokenizer_memory_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_application.py') --rtl (Join-Path $workspacePath 'rtl\parser\top\http2_bidirectional_application.v') --harness (Join-Path $workspacePath 'sim\cocotb_bidirectional_application_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Joined interface generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_application.py')
if($LASTEXITCODE -ne 0) { throw 'Separate application extraction failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_tokenizer_fpga_memory.py')
if($LASTEXITCODE -ne 0) { throw 'Tokenizer memory wiring generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_harness.py') --tokenizer-memory
if($LASTEXITCODE -ne 0) { throw 'Integrated-memory fixture generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_vectors.py') --output (Join-Path $workspacePath 'build\bidirectional-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native reference generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\verify_http2_prefill_references.py') --fixtures (Join-Path $workspacePath 'build\bidirectional-fixtures') --output (Join-Path $workspacePath 'build\bidirectional-reference-validation.json')
if($LASTEXITCODE -ne 0) { throw 'Independent wire/reference verification failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL workspace path conversion failed' }
$linuxWorkspace=$linuxWorkspace.Trim()
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace+'/scripts/run_cocotb_snapshot.py') --suite two_fpga_memory --name $SnapshotName --simulator $Simulator
if($LASTEXITCODE -ne 0) { throw 'Integrated-memory acceptance failed; see the frozen snapshot and archived reports' }
