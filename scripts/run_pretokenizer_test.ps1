$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\pretokenizer'
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_pretokenizer_vectors.py') --output $testBuildPath
if($LASTEXITCODE -ne 0) { throw 'Pretokenizer references failed' }
Push-Location $testBuildPath
try {
    $sources=@('rtl\axis_byte_unpacker.v','rtl\utf8_codepoint_reader.v','rtl\regex_splitter_fsm.v','rtl\bpe_pretokenizer.v','rtl\programmable_table_ram.v','rtl\external_memory_cache.v','rtl\external_memory_arbiter.v','rtl\external_memory_fabric.v','rtl\unicode_external_lookup.v','sim\axi_external_memory_model.sv','sim\tb_bpe_pretokenizer.sv') | ForEach-Object { Join-Path $workspacePath $_ }
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_bpe_pretokenizer -L xpm -L unisims_ver -s pretokenizer_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') pretokenizer_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
