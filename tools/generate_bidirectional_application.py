"""Join real raw prefill and RPC-bound return interfaces without fixture logic."""
import argparse
from pathlib import Path
import re

from rtl_paths import source_path


def ports(source, module):
    header=re.search(r'module\s+'+module+r'\s*#\(.*?\)\s*\((.*?)\);',source,re.S)[1]
    result=[];direction=width=None
    for declaration in re.sub(r'//[^\n]*','',header).split(','):
        match=re.fullmatch(r'\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*',declaration)
        if not match:raise ValueError(declaration)
        new_direction,new_width,name=match.groups()
        if new_direction is not None:direction,width=new_direction,new_width or ''
        result.append((direction,width,name))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rtl',type=Path,required=True);parser.add_argument('--harness',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    fp=ports((source_path(root, 'rtl/http2_grpc_prefill.v')).read_text(),'http2_grpc_prefill')
    rp=ports((source_path(root, 'rtl/rpc_generated_response.v')).read_text(),'rpc_generated_response')
    memory={name for _,_,name in fp if name.startswith('mem_')}
    controls={name for _,_,name in fp if name.startswith('control_')and not name.startswith('control_event_')}
    gated={'s_axis_rx_tvalid','s_axis_rx_tready','command_valid','command_ready','stream_cfg_valid','stream_cfg_ready',
           'queue_cfg_valid','queue_cfg_ready','cfg_schema_valid','cfg_schema_ready','cfg_quiescent','idle'}
    legacy={name for _,_,name in fp if name.startswith(('s_return_','m_return_'))}
    public=[]
    widths={'mem_valid':'[21:0]','mem_ready':'[21:0]','mem_write':'[21:0]','mem_addr':'[22*MEMORY_ADDR_WIDTH-1:0]',
            'mem_bytes':'[87:0]','mem_data':'[1583:0]','mem_rsp_valid':'[21:0]','mem_rsp_ready':'[21:0]',
            'mem_rsp_data':'[1583:0]','mem_rsp_status':'[175:0]'}
    for direction,width,name in fp:
        if name not in legacy:public.append((direction,widths.get(name,width),name))
    shared={'clk','rst','cfg_work_floor','cfg_model_epoch','cfg_schema_epoch'}
    def reverse_name(name):
        if name in shared:return name
        if name=='directory_lease_active':return 'response_directory_lease_active'
        if name in ('cfg_stream_base','cfg_stream_bytes'):return 'owned_'+name[4:]
        if name.startswith('directory_'):return 'r_'+name
        if name.startswith('s_axis_tokens_'):return name.replace('s_axis_tokens_','s_axis_generated_')
        if name.startswith('s_'):return 'generated_'+name[2:]
        if name.startswith('cfg_'):return 'cfg_response_'+name[4:]
        if name.startswith('result_'):return 'response_'+name
        if name.startswith('recovery_'):return 'response_'+name
        if name=='idle':return 'response_idle'
        if name=='mem_valid':return 'mem_valid[20+:2]'
        if name=='mem_ready':return 'mem_ready[20+:2]'
        if name=='mem_write':return 'mem_write[20+:2]'
        if name=='mem_addr':return 'mem_addr[20*MEMORY_ADDR_WIDTH+:2*MEMORY_ADDR_WIDTH]'
        if name=='mem_bytes':return 'mem_bytes[80+:8]'
        if name=='mem_data':return 'mem_data[1440+:144]'
        if name=='mem_rsp_valid':return 'mem_rsp_valid[20+:2]'
        if name=='mem_rsp_ready':return 'mem_rsp_ready[20+:2]'
        if name=='mem_rsp_data':return 'mem_rsp_data[1440+:144]'
        if name=='mem_rsp_status':return 'mem_rsp_status[160+:16]'
        return name
    for direction,width,name in rp:
        if name in shared or name in memory or name.startswith('directory_')and name!='directory_lease_active'or name in ('cfg_stream_base','cfg_stream_bytes'):continue
        public.append((direction,width,reverse_name(name)))
    assert len({p[2]for p in public})==len(public)
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Generated interface wiring; arbitration below is production RTL.',
        '// Application bytes only: full transport, whole-RPC image leases and',
        '// physical PCIe/memory adapters remain required system integration.',
        'module http2_bidirectional_application #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384',')(',
        ',\n'.join(f'    {direction} wire {width} {name}'for direction,width,name in public),');']
    for _,width,name in fp:
        if name in memory|controls|gated:lines.append(f'wire {width} f_{name};')
    for _,width,name in rp:
        if name.startswith('directory_')and name!='directory_lease_active':lines.append(f'wire {width} r_{name};')
    lines.extend('''
reg [1:0] control_owner;
reg control_sent,rx_active,owned_stream_valid,return_pending;
reg [MEMORY_ADDR_WIDTH-1:0] pending_stream_base,owned_stream_base;
reg [MEMORY_ADDR_WIDTH:0] pending_stream_bytes,owned_stream_bytes;
wire reverse_admit=owned_stream_valid&&!cfg_unlock&&!control_valid&&control_owner!=1&&
    !command_valid&&!queue_cfg_valid&&!stream_cfg_valid&&!queue_cfg_result_valid&&!stream_cfg_result_valid;
wire reverse_input_ready;
// Ownership begins at the public descriptor handshake and ends only at its
// held result ACK. Do not feed the deep serializer/decoder idle reduction
// back into ingress capture or configuration enables.
wire allow_new_rx=!return_pending&&!(s_axis_generated_tvalid&&reverse_admit)&&control_owner!=2;
wire allow_config=!return_pending&&control_owner!=2;
assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||allow_new_rx);
assign s_axis_rx_tready=f_s_axis_rx_tready&&(rx_active||allow_new_rx);
assign f_command_valid=command_valid&&allow_config;
assign command_ready=f_command_ready&&allow_config;
assign f_stream_cfg_valid=stream_cfg_valid&&allow_config;
assign stream_cfg_ready=f_stream_cfg_ready&&allow_config;
assign f_queue_cfg_valid=queue_cfg_valid&&allow_config;
assign queue_cfg_ready=f_queue_cfg_ready&&allow_config;
assign f_cfg_schema_valid=cfg_schema_valid&&allow_config;
assign cfg_schema_ready=f_cfg_schema_ready&&allow_config;
assign cfg_quiescent=f_cfg_quiescent&&!return_pending&&control_owner==0;
assign idle=f_idle&&response_idle&&control_owner==0&&!rx_active&&!s_axis_generated_tvalid;
assign s_axis_generated_tready=reverse_input_ready&&reverse_admit;
assign f_control_valid=!control_sent&&(control_owner==1?control_valid:control_owner==2&&r_directory_valid);
assign control_ready=control_owner==1&&!control_sent&&f_control_ready;
assign r_directory_ready=control_owner==2&&!control_sent&&f_control_ready;
assign f_control_result_ready=control_owner==1?control_result_ready:control_owner==2&&r_directory_result_ready;
assign control_result_valid=control_owner==1&&control_sent&&f_control_result_valid;
assign r_directory_result_valid=control_owner==2&&control_sent&&f_control_result_valid;
assign r_directory_status=f_control_status;
assign r_directory_memory_status=f_control_memory_status;
assign r_directory_address=f_control_result_address;
assign r_directory_application=f_control_result_application;
assign r_directory_generation=f_control_result_generation;
assign r_directory_protobuf=f_control_result_protobuf;
assign r_directory_unsupported_encoding=f_control_result_unsupported_encoding;
always @(posedge clk)begin
    if(rst)begin
        control_owner<=0;control_sent<=0;rx_active<=0;owned_stream_valid<=0;return_pending<=0;
        pending_stream_base<=0;pending_stream_bytes<=0;owned_stream_base<=0;owned_stream_bytes<=0;
    end else begin
        if(s_axis_rx_tvalid&&s_axis_rx_tready)rx_active<=!s_axis_rx_tlast;
        if(s_axis_generated_tvalid&&s_axis_generated_tready)return_pending<=1;
        if(response_result_valid&&response_result_ready)return_pending<=0;
        if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;pending_stream_bytes<=cfg_stream_bytes;end
        if(stream_cfg_result_valid&&stream_cfg_status==0)begin owned_stream_base<=pending_stream_base;owned_stream_bytes<=pending_stream_bytes;owned_stream_valid<=1;end
        if(control_owner==0)begin
            control_sent<=0;
            if(control_valid)control_owner<=1;
            else if(r_directory_valid)control_owner<=2;
        end
        if(f_control_valid&&f_control_ready)control_sent<=1;
        if(f_control_result_valid&&f_control_result_ready)begin control_owner<=0;control_sent<=0;end
    end
end
'''.strip().splitlines())
    request_reverse={'control_op':"3'd1",'control_user':'r_directory_user','control_stream':'r_directory_stream'}
    for direction,width,name in fp:
        if name in controls:
            if direction=='input'and name not in ('control_valid','control_result_ready'):
                lines.append(f"assign f_{name}=control_owner==2?{request_reverse.get(name, '0')}:{name};")
            elif direction=='output'and name not in ('control_ready','control_result_valid'):
                lines.append(f'assign {name}=f_{name};')
    slices={'mem_valid':'[0+:20]','mem_ready':'[0+:20]','mem_write':'[0+:20]','mem_addr':'[0+:20*MEMORY_ADDR_WIDTH]',
        'mem_bytes':'[0+:80]','mem_data':'[0+:1440]','mem_rsp_valid':'[0+:20]','mem_rsp_ready':'[0+:20]',
        'mem_rsp_data':'[0+:1440]','mem_rsp_status':'[0+:160]'}
    for direction,_,name in fp:
        if name in memory:lines.append(f'assign {name+slices[name] if direction=="output" else "f_"+name}={"f_"+name if direction=="output" else name+slices[name]};')
    forward_connections=[]
    for direction,width,name in fp:
        if name in legacy:
            target="1'b1"if name=='m_return_tready'else {'s_return_tdata':"128'd0",'s_return_tkeep':"16'd0",'s_return_tuser':"{USER_WIDTH{1'b0}}"}.get(name,"1'b0")if direction=='input'else''
        else:target='f_'+name if name in memory|controls|gated else name
        forward_connections.append(f'.{name}({target})')
    lines.extend(['http2_grpc_prefill #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),',
        '.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) forward(', ',\n'.join(forward_connections),');'])
    reverse_connections=[]
    for _,_,name in rp:
        target=reverse_name(name)
        if name=='s_axis_tokens_tvalid':target='s_axis_generated_tvalid&&reverse_admit'
        if name=='s_axis_tokens_tready':target='reverse_input_ready'
        reverse_connections.append(f'.{name}({target})')
    lines.extend(['rpc_generated_response #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) reverse(',
                  ',\n'.join(reverse_connections),');','endmodule','`default_nettype wire',''])
    args.rtl.parent.mkdir(parents=True,exist_ok=True);args.rtl.write_text('\n'.join(lines))
    harness=['`timescale 1ns/1ps','`default_nettype none','module cocotb_bidirectional_application_top;','localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    for direction,width,name in public:
        driven=direction=='input'and name not in ('mem_ready','mem_rsp_valid','mem_rsp_data','mem_rsp_status')
        harness.append(f"{'reg'if driven else'wire'} {width} {name}{'=0'if driven else''};")
    inputs={'arready':1,'rdata':64,'rresp':2,'rlast':1,'rvalid':1,'awready':1,'wready':1,'bresp':2,'bvalid':1}
    outputs={'araddr':23,'arlen':8,'arsize':3,'arburst':2,'arvalid':1,'rready':1,'awaddr':23,'awlen':8,'awsize':3,'awburst':2,'awvalid':1,'wdata':64,'wstrb':8,'wlast':1,'wvalid':1,'bready':1}
    for name,bits in {**inputs,**outputs}.items():
        harness.append(f"{'reg'if name in inputs else'wire'} {'['+str(bits-1)+':0]'if bits>1 else''} m_axi_{name}{'=0'if name in inputs else''};")
    harness.extend(['wire fabric_idle;wire [175:0] fabric_status;',
        'integer fault_client=-1,fault_target=-1,response_index=0;reg fault_arm=0,fault_injected=0;',
        'http2_bidirectional_application dut(.*);',
        'external_memory_fabric #(.CLIENTS(22)) fabric(',
        ".clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),",
        '.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),',
        '.rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(fabric_status),',
        ',\n'.join([f'.m_axi_{name}(m_axi_{name})'for name in {**outputs,**inputs}]+['.idle(fabric_idle)'])+');',
        'generate for(genvar client=0;client<22;client=client+1)begin: fault_ports',
        "assign mem_rsp_status[client*8+:8]=(fault_client==client&&!fault_injected&&response_index==fault_target)?8'h75:fabric_status[client*8+:8];",
        'end endgenerate','always @(posedge clk)begin',
        'if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end',
        'else if(fault_client>=0&&fault_client<22&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin',
        'if(!fault_injected&&response_index==fault_target)fault_injected<=1;response_index<=response_index+1;',
        'end','end','endmodule','`default_nettype wire',''])
    args.harness.parent.mkdir(parents=True,exist_ok=True);args.harness.write_text('\n'.join(harness))
    print(f'Joined application top: {len(public)} public ports, 22 memory clients, actual shared RPC directory')


if __name__=='__main__':main()
