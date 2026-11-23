set workspace [file dirname [file normalize [info script]]]
source [file join $workspace scripts rtl_sources.tcl]
set project_dir [file join $workspace Parser]
set default_part xcsu35p-sbvb625-2-e
if {[file exists [file join $project_dir Parser.xpr]]} {
    open_project [file join $project_dir Parser.xpr]
} else {
    if {[llength [get_parts -quiet $default_part]] != 1} {
        error "Required Spartan UltraScale+ part is not installed: $default_part"
    }
    create_project Parser $project_dir -part $default_part
    set board [get_board_parts -quiet xilinx.com:scu35:part0:1.0]
    if {[llength $board]==1} { set_property board_part $board [current_project] }
}
set part [get_property PART [current_project]]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY XPM_FIFO} [current_project]
foreach source [collect_rtl [file join $workspace rtl]] {
    if {[llength [get_files -quiet [list $source]]] == 0} { add_files -norecurse [list $source] }
}
foreach source [glob -nocomplain [file join $workspace sim *.sv]] {
    if {[llength [get_files -quiet [list $source]]] == 0} { add_files -fileset sim_1 -norecurse [list $source] }
}
foreach source [glob -nocomplain [file join $workspace sim data *.mem]] {
    if {[llength [get_files -quiet [list $source]]]==0} { add_files -fileset sim_1 -norecurse [list $source] }
}
set constraint [file join $workspace constraints parser.xdc]
if {[llength [get_files -quiet [list $constraint]]] == 0} { add_files -fileset constrs_1 -norecurse [list $constraint] }
# The application Parser uses BRAM and is valid on SCU35. The complete
# external-memory Parser/Tokenizer top remains required integration work.
set_property top proto_json_decoder [get_filesets sources_1]
set_property top tb_decoder [get_filesets sim_1]
update_compile_order -fileset sources_1
puts "PARSER_PROJECT_CREATED=[get_property DIRECTORY [current_project]]/Parser.xpr"
puts "PARSER_PROJECT_PART=[get_property PART [current_project]]"
close_project
