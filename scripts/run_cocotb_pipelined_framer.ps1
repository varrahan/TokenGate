param(
    [ValidateSet('Framer','Windows','Joined')][string]$Suite='Joined',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('pipelined_framer_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
foreach($generator in @('generate_cancel_send_windows.py','generate_cancellable_frame_arbiter.py',
    'generate_fenced_frame_grants.py','generate_registered_input_framer.py','generate_pipelined_cancel_framer.py')) {
    & (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath ('tools/'+$generator))
    if($LASTEXITCODE -ne 0) { throw "Framer generation failed: $generator" }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$suiteFlag=switch($Suite) { 'Framer' {'--registered-framer'} 'Windows' {'--pipelined-windows'} 'Joined' {'--pipelined-fenced-framer'} }
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') $suiteFlag --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw "Pipelined framer regression failed: $Suite" }
