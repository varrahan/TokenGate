# Refine an immutable routed application checkpoint without changing RTL/clock.
set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]!=4} {error "Expected top, part, source run and unique refinement run"}
lassign $argv top part base_run run_name
foreach value [list $top $base_run $run_name] {if {![regexp {^[A-Za-z0-9_][A-Za-z0-9_-]*$} $value]} {error "Invalid refinement identifier"}}
if {![regexp {^xc[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+$} $part]} {error "Invalid refinement part"}
set base [file join $workspace build implementation $part $base_run]
set output [file join $workspace build implementation $part $run_name]
if {![file exists [file join $base routed.dcp]] || [file exists $output]} {error "Refinement needs a routed input and a new output folder"}
file mkdir $output
file copy [file join $base sources] [file join $output sources]
file copy [info script] [file join $output sources scripts refine_registered_route.tcl]
set record [open [file join $output sources refinement-base.txt] w]
puts $record "base_run=$base_run\nbase_part=$part\nbase_checkpoint=[file join $base routed.dcp]\nrtl_changed=0\nclock_changed=0"
close $record
exec [file join $workspace .venv312 Scripts python.exe] -I [file join $workspace tools capture_source_provenance.py] --root [file join $output sources] --output [file join $output source-provenance.json] --tool-version [version -short]
set_param general.maxThreads 4
open_checkpoint [file join $base routed.dcp]
if {[get_property PART [current_design]] ne $part} {error "Checkpoint part mismatch"}
puts "REGISTERED_ROUTE_REFINEMENT_BASE=$base_run RTL_CHANGED=0 CLOCK_CHANGED=0"
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
write_checkpoint [file join $output routed.dcp]
report_utilization -hierarchical -file [file join $output routed_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $output routed_timing.rpt]
report_route_status -file [file join $output route_status.rpt]
report_drc -file [file join $output routed_drc.rpt]
puts "REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=$top PART=$part CLOCK_PERIOD_NS=4.000 PACKAGE_TIMING_EXCLUDED=1"
close_project
exit
