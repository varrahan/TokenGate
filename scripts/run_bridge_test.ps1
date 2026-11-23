$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$vivadoBinPath = 'C:\AMDDesignTools\2025.2\Vivado\bin'
$testBuildPath = Join-Path $workspacePath 'build\bridge'
New-Item -ItemType Directory -Path $testBuildPath -Force | Out-Null
Push-Location $testBuildPath
try {
    & (Join-Path $vivadoBinPath 'xvlog.bat') --sv (Join-Path $workspacePath 'rtl\axis_skid_buffer.v') (Join-Path $workspacePath 'rtl\bow_axi_bridge.v') (Join-Path $workspacePath 'sim\tb_bow_axi_bridge.sv')
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $vivadoBinPath 'xelab.bat') tb_bow_axi_bridge -s bridge_test --debug typical
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $vivadoBinPath 'xsim.bat') bridge_test -runall -log simulation.log
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if (-not (Select-String -LiteralPath 'simulation.log' -Pattern '^PASS:')) { throw 'Simulation did not report PASS' }
} finally { Pop-Location }
