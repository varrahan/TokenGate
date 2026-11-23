"""Replace notice fixtures with durable peer state and actual outbound controls."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY,named_instance

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    read=lambda n:(source_path(root, Path('rtl') / (n+'.v'))).read_text()
    cp=ports(read('http2_journaled_controls'),'http2_journaled_controls')
    pp=ports(read('http2_peer_state'),'http2_peer_state')
    public=[]
    for d,w,n in cp:
        if n.startswith('notice_'):continue
        if n in MEMORY:w=f'[2*{MEMORY[n][0]}-1:0]'
        public.append((d,w,n))
    public += [('input','[MEMORY_ADDR_WIDTH-1:0]','cfg_peer_base'),('input','[MEMORY_ADDR_WIDTH:0]','cfg_peer_bytes'),
        ('output','[7:0]','peer_format_status'),('output','[7:0]','peer_format_memory_status')]
    for d,w,n in pp:
        if n.startswith('req_')and n not in('req_setting','req_value')or n.startswith('rsp_'):
            public.append((d,w,'peer_cmd_'+n))
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Journal replay owns peer notices. External commands support FORMAT/READ/local TX only.',
        '// Parent must hold actual connection ownership and disjoint arena fences.',
        'module http2_peer_controls #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join(f'{d} wire {w} {n}'for d,w,n in public),' );']
    for _,w,n in cp:
        if n in MEMORY:continue
        if n.startswith('notice_')or n.startswith('m_axis_tx_')or n in('start_ready','result_valid','result_ready','result_status','result_detail','result_memory_status',
            'recovery_required','recovery_address','idle','control_http2_error','control_connection_error','control_memory_status'):
            lines.append(f'wire {w} j_{n};')
    for _,w,n in pp:
        if n not in MEMORY and n not in('clk','rst'):lines.append(f'wire {w} p_{n};')
    lines += ['reg [3:0] peer_owner;reg [2:0] format_phase;',
        'reg [USER_WIDTH-1:0] format_user;',
        'reg owned_authority,owned_maintenance;',
        'reg [MEMORY_ADDR_WIDTH-1:0] owned_context_base,owned_peer_base,owned_work_floor;',
        'reg [MEMORY_ADDR_WIDTH:0] owned_context_bytes,owned_peer_bytes;',
        'reg [7:0] format_status,format_detail,format_memory,notice_memory;',
        'reg notice_connection_error;reg [31:0] notice_http2_error;',
        'wire start_gate=format_phase==0&&peer_owner==0&&p_idle&&(!p_recovery_required||start_format&&start_maintenance);',
        'assign start_ready=j_start_ready&&start_gate;',
        'assign peer_format_status=format_status;assign peer_format_memory_status=format_memory;',
        'assign result_valid=j_result_valid&&(format_phase==0||format_phase==4);',
        'assign result_status=j_result_status!=0?j_result_status:format_status!=0?8\'d10:8\'d0;',
        'assign result_detail=j_result_status!=0?j_result_detail:format_detail;',
        'assign result_memory_status=j_result_memory_status!=0?j_result_memory_status:notice_memory!=0?notice_memory:format_memory;',
        'assign j_result_ready=result_valid&&result_ready;',
        'assign recovery_required=j_recovery_required||p_recovery_required;',
        'assign recovery_address=p_recovery_required?p_recovery_address:j_recovery_address;',
        'assign control_http2_error=notice_connection_error?notice_http2_error:j_control_http2_error;',
        'assign control_connection_error=notice_connection_error||j_control_connection_error;',
        'assign control_memory_status=notice_memory!=0?notice_memory:j_control_memory_status;',
        'wire tx_idle;assign idle=j_idle&&p_idle&&peer_owner==0&&format_phase==0&&tx_idle;',
        'assign p_req_valid=peer_owner==1?j_notice_valid:peer_owner==3?peer_cmd_req_valid:peer_owner==5||peer_owner==7;',
        'assign p_req_op=peer_owner==1?(j_notice_kind==0?4:j_notice_kind==1?5:j_notice_kind==2?6:15):peer_owner==5?0:peer_owner==7?2:peer_cmd_req_op<=3?peer_cmd_req_op:15;',
        'assign p_req_user=peer_owner==1?j_notice_user:peer_owner==5||peer_owner==7?format_user:peer_cmd_req_user;',
        'assign p_req_authority=peer_owner==3?peer_cmd_req_authority:owned_authority;',
        'assign p_req_maintenance=peer_owner==5?owned_maintenance:peer_owner==3&&peer_cmd_req_maintenance;',
        'assign p_req_setting=peer_owner==1?j_notice_setting:0;',
        'assign p_req_value=peer_owner==1?j_notice_value:0;',
        'assign p_req_payload=peer_owner==1?j_notice_payload:peer_cmd_req_payload;',
        'assign p_cfg_context_base=peer_owner==3?cfg_context_base:owned_context_base;',
        'assign p_cfg_context_bytes=peer_owner==3?cfg_context_bytes:owned_context_bytes;',
        'assign p_cfg_peer_base=peer_owner==3?cfg_peer_base:owned_peer_base;',
        'assign p_cfg_peer_bytes=peer_owner==3?cfg_peer_bytes:owned_peer_bytes;',
        'assign p_cfg_work_floor=peer_owner==3?cfg_work_floor:owned_work_floor;',
        'assign j_notice_ready=peer_owner==1&&p_req_ready;',
        'assign peer_cmd_req_ready=peer_owner==3&&p_req_ready;',
        'assign j_notice_result_valid=peer_owner==2&&p_rsp_valid;',
        'assign peer_cmd_rsp_valid=peer_owner==4&&p_rsp_valid;',
        'assign p_rsp_ready=peer_owner==2?j_notice_result_ready:peer_owner==4?peer_cmd_rsp_ready:peer_owner==6||peer_owner==8;',
        'assign j_notice_status=p_rsp_status;',
        'always @(posedge clk)begin',
        'if(rst)begin peer_owner<=0;format_phase<=0;format_user<=0;owned_authority<=0;owned_maintenance<=0;',
        'owned_context_base<=0;owned_context_bytes<=0;owned_peer_base<=0;owned_peer_bytes<=0;owned_work_floor<=0;',
        'format_status<=0;format_detail<=0;format_memory<=0;notice_memory<=0;notice_connection_error<=0;notice_http2_error<=0;end',
        'else begin',
        'if(start_valid&&start_ready)begin',
        'format_phase<=start_format?1:0;format_user<=start_user;owned_authority<=start_authority;owned_maintenance<=start_maintenance;',
        'owned_context_base<=cfg_context_base;owned_context_bytes<=cfg_context_bytes;owned_peer_base<=cfg_peer_base;owned_peer_bytes<=cfg_peer_bytes;owned_work_floor<=cfg_work_floor;',
        'format_status<=0;format_detail<=0;format_memory<=0;notice_memory<=0;notice_connection_error<=0;notice_http2_error<=0;end',
        'if(format_phase==1&&j_result_valid)format_phase<=j_result_status==0?2:4;',
        'if(result_valid&&result_ready)format_phase<=0;',
        'case(peer_owner)',
        '0:if(format_phase==2)peer_owner<=5;else if(format_phase==5)peer_owner<=7;else if(j_notice_valid)peer_owner<=1;else if(peer_cmd_req_valid&&j_idle&&!start_valid)peer_owner<=3;',
        '1:if(j_notice_valid&&p_req_ready)peer_owner<=2;',
        '2:if(p_rsp_valid&&j_notice_result_ready)begin peer_owner<=0;',
        'if(p_rsp_status!=0)begin notice_memory<=p_rsp_memory_status;notice_connection_error<=p_rsp_connection_error;notice_http2_error<=p_rsp_http2_error;end end',
        '3:if(peer_cmd_req_valid&&p_req_ready)peer_owner<=4;',
        '4:if(p_rsp_valid&&peer_cmd_rsp_ready)peer_owner<=0;',
        '5:if(p_req_ready)begin peer_owner<=6;format_phase<=3;end',
        '6:if(p_rsp_valid)begin peer_owner<=0;format_phase<=p_rsp_status==0?5:4;format_status<=p_rsp_status;format_detail<=p_rsp_detail;format_memory<=p_rsp_memory_status;end',
        '7:if(p_req_ready)begin peer_owner<=8;format_phase<=6;end',
        '8:if(p_rsp_valid)begin peer_owner<=0;format_phase<=4;format_status<=p_rsp_status;format_detail<=p_rsp_detail;format_memory<=p_rsp_memory_status;end',
        'default:peer_owner<=0;endcase end end']
    for _,_,n in pp:
        if n.startswith('rsp_')and n not in('rsp_valid','rsp_ready'):lines.append(f'assign peer_cmd_{n}=p_{n};')
    cc={}
    internal={'start_ready','result_valid','result_ready','result_status','result_detail','result_memory_status','recovery_required','recovery_address','idle',
        'control_http2_error','control_connection_error','control_memory_status'}
    for _,_,n in cp:
        if n in MEMORY:cc[n]=f'{n}[0+:{MEMORY[n][0]}]'
        elif n=='start_valid':cc[n]='start_valid&&start_gate'
        elif n.startswith(('notice_','m_axis_tx_'))or n in internal:cc[n]='j_'+n
        else:cc[n]=n
    pc={n:f'{n}[{MEMORY[n][0]}+:{MEMORY[n][0]}]'if n in MEMORY else n if n in('clk','rst')else'p_'+n for _,_,n in pp}
    lines +=[named_instance('http2_journaled_controls','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','journaled',cc),
        named_instance('http2_peer_state','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','peer',pc)]
    arb=ports(read('axis_frame_arbiter'),'axis_frame_arbiter');ac={}
    for _,_,n in arb:
        ac[n]='j_m_axis_tx_'+n[7:]if n.startswith('a_axis_')else'p_m_axis_tx_'+n[7:]if n.startswith('b_axis_')else'm_axis_tx_'+n[7:]if n.startswith('m_axis_')else'tx_idle'if n=='idle'else n
    lines +=[named_instance('axis_frame_arbiter','.DATA_WIDTH(512),.KEEP_WIDTH(64),.USER_WIDTH(USER_WIDTH)','tx',ac),'endmodule','`default_nettype wire','']
    target=source_path(root, 'rtl/http2_peer_controls.v');target.write_text('\n'.join(lines))
    # Keep the exact actual directory/window fixture and add the real peer state
    # as its fourth memory client. The fixture no longer supplies any notice.
    old=(root/'sim/cocotb_journaled_controls_top.sv').read_text()
    old=old.replace('module cocotb_journaled_controls_top;','module cocotb_peer_controls_top;')
    old='\n'.join(line for line in old.splitlines()if not any(line.startswith(t)for t in('reg ','wire '))or not any(' '+n+'='in line or' '+n+';'in line for _,_,n in cp if n.startswith('notice_')))+'\n'
    for _,w,n in public:
        if n in MEMORY or any(n==x for _,_,x in cp):continue
        old=old.replace('localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;','localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;\n'+f"{'reg'if next(d for d,_,name in public if name==n)=='input'else'wire'} {w} {n}{'=0'if next(d for d,_,name in public if name==n)=='input'else''};",1)
    for n,(bits,d)in MEMORY.items():
        old=old.replace(f'[3*{bits}-1:0] {n}',f'[4*{bits}-1:0] {n}')
        old=old.replace(f'wire [{bits}-1:0] journal_{n};',f'wire [2*{bits}-1:0] journal_{n};')
        old=old.replace(f'{n}[0+:{bits}]',f'{n}[0+:2*{bits}]')
        old=old.replace(f'{n}[{bits}+:2*{bits}]',f'{n}[2*{bits}+:2*{bits}]')
    # Replace the old component instance using its parsed boundary.
    from generate_two_fpga_application import instance
    start,end,params,_=instance(old,'http2_journaled_controls','dut')
    connections={n:'journal_'+n if n in MEMORY else'exec_'+n if n.startswith('window_')else n for _,_,n in public}
    old=old[:start]+named_instance('http2_peer_controls',params,'dut',connections)+old[end:]
    harness=root/'sim/cocotb_peer_controls_top.sv';harness.write_text(old)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='generated_actual_peer_control_join',production_sha256=sha(target),harness_sha256=sha(harness),
        input_sha256={str(source_relative(p, root)).replace('\\','/'):sha(p)for p in(source_path(root, 'rtl/http2_journaled_controls.v'),source_path(root, 'rtl/http2_peer_state.v'),source_path(root, 'rtl/axis_frame_arbiter.v'),root/'sim/cocotb_journaled_controls_top.sv',Path(__file__))},
        actual_shared_directory=True,notice_callbacks_supplied_by_rtl=True,full_raw_parser_joined=False,full_system_complete=False)
    (root/'build/validation/peer-controls-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated journal controls with real durable peer notices and native local SETTINGS/PING TX')


if __name__=='__main__':main()
