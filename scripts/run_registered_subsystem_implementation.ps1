param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*$')][string]$Top,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName,
    [switch]$SynthesisOnly,
    [switch]$ResumeSynthesis,
    [switch]$PlacementOnly,
    [switch]$ResumePlacement,
    [ValidateSet('Default','AreaOptimized_high')][string]$SynthesisDirective='Default',
    [ValidateRange(1,8)][int]$MaxThreads=4,
    [ValidatePattern('^xc[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+$')][string]$Part,
    [string]$RtlOverride
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$selectedModes=0
foreach($selectedMode in @($SynthesisOnly,$ResumeSynthesis,$PlacementOnly,$ResumePlacement)) { if($selectedMode) { $selectedModes++ } }
if($selectedModes -gt 1) { throw 'Choose one synthesis, placement or resume mode' }
if(($ResumeSynthesis -or $ResumePlacement) -and $SynthesisDirective -ne 'Default') { throw 'Resume uses the frozen checkpoint; its synthesis directive cannot be changed' }
$executionMode=if($SynthesisOnly) {'synthesis'} elseif($ResumeSynthesis) {'resume'} elseif($PlacementOnly) {'placement'} elseif($ResumePlacement) {'route-placement'} else {'implementation'}
$harnessTop=$Top+'_timing_harness'
$harnessFile=Join-Path $workspacePath ('build\'+$RunName+'-timing-harness.v')
if(-not $ResumeSynthesis -and -not $ResumePlacement) {
    $matchingSources=@(Get-ChildItem -LiteralPath (Join-Path $workspacePath 'rtl') -Filter ($Top+'.v') -Recurse -File)
    if($matchingSources.Count -ne 1) { throw 'Expected exactly one RTL source for the selected top' }
    $timingSource=$matchingSources[0].FullName
    if($RtlOverride) {
        $overrideItem=Get-Item -LiteralPath $RtlOverride
        $overrideTop=if($overrideItem.PSIsContainer) {Join-Path $overrideItem.FullName ($Top+'.v')} else {$overrideItem.FullName}
        if((Test-Path -LiteralPath $overrideTop -PathType Leaf) -and (Split-Path -Leaf $overrideTop) -eq ($Top+'.v')) {$timingSource=$overrideTop}
    }
    & (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_parser_timing_harness.py') --source $timingSource --top $Top --harness-top $harnessTop --output $harnessFile
    if($LASTEXITCODE -ne 0) { throw 'Timing harness generation failed' }
}
$logSuffix=if($ResumeSynthesis) {'route-resume'} elseif($ResumePlacement) {'route-placement'} else {'implementation'}
$implementationArguments=@($Top,$RunName,$executionMode,$SynthesisDirective)
if($Part) { $implementationArguments+=$Part }
if($RtlOverride) {
    if(-not $Part) { throw 'An isolated RTL override requires an explicit experimental Part' }
    if($ResumeSynthesis -or $ResumePlacement) { throw 'Resume uses its frozen RTL; do not supply an override' }
    $implementationArguments+=(Resolve-Path -LiteralPath $RtlOverride).Path
}
if($MaxThreads -ne 4) {
    if(-not $Part -or -not $RtlOverride) { throw 'An explicit thread limit requires an isolated experimental Part and RTL override' }
    $implementationArguments+=$MaxThreads
}
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch -source (Join-Path $PSScriptRoot 'implement_registered_subsystem.tcl') -log (Join-Path $workspacePath ('build\'+$RunName+'-'+$logSuffix+'.log')) -journal (Join-Path $workspacePath ('build\'+$RunName+'-'+$logSuffix+'.jou')) -notrace -tclargs @implementationArguments
if($LASTEXITCODE -ne 0) { throw "Registered implementation failed: $Top" }
