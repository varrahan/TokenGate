param([ValidateSet('icarus','verilator')][string]$Simulator='icarus')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_application.py') --rtl (Join-Path $workspacePath 'rtl\http2_bidirectional_application.v') --harness (Join-Path $workspacePath 'sim\cocotb_bidirectional_application_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Joint application interface generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_bidirectional_vectors.py') --output (Join-Path $workspacePath 'build\bidirectional-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Joint native reference generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\verify_http2_prefill_references.py') --fixtures (Join-Path $workspacePath 'build\bidirectional-fixtures') --output (Join-Path $workspacePath 'build\bidirectional-reference-validation.json')
if($LASTEXITCODE -ne 0) { throw 'Independent raw wire/reference validation failed' }
$linuxWorkspace='/mnt/c/Users/varra/OneDrive/Documents/ChatGPT/Protobuf SerDes + Tokenizer'
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/sync_wsl_workspace.py') --fixture bidirectional-fixtures
if($LASTEXITCODE -ne 0) { throw 'Joint WSL synchronization failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python /home/varrahan/development/hardware/parser/scripts/run_cocotb.py bidirectional --simulator $Simulator
$simulationExit=$LASTEXITCODE
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/collect_cocotb_reports.py') bidirectional
if($LASTEXITCODE -ne 0) { throw 'Joint report archive failed' }
if($simulationExit -ne 0) { throw 'Joint application acceptance failed; see archived reports' }
