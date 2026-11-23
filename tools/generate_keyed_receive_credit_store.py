"""Join real runtime RPC lookup to the unchanged durable receive backend."""
import hashlib
import json
from pathlib import Path
from generate_bidirectional_application import ports


BODY = r'''
localparam IDLE=0,PREPARE=1,PRECHECK_SEND=2,PRECHECK_WAIT=3,SCAN_REQ=4,SCAN_WAIT=5,
    SCAN_CHECK=6,COMMAND_SEND=7,COMMAND_WAIT=8,LOCAL_RESULT=9;
reg [3:0] state;
reg [MEMORY_ADDR_WIDTH-1:0] resolved_address,scan_address;
reg [31:0] resolved_generation;
reg [1:0] word_index;
reg [255:0] record_data;
integer record_bank;
reg [7:0] local_status,local_detail,local_memory;
reg local_connection_error;reg [31:0] local_http2_error;
reg scan_recovery;reg [MEMORY_ADDR_WIDTH-1:0] scan_recovery_address;
reg [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] scan_recovery_scope;
wire [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] current_scope={held_req_user,
    held_cfg_context_base,held_cfg_rpc_base,held_cfg_receive_connection_base,held_cfg_receive_stream_base,held_cfg_work_floor,
    held_cfg_context_bytes,held_cfg_rpc_bytes,held_cfg_receive_connection_bytes,held_cfg_receive_stream_bytes};
wire selected_scan=state==SCAN_REQ||state==SCAN_WAIT||state==SCAN_CHECK;
wire [63:0] pool_end={1'b0,held_cfg_rpc_base}+{1'b0,held_cfg_rpc_bytes};
wire [MEMORY_ADDR_WIDTH-1:0] scan_word_address=scan_address+word_index*8;
wire scan_slot_ready,scan_slot_valid,scan_slot_idle;
wire [71:0] scan_slot_data;wire [7:0] scan_slot_status;
memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) lookup_slot(
    .clk(clk),.rst(rst),.req_valid(state==SCAN_REQ),.req_ready(scan_slot_ready),.req_write(1'b0),
    .req_addr(scan_word_address),.req_bytes(4'd8),.req_data(72'd0),.result_valid(scan_slot_valid),
    .result_ready(state==SCAN_WAIT),.result_data(scan_slot_data),.result_status(scan_slot_status),
    .mem_valid(scan_mem_valid),.mem_ready(scan_mem_ready),.mem_write(scan_mem_write),.mem_addr(scan_mem_addr),
    .mem_bytes(scan_mem_bytes),.mem_data(scan_mem_data),.mem_rsp_valid(scan_mem_rsp_valid),.mem_rsp_ready(scan_mem_rsp_ready),
    .mem_rsp_data(scan_mem_rsp_data),.mem_rsp_status(scan_mem_rsp_status),.idle(scan_slot_idle));
assign req_ready=!rst&&state==IDLE&&c_idle&&scan_slot_idle;
assign c_req_valid=state==PRECHECK_SEND||state==COMMAND_SEND;
assign c_rsp_ready=state==PRECHECK_WAIT||state==COMMAND_WAIT&&rsp_ready;
assign rsp_valid=state==LOCAL_RESULT||state==COMMAND_WAIT&&c_rsp_valid;
assign rsp_op=held_req_op;assign rsp_user=held_req_user;assign rsp_stream=held_req_stream;
assign rsp_status=state==LOCAL_RESULT?local_status:c_rsp_status;
assign rsp_detail=state==LOCAL_RESULT?local_detail:c_rsp_detail;
assign rsp_memory_status=state==LOCAL_RESULT?local_memory:c_rsp_memory_status;
assign rsp_connection_error=state==LOCAL_RESULT?local_connection_error:c_rsp_connection_error;
assign rsp_http2_error=state==LOCAL_RESULT?local_http2_error:c_rsp_http2_error;
assign rsp_debit_authorized=state==COMMAND_WAIT&&c_rsp_debit_authorized;
assign rsp_wire_retired=state==COMMAND_WAIT&&c_rsp_wire_retired;
assign rsp_update_bytes=state==COMMAND_WAIT?c_rsp_update_bytes:0;
assign rsp_binding_valid=rsp_valid&&rsp_status==0&&held_req_stream!=0&&resolved_generation!=0;
assign rsp_record_address=resolved_address;assign rsp_generation=resolved_generation;
assign recovery_required=scan_recovery||c_recovery_required;
assign recovery_address=scan_recovery?scan_recovery_address:c_recovery_address;
assign idle=state==IDLE&&c_idle&&scan_slot_idle&&!req_valid;
task local_fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status,input quarantine);
    begin local_status<=status;local_detail<=detail;local_memory<=memory_status;
        local_connection_error<=status!=3;local_http2_error<=status==3?0:2;state<=LOCAL_RESULT;
        if(quarantine)begin scan_recovery<=1;scan_recovery_address<=scan_word_address;scan_recovery_scope<=current_scope;end
    end
endtask
task next_record;
    begin
        if({1'b0,scan_address}+128<pool_end)begin scan_address<=scan_address+128;word_index<=0;state<=SCAN_REQ;end
        else local_fail(3,10,0,0);
    end
endtask
always @(posedge clk)begin
    if(rst)begin
        state<=IDLE;resolved_address<=0;resolved_generation<=0;scan_address<=0;word_index<=0;record_data<=0;
        local_status<=0;local_detail<=0;local_memory<=0;local_connection_error<=0;local_http2_error<=0;
        scan_recovery<=0;scan_recovery_address<=0;scan_recovery_scope<=0;
        // CAPTURE_RESET
    end else case(state)
        IDLE:if(req_valid&&req_ready)begin
            // CAPTURE_REQUEST
            resolved_address<=req_record_address;resolved_generation<=req_generation;
            local_status<=0;local_detail<=0;local_memory<=0;local_connection_error<=0;local_http2_error<=0;state<=PREPARE;
        end
        PREPARE:if(scan_recovery&&(held_req_keyed||held_req_op!=0||!held_req_maintenance||current_scope!=scan_recovery_scope))local_fail(6,1,0,0);
            else if(held_req_keyed&&(held_req_stream==0||held_req_generation!=0||held_req_record_address!=0||
                !(held_req_op==2||held_req_op==3||held_req_op==4||held_req_op==5||held_req_op==8)))local_fail(2,7,0,0);
            else state<=held_req_keyed?PRECHECK_SEND:COMMAND_SEND;
        PRECHECK_SEND:if(c_req_ready)state<=PRECHECK_WAIT;
        PRECHECK_WAIT:if(c_rsp_valid)begin
            if(c_rsp_status!=0)begin
                local_status<=c_rsp_status;local_detail<=c_rsp_detail;local_memory<=c_rsp_memory_status;
                local_connection_error<=c_rsp_connection_error;local_http2_error<=c_rsp_http2_error;state<=LOCAL_RESULT;
            end else begin scan_address<=held_cfg_rpc_base;word_index<=0;state<=SCAN_REQ;end
        end
        SCAN_REQ:if(scan_slot_ready)state<=SCAN_WAIT;
        SCAN_WAIT:if(scan_slot_valid)begin
            if(scan_slot_status!=0)local_fail(5,20,scan_slot_status,1);
            else if(word_index==0&&scan_slot_data[63:0]==0)next_record;
            else if(word_index==0&&(scan_slot_data[31:0]!=32'h47525331||!scan_slot_data[32]||scan_slot_data[63:35]!=0))local_fail(5,21,0,1);
            else if(word_index==1&&(scan_slot_data[63]||scan_slot_data[62:32]==0))local_fail(5,21,0,1);
            else if(word_index==1&&(scan_slot_data[15:0]!=held_req_user||scan_slot_data[62:32]!=held_req_stream))next_record;
            else begin
                for(record_bank=0;record_bank<4;record_bank=record_bank+1)if(word_index==record_bank)record_data[record_bank*64+:64]<=scan_slot_data[63:0];
                if(word_index==3)state<=SCAN_CHECK;else begin word_index<=word_index+1'b1;state<=SCAN_REQ;end
            end
        end
        SCAN_CHECK:if(record_data[255:224]==0)local_fail(5,21,0,1);
            else begin resolved_address<=scan_address;resolved_generation<=record_data[255:224];state<=COMMAND_SEND;end
        COMMAND_SEND:if(c_req_ready)state<=COMMAND_WAIT;
        COMMAND_WAIT:if(c_rsp_valid&&rsp_ready)begin
            if(held_req_op==0&&c_rsp_status==0)begin scan_recovery<=0;scan_recovery_address<=0;end
            state<=IDLE;
        end
        LOCAL_RESULT:if(rsp_ready)state<=IDLE;
        default:state<=IDLE;
    endcase
end
'''


def main():
    root = Path(__file__).resolve().parents[1]; base = root / 'rtl/http2_receive_credit_store.v'
    public = ports(base.read_text(), 'http2_receive_credit_store')
    extra = [('input', '', 'req_keyed'), ('output', '', 'rsp_binding_valid'),
             ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'rsp_record_address'), ('output', '[31:0]', 'rsp_generation')]
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Generated actual runtime key lookup plus durable receive accounting.',
        '// Parent holds connection/directory-pool authority until public result ACK.',
        '// req_keyed resolves wire keys; address/generation must be zero on input.',
        'module http2_keyed_receive_credit_store #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join('    ' + d + ' wire ' + w + ' ' + n for d, w, n in public + extra), ');']
    captured = [(w, n) for d, w, n in public + extra if d == 'input' and n.startswith(('req_', 'cfg_')) and n != 'req_valid']
    for w, n in captured: lines.append('reg ' + w + ' held_' + n + ';')
    for d, w, n in public:
        if n not in ('clk', 'rst') and not n.startswith('context_write_'): lines.append('wire ' + w + ' c_' + n + ';')
    for d, w, n in public:
        if not n.startswith('mem_'): continue
        lines.append('wire ' + w + ' scan_' + n + ';')
        if d == 'output': lines.append('assign ' + n + '=selected_scan?scan_' + n + ':c_' + n + ';')
        elif n in ('mem_rsp_data', 'mem_rsp_status'):
            lines += ['assign scan_' + n + '=' + n + ';', 'assign c_' + n + '=' + n + ';']
        else:
            lines += ['assign scan_' + n + '=selected_scan&&' + n + ';', 'assign c_' + n + '=!selected_scan&&' + n + ';']
    for n in ('rsp_connection_available', 'rsp_stream_available', 'rsp_connection_pending', 'rsp_stream_pending'):
        lines.append('assign ' + n + '=c_' + n + ';')
    body = BODY.replace('// CAPTURE_RESET', ''.join('held_' + n + '<=0;' for _, n in captured))
    body = body.replace('// CAPTURE_REQUEST', ''.join('held_' + n + '<=' + n + ';' for _, n in captured))
    lines.append(body)
    connections = []
    for d, w, n in public:
        if n in ('clk', 'rst') or n.startswith(('context_write_', 'm_axis_tx_')): signal = n
        elif n == 'req_op': signal = 'state==PRECHECK_SEND?4\'d8:held_req_op'
        elif n == 'req_stream': signal = 'state==PRECHECK_SEND?31\'d0:held_req_stream'
        elif n == 'req_generation': signal = 'state==PRECHECK_SEND?32\'d0:resolved_generation'
        elif n == 'req_record_address': signal = 'state==PRECHECK_SEND?{MEMORY_ADDR_WIDTH{1\'b0}}:resolved_address'
        elif n == 'req_amount': signal = 'state==PRECHECK_SEND?32\'d0:held_req_amount'
        elif d == 'input' and n.startswith(('req_', 'cfg_')) and n != 'req_valid': signal = 'held_' + n
        else: signal = 'c_' + n
        connections.append('    .' + n + '(' + signal + ')')
    lines += ['http2_receive_credit_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) controller(',
              ',\n'.join(connections), ');', 'endmodule', '`default_nettype wire']
    target = root / 'rtl/http2_keyed_receive_credit_store.v'; target.write_text('\n'.join(lines) + '\n')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(phase='keyed_receive_credit_store_generated', source_sha256=sha(base), output_sha256=sha(target),
        generator_sha256=sha(Path(__file__)), directory_authority_must_be_supplied_by_actual_parent=True, full_system_complete=False)
    folder = root / 'build/receive-credit-keyed'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'generation.json').write_text(json.dumps(report, indent=2) + '\n'); print(target)


if __name__ == '__main__': main()
