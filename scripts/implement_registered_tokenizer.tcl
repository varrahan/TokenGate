set workspace [file dirname [file dirname [file normalize [info script]]]]
source [file join $workspace scripts rtl_sources.tcl]
if {![file exists [file join $workspace Parser Parser.xpr]]} {source [file join $workspace create_parser.tcl]}
open_project [file join $workspace Parser Parser.xpr]
set part [get_property PART [current_project]]
close_project
set run_name tokenizer_registered_harness
if {[llength $argv]>0} {set run_name [lindex $argv 0]}
if {![regexp {^[A-Za-z0-9_-]+$} $run_name]} {error "Invalid implementation run name"}
set report_dir [file join $workspace build implementation $part $run_name]
file mkdir $report_dir
set source_root [file join $report_dir sources]
file mkdir [file join $source_root rtl]
foreach source [collect_rtl [file join $workspace rtl]] {
    file copy -force $source [file join $source_root rtl [file tail $source]]
}
file copy -force [file join $workspace build tokenizer_timing_harness.v] [file join $source_root timing_harness.v]
file copy -force [file join $workspace constraints parser.xdc] [file join $source_root timing.xdc]
exec [file join $workspace .venv312 Scripts python.exe] -I [file join $workspace tools capture_source_provenance.py] --root $source_root --output [file join $report_dir source-provenance.json] --tool-version [version -short]
set_param general.maxThreads 4
create_project -in_memory -part $part
set_property XPM_LIBRARIES {XPM_MEMORY XPM_FIFO} [current_project]
read_verilog [glob [file join $source_root rtl *.v]]
read_verilog [list [file join $source_root timing_harness.v]]
read_xdc [list [file join $source_root timing.xdc]]
synth_design -top tokenizer_timing_harness -part $part -mode out_of_context
# Package paths only are excluded. Every neighboring-register/core path,
# shared-cache path and MMIO/epoch/stream boundary remains timed at 4 ns.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_false_path -to [all_outputs]
write_checkpoint -force [file join $report_dir synthesized.dcp]
report_utilization -hierarchical -file [file join $report_dir synthesis_utilization.rpt]
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
puts "REGISTERED_TOKENIZER_ROUTE_COMPLETE PART=$part CLOCK_PERIOD_NS=4.000 PACKAGE_TIMING_EXCLUDED=1"
