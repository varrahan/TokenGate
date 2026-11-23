$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\token-packager'
New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
Push-Location $testBuildPath
try {
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv (Join-Path $workspacePath 'rtl\tokenizer\bpe\token_packager.v') (Join-Path $workspacePath 'sim\tb_token_packager.sv')
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_token_packager -L xpm -L unisims_ver -s token_packager_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') token_packager_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
