param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('controlled_hpack_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')))
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
& $referencePython (Join-Path $workspacePath 'tools\generate_controlled_hpack.py')
if($LASTEXITCODE -ne 0) { throw 'Controlled HPACK generation failed' }
& $referencePython (Join-Path $workspacePath 'tools\generate_http2_hpack_vectors.py') --output (Join-Path $workspacePath 'build\http2-controlled-hpack')
if($LASTEXITCODE -ne 0) { throw 'Native wire/header references failed' }
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_controlled_hpack.py') --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Raw controlled-HPACK regression failed' }
