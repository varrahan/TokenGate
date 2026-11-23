$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\external-detokenizer'
New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_external_detokenizer_vectors.py') --output $testBuildPath
if($LASTEXITCODE -ne 0) { throw 'External detokenizer fixtures failed' }
Push-Location $testBuildPath
try {
    $sources=@('rtl\shared\memory\programmable_table_ram.v','rtl\shared\axis\axis_byte_packer.v','rtl\shared\memory\external_memory_cache.v','rtl\tokenizer\detokenizer\detokenizer_engine.v','rtl\tokenizer\detokenizer\scu35_detokenizer_subsystem.v','sim\tb_external_detokenizer.sv') | ForEach-Object { Join-Path $workspacePath $_ }
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_external_detokenizer -L xpm -L unisims_ver -s external_detokenizer_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') external_detokenizer_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
