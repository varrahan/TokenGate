# Compare the original serializer->ingress CE path with the registered grant.
# Both endpoints must exist; a zero-path result alone is not adequate evidence.
set workspace [file dirname [file dirname [file normalize [info script]]]]
set entries {}
set counts {}
foreach run {http2_bidirectional_application_initial http2_bidirectional_application_registered_grant} {
    set folder [file join $workspace build implementation xcsu35p-sbvb625-2-e $run]
    open_checkpoint [file join $folder synthesized.dcp]
    set sources [get_cells -hier -quiet -filter {NAME =~ "core/reverse/response/response/serializer/packet_builder/count_reg*" && IS_SEQUENTIAL == 1}]
    set destinations [get_cells -hier -quiet -filter {NAME =~ "core/forward/first_data_reg*" && IS_SEQUENTIAL == 1}]
    set source_pins [get_pins -quiet -of_objects $sources -filter {REF_PIN_NAME == Q}]
    set destination_pins [get_pins -quiet -of_objects $destinations -filter {REF_PIN_NAME == CE}]
    if {[llength $source_pins]==0||[llength $destination_pins]==0} {error "Required timing endpoints missing in $run"}
    set paths [get_timing_paths -quiet -from $source_pins -to $destination_pins -max_paths 1]
    set number [llength $paths]
    set slack null
    if {$number!=0} {set slack [get_property SLACK [lindex $paths 0]]}
    lappend counts $number
    lappend entries "\{\"native_run\":\"$run\",\"source_register_pins\":[llength $source_pins],\"destination_enable_pins\":[llength $destination_pins],\"timing_paths_found\":$number,\"worst_setup_slack_ns\":$slack\}"
    puts "REGISTERED_GRANT_PATH_CHECK RUN=$run SOURCES=[llength $source_pins] DESTINATIONS=[llength $destination_pins] PATHS=$number SLACK=$slack"
    close_project
}
if {[lindex $counts 0]==0||[lindex $counts 1]!=0} {error "Expected baseline path and no combinational path after the registered grant"}
set stream [open [file join $workspace build validation registered-grant-path-check.json] w]
puts $stream "\{\"phase\":\"passed\",\"tool_version\":\"[version -short]\",\"runs\":\[[join $entries ,]\],\"project_target_changed\":false,\"full_system_timing_verified\":false\}"
close $stream
puts "REGISTERED_GRANT_PATH_CHECK_PASSED=1"
exit
