"""Join missing-key classification to actual committed raw packet ownership."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import MEMORY,add_ports,header_end,instance,named_instance,rename

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];inputs={};outputs={}
    def read(n):
        p=source_path(root, Path('rtl') / (n+'.v'));inputs[source_relative(p, root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p.read_text()
    def emit(n,t):
        p=source_path(root, Path('rtl') / (n+'.v'));p.write_text(t);outputs[source_relative(p, root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    life=[('output','','ctl_history_fence'),('input','[31:0]','ctl_result_http2_error')]
    transport=add_ports(read('http2_peer_parser_transport'),'http2_peer_parser_transport',life)
    transport=rename(transport,'http2_peer_parser_transport','http2_classified_parser_transport')
    transport=replace_once(transport,'assign ctl_cfg_peer_base=owned_peer_base;',
        'assign ctl_history_fence=state==CONTROL_FINISH_WAIT&&p_packet_result_valid&&p_packet_committed&&r_idle&&a_idle&&h_idle&&!header_pending&&!router_active&&control_owner==0;\nassign ctl_cfg_peer_base=owned_peer_base;')
    assert transport.count('raw_memory<=ctl_result_memory_status;raw_h2<=2;')==2
    transport=transport.replace('raw_memory<=ctl_result_memory_status;raw_h2<=2;',
        'raw_memory<=ctl_result_memory_status;raw_h2<=ctl_result_http2_error!=0?ctl_result_http2_error:32\'d2;')
    emit('http2_classified_parser_transport',transport)
    core=read('http2_peer_parser_core');cp=ports(read('http2_classified_peer_controls'),'http2_classified_peer_controls')
    public=[(d,f'[26*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in ports(core,'http2_peer_parser_core')if not n.startswith('classify_')]
    public += [p for p in cp if p[2].startswith('history_')and p[2]!='history_fence']
    stop=header_end(core,'http2_peer_parser_core');body=core[core.index(';',stop)+1:]
    start,end,params,connections=instance(body,'http2_peer_parser_transport','forward');connections['ctl_history_fence']='ctl_history_fence';connections['ctl_result_http2_error']='journal_control_http2_error'
    body=body[:start]+named_instance('http2_classified_parser_transport',params,'forward',connections)+body[end:]
    start,end,params,old=instance(body,'http2_peer_controls','controls');connections={}
    for d,w,n in cp:
        if n in MEMORY:connections[n]=f'{n}[23*{MEMORY[n][0]}+:3*{MEMORY[n][0]}]'
        elif n=='history_fence':connections[n]='ctl_history_fence'
        elif n.startswith('history_'):connections[n]=n
        else:connections[n]=old[n]
    body=body[:start]+named_instance('http2_classified_peer_controls',params,'controls',connections)+body[end:]
    params='parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    declaration=lambda name,ps:'`timescale 1ns/1ps\n`default_nettype none\nmodule '+name+' #(\n'+params+'\n)(\n'+',\n'.join(f'{d} wire {w} {n}'for d,w,n in ps)+'\n);\n'
    emit('http2_classified_parser_core',declaration('http2_classified_parser_core',public)+'wire ctl_history_fence;\n'+body)
    ap=[(d,f'[17*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in public if not n.startswith('m_axis_tokens_')]
    lines=[declaration('http2_classified_parser_application',ap)];kept=[*range(1,5),*range(13,26)]
    for n,(bits,d)in MEMORY.items():
        lines.append(f'wire [26*{bits}-1:0] all_{n};')
        for compact,old in enumerate(kept):
            left=f'all_{n}[{old}*{bits}+:{bits}]';right=f'{n}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {right}={left};'if d=='output'else f'assign {left}={right};')
        if d=='input':
            for old in[0,*range(5,13)]:lines.append(f'assign all_{n}[{old}*{bits}+:{bits}]=0;')
    connections={n:'all_'+n if n in MEMORY else"1'b0"if n=='m_axis_tokens_tready'else''if n.startswith('m_axis_tokens_')else n for _,_,n in public}
    lines +=[named_instance('http2_classified_parser_core','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)','core',connections),'endmodule','`default_nettype wire','']
    emit('http2_classified_parser_application','\n'.join(lines))
    result=dict(phase='generated_fenced_actual_history_parser',input_sha256=inputs,generated_sha256=outputs,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),parser_memory_clients=17,actual_raw_admission_fence=True,
        missing_key_classification_supplied_by_rtl=True,cancellation_complete=False,full_system_complete=False)
    (root/'build/validation/http2-classified-parser-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated classified raw Parser with actual packet/admission fence and seventeen clients')


if __name__=='__main__':main()
