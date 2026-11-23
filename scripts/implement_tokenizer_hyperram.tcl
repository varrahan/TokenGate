# Actual Tokenizer/cache/dual-clock controller, with registered external neighbors.
set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]!=2 || ![regexp {^[A-Za-z0-9_-]+$} [lindex $argv 0]] || ![regexp {^[A-Za-z0-9_-]+$} [lindex $argv 1]]} {error "Expected unique run and simulation names"}
set run [lindex $argv 0]
set simulation [lindex $argv 1]
set folder [file join $workspace build implementation xcsu35p-sbvb625-2-e $run]
if {[file exists $folder]} {error "Preserve prior implementation evidence"}
set frozen [file join $folder sources]
file mkdir [file join $frozen rtl]
file mkdir [file join $frozen scripts]
set tested [file join $workspace build validation $simulation sources rtl]
foreach source [glob [file join $tested *.v]] {file copy $source [file join $frozen rtl [file tail $source]]}
file copy [file join $workspace scripts implement_tokenizer_hyperram.tcl] [file join $frozen scripts]
file copy [file join $workspace build tokenizer-hyperram timing_harness.v] [file join $frozen timing_harness.v]
set xdc [open [file join $frozen timing.xdc] w]
puts $xdc {create_clock -name application_clk -period 4.000 [get_ports app_clk]}
puts $xdc {create_clock -name memory_clk -period 5.000 [get_ports mem_clk]}
close $xdc
exec [file join $workspace .venv312 Scripts python.exe] -I [file join $workspace tools capture_source_provenance.py] --root $frozen --output [file join $folder source-provenance.json] --tool-version [version -short]
set_param general.maxThreads 1
create_project -in_memory -part xcsu35p-sbvb625-2-e
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO XPM_MEMORY} [current_project]
read_verilog [glob [file join $frozen rtl *.v]]
read_verilog [list [file join $frozen timing_harness.v]]
read_xdc [list [file join $frozen timing.xdc]]
set_msg_config -id {Synth 8-326} -new_severity ERROR
set_msg_config -id {Synth 8-295} -new_severity ERROR
set_msg_config -id {Synth 8-6859} -new_severity ERROR
synth_design -top tokenizer_hyperram_timing_harness -part xcsu35p-sbvb625-2-e -mode out_of_context
# Exclude external package paths only. All core/cache/ownership/neighbor paths
# and both clocks remain timed; vendor scoped Gray-pointer/skew constraints stay.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != app_clk && NAME != mem_clk}]
set_false_path -to [all_outputs]
write_checkpoint [file join $folder synthesized.dcp]
report_utilization -hierarchical -file [file join $folder synthesis_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $folder synthesis_timing.rpt]
report_cdc -details -file [file join $folder synthesis_cdc.rpt]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $folder routed.dcp]
report_utilization -hierarchical -file [file join $folder routed_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $folder routed_timing.rpt]
report_cdc -details -file [file join $folder routed_cdc.rpt]
report_bus_skew -file [file join $folder routed_bus_skew.rpt]
report_exceptions -file [file join $folder routed_exceptions.rpt]
report_route_status -file [file join $folder route_status.rpt]
report_drc -file [file join $folder routed_drc.rpt]
puts "TOKENIZER_HYPERRAM_ROUTED APP_PERIOD_NS=4.000 MEM_PERIOD_NS=5.000 PACKAGE_TIMING_EXCLUDED=1 PHYSICAL_DDR_PHY_PRESENT=0"
close_project
exit
