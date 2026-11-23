"""Join the committed journal and executor; retain one external window service."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY,named_instance


def main():
    root=Path(__file__).resolve().parents[1]
    def interface(name):return ports((root/'rtl'/(name+'.v')).read_text(),name)
    jp=interface('http2_control_journal');ep=interface('http2_control_executor')
    public=[p for p in jp if not p[2].startswith('m_')and p[2]!='consume_status']
    names={n for _,_,n in public}
    for d,w,n in ep:
        if n.startswith(('window_','notice_','cancel_','classify_','m_axis_'))or n in('cfg_stream_base','cfg_stream_bytes','cfg_window_base','cfg_window_bytes'):
            assert n not in names;public.append((d,w,n));names.add(n)
        elif n.startswith('result_')and n not in('result_valid','result_ready','result_user'):
            public.append((d,w,'control_'+n[7:]))
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Actual journal/executor. Connect typed windows to the existing shared service.',
        'module http2_journaled_controls #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join(f'{d} wire {w} {n}'for d,w,n in public),' );',
        'reg formatting;wire j_start_ready,e_start_ready,j_idle,e_idle,e_result_valid,e_finish_ready;']
    jc={};ec={}
    combined={'result_valid','result_status','result_detail','result_memory_status','result_committed'}
    for d,w,n in jp:
        if n.startswith('m_')or n=='consume_status':
            jc[n]='j_'+n;lines.append(f'wire {w} j_{n};')
        elif n.startswith('result_')and n!='result_ready':
            jc[n]='j_'+n;lines.append(f'wire {w} j_{n};')
            if n not in combined:lines.append(f'assign {n}=j_{n};')
        elif n=='result_ready':jc[n]='result_valid&&result_ready'
        elif n=='start_valid':jc[n]='start_valid&&(start_format||e_start_ready)'
        elif n=='start_ready':jc[n]='j_start_ready'
        elif n=='idle':jc[n]='j_idle'
        else:jc[n]=n
    for d,w,n in ep:
        if n=='start_valid':ec[n]='start_valid&&!start_format&&j_start_ready'
        elif n=='start_ready':ec[n]='e_start_ready'
        elif n=='finish_valid':ec[n]='j_result_valid&&!formatting'
        elif n=='finish_ready':ec[n]='e_finish_ready'
        elif n=='finish_abort':ec[n]='j_result_status!=0'
        elif n=='result_valid':ec[n]='e_result_valid'
        elif n=='result_ready':ec[n]='result_valid&&result_ready&&!formatting'
        elif n=='result_user':ec[n]=''
        elif n.startswith('result_'):ec[n]='control_'+n[7:]
        elif n=='s_status':ec[n]='j_consume_status'
        elif n.startswith('s_'):ec[n]='j_m_'+n[2:]
        elif n=='idle':ec[n]='e_idle'
        else:ec[n]=n
    lines += ['assign start_ready=j_start_ready&&(start_format||e_start_ready);',
        'assign result_valid=j_result_valid&&(formatting||e_result_valid);',
        'assign result_status=j_result_status!=0?j_result_status:formatting?0:control_status;',
        'assign result_detail=j_result_status!=0?j_result_detail:formatting?0:control_detail;',
        'assign result_memory_status=j_result_memory_status!=0?j_result_memory_status:formatting?0:control_memory_status;',
        'assign result_committed=j_result_committed&&(formatting||control_status==0);',
        'assign idle=j_idle&&e_idle;',
        'always @(posedge clk)begin if(rst)formatting<=0;else if(start_valid&&start_ready)formatting<=start_format;end',
        named_instance('http2_control_journal','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','journal',jc),
        named_instance('http2_control_executor','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','executor',ec),
        'endmodule','`default_nettype wire','']
    target=root/'rtl/http2_journaled_controls.v';target.write_text('\n'.join(lines))
    # A passive component fixture uses the actual pool-owned directory/window
    # service. Production keeps that service external to prevent duplication.
    wp=interface('http2_owned_keyed_windows');cp=interface('http2_journaled_controls')
    lines=['`timescale 1ns/1ps','`default_nettype none','module cocotb_journaled_controls_top;',
        'localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    declared=set()
    for d,w,n in cp:
        if n in MEMORY:continue
        name='exec_'+n if n.startswith('window_')else n
        driven=d=='input'and not n.startswith('window_')
        lines.append(f"{'reg'if driven else'wire'} {w} {name}{'=0'if driven else''};");declared.add(name)
    for d,w,n in wp:
        if n in MEMORY or n in('clk','rst','idle'):continue
        name='directory_'+n if n in('recovery_required','recovery_address')else n
        assert name not in declared,name
        lines.append(f"{'reg'if d=='input'else'wire'} {w} {name}{'=0'if d=='input'else''};")
        declared.add(name)
        if d=='output'and n.startswith('window_rsp_')and n!='window_rsp_valid':lines.append(f'wire {w} service_{n};\nassign {n}=service_{n};')
    for n,(bits,d)in MEMORY.items():
        lines += [f"{'reg'if d=='input'else'wire'} [3*{bits}-1:0] {n}{'=0'if d=='input'else''};",
            f'wire [{bits}-1:0] journal_{n};',f'wire [2*{bits}-1:0] service_{n};']
        if d=='output':lines.append(f'assign {n}={{service_{n},journal_{n}}};')
        else:lines += [f'assign journal_{n}={n}[0+:{bits}];',f'assign service_{n}={n}[{bits}+:2*{bits}];']
    lines += ['reg [2:0] window_owner=0;',
        'wire service_window_req_ready,service_window_rsp_valid;',
        'assign exec_window_req_ready=window_owner==1&&service_window_req_ready;',
        'assign window_req_ready=window_owner==3&&service_window_req_ready;',
        'assign exec_window_rsp_valid=window_owner==2&&service_window_rsp_valid;',
        'assign window_rsp_valid=window_owner==4&&service_window_rsp_valid;',
        'always @(posedge clk)begin if(rst)window_owner<=0;else case(window_owner)',
        '0:if(exec_window_req_valid)window_owner<=1;else if(window_req_valid)window_owner<=3;',
        '1:if(exec_window_req_valid&&service_window_req_ready)window_owner<=2;',
        '2:if(service_window_rsp_valid&&exec_window_rsp_ready)window_owner<=0;',
        '3:if(window_req_valid&&service_window_req_ready)window_owner<=4;',
        '4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;',
        'default:window_owner<=0;endcase end']
    controller_names={n for _,_,n in cp}
    wc={}
    for d,w,n in wp:
        if n in MEMORY:wc[n]='service_'+n
        elif n in('recovery_required','recovery_address'):wc[n]='directory_'+n
        elif n=='idle':wc[n]='service_idle';lines.append('wire service_idle;')
        elif n=='window_req_valid':wc[n]='window_owner==1?exec_window_req_valid:window_owner==3&&window_req_valid'
        elif n=='window_req_ready':wc[n]='service_window_req_ready'
        elif n=='window_rsp_valid':wc[n]='service_window_rsp_valid'
        elif n=='window_rsp_ready':wc[n]='window_owner==2?exec_window_rsp_ready:window_owner==4&&window_rsp_ready'
        elif n.startswith('window_')and d=='input':wc[n]=f'window_owner==1?exec_{n}:{n}'
        elif n.startswith('window_rsp_'):
            wc[n]='service_'+n
            if n in controller_names:lines.append(f'assign exec_{n}=service_{n};')
        else:wc[n]=n
    cc={n:'journal_'+n if n in MEMORY else'exec_'+n if n.startswith('window_')else n for _,_,n in cp}
    lines += [named_instance('http2_journaled_controls','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','dut',cc),
        named_instance('http2_owned_keyed_windows','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','service',wc),
        'endmodule','`default_nettype wire','']
    harness=root/'sim/cocotb_journaled_controls_top.sv';harness.write_text('\n'.join(lines))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/journaled-controls-generation.json').write_text(json.dumps(dict(phase='generated_journal_executor_join',
        input_sha256={str(p.relative_to(root)).replace('\\','/'):sha(p)for p in(root/'rtl/http2_control_journal.v',root/'rtl/http2_control_executor.v',Path(__file__))},
        production_sha256=sha(target),harness_sha256=sha(harness),production_window_service_external=True,
        actual_window_service_only_in_fixture=True,full_parser_joined=False,full_system_complete=False),indent=2)+'\n')
    print('Generated journal/executor with external shared windows and actual-service fixture')


if __name__=='__main__':main()
