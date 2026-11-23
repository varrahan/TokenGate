# Isolated two-clock CDC experiment. Preserve all vendor scoped constraints.
set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]<1 || [llength $argv]>2 || ![regexp {^[A-Za-z0-9_-]+$} [lindex $argv 0]]} {error "Expected unique run name and optional isolated FIFO override"}
set run [lindex $argv 0]
set folder [file join $workspace build implementation xcsu35p-sbvb625-2-e $run]
if {[file exists $folder]} {error "Preserve existing native evidence"}
set frozen [file join $folder sources]
file mkdir [file join $frozen rtl]
file mkdir [file join $frozen scripts]
foreach name {cdc_packet_fifo hyperram_clock_bridge} {
    file copy [file join $workspace rtl $name.v] [file join $frozen rtl $name.v]
}
if {[llength $argv]==2} {
    set isolated_fifo [file normalize [lindex $argv 1]]
    if {![file isfile $isolated_fifo] || [file tail $isolated_fifo] ne "cdc_packet_fifo.v"} {error "Expected isolated cdc_packet_fifo.v"}
    file copy -force $isolated_fifo [file join $frozen rtl cdc_packet_fifo.v]
    set record [open [file join $frozen isolated-override.txt] w]
    puts $record "source=$isolated_fifo\nprimary_rtl_modified=0"
    close $record
}
file copy [file join $workspace scripts implement_hyperram_clock_bridge.tcl] [file join $frozen scripts]
file copy [file join $workspace build hyperram-cdc timing_harness.v] [file join $frozen timing_harness.v]
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
synth_design -top hyperram_clock_bridge_timing_harness -part xcsu35p-sbvb625-2-e -mode out_of_context
# Only external package paths are excluded. No global asynchronous clock groups
# or custom CDC waivers: retain vendor Gray-bus max-delay and skew constraints.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != app_clk && NAME != mem_clk}]
set_false_path -to [all_outputs]
write_checkpoint [file join $folder synthesized.dcp]
report_utilization -hierarchical -file [file join $folder synthesis_utilization.rpt]
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
puts "HYPERRAM_CLOCK_BRIDGE_ROUTED APP_PERIOD_NS=4.000 MEM_PERIOD_NS=5.000 PACKAGE_TIMING_EXCLUDED=1"
close_project
exit
