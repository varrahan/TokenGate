$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
foreach($testTop in @('tb_vocabulary_epoch','tb_axis_conversion')) {
    $testBuildPath=Join-Path $workspacePath ('build\'+$testTop)
    New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
    Push-Location $testBuildPath
    try {
        $sources=Get-ChildItem -LiteralPath (Join-Path $workspacePath 'rtl') -Filter '*.v' -Recurse | ForEach-Object { $_.FullName }
        $sources+=Join-Path $workspacePath ('sim\'+$testTop+'.sv')
        & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
        if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
        & (Join-Path $vivadoBinPath 'xelab.bat') $testTop -L xpm -L unisims_ver -s $testTop --debug typical
        if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
        & (Join-Path $vivadoBinPath 'xsim.bat') $testTop -runall -log simulation.log
        if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
        if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
    } finally { Pop-Location }
}
