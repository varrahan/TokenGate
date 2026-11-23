param([ValidateSet('icarus','verilator')][string]$Simulator='icarus')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_application.py') --rtl (Join-Path $workspacePath 'rtl\parser\top\http2_bidirectional_application.v') --harness (Join-Path $workspacePath 'sim\cocotb_bidirectional_application_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Joined baseline generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_application.py')
if($LASTEXITCODE -ne 0) { throw 'Separate application extraction failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_two_fpga_harness.py')
if($LASTEXITCODE -ne 0) { throw 'Separate-memory fixture wiring failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_vectors.py') --output (Join-Path $workspacePath 'build\bidirectional-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native references failed' }
& $referencePython (Join-Path $workspacePath 'tools\verify_http2_prefill_references.py') --fixtures (Join-Path $workspacePath 'build\bidirectional-fixtures') --output (Join-Path $workspacePath 'build\bidirectional-reference-validation.json')
if($LASTEXITCODE -ne 0) { throw 'Independent wire/reference verification failed' }
$linuxWorkspace='/mnt/c/Users/varra/OneDrive/Documents/ChatGPT/Protobuf SerDes + Tokenizer'
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/sync_wsl_workspace.py') --fixture bidirectional-fixtures
if($LASTEXITCODE -ne 0) { throw 'WSL synchronization failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python /home/varrahan/development/hardware/parser/scripts/run_cocotb.py two_fpga --simulator $Simulator
$simulationExit=$LASTEXITCODE
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/collect_cocotb_reports.py') two_fpga
if($LASTEXITCODE -ne 0) { throw 'Separate application report archive failed' }
if($simulationExit -ne 0) { throw 'Separate application acceptance failed; see archived reports' }
