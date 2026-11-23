# Tiny synthesis establishes tool/license usability only, not design fit.
# Do not open, edit or retarget the saved Parser project.
set workspace [file dirname [file dirname [file normalize [info script]]]]
set output_dir [file join $workspace build parser-candidates]
file mkdir $output_dir
set part xcau15p-ffvb676-2-e
if {[llength [get_parts -quiet $part]]!=1} {error "Candidate part unavailable: $part"}
set source_file [file join $output_dir parser_license_probe.v]
set stream [open $source_file w]
puts $stream {module parser_license_probe(input wire clk,input wire rst,output reg [7:0] count);
always @(posedge clk)if(rst)count<=0;else count<=count+1'b1;
endmodule}
close $stream
create_project -in_memory -part $part
read_verilog [list $source_file]
set result passed
if {[catch {synth_design -top parser_license_probe -part $part -mode out_of_context} reason]} {set result failed}
set stream [open [file join $output_dir xcau15p-license-probe.json] w]
puts $stream "\{\"part\":\"$part\",\"tiny_synthesis_phase\":\"$result\",\"tool_version\":\"[version -short]\",\"parser_fit_verified\":false,\"project_target_changed\":false\}"
close $stream
puts "PARSER_CANDIDATE_LICENSE_PROBE=$result PART=$part DESIGN_FIT_UNVERIFIED=1 PROJECT_UNCHANGED=1"
close_project
exit
