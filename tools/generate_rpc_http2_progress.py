"""Give the actual RPC progress owner durable response-header/trailer phases."""
import hashlib
import json
from pathlib import Path

from generate_two_fpga_application import add_ports,rename
from generate_lifecycle_send_windows import replace_once

from rtl_paths import source_path, source_relative


TRANSPORT_PORTS=[('input','','transport_req_valid'),('output','','transport_req_ready'),
    ('input','[2:0]','transport_req_op'),('input','','transport_private_abort_proof'),
    ('output','','transport_rsp_valid'),('input','','transport_rsp_ready'),
    ('output','reg [7:0]','transport_rsp_status'),('output','reg [7:0]','transport_rsp_memory_status'),
    ('output','[1:0]','transport_result_format'),('output','','transport_header_intent'),
    ('output','','transport_headers_sent'),('output','','transport_trailer_intent'),
    ('output','','transport_trailers_sent'),('output','','transport_busy'),
    ('output','','transport_retirement_pending')]


def main():
    root=Path(__file__).resolve().parents[1];source=source_path(root, 'rtl/rpc_cancel_response_partition.v')
    text=rename(source.read_text(),'rpc_cancel_response_partition','rpc_http2_response_partition')
    # add_ports emits wire by default; the two response status registers are
    # declared separately so their driven public values remain stable under stalls.
    extra=[(d,w.replace('reg ',''),n)for d,w,n in TRANSPORT_PORTS]
    text=add_ports(text,'rpc_http2_response_partition',extra)
    for name in('transport_rsp_status','transport_rsp_memory_status'):
        text=replace_once(text,'output wire [7:0] '+name,'output reg [7:0] '+name)
    text=replace_once(text,'WRITE=14,WWAIT=15,COMMIT=16,CWAIT=17,RELEASE=18,RESULT=19;',
        'WRITE=14,WWAIT=15,COMMIT=16,CWAIT=17,RELEASE=18,RESULT=19,\n'
        '        T_CHECK=20,T_INVALIDATE=21,T_IWAIT=22,T_WRITE=23,T_WWAIT=24,T_COMMIT=25,T_CWAIT=26,T_RESULT=27;')
    text=replace_once(text,'reg [4:0] state;reg [2:0] word_index;', '''reg [4:0] state;reg [2:0] word_index;
    reg [2:0] transport_operation;reg private_abort_proof,base_ack_pending;
    wire base_complete=state==RESULT||state>=T_CHECK;
    wire base_ack=result_valid&&result_ready;
    wire transport_authority=directory_result_valid&&directory_status==0&&
        directory_generation==generation&&directory_address==rpc_address&&directory_application==application&&loaded_address_good;
    assign transport_req_ready=!rst&&state==RESULT&&!result_ready&&!base_ack_pending&&result_status==0&&!recovery_required;
    assign transport_rsp_valid=state==T_RESULT;
    assign transport_result_format=format_mode;
    assign transport_header_intent=progress[187];assign transport_headers_sent=progress[188];
    assign transport_trailer_intent=progress[189];assign transport_trailers_sent=progress[190];
    assign transport_busy=state>=T_CHECK;assign transport_retirement_pending=base_ack_pending;''')
    text=replace_once(text,'wire slot_request=state==AREAD||state==PREAD||state==INVALIDATE||state==WRITE||state==COMMIT;',
        'wire slot_request=state==AREAD||state==PREAD||state==INVALIDATE||state==WRITE||state==COMMIT||\n'
        '        state==T_INVALIDATE||state==T_WRITE||state==T_COMMIT;')
    text=replace_once(text,'wire slot_write=state==INVALIDATE||state==WRITE||state==COMMIT;',
        'wire slot_write=state==INVALIDATE||state==WRITE||state==COMMIT||state==T_INVALIDATE||state==T_WRITE||state==T_COMMIT;')
    text=replace_once(text,'state==PREAD||state==PWAIT||state==WRITE||state==WWAIT?word_index*8:0',
        'state==PREAD||state==PWAIT||state==WRITE||state==WWAIT||state==T_WRITE||state==T_WWAIT?word_index*8:0')
    text=replace_once(text,'state==INVALIDATE?72\'d0:state==COMMIT?',
        'state==INVALIDATE||state==T_INVALIDATE?72\'d0:state==COMMIT||state==T_COMMIT?')
    text=replace_once(text,'state==AWAIT||state==PWAIT||state==IWAIT||state==WWAIT||state==CWAIT)',
        'state==AWAIT||state==PWAIT||state==IWAIT||state==WWAIT||state==CWAIT||state==T_IWAIT||state==T_WWAIT||state==T_CWAIT)')
    text=replace_once(text,'assign result_valid=state==RESULT;', 'assign result_valid=base_complete&&!base_ack_pending;')
    text=replace_once(text,'assign link_r_result_ready=state==RESULT&&result_ready&&child_started;',
        'assign link_r_result_ready=state==RESULT&&(base_ack_pending||result_ready)&&child_started;')
    text=replace_once(text,'task quarantine(input [7:0] status_code);', '''task transport_failure(input [7:0] code,input [7:0] memory_code,input uncertain);
        begin transport_rsp_status<=code;transport_rsp_memory_status<=memory_code;state<=T_RESULT;
            if(uncertain)begin recovery_required<=1;recovery_address<=slot_address;end
        end
    endtask
    task quarantine(input [7:0] status_code);''')
    text=replace_once(text,'state<=IDLE;cancelled<=0;',
        'state<=IDLE;transport_operation<=0;private_abort_proof<=0;base_ack_pending<=0;transport_rsp_status<=0;transport_rsp_memory_status<=0;cancelled<=0;')
    text=replace_once(text,'if(local_tx_accepted)result_tx_emitted<=1;',
        'if(local_tx_accepted)result_tx_emitted<=1;\n'
        '        if(base_ack&&state!=RESULT)base_ack_pending<=1;')
    text=replace_once(text,"progress[191:187]!=0||progress[255:225]!=0", "progress[191]!=0||progress[255:225]!=0")
    text=replace_once(text,'else if(progress[95:64]!=model_epoch||progress[127:96]!=schema_epoch)fail(4,2,0);',
        '''else if(progress[187]||progress[189])begin recovery_required<=1;recovery_address<=progress_address;fail(4,6,0);end
            else if(!progress[188]||progress[190]&&!progress[186])fail(4,7,0);
            else if(progress[95:64]!=model_epoch||progress[127:96]!=schema_epoch)fail(4,2,0);''')
    text=replace_once(text,'else if((format_mode==2)!=protobuf_mode)fail(3,5,0);',
        'else if(format_mode==1)fail(3,6,0);else if((format_mode==2)!=protobuf_mode)fail(3,5,0);')
    text=replace_once(text,'else if((progress[222:221]==2)!=protobuf_mode)fail(3,5,0);',
        'else if(progress[222:221]==1)fail(3,6,0);else if((progress[222:221]==2)!=protobuf_mode)fail(3,5,0);')
    text=replace_once(text,"result_bytes<=child_bytes;progress[191:128]<={5'd0,eos,child_count,child_carry,ordinal+32'd1};",
        "result_bytes<=child_bytes;progress[186:128]<={eos,child_count,child_carry,ordinal+32'd1};\n"
        "                    if(ordinal==0)progress[187]<=1;")
    text=replace_once(text,'RESULT:if(result_ready)state<=IDLE;', '''RESULT:if(base_ack_pending||base_ack)begin base_ack_pending<=0;state<=IDLE;end
            else if(transport_req_valid&&transport_req_ready)begin
                transport_operation<=transport_req_op;private_abort_proof<=transport_private_abort_proof;
                transport_rsp_status<=0;transport_rsp_memory_status<=0;state<=T_CHECK;
            end
            T_CHECK:if(!transport_authority)transport_failure(2,0,0);
                else case(transport_operation)
                    // Caller has an actual successful initial-header wire result.
                    0:if(!progress[187]||progress[188]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[187]<=0;progress[188]<=1;state<=T_INVALIDATE;end
                    // Caller has witnessed the actual final DATA TLAST.
                    1:if(!progress[186]||!progress[188]||progress[187]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=1;state<=T_INVALIDATE;end
                    // Caller has the actual successful trailing HEADERS result.
                    2:if(!progress[189]||!progress[188]||progress[187]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=0;progress[190]<=1;state<=T_INVALIDATE;end
                    // Only an actual formatter abort result can prove that the
                    // initial block was private and no bytes reached the wire.
                    3:if(!private_abort_proof||!progress[187]||progress[188]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[187]<=0;state<=T_INVALIDATE;end
                    4:if(!private_abort_proof||!progress[189]||!progress[188]||progress[187]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=0;state<=T_INVALIDATE;end
                    default:transport_failure(1,0,0);
                endcase
            T_INVALIDATE:if(slot_ready)state<=T_IWAIT;
            T_IWAIT:if(slot_valid)begin
                if(slot_status!=0)transport_failure(3,slot_status,1);else begin word_index<=1;state<=T_WRITE;end
            end
            T_WRITE:if(slot_ready)state<=T_WWAIT;
            T_WWAIT:if(slot_valid)begin
                if(slot_status!=0)transport_failure(3,slot_status,1);
                else if(word_index==3)state<=T_COMMIT;else begin word_index<=word_index+1'b1;state<=T_WRITE;end
            end
            T_COMMIT:if(slot_ready)state<=T_CWAIT;
            T_CWAIT:if(slot_valid)begin if(slot_status!=0)transport_failure(3,slot_status,1);else state<=T_RESULT;end
            T_RESULT:if(transport_rsp_ready)state<=RESULT;''')
    target=source_path(root, 'rtl/rpc_http2_response_partition.v');target.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/rpc-http2-progress-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_rpc_transport_progress',input_sha256={source_relative(source, root).as_posix():sha(source),
            source_relative(Path(__file__), root).as_posix():sha(Path(__file__))},generated_sha256=sha(target),
        actual_shared_progress_memory_owner=True,raw_rpc_header_coordinator_joined=False,full_system_complete=False),indent=2)+'\n')
    print('Generated actual RPC header/trailer progress owner')


if __name__=='__main__':main()
