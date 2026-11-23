$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
& (Join-Path $workspacePath '.venv312\Scripts\python.exe') (Join-Path $workspacePath 'tools\generate_parser_timing_harness.py') --source (Join-Path $workspacePath 'rtl\proto_json_decoder.v') --output (Join-Path $workspacePath 'build\parser_timing_harness.v')
if($LASTEXITCODE -ne 0) { throw 'Timing harness generation failed' }
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch -source (Join-Path $PSScriptRoot 'implement_registered_parser.tcl') -log (Join-Path $workspacePath 'build\registered-parser-implementation.log') -journal (Join-Path $workspacePath 'build\registered-parser-implementation.jou') -notrace
if($LASTEXITCODE -ne 0) { throw 'Registered Parser implementation failed' }
