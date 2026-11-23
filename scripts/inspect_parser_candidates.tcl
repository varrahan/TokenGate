# Read installed part metadata only. Do not open or retarget the saved project.
set workspace [file dirname [file dirname [file normalize [info script]]]]
set output_dir [file join $workspace build parser-candidates]
file mkdir $output_dir
foreach device {xcsu100p xcsu150p xcau15p xcau20p} {
    set matches [lsort [get_parts -quiet ${device}-*-2-e]]
    if {[llength $matches]==0} {set matches [lsort [get_parts -quiet ${device}*]]}
    if {[llength $matches]==0} {puts "PARSER_CANDIDATE_UNAVAILABLE=$device";continue}
    set selected [lindex $matches 0]
    report_property -all $selected -file [file join $output_dir ${device}-properties.txt]
    puts "PARSER_CANDIDATE_AVAILABLE=$selected"
}
puts "PARSER_CANDIDATE_INSPECTION_COMPLETE=1 PROJECT_UNCHANGED=1"
exit
