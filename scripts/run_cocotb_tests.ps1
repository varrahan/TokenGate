param([ValidateSet('mmio','mmio_system')][string]$Suite='mmio')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$linuxSource=(& wsl.exe --exec wslpath -a -u $workspacePath).Trim()
if($LASTEXITCODE -ne 0) { throw 'WSL source mapping failed' }
$fixtureArguments=@()
if($Suite -eq 'mmio_system') {
    & (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_tokenizer_vectors.py') --output (Join-Path $workspacePath 'build\tokenizer-engine')
    if($LASTEXITCODE -ne 0) { throw 'MMIO system fixtures failed' }
    $fixtureArguments=@('--fixture','tokenizer-engine')
}
& wsl.exe --exec python3 "$linuxSource/scripts/sync_wsl_workspace.py" @fixtureArguments
if($LASTEXITCODE -ne 0) { throw 'WSL synchronization failed' }
$linuxWorkspace=(& wsl.exe --exec python3 -c 'from pathlib import Path; print(Path.home()/"development/hardware/parser")').Trim()
& wsl.exe --exec "$linuxWorkspace/.venv-sim/bin/python" "$linuxWorkspace/scripts/run_cocotb.py" $Suite
if($LASTEXITCODE -ne 0) { throw "Cocotb regression failed: $Suite" }
& wsl.exe --exec python3 -c 'from pathlib import Path; import shutil,sys; source=Path.home()/"development/hardware/parser/build"/("cocotb-"+sys.argv[2]); target=Path(sys.argv[1])/"build/wsl-reports"/("cocotb-"+sys.argv[2]); target.mkdir(parents=True,exist_ok=True); [shutil.copy2(source/name,target/name) for name in ("build.log","simulation.log","results.xml","report.json") if (source/name).exists()]; print("Archived cocotb reports:",target)' $linuxSource $Suite
if($LASTEXITCODE -ne 0) { throw 'Cocotb report archival failed' }
