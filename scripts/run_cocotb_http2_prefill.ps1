param([ValidateSet('icarus','verilator')][string]$Simulator='icarus')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_cocotb_prefill_harness.py') --output (Join-Path $workspacePath 'sim\cocotb_http2_prefill_top.sv')
if($LASTEXITCODE -ne 0) { throw 'Cocotb harness generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_http2_prefill_vectors.py') --output (Join-Path $workspacePath 'build\cocotb-prefill-fixtures')
if($LASTEXITCODE -ne 0) { throw 'Native-reference fixture generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\verify_http2_prefill_references.py') --fixtures (Join-Path $workspacePath 'build\cocotb-prefill-fixtures') --output (Join-Path $workspacePath 'build\cocotb-prefill-reference-validation.json')
if($LASTEXITCODE -ne 0) { throw 'Independent native wire/reference validation failed' }
$linuxWorkspace='/mnt/c/Users/varra/OneDrive/Documents/ChatGPT/Protobuf SerDes + Tokenizer'
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/sync_wsl_workspace.py') --fixture cocotb-prefill-fixtures
if($LASTEXITCODE -ne 0) { throw 'WSL source/fixture synchronization failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python /home/varrahan/development/hardware/parser/scripts/run_cocotb.py http2_prefill --simulator $Simulator
$simulationExit=$LASTEXITCODE
& wsl.exe -d Ubuntu -- python3 ($linuxWorkspace+'/scripts/collect_cocotb_reports.py') http2_prefill
if($LASTEXITCODE -ne 0) { throw 'Cocotb report archive failed' }
if($simulationExit -ne 0) { throw 'Cocotb raw HTTP/2 prefill failed; see the archived report/log' }
& $referencePython (Join-Path $workspacePath 'tools\verify_cocotb_prefill.py')
if($LASTEXITCODE -ne 0) { throw 'Combined cocotb/native-reference audit failed' }
