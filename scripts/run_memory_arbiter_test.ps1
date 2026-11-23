$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\memory-arbiter'
New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
Push-Location $testBuildPath
try {
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv (Join-Path $workspacePath 'rtl\external_memory_arbiter.v') (Join-Path $workspacePath 'sim\tb_external_memory_arbiter.sv')
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_external_memory_arbiter -s memory_arbiter_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') memory_arbiter_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS: all')) { throw 'Simulation did not report complete PASS' }
} finally { Pop-Location }
