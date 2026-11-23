"""Integrate actual durable peer notices and server preface in the raw Parser."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import MEMORY,add_ports,header_end,instance,named_instance,rename


def main():
    root=Path(__file__).resolve().parents[1];inputs={};outputs={}
    def read(n):
        p=root/'rtl'/(n+'.v');inputs[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest();return p.read_text()
    def emit(n,t):
        p=root/'rtl'/(n+'.v');p.write_text(t);outputs[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    cfg=[('input','[MEMORY_ADDR_WIDTH-1:0]','cfg_peer_base'),('input','[MEMORY_ADDR_WIDTH:0]','cfg_peer_bytes')]
    life=[('output','[MEMORY_ADDR_WIDTH-1:0]','ctl_cfg_peer_base'),('output','[MEMORY_ADDR_WIDTH:0]','ctl_cfg_peer_bytes')]
    transport=add_ports(read('http2_journaled_parser_transport'),'http2_journaled_parser_transport',cfg+life)
    transport=rename(transport,'http2_journaled_parser_transport','http2_peer_parser_transport')
    transport=replace_once(transport,'reg [MEMORY_ADDR_WIDTH-1:0] owned_control_journal_base;',
        'reg [MEMORY_ADDR_WIDTH-1:0] owned_peer_base;reg [MEMORY_ADDR_WIDTH:0] owned_peer_bytes;\n    reg [MEMORY_ADDR_WIDTH-1:0] owned_control_journal_base;')
    transport=replace_once(transport,'state<=IDLE;owned_control_journal_base<=0;',
        'state<=IDLE;owned_peer_base<=0;owned_peer_bytes<=0;owned_control_journal_base<=0;')
    transport=replace_once(transport,'owned_control_journal_base<=cfg_control_journal_base;',
        'owned_peer_base<=cfg_peer_base;owned_peer_bytes<=cfg_peer_bytes;owned_control_journal_base<=cfg_control_journal_base;')
    transport=replace_once(transport,'assign ctl_cfg_journal_base=owned_control_journal_base;',
        'assign ctl_cfg_peer_base=owned_peer_base;assign ctl_cfg_peer_bytes=owned_peer_bytes;\nassign ctl_cfg_journal_base=owned_control_journal_base;')
    emit('http2_peer_parser_transport',transport)
    core=read('http2_journaled_parser_core');cp=ports(read('http2_peer_controls'),'http2_peer_controls')
    public=[(d,f'[25*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in ports(core,'http2_journaled_parser_core')if not n.startswith('notice_')]
    public+=cfg+[p for p in cp if p[2].startswith('peer_format_')]
    stop=header_end(core,'http2_journaled_parser_core');body=core[core.index(';',stop)+1:]
    # Old core memory spans only the inherited 23 clients plus its journal. The
    # peer controller adds client 24; unchanged forward/return identities stay put.
    for n,(bits,_)in MEMORY.items():body=body.replace(f'[24*{bits}-1:0]',f'[25*{bits}-1:0]')
    start,end,params,connections=instance(body,'http2_journaled_parser_transport','forward')
    connections.update({n:n for _,_,n in cfg+life})
    body=body[:start]+named_instance('http2_peer_parser_transport',params,'forward',connections)+body[end:]
    start,end,params,old=instance(body,'http2_journaled_controls','controls');connections={}
    for d,w,n in cp:
        if n in MEMORY:connections[n]=f'{n}[23*{MEMORY[n][0]}+:2*{MEMORY[n][0]}]'
        elif n in('cfg_peer_base','cfg_peer_bytes'):connections[n]='ctl_'+n
        elif n.startswith('peer_format_'):connections[n]=n
        elif n.startswith('peer_cmd_'):
            connections[n]="0"if d=='input'else''
        else:connections[n]=old[n]
    body=body[:start]+named_instance('http2_peer_controls',params,'controls',connections)+body[end:]
    params='parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    declaration=lambda name,ps:'`timescale 1ns/1ps\n`default_nettype none\nmodule '+name+' #(\n'+params+'\n)(\n'+',\n'.join(f'{d} wire {w} {n}'for d,w,n in ps)+'\n);\n'
    core=declaration('http2_peer_parser_core',public)+'\n'.join(f'wire {w} {n};'for _,w,n in life)+'\n'+body
    emit('http2_peer_parser_core',core)
    ap=[(d,f'[16*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in public if not n.startswith('m_axis_tokens_')]
    lines=[declaration('http2_peer_parser_application',ap)];kept=[*range(1,5),*range(13,25)]
    for n,(bits,d)in MEMORY.items():
        lines.append(f'wire [25*{bits}-1:0] all_{n};')
        for compact,old in enumerate(kept):
            left=f'all_{n}[{old}*{bits}+:{bits}]';right=f'{n}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {right}={left};'if d=='output'else f'assign {left}={right};')
        if d=='input':
            for old in[0,*range(5,13)]:lines.append(f'assign all_{n}[{old}*{bits}+:{bits}]=0;')
    connections={n:'all_'+n if n in MEMORY else"1'b0"if n=='m_axis_tokens_tready'else''if n.startswith('m_axis_tokens_')else n for _,_,n in public}
    lines +=[named_instance('http2_peer_parser_core','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)','core',connections),'endmodule','`default_nettype wire','']
    emit('http2_peer_parser_application','\n'.join(lines))
    result=dict(phase='generated_actual_peer_parser',input_sha256=inputs,generated_sha256=outputs,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),parser_memory_clients=16,
        actual_notice_controller=True,server_settings_before_open_result=True,external_peer_commands_disabled=True,
        actual_cancellation_and_classification=False,full_system_complete=False)
    (root/'build/validation/http2-peer-parser-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated raw peer-state Parser with sixteen clients and automatic wire SETTINGS before OPEN')


if __name__=='__main__':main()
