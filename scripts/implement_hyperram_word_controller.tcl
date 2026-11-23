# Isolated 200 MHz word-interface timing experiment, not package/DDR timing.
set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]!=1 || ![regexp {^[A-Za-z0-9_-]+$} [lindex $argv 0]]} {error "Expected unique run name"}
set run [lindex $argv 0]
set folder [file join $workspace build implementation xcsu35p-sbvb625-2-e $run]
if {[file exists $folder]} {error "Preserve existing implementation evidence"}
set frozen [file join $folder sources]
file mkdir [file join $frozen rtl]
file mkdir [file join $frozen scripts]
foreach name {axi_hyperram_bridge hyperram_transaction_engine hyperram_startup axi_hyperram_controller} {
    file copy [file join $workspace rtl $name.v] [file join $frozen rtl $name.v]
}
file copy [file join $workspace scripts implement_hyperram_word_controller.tcl] [file join $frozen scripts]
file copy [file join $workspace build ${run}-timing-harness.v] [file join $frozen timing_harness.v]
set xdc [open [file join $frozen timing.xdc] w]
puts $xdc {create_clock -name memory_word_clk -period 5.000 [get_ports clk]}
close $xdc
exec [file join $workspace .venv312 Scripts python.exe] -I [file join $workspace tools capture_source_provenance.py] --root $frozen --output [file join $folder source-provenance.json] --tool-version [version -short]
set_param general.maxThreads 1
create_project -in_memory -part xcsu35p-sbvb625-2-e
read_verilog [glob [file join $frozen rtl *.v]]
read_verilog [list [file join $frozen timing_harness.v]]
read_xdc [list [file join $frozen timing.xdc]]
set_msg_config -id {Synth 8-326} -new_severity ERROR
set_msg_config -id {Synth 8-295} -new_severity ERROR
set_msg_config -id {Synth 8-6859} -new_severity ERROR
synth_design -top axi_hyperram_controller_timing_harness -part xcsu35p-sbvb625-2-e -mode out_of_context
# Only external package paths are excluded; every core and neighbor register is timed.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_false_path -to [all_outputs]
write_checkpoint [file join $folder synthesized.dcp]
report_utilization -hierarchical -file [file join $folder synthesis_utilization.rpt]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $folder routed.dcp]
report_utilization -hierarchical -file [file join $folder routed_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $folder routed_timing.rpt]
report_route_status -file [file join $folder route_status.rpt]
report_drc -file [file join $folder routed_drc.rpt]
puts "HYPERRAM_WORD_CONTROLLER_ROUTED CLOCK_PERIOD_NS=5.000 PHYSICAL_DDR_PHY_PRESENT=0 PACKAGE_TIMING_EXCLUDED=1"
close_project
exit
