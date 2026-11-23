# Validate a workspace-local board repository in an isolated in-memory project.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set evidence [file join $task_root build validation scu35-board-vivado]
file mkdir $evidence
set result_path [file join $evidence board-validation.tsv]
if {[file exists $result_path]} { error "Preserve the existing board validation evidence" }
set expected_board xilinx.com:scu35:part0:1.0
set expected_part xcsu35p-sbvb625-2-e
set_param board.repoPaths [list [file join $task_root FPGA boards]]
set selected [get_board_parts -quiet $expected_board]
if {[llength $selected] != 1} { error "Expected exactly one pinned SCU35 board definition: $selected" }
create_project -in_memory -part $expected_part
set_property board_part $expected_board [current_project]
set actual_board [get_property BOARD_PART [current_project]]
set actual_part [get_property PART [current_project]]
if {$actual_board ne $expected_board || $actual_part ne $expected_part} {
    error "Board/device selection did not match the pinned definition"
}
report_property -file [file join $evidence board-properties.rpt] $selected
set result [open $result_path w]
puts $result "BOARD_PART\t$actual_board"
puts $result "PART\t$actual_part"
puts $result "REPOSITORY\t[file join $task_root FPGA boards]"
puts $result "ORIGINAL_PROJECTS_MODIFIED\t0"
puts $result "PHYSICAL_HARDWARE_AVAILABLE\t0"
close $result
close_project
puts "SCU35_BOARD_DEFINITION_VALIDATION_PASS board=$actual_board part=$actual_part"
