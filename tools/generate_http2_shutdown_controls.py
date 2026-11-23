"""Connect actual reset results, shared history and durable incoming GOAWAY."""
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
    def swap(text,old,new,label,extra):
        start,end,params,connections=instance(text,old,label);connections.update({n:n for _,_,n in extra})
        return text[:start]+named_instance(new,params,label,connections)+text[end:]
    errors=[('input','[7:0]','cancel_detail'),('input','[7:0]','cancel_memory_status'),
        ('input','','cancel_connection_error'),('input','[31:0]','cancel_http2_error')]
    state=rename(read('http2_peer_state'),'http2_peer_state','http2_shutdown_peer_state')
    peer_fields=[('output','','rsp_goaway_received'),('output','[30:0]','rsp_goaway_last_stream'),('output','[31:0]','rsp_goaway_error')]
    state=add_ports(state,'http2_shutdown_peer_state',peer_fields)
    state=replace_once(state,'record_data[63:50]==0&&record_data[48]==server_role&&','record_data[63:51]==0&&record_data[48]==server_role&&')
    state=replace_once(state,'record_data[319:289]==0&&record_data[479:448]==0;',
        '(record_data[50]||record_data[319:289]==0&&record_data[479:448]==0);')
    state=replace_once(state,'assign rsp_ping_acks=record_data[511:480];', '''assign rsp_ping_acks=record_data[511:480];
    assign rsp_goaway_received=record_data[50];assign rsp_goaway_last_stream=record_data[319:289];
    assign rsp_goaway_error=record_data[479:448];''')
    state=replace_once(state,'else if(operation>6)fail(9,1);','else if(operation>7)fail(9,1);')
    state=replace_once(state,'                default:fail(9,1);', '''                7:begin
                    // Last-Stream-ID concerns streams initiated by this endpoint.
                    // It is never a cutoff for the opposite-direction RPC pool.
                    // Retain the lower bound if a peer repeats GOAWAY with a
                    // larger ID; a prior retry boundary cannot be expanded.
                    record_data[50]<=1;
                    if(!record_data[50]||amount[30:0]<record_data[319:289])record_data[319:289]<=amount[30:0];
                    record_data[479:448]<=payload[31:0];save;
                end
                default:fail(9,1);''')
    emit('http2_shutdown_peer_state',state)

    text=rename(read('http2_control_executor'),'http2_control_executor','http2_shutdown_control_executor')
    text=add_ports(text,'http2_shutdown_control_executor',errors)
    text=replace_once(text,'CANCEL_WAIT:if(cancel_result_valid)begin if(cancel_status!=0)fail(10,cancel_status,1,2);else state<=ACK;end',
        'CANCEL_WAIT:if(cancel_result_valid)begin if(cancel_status!=0)begin result_memory_status<=cancel_memory_status;\n'
        '                fail(cancel_status,cancel_detail,cancel_connection_error,cancel_http2_error);end else state<=ACK;end')
    emit('http2_shutdown_control_executor',text)
    text=rename(read('http2_journaled_controls'),'http2_journaled_controls','http2_shutdown_journaled_controls')
    text=add_ports(text,'http2_shutdown_journaled_controls',errors)
    text=swap(text,'http2_control_executor','http2_shutdown_control_executor','executor',errors)
    emit('http2_shutdown_journaled_controls',text)

    goaway=[('input','','goaway_req_valid'),('output','','goaway_req_ready'),('input','[USER_WIDTH-1:0]','goaway_user'),
        ('input','[30:0]','goaway_last_stream'),('input','[31:0]','goaway_error'),('output','','goaway_rsp_valid'),('input','','goaway_rsp_ready')]
    for d,w,n in ports(state,'http2_shutdown_peer_state'):
        if n.startswith('rsp_')and n in('rsp_status','rsp_detail','rsp_memory_status','rsp_connection_error','rsp_http2_error','rsp_op','rsp_user'):
            goaway.append((d,w,'goaway_'+n))
    goaway +=[(d,w,'peer_'+n[4:])for d,w,n in peer_fields]
    text=rename(read('http2_peer_controls'),'http2_peer_controls','http2_shutdown_peer_controls')
    text=add_ports(text,'http2_shutdown_peer_controls',errors+goaway)
    text=swap(text,'http2_journaled_controls','http2_shutdown_journaled_controls','journaled',errors)
    start,end,params,connections=instance(text,'http2_peer_state','peer')
    connections.update({n:'peer_'+n[4:]for _,_,n in peer_fields})
    text=text[:start]+named_instance('http2_shutdown_peer_state',params,'peer',connections)+text[end:]
    text=replace_once(text,'assign p_req_valid=peer_owner==1?', 'assign p_req_valid=peer_owner==9?goaway_req_valid:peer_owner==1?')
    text=replace_once(text,'assign p_req_op=peer_owner==1?', 'assign p_req_op=peer_owner==9?4\'d7:peer_owner==1?')
    text=replace_once(text,'assign p_req_user=peer_owner==1?', 'assign p_req_user=peer_owner==9?goaway_user:peer_owner==1?')
    text=replace_once(text,'assign p_req_authority=peer_owner==3?',
        'assign p_req_authority=peer_owner==9?(owned_authority&&goaway_user==format_user):peer_owner==3?')
    text=replace_once(text,'assign p_req_value=peer_owner==1?', 'assign p_req_value=peer_owner==9?{1\'b0,goaway_last_stream}:peer_owner==1?')
    text=replace_once(text,'assign p_req_payload=peer_owner==1?', 'assign p_req_payload=peer_owner==9?{32\'d0,goaway_error}:peer_owner==1?')
    text=replace_once(text,'assign p_rsp_ready=peer_owner==2?', 'assign p_rsp_ready=peer_owner==10?goaway_rsp_ready:peer_owner==2?')
    text=replace_once(text,'else if(j_notice_valid)peer_owner<=1;else if(peer_cmd_req_valid&&j_idle&&!start_valid)peer_owner<=3;',
        'else if(j_notice_valid)peer_owner<=1;else if(goaway_req_valid&&!start_valid)peer_owner<=9;else if(peer_cmd_req_valid&&j_idle&&!start_valid)peer_owner<=3;')
    text=replace_once(text,'default:peer_owner<=0;endcase end end', '''9:if(goaway_req_valid&&p_req_ready)peer_owner<=10;
10:if(p_rsp_valid&&goaway_rsp_ready)peer_owner<=0;
default:peer_owner<=0;endcase end end''')
    extra=['assign goaway_req_ready=peer_owner==9&&p_req_ready;','assign goaway_rsp_valid=peer_owner==10&&p_rsp_valid;']
    extra +=[f'assign {n}=p_{n[7:]};'for _,_,n in goaway if n.startswith('goaway_rsp_')and n not in('goaway_rsp_valid','goaway_rsp_ready')]
    text=text.replace('endmodule','\n'.join(extra)+'\nendmodule');emit('http2_shutdown_peer_controls',text)

    classify=[('input','','shutdown_classify_valid'),('output','','shutdown_classify_ready'),
        ('input','[USER_WIDTH-1:0]','shutdown_classify_user'),('input','[30:0]','shutdown_classify_stream'),
        ('output','','shutdown_classify_rsp_valid'),('input','','shutdown_classify_rsp_ready')]
    classifier=read('http2_missing_stream_classifier')
    for d,w,n in ports(classifier,'http2_missing_stream_classifier'):
        if n.startswith('rsp_')and n not in('rsp_valid','rsp_ready'):classify.append((d,w,'shutdown_classify_'+n))
    text=rename(read('http2_classified_peer_controls'),'http2_classified_peer_controls','http2_shutdown_classified_controls')
    text=add_ports(text,'http2_shutdown_classified_controls',errors+goaway+classify)
    text=swap(text,'http2_peer_controls','http2_shutdown_peer_controls','controls',errors+goaway)
    old='''assign h_req_valid=c_classify_valid;assign c_classify_ready=h_req_ready;
assign h_req_missing_key=c_classify_user==owned_user;
assign h_req_user=c_classify_user;assign h_req_stream=c_classify_stream;'''
    new='''reg [2:0] classifier_owner;
wire shutdown_history=classifier_owner==3||classifier_owner==4;
assign h_req_valid=classifier_owner==1?c_classify_valid:classifier_owner==3&&shutdown_classify_valid;
assign c_classify_ready=classifier_owner==1&&h_req_ready;
assign shutdown_classify_ready=classifier_owner==3&&h_req_ready;
assign h_req_user=shutdown_history?shutdown_classify_user:c_classify_user;
assign h_req_stream=shutdown_history?shutdown_classify_stream:c_classify_stream;
assign h_req_missing_key=h_req_user==owned_user;
always @(posedge clk)begin
if(rst)classifier_owner<=0;else case(classifier_owner)
0:if(shutdown_classify_valid)classifier_owner<=3;else if(c_classify_valid)classifier_owner<=1;
1:if(c_classify_valid&&h_req_ready)classifier_owner<=2;
2:if(h_rsp_valid&&c_classify_result_ready)classifier_owner<=0;
3:if(shutdown_classify_valid&&h_req_ready)classifier_owner<=4;
4:if(h_rsp_valid&&shutdown_classify_rsp_ready)classifier_owner<=0;
default:classifier_owner<=0;endcase end'''
    text=replace_once(text,old,new)
    text=replace_once(text,'assign c_classify_result_valid=h_rsp_valid;assign h_rsp_ready=c_classify_result_ready;',
        'assign c_classify_result_valid=classifier_owner==2&&h_rsp_valid;\n'
        'assign shutdown_classify_rsp_valid=classifier_owner==4&&h_rsp_valid;\n'
        'assign h_rsp_ready=classifier_owner==2?c_classify_result_ready:classifier_owner==4&&shutdown_classify_rsp_ready;')
    extra=[f'assign {n}=h_{n[len("shutdown_classify_"):]};'for _,_,n in classify
        if n.startswith('shutdown_classify_rsp_')and n not in('shutdown_classify_rsp_valid','shutdown_classify_rsp_ready')]
    text=text.replace('endmodule','\n'.join(extra)+'\nendmodule');emit('http2_shutdown_classified_controls',text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/http2-shutdown-controls-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_shutdown_control_owners',input_sha256={source_relative(p, root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in targets},
        shared_actual_history_classifier=True,durable_goaway_without_odd_rpc_cutoff=True,full_system_complete=False),indent=2)+'\n')
    print('Generated shutdown executor, shared history arbitration and durable incoming GOAWAY owner')


if __name__=='__main__':main()
