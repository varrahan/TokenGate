# Actual AXI/startup/packet-CDC/word-engine assembly, isolated two-clock timing.
set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]!=1 || ![regexp {^[A-Za-z0-9_-]+$} [lindex $argv 0]]} {error "Expected unique run name"}
set run [lindex $argv 0]
set folder [file join $workspace build implementation xcsu35p-sbvb625-2-e $run]
if {[file exists $folder]} {error "Preserve previous native evidence"}
set frozen [file join $folder sources]
file mkdir [file join $frozen rtl]
file mkdir [file join $frozen scripts]
# Consume the audited frozen simulation sources, including its explicit FIFO
# override. Do not silently fall back to the different primary FIFO source.
set tested [file join $workspace build validation hyperram_async_windows_full_image_wide_timeout sources rtl]
foreach name {axi_hyperram_bridge cdc_packet_fifo hyperram_clock_bridge hyperram_startup hyperram_transaction_engine hyperram_word_backend axi_hyperram_async_controller} {
    file copy [file join $tested $name.v] [file join $frozen rtl $name.v]
}
file copy [file join $workspace scripts implement_hyperram_async_controller.tcl] [file join $frozen scripts]
file copy [file join $workspace build hyperram-async timing_harness.v] [file join $frozen timing_harness.v]
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
synth_design -top axi_hyperram_async_controller_timing_harness -part xcsu35p-sbvb625-2-e -mode out_of_context
# Exclude only external package paths. Retain vendor FIFO pointer max-delay and
# skew constraints; no global clock groups, custom false paths or CDC waivers.
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
puts "HYPERRAM_ASYNC_ASSEMBLY_ROUTED APP_PERIOD_NS=4.000 MEM_PERIOD_NS=5.000 PACKAGE_TIMING_EXCLUDED=1 PHYSICAL_DDR_PHY_PRESENT=0"
close_project
exit
