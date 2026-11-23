$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\json-parser'
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_json_parser_vectors.py') --output (Join-Path $testBuildPath 'json_parser_vectors.txt')
if($LASTEXITCODE -ne 0) { throw 'JSON reference generation failed' }
Push-Location $testBuildPath
try {
    $sources=@('rtl\parser\decoder\json\json_string_normalizer.v','rtl\parser\decoder\schema\schema_cam_lut.v','rtl\parser\decoder\json\speculative_json_fsm.v','sim\tb_json_parser.sv') | ForEach-Object { Join-Path $workspacePath $_ }
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_json_parser -s json_parser_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') json_parser_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
