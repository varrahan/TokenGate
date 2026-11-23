param([ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName='tokenizer_registered_harness')
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_parser_timing_harness.py') --source (Join-Path $workspacePath 'rtl\tokenizer\top\scu35_tokenizer_mmio_subsystem.v') --top scu35_tokenizer_mmio_subsystem --harness-top tokenizer_timing_harness --output (Join-Path $workspacePath 'build\tokenizer_timing_harness.v')
if($LASTEXITCODE -ne 0) { throw 'Tokenizer timing harness generation failed' }
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch -source (Join-Path $PSScriptRoot 'implement_registered_tokenizer.tcl') -log (Join-Path $workspacePath ("build\$RunName-implementation.log")) -journal (Join-Path $workspacePath ("build\$RunName-implementation.jou")) -notrace -tclargs $RunName
if($LASTEXITCODE -ne 0) { throw 'Registered tokenizer implementation failed' }
