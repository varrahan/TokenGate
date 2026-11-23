set workspace [file dirname [file dirname [file normalize [info script]]]]
if {[llength $argv]<2 || [llength $argv]>7} {error "Expected module top, unique run name, optional execution mode, synthesis directive, experimental part, isolated RTL override and thread limit"}
set top [lindex $argv 0]
set run_name [lindex $argv 1]
set execution_mode implementation
if {[llength $argv]>=3} {set execution_mode [lindex $argv 2]}
set synthesis_directive Default
if {[llength $argv]>=4} {set synthesis_directive [lindex $argv 3]}
if {$synthesis_directive ni {Default AreaOptimized_high}} {error "Invalid synthesis directive"}
if {$execution_mode ni {implementation synthesis resume placement route-placement}} {error "Invalid execution mode"}
if {$execution_mode in {resume route-placement} && $synthesis_directive ne "Default"} {error "Resume uses the existing checkpoint; synthesis options cannot be changed"}
if {![regexp {^[A-Za-z_][A-Za-z0-9_]*$} $top] || ![regexp {^[A-Za-z0-9_-]+$} $run_name]} {error "Invalid implementation name"}
# Read the saved device without acquiring the project already open in the GUI.
set saved_project_file [open [file join $workspace Parser Parser.xpr] r]
set saved_project_xml [read $saved_project_file]
close $saved_project_file
set saved_part_matches [regexp -all -inline {<Option\s+Name="Part"\s+Val="([^"]+)"\s*/>} $saved_project_xml]
if {[llength $saved_part_matches]!=2} {error "Expected exactly one saved project Part option"}
set part [lindex $saved_part_matches 1]
if {![regexp {^xc[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+$} $part] || [llength [get_parts -quiet $part]]!=1} {error "Saved project device is invalid or unavailable"}
set saved_part $part
if {[llength $argv]>=5} {
    set part [lindex $argv 4]
    if {![regexp {^xc[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+$} $part] || [llength [get_parts -quiet $part]]!=1} {error "Invalid or unavailable experimental part"}
    puts "EXPERIMENTAL_PART=$part SAVED_PROJECT_PART=$saved_part PROJECT_TARGET_UNCHANGED=1"
}
set report_dir [file join $workspace build implementation $part $run_name]
if {$execution_mode ni {resume route-placement} && [file exists $report_dir]} {error "Implementation run already exists; choose a new run name to preserve evidence"}
set source_root [file join $report_dir sources]
set implementation_threads 4
if {[llength $argv]==7} {
    set implementation_threads [lindex $argv 6]
    if {![string is integer -strict $implementation_threads] || $implementation_threads<1 || $implementation_threads>8} {error "Invalid implementation thread limit"}
}
set_param general.maxThreads $implementation_threads
puts "REGISTERED_SUBSYSTEM_MAX_THREADS=$implementation_threads"
if {$execution_mode eq "route-placement"} {
    if {![file exists [file join $report_dir placed.dcp]] || [file exists [file join $report_dir routed.dcp]]} {error "Resume placement requires a placed checkpoint without an existing routed checkpoint"}
    open_checkpoint [file join $report_dir placed.dcp]
} elseif {$execution_mode eq "resume"} {
    if {![file exists [file join $report_dir synthesized.dcp]] || [file exists [file join $report_dir routed.dcp]]} {error "Resume requires a synthesized checkpoint without an existing routed checkpoint"}
    open_checkpoint [file join $report_dir synthesized.dcp]
} else {
file mkdir [file join $source_root rtl]
file mkdir [file join $source_root scripts]
file mkdir [file join $source_root tools]
foreach source [glob [file join $workspace rtl *.v]] {file copy $source [file join $source_root rtl [file tail $source]]}
if {[llength $argv]>=6} {
    set override [file normalize [lindex $argv 5]]
    if {[file isdirectory $override]} {set replacements [lsort [glob -nocomplain -types f [file join $override *.v]]]} else {set replacements [list $override]}
    if {[llength $replacements]==0} {error "Isolated override has no RTL replacements"}
    foreach replacement $replacements {
        set destination [file join $source_root rtl [file tail $replacement]]
        if {![file isfile $replacement] || ![regexp {^[A-Za-z_][A-Za-z0-9_]*\.v$} [file tail $replacement]] || ![file isfile $destination]} {error "Isolated overrides must replace existing RTL filenames"}
    }
    set record [open [file join $source_root isolated-override.txt] w]
    foreach replacement $replacements {
        set destination [file join $source_root rtl [file tail $replacement]]
        file copy -force $replacement $destination
        puts $record "source=$replacement\nfrozen_destination=$destination"
    }
    puts $record "primary_rtl_changed=0"
    close $record
    puts "ISOLATED_RTL_OVERRIDE=$override FILES=[llength $replacements] PRIMARY_RTL_UNCHANGED=1"
}
foreach relative {scripts/implement_registered_subsystem.tcl scripts/run_registered_subsystem_implementation.ps1 tools/generate_parser_timing_harness.py tools/capture_source_provenance.py} {
    file copy [file join $workspace $relative] [file join $source_root $relative]
}
file copy [file join $workspace build ${run_name}-timing-harness.v] [file join $source_root timing_harness.v]
file copy [file join $workspace constraints parser.xdc] [file join $source_root timing.xdc]
set options_file [open [file join $source_root synthesis-options.txt] w]
puts $options_file "synthesis_directive=$synthesis_directive"
puts $options_file "general_max_threads=$implementation_threads"
puts $options_file "part=$part\nsaved_project_part=$saved_part\nproject_target_changed=0"
if {$synthesis_directive eq "AreaOptimized_high"} {puts $options_file "resource_sharing=on\ncontrol_set_opt_threshold=1"}
close $options_file
exec [file join $workspace .venv312 Scripts python.exe] -I [file join $workspace tools capture_source_provenance.py] --root $source_root --output [file join $report_dir source-provenance.json] --tool-version [version -short]
create_project -in_memory -part $part
set_property XPM_LIBRARIES {XPM_MEMORY XPM_FIFO} [current_project]
read_verilog [glob [file join $source_root rtl *.v]]
read_verilog [list [file join $source_root timing_harness.v]]
read_xdc [list [file join $source_root timing.xdc]]
# An inferred exception would hide an internal combinational loop from timing.
# Reject it instead of allowing a green report with an unrequested false path.
set_msg_config -id {Synth 8-326} -new_severity ERROR
set_msg_config -id {Synth 8-295} -new_severity ERROR
set_msg_config -id {Synth 8-6859} -new_severity ERROR
set synthesis_options [list -top ${top}_timing_harness -part $part -mode out_of_context]
if {$synthesis_directive eq "AreaOptimized_high"} {
    lappend synthesis_options -directive AreaOptimized_high -resource_sharing on -control_set_opt_threshold 1
}
synth_design {*}$synthesis_options
# Only package paths are excluded. Every core/neighbor register path is timed.
set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_false_path -to [all_outputs]
write_checkpoint [file join $report_dir synthesized.dcp]
report_utilization -hierarchical -file [file join $report_dir synthesis_utilization.rpt]
report_timing_summary -file [file join $report_dir synthesis_timing.rpt]
if {$execution_mode eq "synthesis"} {
    puts "REGISTERED_SUBSYSTEM_SYNTHESIS_COMPLETE TOP=$top PART=$part CLOCK_PERIOD_NS=4.000 ROUTING_NOT_RUN=1"
    close_project
    exit
}
}
if {$execution_mode ne "route-placement"} {
    opt_design
    place_design
    phys_opt_design
}
if {$execution_mode eq "placement"} {
    write_checkpoint [file join $report_dir placed.dcp]
    report_utilization -hierarchical -file [file join $report_dir placed_utilization.rpt]
    report_timing_summary -report_unconstrained -file [file join $report_dir placed_timing.rpt]
    report_timing -max_paths 50 -nworst 5 -file [file join $report_dir placed_critical_paths.rpt]
    report_high_fanout_nets -max_nets 40 -file [file join $report_dir placed_high_fanout.rpt]
    report_design_analysis -congestion -min_congestion_level 3 -file [file join $report_dir placed_congestion.rpt]
    puts "REGISTERED_SUBSYSTEM_PLACEMENT_COMPLETE TOP=$top PART=$part CLOCK_PERIOD_NS=4.000 ROUTING_NOT_RUN=1"
    close_project
    exit
}
route_design
write_checkpoint [file join $report_dir routed.dcp]
report_utilization -hierarchical -file [file join $report_dir routed_utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $report_dir routed_timing.rpt]
report_route_status -file [file join $report_dir route_status.rpt]
report_drc -file [file join $report_dir routed_drc.rpt]
puts "REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=$top PART=$part CLOCK_PERIOD_NS=4.000 PACKAGE_TIMING_EXCLUDED=1"
