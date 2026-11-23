set workspace [file dirname [file dirname [file normalize [info script]]]]
open_project [file join $workspace Parser Parser.xpr]
set part [get_property PART [current_project]]
close_project
set report_dir [file join $workspace build implementation $part parser_registered_harness]
file mkdir $report_dir
set_param general.maxThreads 4
create_project -in_memory -part $part
set_property XPM_LIBRARIES {XPM_MEMORY XPM_FIFO} [current_project]
read_verilog [glob [file join $workspace rtl *.v]]
read_verilog [list [file join $workspace build parser_timing_harness.v]]
read_xdc [list [file join $workspace constraints parser.xdc]]
synth_design -top parser_timing_harness -part $part -mode out_of_context
# Only external package paths are excluded. All neighboring-register -> core,
# core -> neighboring-register and core internal paths remain constrained.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_false_path -to [all_outputs]
write_checkpoint -force [file join $report_dir synthesized.dcp]
report_utilization -file [file join $report_dir synthesis_utilization.rpt]
report_timing_summary -file [file join $report_dir synthesis_timing.rpt]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint -force [file join $report_dir routed.dcp]
report_utilization -hierarchical -file [file join $report_dir routed_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $report_dir routed_timing.rpt]
report_route_status -file [file join $report_dir route_status.rpt]
report_drc -file [file join $report_dir routed_drc.rpt]
puts "REGISTERED_PARSER_ROUTE_COMPLETE PART=$part CLOCK_PERIOD_NS=4.000 PACKAGE_TIMING_EXCLUDED=1"
