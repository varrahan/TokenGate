"""Replace the missing-key callback with fenced reads of actual admission history."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY,named_instance


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'rtl/http2_peer_controls.v';classifier=root/'rtl/http2_missing_stream_classifier.v'
    cp=ports(source.read_text(),'http2_peer_controls');hp=ports(classifier.read_text(),'http2_missing_stream_classifier')
    public=[(d,f'[3*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in cp if not n.startswith('classify_')]
    public += [('input','','history_fence'),('output','[7:0]','history_status'),('output','[7:0]','history_detail'),
        ('output','[7:0]','history_memory_status'),('output','','history_closed'),
        ('output','[30:0]','history_last_stream'),('output','[31:0]','history_queries')]
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Missing keys are resolved against actual fenced admission history.',
        'module http2_classified_peer_controls #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join(f'{d} wire {w} {n}'for d,w,n in public),' );']
    for _,w,n in cp:
        if n.startswith('classify_')or n in('result_memory_status','control_memory_status','idle'):lines.append(f'wire {w} c_{n};')
    for _,w,n in hp:
        if n not in MEMORY and n not in('clk','rst','history_fence'):lines.append(f'wire {w} h_{n};')
    lines += ['reg [MEMORY_ADDR_WIDTH-1:0] owned_context_base,owned_work_floor;',
        'reg [MEMORY_ADDR_WIDTH:0] owned_context_bytes;reg [USER_WIDTH-1:0] owned_user;',
        'reg [7:0] history_memory;reg [31:0] query_count;',
        'assign h_req_valid=c_classify_valid;assign c_classify_ready=h_req_ready;',
        'assign h_req_missing_key=c_classify_user==owned_user;',
        'assign h_req_user=c_classify_user;assign h_req_stream=c_classify_stream;',
        'assign h_cfg_context_base=owned_context_base;assign h_cfg_context_bytes=owned_context_bytes;assign h_cfg_work_floor=owned_work_floor;',
        'assign c_classify_result_valid=h_rsp_valid;assign h_rsp_ready=c_classify_result_ready;',
        'assign c_classify_status=h_rsp_status;assign c_classify_closed=h_rsp_closed;',
        'assign history_status=h_rsp_status;assign history_detail=h_rsp_detail;assign history_memory_status=h_rsp_memory_status;',
        'assign history_closed=h_rsp_closed;assign history_last_stream=h_rsp_last_stream;assign history_queries=query_count;',
        'assign result_memory_status=c_result_memory_status!=0?c_result_memory_status:history_memory;',
        'assign control_memory_status=c_control_memory_status!=0?c_control_memory_status:history_memory;',
        'assign idle=c_idle&&h_idle;',
        'always @(posedge clk)begin',
        'if(rst)begin owned_context_base<=0;owned_context_bytes<=0;owned_work_floor<=0;owned_user<=0;history_memory<=0;query_count<=0;end',
        'else begin',
        'if(start_valid&&start_ready)begin owned_context_base<=cfg_context_base;owned_context_bytes<=cfg_context_bytes;owned_work_floor<=cfg_work_floor;owned_user<=start_user;history_memory<=0;end',
        'if(h_req_valid&&h_req_ready)query_count<=query_count+1\'b1;',
        'if(h_rsp_valid&&h_rsp_ready)history_memory<=h_rsp_memory_status;',
        'end end']
    cc={n:f'{n}[0+:2*{MEMORY[n][0]}]'if n in MEMORY else'c_'+n if n.startswith('classify_')or n in('result_memory_status','control_memory_status','idle')else n for _,_,n in cp}
    hc={n:f'{n}[2*{MEMORY[n][0]}+:{MEMORY[n][0]}]'if n in MEMORY else n if n in('clk','rst','history_fence')else'h_'+n for _,_,n in hp}
    lines +=[named_instance('http2_peer_controls','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','controls',cc),
        named_instance('http2_missing_stream_classifier','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','classifier',hc),
        'endmodule','`default_nettype wire','']
    target=root/'rtl/http2_classified_peer_controls.v';target.write_text('\n'.join(lines));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='generated_actual_classification_controls',input_sha256={str(p.relative_to(root)).replace('\\','/'):sha(p)for p in(source,classifier,Path(__file__))},
        production_sha256=sha(target),actual_parent_history_fence_required=True,shadow_directory=False,full_raw_parser_joined=False,full_system_complete=False)
    (root/'build/validation/classified-peer-controls-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated actual missing-key classifier around peer/journal controls')


if __name__=='__main__':main()
