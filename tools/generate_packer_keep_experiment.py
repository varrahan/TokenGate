"""Remove clears of unkept packer bytes, with AXI-visible equivalence proof."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'build/experiments/local-cancel'
    folder = root / 'build/experiments/packer-keep'
    target = folder / 'rtl'
    target.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {}
    for path in (source / 'rtl').glob('*.v'):
        shutil.copy2(path, target / path.name)
        inputs[path.relative_to(root).as_posix()] = sha(path)
    path = root / 'rtl/axis_byte_packer.v'
    original = path.read_text()
    inputs[path.relative_to(root).as_posix()] = sha(path)
    candidate = replace(original, '                data_reg<=0; keep_reg<=0; count<=0; end_pending<=0;',
        '                keep_reg<=0; count<=0; end_pending<=0;')
    candidate = replace(candidate, "                        data_reg<={{(DATA_WIDTH-8){1'b0}},s_data};",
        '                        data_reg[7:0]<=s_data;')
    candidate = replace(candidate, '    reg [DATA_WIDTH-1:0] data_reg;',
        '    // Unkept bytes are unspecified; overwrite each byte before setting its keep bit.\n    reg [DATA_WIDTH-1:0] data_reg;')
    (target / path.name).write_text(candidate)
    formal = folder / 'formal'
    formal.mkdir(exist_ok=True)
    for name, text in (('reference', original), ('candidate', candidate)):
        text = replace(text, 'module axis_byte_packer #(', 'module packer_' + name + ' #(')
        text = replace(text, 'output wire m_last, output wire [USER_WIDTH-1:0] m_user',
            'output wire m_last, output wire [USER_WIDTH-1:0] m_user,\n    output wire [$clog2(DATA_WIDTH/8+1)-1:0] formal_count')
        text = replace(text, '    assign m_data = data_reg;', '    assign formal_count=count;\n    assign m_data = data_reg;')
        (formal / (name + '.v')).write_text(text)
    harness = '''`default_nettype none
module packer_checker #(parameter WIDTH=128)(
 input wire clk,rst,input wire [7:0] s_data,input wire s_keep,s_valid,s_last,
 input wire [15:0] s_user,input wire m_ready
);
 localparam BYTES=WIDTH/8;
 wire [WIDTH-1:0] g_data,c_data,mask;
 wire [BYTES-1:0] g_keep,c_keep;
 wire g_valid,c_valid,g_last,c_last,g_ready,c_ready;
 wire [15:0] g_user,c_user;
 wire [$clog2(BYTES+1)-1:0] g_count,c_count;
 packer_reference #(.DATA_WIDTH(WIDTH)) gold(
  .clk(clk),.rst(rst),.s_data(s_data),.s_keep(s_keep),.s_valid(s_valid),.s_ready(g_ready),
  .s_last(s_last),.s_user(s_user),.m_data(g_data),.m_keep(g_keep),.m_valid(g_valid),
  .m_ready(m_ready),.m_last(g_last),.m_user(g_user),.formal_count(g_count));
 packer_candidate #(.DATA_WIDTH(WIDTH)) candidate(
  .clk(clk),.rst(rst),.s_data(s_data),.s_keep(s_keep),.s_valid(s_valid),.s_ready(c_ready),
  .s_last(s_last),.s_user(s_user),.m_data(c_data),.m_keep(c_keep),.m_valid(c_valid),
  .m_ready(m_ready),.m_last(c_last),.m_user(c_user),.formal_count(c_count));
 for(genvar i=0;i<BYTES;i=i+1)assign mask[i*8+:8]={8{g_keep[i]}};
 always @* begin
  assert(g_count==c_count);
  assert(g_ready==c_ready);
  assert(g_valid==c_valid);
  assert(g_keep==c_keep);
  assert(g_last==c_last);
  assert(g_user==c_user);
  // Stronger than comparison only on transfer: all kept bytes agree while held.
  assert(((g_data^c_data)&mask)==0);
 end
endmodule
module packer_keep_equivalence(
 input wire clk,rst,input wire [7:0] s_data,input wire s_keep,s_valid,s_last,
 input wire [15:0] s_user,input wire m_ready
);
 packer_checker #(.WIDTH(128)) bow(.*);
 packer_checker #(.WIDTH(512)) wire_output(.*);
endmodule
`default_nettype wire
'''
    (formal / 'equivalence.sv').write_text(harness)
    script = '\n'.join([
        'read_verilog -formal -sv build/experiments/packer-keep/formal/reference.v build/experiments/packer-keep/formal/candidate.v build/experiments/packer-keep/formal/equivalence.sv',
        'prep -top packer_keep_equivalence', 'flatten', 'memory_map', 'opt',
        'sat -seq 2 -tempinduct -maxsteps 10 -prove-asserts -set-init-zero -verify -timeout 60', ''])
    (formal / 'proof.ys').write_text(script)
    result = dict(phase='packer_unkept_clear_removal_generated', generator_sha256=sha(Path(__file__)),
        input_sha256=inputs, generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        formal_sha256={p.name:sha(p) for p in formal.iterdir() if p.suffix in ('.v','.sv','.ys')},
        original_74_module_route_critical_path='saved_frame_cfg_work_floor -> chained wire arbiters -> output_bytes/data_reg/R',
        changes_only_unkept_data=True, valid_byte_and_handshake_equivalence_verified=False,
        joined_simulation_verified=False, native_timing_verified=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(folder)


if __name__ == '__main__':
    main()
