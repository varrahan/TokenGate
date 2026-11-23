$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$vivadoBinPath='C:\AMDDesignTools\2025.2\Vivado\bin'
$simulationPath=Join-Path $workspacePath 'Parser\Parser.sim\sim_1\behav\xsim'
Push-Location $workspacePath
try {
    & (Join-Path $vivadoBinPath 'vivado.bat') -mode batch -source scripts\validate_project_simulation.tcl -log build\project-scripts.log -journal build\project-scripts.jou -notrace
    if($LASTEXITCODE -ne 0) { throw 'Vivado project script generation failed' }
    Push-Location $simulationPath
    try {
        & (Join-Path $vivadoBinPath 'xvlog.bat') --incr --relax -L uvm -prj tb_decoder_vlog.prj -log xvlog.log
        if($LASTEXITCODE -ne 0) { throw 'Project compilation failed' }
        & (Join-Path $vivadoBinPath 'xelab.bat') --incr --debug typical --relax --mt 2 -L xil_defaultlib -L uvm -L unisims_ver -L unimacro_ver -L secureip -L xpm --snapshot tb_decoder_behav xil_defaultlib.tb_decoder xil_defaultlib.glbl -log elaborate.log
        if($LASTEXITCODE -ne 0) { throw 'Project elaboration failed' }
        & (Join-Path $vivadoBinPath 'xsim.bat') tb_decoder_behav -runall -log project-direct-simulation.log
        if($LASTEXITCODE -ne 0) { throw 'Project snapshot simulation failed' }
        if(-not(Select-String project-direct-simulation.log -Pattern '^PASS:')) { throw 'Project snapshot did not report PASS' }
    } finally { Pop-Location }
} finally { Pop-Location }
