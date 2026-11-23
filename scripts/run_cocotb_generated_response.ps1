param([ValidateSet('icarus','verilator')][string]$Simulator='icarus')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_cocotb_response_harness.py') --output (Join-Path $workspacePath 'sim\cocotb_generated_response_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Cocotb response harness generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_token_response_vectors.py') --output (Join-Path $workspacePath 'build\generated-response-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native response fixture generation failed' }
$linuxWorkspace='/mnt/c/Users/varra/OneDrive/Documents/ChatGPT/Protobuf SerDes + Tokenizer'
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/sync_wsl_workspace.py') --fixture generated-response-fixtures
if($LASTEXITCODE -ne 0) { throw 'WSL response source/fixture synchronization failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python /home/varrahan/development/hardware/parser/scripts/run_cocotb.py generated_response --simulator $Simulator
$simulationExit=$LASTEXITCODE
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/collect_cocotb_reports.py') generated_response
if($LASTEXITCODE -ne 0) { throw 'Cocotb response report archive failed' }
if($simulationExit -ne 0) { throw 'Generated-token response acceptance failed; see the archived report/log' }
