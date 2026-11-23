"""Clear retained response progress under the real global FORMAT ownership."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import instance,named_instance

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1];previous=root/'build/experiments/window-authority/rtl'
    folder=root/'build/experiments/progress-format';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={source_relative(p, root).as_posix():sha(p)for p in previous.glob('*.v')}
    for p in previous.glob('*.v'):shutil.copy2(p,target/p.name)
    name='http2_enveloped_parser_core';text=(previous/(name+'.v')).read_text()
    block='''// Response progress belongs to global FORMAT, never an external window opcode.
// The successful send-ledger result retains the real directory/pool locks
// throughout these client-20 writes and their public result acknowledgement.
reg [1:0] progress_format_state;
reg progress_format_quarantined;
reg [MEMORY_ADDR_WIDTH-1:0] progress_format_base;
reg [MEMORY_ADDR_WIDTH:0] progress_format_bytes,progress_format_cursor;
reg [13*MEMORY_ADDR_WIDTH+5:0] progress_format_scope,progress_format_recovery_scope;
reg [7:0] progress_format_status,progress_format_detail,progress_format_memory_status;
wire progress_format_owner=progress_format_state==1||progress_format_state==2;
wire progress_format_complete=progress_format_state==3;
wire progress_format_start=rx_format_needed&&tx_format_complete&&service_window_rsp_status==0&&progress_format_state==0;
wire [MEMORY_ADDR_WIDTH-1:0] progress_format_address=progress_format_base+progress_format_cursor;
wire [MEMORY_ADDR_WIDTH+1:0] progress_format_end={2'b0,progress_format_base}+{1'b0,progress_format_bytes};
wire progress_format_geometry=progress_format_bytes!=0&&progress_format_bytes[2:0]==0&&
    progress_format_bytes>=(rx_format_rpc_bytes>>2)&&progress_format_base>=rx_format_floor&&
    progress_format_end<={1'b1,{MEMORY_ADDR_WIDTH{1'b0}}}&&
    PROGRESS_NONOVERLAP;
wire [2:0] progress_reverse_mem_valid,progress_reverse_mem_ready,progress_reverse_mem_write;
wire [3*MEMORY_ADDR_WIDTH-1:0] progress_reverse_mem_addr;
wire [11:0] progress_reverse_mem_bytes;
wire [215:0] progress_reverse_mem_data,progress_reverse_mem_rsp_data;
wire [2:0] progress_reverse_mem_rsp_valid,progress_reverse_mem_rsp_ready;
wire [23:0] progress_reverse_mem_rsp_status;
assign mem_valid[20+:3]={progress_reverse_mem_valid[1+:2],progress_format_owner?progress_format_state==1:progress_reverse_mem_valid[0]};
assign mem_write[20+:3]={progress_reverse_mem_write[1+:2],progress_format_owner?1'b1:progress_reverse_mem_write[0]};
assign mem_addr[20*MEMORY_ADDR_WIDTH+:3*MEMORY_ADDR_WIDTH]={progress_reverse_mem_addr[MEMORY_ADDR_WIDTH+:2*MEMORY_ADDR_WIDTH],progress_format_owner?progress_format_address:progress_reverse_mem_addr[0+:MEMORY_ADDR_WIDTH]};
assign mem_bytes[20*4+:12]={progress_reverse_mem_bytes[4+:8],progress_format_owner?4'd8:progress_reverse_mem_bytes[0+:4]};
assign mem_data[20*72+:216]={progress_reverse_mem_data[72+:144],progress_format_owner?72'd0:progress_reverse_mem_data[0+:72]};
assign mem_rsp_ready[20+:3]={progress_reverse_mem_rsp_ready[1+:2],progress_format_owner?progress_format_state==2:progress_reverse_mem_rsp_ready[0]};
assign progress_reverse_mem_ready={mem_ready[21+:2],!progress_format_owner&&mem_ready[20]};
assign progress_reverse_mem_rsp_valid={mem_rsp_valid[21+:2],!progress_format_owner&&mem_rsp_valid[20]};
assign progress_reverse_mem_rsp_data=mem_rsp_data[20*72+:216];
assign progress_reverse_mem_rsp_status=mem_rsp_status[20*8+:24];
always @(posedge clk)begin
    if(rst)begin
        progress_format_state<=0;progress_format_quarantined<=0;
        progress_format_base<=0;progress_format_bytes<=0;progress_format_cursor<=0;
        progress_format_scope<=0;progress_format_recovery_scope<=0;
        progress_format_status<=0;progress_format_detail<=0;progress_format_memory_status<=0;
    end else begin
        if(control_valid&&control_ready&&control_op==4)begin
            progress_format_state<=0;progress_format_base<=cfg_response_progress_base;
            progress_format_bytes<=cfg_response_progress_bytes;progress_format_cursor<=0;
            progress_format_scope<=PROGRESS_SCOPE;
            progress_format_status<=0;progress_format_detail<=0;progress_format_memory_status<=0;
        end
        if(progress_format_start)begin
            if(progress_format_quarantined&&progress_format_scope!=progress_format_recovery_scope)begin
                progress_format_status<=7;progress_format_detail<=19;progress_format_state<=3;
            end else if(!progress_format_geometry)begin
                progress_format_status<=2;progress_format_detail<=20;progress_format_state<=3;
            end else progress_format_state<=1;
        end
        if(progress_format_state==1&&mem_ready[20])progress_format_state<=2;
        if(progress_format_state==2&&mem_rsp_valid[20])begin
            if(mem_rsp_status[20*8+:8]!=0)begin
                progress_format_quarantined<=1;progress_format_recovery_scope<=progress_format_scope;
                progress_format_status<=5;progress_format_detail<=18;
                progress_format_memory_status<=mem_rsp_status[20*8+:8];progress_format_state<=3;
            end else if(progress_format_cursor+8>=progress_format_bytes)progress_format_state<=3;
            else begin progress_format_cursor<=progress_format_cursor+8;progress_format_state<=1;end
        end
        if(control_result_valid&&control_result_ready&&rx_format_pending)begin
            progress_format_state<=0;
            if(control_status==0)progress_format_quarantined<=0;
        end
    end
end

'''
    arenas=[('rx_format_context_base','rx_format_context_bytes'),('rx_format_rpc_base','rx_format_rpc_bytes'),
        ('rx_format_connection_base','rx_format_connection_bytes'),('rx_format_stream_base','rx_format_stream_bytes'),
        ('tx_format_window_base','tx_format_window_bytes')]
    disjoint=['(progress_format_end<={2\'b0,'+base+'}||{2\'b0,progress_format_base}>=({2\'b0,'+base+'}+{1\'b0,'+size+'}))'for base,size in arenas]
    scope=['cfg_context_base','cfg_context_bytes','cfg_stream_base','cfg_stream_bytes',
        'cfg_receive_connection_base','cfg_receive_connection_bytes','cfg_receive_stream_base','cfg_receive_stream_bytes',
        'cfg_window_base','cfg_window_bytes','cfg_response_progress_base','cfg_response_progress_bytes','cfg_work_floor']
    block=block.replace('PROGRESS_NONOVERLAP','&&\n    '.join(disjoint)).replace('PROGRESS_SCOPE','{'+','.join(scope)+'}')
    text=replace(text,'reg shutdown_control_offered;',block+'reg shutdown_control_offered;')
    text=replace(text,'wire global_format_complete=rx_format_complete&&(rx_init_status!=0||tx_format_complete);',
        'wire global_format_complete=rx_format_complete&&(rx_init_status!=0||tx_format_complete&&(service_window_rsp_status!=0||progress_format_complete));')
    for suffix in ('status','detail','memory_status'):
        before='service_window_rsp_'+suffix+':f_control_'+suffix+';'
        after='service_window_rsp_'+suffix+':rx_format_needed&&progress_format_complete&&progress_format_status!=0?progress_format_'+suffix+':f_control_'+suffix+';'
        text=replace(text,before,after)
    a,b,params,connections=instance(text,'rpc_grpc_http2_return','reverse')
    for port in ('mem_valid','mem_ready','mem_write','mem_addr','mem_bytes','mem_data',
        'mem_rsp_valid','mem_rsp_ready','mem_rsp_data','mem_rsp_status'):
        connections[port]='progress_reverse_'+port
    text=text[:a]+named_instance('rpc_grpc_http2_return',params,'reverse',connections)+text[b:]
    (target/(name+'.v')).write_text(text)
    result=dict(phase='global_response_progress_format_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p)for p in target.glob('*.v')},
        private_global_format_only=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    fixture=root/'build/experiments/retained-native-roundtrip/test_raw_grpc_enveloped.py'
    adapted=replace(fixture.read_text(),'        await b.directory(4);await b.open();',
        '        b.response_configuration(0)\n        await b.directory(4);await b.open();')
    adapted=replace(adapted,'    from window_format_witness import WindowFormatWitness',
        '    from progress_format_witness import ProgressFormatWitness as WindowFormatWitness')
    output=folder/'sim/test_raw_grpc_enveloped.py';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(adapted)
    (folder/'case-generation.json').write_text(json.dumps(dict(generator_sha256=sha(Path(__file__)),
        source_sha256=sha(fixture),fixture_sha256=sha(output),host_supplies_progress_geometry_before_format=True,
        witness_sha256=sha(root/'sim/cocotb/progress_format_witness.py'),
        base_witness_sha256=sha(root/'sim/cocotb/window_format_witness.py')),indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
