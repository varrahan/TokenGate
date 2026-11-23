"""Join actual close bindings, pre-lookup cancellation and owned wire draining."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import add_ports,instance,named_instance,rename

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];sources=[];targets=[]
    def read(name):
        p=source_path(root, f'rtl/{name}.v');sources.append(p);return p.read_text()
    def emit(name,text):
        p=source_path(root, f'rtl/{name}.v');p.write_text(text);targets.append(p)
    close_ports=[('input','','closed_valid'),('input','[USER_WIDTH-1:0]','closed_user'),('input','[30:0]','closed_stream'),
        ('input','[31:0]','closed_generation'),('input','[MEMORY_ADDR_WIDTH-1:0]','closed_address'),
        ('input','[MEMORY_ADDR_WIDTH-1:0]','closed_pool_base'),('input','[MEMORY_ADDR_WIDTH:0]','closed_pool_bytes')]
    text=rename(read('rpc_response_parser_partition'),'rpc_response_parser_partition','rpc_cancel_response_partition')
    text=add_ports(text,'rpc_cancel_response_partition',close_ports+[('input','','service_abort'),('input','','directory_abort'),('output','','result_cancelled')])
    text=replace_once(text,'    assign directory_valid=state==DREQ;', '''    reg cancelled;
    // CHECK already validates the captured pool. Register its full-width end
    // there so lookup suppression does not add pool addition ahead of range
    // comparison and the actual directory-arbitration enable. DREQ starts at
    // the same edge as before; a later close still suppresses its real LOAD.
    reg [63:0] checked_stream_end;
    // Only the parent actual window service may supply this acknowledged close.
    // Before DREQ handshakes there is no shared-memory or remote inverse owner.
    wire closed_address_good=closed_address>=streams&&{1'b0,closed_address}+128<=checked_stream_end&&((closed_address-streams)&127)==0;
    wire early_closed=state==DREQ&&closed_valid&&closed_user==owner&&closed_stream==stream_id&&
        closed_generation!=0&&closed_pool_base==streams&&closed_pool_bytes==stream_bytes&&closed_address_good&&
        !directory_held&&!child_started&&slot_idle&&child_idle;
    wire early_abort=state==DREQ&&service_abort&&!directory_held&&!child_started&&slot_idle&&child_idle;
    assign result_cancelled=cancelled;
    assign directory_valid=state==DREQ&&!early_closed&&!early_abort;''')
    text=replace_once(text,'state<=IDLE;word_index<=0;', 'state<=IDLE;cancelled<=0;checked_stream_end<=0;word_index<=0;')
    text=replace_once(text,'token<=s_axis_tokens_tdata;token_keep<=s_axis_tokens_tkeep;',
        'cancelled<=0;token<=s_axis_tokens_tdata;token_keep<=s_axis_tokens_tkeep;')
    text=replace_once(text,'else state<=DREQ;', 'else begin checked_stream_end<=stream_end;state<=DREQ;end')
    text=replace_once(text,'DREQ:if(directory_ready)state<=DWAIT;', '''DREQ:if(early_abort)fail(directory_abort?8'd2:8'd17,directory_abort?8'd6:8'd3,0);
            else if(early_closed)begin
                rpc_address<=closed_address;cancelled<=closed_generation==generation;
                // Preserve the submitted identity. A stale generation is a
                // terminal mismatch, not authority over the newer allocation.
                fail(17,closed_generation==generation?8'd1:8'd2,0);
            end else if(directory_ready)state<=DWAIT;''')
    emit('rpc_cancel_response_partition',text)

    text=rename(read('rpc_grpc_parser_response'),'rpc_grpc_parser_response','rpc_grpc_cancel_parser_response')
    text=add_ports(text,'rpc_grpc_cancel_parser_response',close_ports+[
        ('input','','service_abort'),('input','','directory_abort'),('input','','closed_reservation_verified'),('output','','result_cancelled')])
    text=replace_once(text,'wire transport_failure=active&&rpc_result_valid&&rpc_status==0&&framer_result&&framer_status!=0;',
        '''wire rpc_cancelled;
wire expected_closed=closed_reservation_verified&&framer_result&&framer_status==5;
assign result_cancelled=rpc_result_valid&&(rpc_cancelled||rpc_status==0&&expected_closed);
wire transport_failure=active&&rpc_result_valid&&rpc_status==0&&framer_result&&framer_status!=0&&!expected_closed;''')
    start,end,params,connections=instance(text,'rpc_response_parser_partition','rpc')
    connections.update({n:n for _,_,n in close_ports});connections.update(result_cancelled='rpc_cancelled',service_abort='service_abort',directory_abort='directory_abort')
    text=text[:start]+named_instance('rpc_cancel_response_partition',params,'rpc',connections)+text[end:]
    text=replace_once(text,'grpc_http2_response_framer #(', 'grpc_registered_input_framer #(')
    emit('rpc_grpc_cancel_parser_response',text)

    text=rename(read('rpc_grpc_initialized_return'),'rpc_grpc_initialized_return','rpc_grpc_cancellable_return')
    scheduler=read('http2_fenced_pipelined_grants');arb=read('axis_cancellable_frame_arbiter')
    extra=[p for p in ports(scheduler,'http2_fenced_pipelined_grants')if p[2].startswith(('freeze_','frame_tracking_error','frame_wire_pending','window_rsp_binding_',
        'window_rsp_record_address','window_rsp_generation','window_rsp_send_closed'))]
    extra += [(d,w.replace('DATA_WIDTH','512').replace('KEEP_WIDTH','64'),n)for d,w,n in ports(arb,'axis_cancellable_frame_arbiter')if n.startswith('b_axis_')]
    extra += [('output','','data_wire_paused'),('output','','result_cancelled'),('output','','result_retirement_pending')]
    text=add_ports(text,'rpc_grpc_cancellable_return',extra)
    text=replace_once(text,'assign result_valid=child_result_valid&&grant_finish_ready;\nwire retire=result_valid&&result_ready;', '''// An already offered GPU result survives independent window commands. Its
// ACK is retained if actual cached-LOAD retirement must wait for that owner.
reg result_presented,result_ack_pending;
assign result_valid=!result_ack_pending&&(result_presented||child_result_valid&&grant_finish_ready);
wire public_result_ack=result_valid&&result_ready;
wire retire=child_result_valid&&grant_finish_ready&&(result_ack_pending||public_result_ack);
assign result_retirement_pending=result_ack_pending;
always @(posedge clk)begin
    if(rst)begin result_presented<=0;result_ack_pending<=0;end
    else begin
        if(result_valid)result_presented<=1;
        if(public_result_ack&&!retire)result_ack_pending<=1;
        if(retire)begin result_presented<=0;result_ack_pending<=0;end
    end
end''')
    text=replace_once(text,'assign idle=response_idle&&grant_idle;', 'assign idle=response_idle&&grant_idle&&arb_idle;')
    text=replace_once(text,'assign recovery_required=response_recovery||directory_recovery_required||window_recovery_required;',
        'assign recovery_required=response_recovery||directory_recovery_required||window_recovery_required||frame_tracking_error;')
    text=replace_once(text,'assign recovery_address=response_recovery?response_recovery_address:directory_recovery_required?directory_recovery_address:window_recovery_address;',
        'assign recovery_address=response_recovery?response_recovery_address:directory_recovery_required?directory_recovery_address:window_recovery_required?window_recovery_address:frame_tracking_error?directory_address:0;')
    start,end,params,connections=instance(text,'rpc_grpc_parser_response','response')
    connections.update({n:'saved_'+n for _,_,n in close_ports})
    connections['closed_valid']='saved_closed_valid&&closed_scope_matches&&!directory_recovery_required&&!window_recovery_required&&!frame_tracking_error'
    connections.update(service_abort='directory_recovery_required||window_recovery_required||frame_tracking_error',directory_abort='directory_recovery_required',
        closed_reservation_verified='held_closed_verified',result_cancelled='result_cancelled')
    connections['result_ready']='retire'
    connections.update({f'm_axis_tx_{n}':f'data_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    text=text[:start]+named_instance('rpc_grpc_cancel_parser_response',params,'response',connections)+text[end:]
    start,end,params,connections=instance(text,'http2_keyed_frame_grants','directory_service')
    for _,_,n in extra:
        if n.startswith(('freeze_','frame_tracking_error','frame_wire_pending','window_rsp_')):connections[n]=n
    connections['frame_tx_done']='data_tvalid&&data_tready&&data_tlast'
    text=text[:start]+named_instance('http2_fenced_pipelined_grants',params,'directory_service',connections)+text[end:]
    end=text.rindex('endmodule')
    body='''
// One actual acknowledged close binding accelerates the pending pre-lookup
// descriptor. Mutating directory/connection commands invalidate it. A miss
// uses the ordinary real LOAD; no guessed address or generation is accepted.
reg saved_closed_valid,held_closed_verified;
reg [USER_WIDTH-1:0] saved_closed_user;
reg [30:0] saved_closed_stream;reg [31:0] saved_closed_generation;
reg [MEMORY_ADDR_WIDTH-1:0] saved_closed_address,saved_closed_pool_base,closing_pool_base;
reg [MEMORY_ADDR_WIDTH:0] saved_closed_pool_bytes,closing_pool_bytes;
wire [511:0] data_tdata;wire [63:0] data_tkeep;wire data_tvalid,data_tready,data_tlast;
wire [USER_WIDTH-1:0] data_tuser;wire arb_idle;
always @(posedge clk)begin
    if(rst)begin
        saved_closed_valid<=0;held_closed_verified<=0;saved_closed_user<=0;saved_closed_stream<=0;saved_closed_generation<=0;
        saved_closed_address<=0;saved_closed_pool_base<=0;saved_closed_pool_bytes<=0;closing_pool_base<=0;closing_pool_bytes<=0;
    end else begin
        if(s_axis_tokens_tvalid&&s_axis_tokens_tready)held_closed_verified<=0;
        if(credit_error_valid)held_closed_verified<=credit_error_status==8&&credit_error_http2_error==5&&
            !credit_error_connection_error&&credit_error_memory_status==0&&!frame_wire_pending&&!frame_tracking_error;
        if(control_req_valid&&control_req_ready&&(control_req_op==0||control_req_op==3||control_req_op==4||control_req_op==5))saved_closed_valid<=0;
        if(window_req_valid&&window_req_ready)begin
            closing_pool_base<=window_cfg_stream_base;closing_pool_bytes<=window_cfg_stream_bytes;
            if(window_req_op==0||window_req_op==1||window_req_op==7||window_req_op==8||window_req_op==10)saved_closed_valid<=0;
        end
        if(window_rsp_valid&&window_rsp_ready&&window_rsp_status==0&&window_rsp_binding_valid&&window_rsp_send_closed)begin
            saved_closed_valid<=1;saved_closed_user<=window_rsp_user;saved_closed_stream<=window_rsp_stream;
            saved_closed_generation<=window_rsp_generation;saved_closed_address<=window_rsp_record_address;
            saved_closed_pool_base<=closing_pool_base;saved_closed_pool_bytes<=closing_pool_bytes;
        end
    end
end
'''
    ac={n:n for _,_,n in ports(arb,'axis_cancellable_frame_arbiter')}
    ac.update(idle='arb_idle',a_pause='freeze_binding_valid&&freeze_drained',a_paused='data_wire_paused')
    ac.update({f'a_axis_{n}':f'data_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    ac.update({f'm_axis_{n}':f'm_axis_tx_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    body += named_instance('axis_cancellable_frame_arbiter','.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)','wire_arbiter',ac)+'\n'
    # The same RPC pool may appear in multiple runtime arena configurations.
    # Cache authority must cover the actual window/context/protected-prefix
    # geometry captured by this descriptor, not just its directory address.
    scope=('context_base','context_bytes','window_base','window_bytes','work_floor')
    scope_declarations=[];scope_reset=[];scope_capture=[];scope_commit=[];scope_checks=[]
    for name in scope:
        width='[MEMORY_ADDR_WIDTH:0]'if name.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]'
        scope_declarations.append(f'reg {width} saved_closed_{name},closing_{name};')
        scope_reset.append(f'saved_closed_{name}<=0;closing_{name}<=0;')
        scope_capture.append(f'closing_{name}<=window_cfg_{name};')
        scope_commit.append(f'saved_closed_{name}<=closing_{name};')
        scope_checks.append(f'saved_closed_{name}==saved_frame_cfg_{name}')
    body=replace_once(body,'wire [511:0] data_tdata;', '\n'.join(scope_declarations)+'\nwire closed_scope_matches='+
        '&&'.join(scope_checks)+';\nwire [511:0] data_tdata;')
    body=replace_once(body,'closing_pool_base<=0;closing_pool_bytes<=0;', 'closing_pool_base<=0;closing_pool_bytes<=0;'+''.join(scope_reset))
    body=replace_once(body,'closing_pool_base<=window_cfg_stream_base;closing_pool_bytes<=window_cfg_stream_bytes;',
        'closing_pool_base<=window_cfg_stream_base;closing_pool_bytes<=window_cfg_stream_bytes;'+''.join(scope_capture))
    body=replace_once(body,'saved_closed_pool_base<=closing_pool_base;saved_closed_pool_bytes<=closing_pool_bytes;',
        'saved_closed_pool_base<=closing_pool_base;saved_closed_pool_bytes<=closing_pool_bytes;'+''.join(scope_commit))
    text=text[:end]+body+text[end:];emit('rpc_grpc_cancellable_return',text)

    harness_path=root/'sim/cocotb_rpc_keyed_top.sv';sources.append(harness_path)
    harness=harness_path.read_text().replace('module cocotb_rpc_keyed_top;', 'module cocotb_rpc_cancel_top;')
    start,end,params,connections=instance(harness,'rpc_grpc_keyed_return','dut')
    existing=set(connections);declarations=[]
    for d,w,n in ports(text,'rpc_grpc_cancellable_return'):
        if n not in existing:
            connections[n]=n;initial='=1'if n=='lookup_admit'else'=0'
            declarations.append(f'{"reg"if d=="input"else"wire"} {w} {n}{initial if d=="input"else""};')
    harness=harness[:start]+'\n'.join(declarations)+'\n'+named_instance('rpc_grpc_cancellable_return',params,'dut',connections)+harness[end:]
    p=root/'sim/cocotb_rpc_cancel_top.sv';p.write_text(harness);targets.append(p)
    matrix=root/'sim/cocotb/test_rpc_keyed_response.py';sources.append(matrix)
    test=matrix.read_text().replace('class KeyedBench(', 'class CancelBench(').replace('exercise_rpc_fixture(d, KeyedBench)', 'exercise_rpc_fixture(d, CancelBench)')
    test=test.replace('async def actual_keyed_rpc_progress_credit_and_data(d):','async def actual_cancellable_rpc_preserves_full_native_matrix(d):')
    p=root/'sim/cocotb/test_rpc_cancel_matrix.py';p.write_text('# Generated full native RPC matrix for the cancellable service.\n'+test);targets.append(p)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/rpc-cancel-return-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_cancellable_rpc_return',input_sha256={source_relative(p, root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in targets},
        prelookup_close_binding_from_actual_service=True,expected_closed_result_distinct_from_uncertain_failure=True,
        actual_raw_rst_controller_integrated=False,whole_rpc_gpu_image_leases_verified=False,full_system_complete=False),indent=2)+'\n')
    print('Generated actual close-aware RPC return, private pre-lookup termination and passive inverse/fabric harness')


if __name__=='__main__':main()
