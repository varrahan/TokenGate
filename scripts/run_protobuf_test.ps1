$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath=Join-Path $workspacePath 'build\protobuf'
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_protobuf_vectors.py') --output (Join-Path $testBuildPath 'protobuf_vectors.txt')
if($LASTEXITCODE -ne 0) { throw 'Protobuf reference generation failed' }
Push-Location $testBuildPath
try {
    $sources=@('rtl\utf8_byte_validator.v','rtl\protobuf_varint_decoder.v','rtl\protobuf_wire_fsm.v','sim\tb_protobuf_wire.sv') | ForEach-Object { Join-Path $workspacePath $_ }
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv @sources
    if($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_protobuf_wire -s protobuf_test --debug typical
    if($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') protobuf_test -runall -log simulation.log
    if($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if(-not(Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
