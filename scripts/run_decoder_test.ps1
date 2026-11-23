$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\decoder'
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_decoder_vectors.py') --output (Join-Path $testBuildPath 'decoder_vectors.mem')
if($LASTEXITCODE -ne 0) { throw 'Decoder reference generation failed' }
Push-Location $testBuildPath
try {
    $sources=Get-ChildItem -LiteralPath (Join-Path $workspacePath 'rtl') -Filter '*.v' -Recurse | ForEach-Object { $_.FullName }
    $sources+=Join-Path $workspacePath 'sim\tb_decoder.sv'
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_decoder -L xpm -L unisims_ver -s decoder_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') decoder_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
