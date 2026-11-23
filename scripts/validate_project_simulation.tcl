set workspace [file dirname [file dirname [file normalize [info script]]]]
if {![file exists [file join $workspace Parser Parser.xpr]]} {source [file join $workspace create_parser.tcl]}
open_project [file join $workspace Parser Parser.xpr]
puts "PROJECT_SIM_PART=[get_property PART [current_project]]"
set fixture [get_files -quiet [list [file join $workspace sim data decoder_vectors.mem]]]
puts "PROJECT_FIXTURE_TYPE=[get_property FILE_TYPE $fixture]"
# Use generated batch scripts: the GUI-mode simulator/socket handshake can
# stall under desktop automation even though the same snapshot runs headless.
launch_simulation -simset sim_1 -mode behavioral -scripts_only
close_project
puts "PROJECT_SCRIPTS_COMPLETE"
