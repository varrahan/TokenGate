param([ValidateSet('icarus','verilator')][string]$Simulator='icarus')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_cocotb_rpc_response_harness.py') --output (Join-Path $workspacePath 'sim\cocotb_rpc_response_top.sv')
if($LASTEXITCODE -ne 0) { throw 'RPC response harness generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_rpc_response_vectors.py') --output (Join-Path $workspacePath 'build\rpc-response-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native RPC response references failed' }
$linuxWorkspace='/mnt/c/Users/varra/OneDrive/Documents/ChatGPT/Protobuf SerDes + Tokenizer'
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/sync_wsl_workspace.py') --fixture rpc-response-fixtures
if($LASTEXITCODE -ne 0) { throw 'WSL RPC response synchronization failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python /home/varrahan/development/hardware/parser/scripts/run_cocotb.py rpc_response --simulator $Simulator
$simulationExit=$LASTEXITCODE
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/collect_cocotb_reports.py') rpc_response
if($LASTEXITCODE -ne 0) { throw 'RPC response report archive failed' }
if($simulationExit -ne 0) { throw 'RPC response acceptance failed; see archived reports' }
