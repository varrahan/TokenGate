"""Isolate geometry-backed receive capacities without changing application RTL."""
import hashlib
import json
from pathlib import Path
import shutil

from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    audit = json.loads((root / 'build/validation/open-rpc-reclaim-assembly.json').read_text())
    assert audit['key'] == 'ad1b6bc9beebcaf5'
    parent = root / 'build/experiments/open-rpc-reclaim'
    target = root / 'build/experiments/receive-capacity-store'
    target.mkdir(parents=True, exist_ok=False)
    for n in ('http2_receive_credit_store', 'memory_command_slot'):
        p = parent / 'rtl' / (n + '.v')
        assert sha(p) == audit['executed_parser_sha256'][n]
        destination = target / 'rtl' / p.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    p = target / 'rtl/http2_receive_credit_store.v'
    raw = p.read_bytes().decode(); newline = '\r\n' if '\r\n' in raw else '\n'
    text = raw.replace('\r\n', '\n'); certificate = []
    def edit(before, after):
        nonlocal text
        assert text.count(before) == 1, before
        text = text.replace(before, after); certificate.append([before, after])
    edit('parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23',
         'parameter integer ENABLE_CAPACITY=0,ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23')
    marker = '    input wire context_write_busy,input wire [USER_WIDTH-1:0] context_write_user,'
    edit(marker, '''    // Internal backing geometry; operation 12 derives its budget from these
    // captured ranges. No scalar amount can assert additional memory backing.
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes,cfg_payload_slot_bytes,
''' + marker)
    marker = '    reg [63:0] ends[0:3];'
    edit(marker, '''    reg [MEMORY_ADDR_WIDTH-1:0] payloads,recovery_payloads;
    reg [MEMORY_ADDR_WIDTH:0] payload_bytes,payload_slot_bytes,recovery_payload_bytes,recovery_payload_slot_bytes;
    wire capacity_format=ENABLE_CAPACITY&&operation==12;
    wire connection_format=operation==0||capacity_format;
''' + marker)
    marker = '    wire [MEMORY_ADDR_WIDTH-1:0] context_address=context_full[MEMORY_ADDR_WIDTH-1:0];'
    edit(marker, '''    wire [63:0] payload_end={1'b0,payloads}+{1'b0,payload_bytes};
    wire [63:0] rpc_slots={1'b0,rpc_bytes}>>7;
    wire [63:0] backed_stream_capacity={1'b0,payload_slot_bytes}+64'd5;
    wire [63:0] backed_connection_capacity=backed_stream_capacity*rpc_slots;
    wire [63:0] required_payload_bytes={1'b0,payload_slot_bytes}*rpc_slots;
    reg capacity_geometry_good;integer capacity_arena;
    always @*begin
        capacity_geometry_good=payload_slot_bytes>=65530&&rpc_slots!=0&&
            backed_stream_capacity<=64'h7fffffff&&backed_connection_capacity<=64'h7fffffff&&
            required_payload_bytes<={1'b0,payload_bytes}&&payloads>=work_floor&&
            payload_end<=(64'd1<<MEMORY_ADDR_WIDTH);
        for(capacity_arena=0;capacity_arena<4;capacity_arena=capacity_arena+1)
            if(!(payload_end<=bases[capacity_arena]||ends[capacity_arena]<={1'b0,payloads}))capacity_geometry_good=0;
    end
''' + marker)
    marker = '    wire connection_good=connection_record[63:0]=='
    insertion = '''    wire capacity_mode=ENABLE_CAPACITY&&connection_record[511:448]!=0;
    wire [31:0] payloads32=payloads,payload_bytes32=payload_bytes;
    wire [63:0] saved_connection_capacity={32'd0,initial_stream}*rpc_slots;
    wire [31:0] connection_limit=capacity_mode?saved_connection_capacity[31:0]:32'd65535;
    wire backing_record_good=connection_record[511:448]==0||
        (ENABLE_CAPACITY&&capacity_geometry_good&&connection_record[511:448]=={payload_bytes32,payloads32}&&
         {32'd0,initial_stream}==backed_stream_capacity&&saved_connection_capacity<=64'h7fffffff);
    wire [63:0] expected_rpc_payload={1'b0,payloads}+(({1'b0,rpc_address}-{1'b0,rpcs})>>7)*{1'b0,payload_slot_bytes};
    wire rpc_backing_good=!capacity_mode||
        ({32'd0,rpc_record[159:128]}==expected_rpc_payload&&
         {32'd0,rpc_record[191:160]}=={1'b0,payload_slot_bytes}&&
         rpc_record[223:192]!=0&&{32'd0,rpc_record[223:192]}<={1'b0,payload_slot_bytes});
    wire [31:0] initial_available=capacity_mode?32'd65535:initial_stream;
    wire [31:0] initial_pending=capacity_mode?initial_stream-32'd65535:32'd0;
'''
    edit(marker, insertion + marker)
    edit("{2'd0,connection_available}+{2'd0,connection_pending}+{2'd0,connection_intent}<=34'd65535&&",
         "{2'd0,connection_available}+{2'd0,connection_pending}+{2'd0,connection_intent}<={2'd0,connection_limit}&&")
    edit('connection_record[447:384]=={stream_bytes32,streams32}&&connection_record[511:448]==0;',
         'connection_record[447:384]=={stream_bytes32,streams32}&&backing_record_good;')
    edit('rpc_record[63:35]==0&&rpc_identity;', 'rpc_record[63:35]==0&&rpc_identity&&rpc_backing_good;')
    edit('wire retired_rpc_good=rpc_record[63:0]==0&&rpc_identity;',
         'wire retired_rpc_good=rpc_record[63:0]==0&&rpc_identity&&rpc_backing_good;')
    edit('!stream_available[31]&&!stream_limit[31]&&',
         '!stream_available[31]&&!stream_limit[31]&&(!capacity_mode||stream_limit==initial_stream)&&')
    edit("wire [33:0] connection_outstanding=34'd65535-", "wire [33:0] connection_outstanding={2'd0,connection_limit}-")
    edit('{context_bytes,rpc_bytes,connection_bytes,stream_bytes}==recovery_sizes;',
         '{context_bytes,rpc_bytes,connection_bytes,stream_bytes}==recovery_sizes&&\n        (!ENABLE_CAPACITY||payloads==recovery_payloads&&payload_bytes==recovery_payload_bytes&&payload_slot_bytes==recovery_payload_slot_bytes);')
    edit('recovery_user<=owner;recovery_connection<=connection_address;recovery_floor<=work_floor;',
         'recovery_user<=owner;recovery_connection<=connection_address;recovery_floor<=work_floor;\n            recovery_payloads<=payloads;recovery_payload_bytes<=payload_bytes;recovery_payload_slot_bytes<=payload_slot_bytes;')
    edit('state<=IDLE;operation<=0;authority<=0;',
         'state<=IDLE;payloads<=0;payload_bytes<=0;payload_slot_bytes<=0;recovery_payloads<=0;recovery_payload_bytes<=0;recovery_payload_slot_bytes<=0;operation<=0;authority<=0;')
    edit('generation<=req_generation;amount<=req_amount;rpc_address<=req_record_address;',
         'generation<=req_generation;amount<=req_amount;rpc_address<=req_record_address;\n                    payloads<=cfg_payload_base;payload_bytes<=cfg_payload_bytes;payload_slot_bytes<=cfg_payload_slot_bytes;')
    edit('(operation==0||ENABLE_STREAM_FORMAT&&operation==11)&&!maintenance',
         '(connection_format||ENABLE_STREAM_FORMAT&&operation==11)&&!maintenance')
    edit('operation>(ENABLE_STREAM_FORMAT?11:10)||!config_good',
         'operation>(ENABLE_CAPACITY?12:ENABLE_STREAM_FORMAT?11:10)||(operation==11&&!ENABLE_STREAM_FORMAT)||!config_good')
    edit('(operation!=0&&!(ENABLE_STREAM_FORMAT&&operation==11))',
         '(!connection_format&&!(ENABLE_STREAM_FORMAT&&operation==11))')
    edit('(operation==0||operation==6||operation==7||operation==11)&&stream_command',
         '(connection_format||operation==6||operation==7||operation==11)&&stream_command')
    marker = '                    else if(ENABLE_STREAM_FORMAT&&operation==11)begin format_cursor<=streams;write_words(WFORMAT_STREAMS);end'
    edit(marker, "                    else if(capacity_format&&(!capacity_geometry_good||amount!=0))fail(2,7,2,1);\n" + marker)
    edit('else if(operation==0)begin', 'else if(connection_format)begin')
    before = '''connection_record<={64'd0,{stream_bytes32,streams32},{connection_bytes32,connections32},
                                {rpc_bytes32,rpcs32},{context_bytes32,contexts32},64'd0,{amount,32'd65535},{16'd0,owner16,CONNECTION_MAGIC}};'''
    edit(before, '''connection_record<={capacity_format?{payload_bytes32,payloads32}:64'd0,
                                {stream_bytes32,streams32},{connection_bytes32,connections32},
                                {rpc_bytes32,rpcs32},{context_bytes32,contexts32},
                                {32'd0,capacity_format?(backed_connection_capacity[31:0]-32'd65535):32'd0},
                                {capacity_format?backed_stream_capacity[31:0]:amount,32'd65535},{16'd0,owner16,CONNECTION_MAGIC}};''')
    edit("stream_record<={{32'd0,initial_stream},64'd0,{{1'b0,stream_id},initial_stream},{generation,STREAM_MAGIC}};",
         "stream_record<={{32'd0,initial_stream},{32'd0,initial_pending},{{1'b0,stream_id},initial_available},{generation,STREAM_MAGIC}};")
    edit('if(operation==0||ENABLE_STREAM_FORMAT&&operation==11)begin recovery_required<=0;',
         'if(connection_format||ENABLE_STREAM_FORMAT&&operation==11)begin recovery_required<=0;')
    inverse = text
    for before, after in reversed(certificate):
        assert inverse.count(after) == 1; inverse = inverse.replace(after, before)
    assert inverse.replace('\n', newline) == raw
    p.write_bytes(text.replace('\n', newline).encode())
    modules = closure('http2_receive_credit_store', target)
    assert set(modules) == {'http2_receive_credit_store', 'memory_command_slot'}
    result = dict(phase='receive_capacity_store_component_generated', parent_assembly_audit_key=audit['key'],
        original_store_sha256=audit['executed_parser_sha256']['http2_receive_credit_store'],
        only_changed_module='http2_receive_credit_store', exact_component_modules=2,
        new_internal_operation=12, capacity_derived_from_captured_backing_geometry=True,
        durable_backing_word_bits=[511, 448], initial_credit_remains_pending_until_real_wire_retirement=True,
        legacy_mode_default=True, source_edit_certificate=certificate, original_newline=newline,
        source_inverse_verified=True, outputs_sha256={'rtl/'+p.name:sha(p) for p in modules.values()},
        generator_sha256=sha(Path(__file__)), component_runtime_verified=False,
        actual_parser_integrated=False, large_message_deadlock_fixed=False, full_system_complete=False)
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    print(json.dumps(dict(phase=result['phase'],exact_component_modules=2)))


if __name__ == '__main__':main()
