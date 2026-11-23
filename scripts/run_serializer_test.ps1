$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\serializer'
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_serializer_vectors.py') --output (Join-Path $testBuildPath 'serializer_vectors.txt')
if($LASTEXITCODE -ne 0) { throw 'Serializer reference generation failed' }
Push-Location $testBuildPath
try {
    $sources=@('rtl\axis_byte_unpacker.v','rtl\axis_byte_packer.v','rtl\json_escape_encoder.v','rtl\proto_json_serializer.v','sim\tb_serializer.sv') | ForEach-Object { Join-Path $workspacePath $_ }
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_serializer -s serializer_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') serializer_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
