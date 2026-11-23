param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$SnapshotName=('key_close_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff')),
    [switch]$ParkedScheduler,
    [switch]$WireFence,
    [switch]$FencedFramer
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
if(([int]$WireFence.IsPresent+[int]$ParkedScheduler.IsPresent+[int]$FencedFramer.IsPresent) -gt 1) { throw 'Select one cancellation component' }
$generators=if($FencedFramer) {@('tools/generate_cancel_send_windows.py','tools/generate_cancellable_frame_arbiter.py','tools/generate_fenced_frame_grants.py')} elseif($WireFence) {@('tools/generate_cancellable_frame_arbiter.py')} else {@('tools/generate_cancel_send_windows.py')}
foreach($generator in $generators) {
    & (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath $generator)
    if($LASTEXITCODE -ne 0) { throw 'Actual key-close generation failed' }
}
$linuxWorkspace=(& wsl.exe -d Ubuntu -- wslpath -u $workspacePath)
if($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
$suiteFlag=if($FencedFramer) {'--fenced-framer'} elseif($WireFence) {'--cancellable-arbiter'} elseif($ParkedScheduler) {'--cancel-grants'} else {'--cancel-windows'}
& wsl.exe -d Ubuntu -- /home/varrahan/development/hardware/parser/.venv-sim/bin/python ($linuxWorkspace.Trim()+'/scripts/run_http2_send_windows.py') $suiteFlag --name $SnapshotName
if($LASTEXITCODE -ne 0) { throw 'Actual key-close regression failed' }
