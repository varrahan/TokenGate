$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\splitter'
New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_splitter_vectors.py') --output (Join-Path $testBuildPath 'vectors.txt')
if($LASTEXITCODE -ne 0) { throw 'Splitter references failed' }
Push-Location $testBuildPath
try {
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv (Join-Path $workspacePath 'rtl\tokenizer\bpe\regex_splitter_fsm.v') (Join-Path $workspacePath 'sim\tb_regex_splitter.sv')
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_regex_splitter -s splitter_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') splitter_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
