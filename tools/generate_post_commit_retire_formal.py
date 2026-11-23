"""Check held-result promises on the actual extended ingress RTL."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    source = root/'build/experiments/post-commit-retire/rtl/grpc_external_directory_ingress.v'
    folder = root/'build/experiments/post-commit-retire/formal'
    folder.mkdir(exist_ok=True)
    assertions = '''
    reg formal_past_valid=0;
    wire [72:0] formal_packet={packet_committed,packet_status,packet_detail,packet_memory_status,packet_user,packet_tag};
    wire [23:0] formal_abort={post_abort_status,post_abort_detail,post_abort_memory_status};
    always @(posedge clk)begin
        formal_past_valid<=1;
        if(formal_past_valid&&!rst&&!$past(rst))begin
            if($past(packet_result_valid&&!packet_result_ready))begin
                assert(packet_result_valid);
                assert(formal_packet==$past(formal_packet));
            end
            if($past(post_abort_result_valid&&!post_abort_result_ready))begin
                assert(post_abort_result_valid);
                assert(formal_abort==$past(formal_abort));
            end
            if($past(post_abort_valid&&post_abort_ready&&
                (post_abort_user!=owner||post_abort_tag!=tag)))begin
                assert(late_active&&late_done&&retire_needed);
                assert(formal_abort==24'h073000);
                assert(!dir_req_valid);
            end
        end
        if(!rst&&late_active)begin
            assert(state==STORE_REQ||state==STORE_WAIT||state==PACKET_RESULT);
            assert(!packet_active&&!cache_active);
            if(state==STORE_REQ||state==STORE_WAIT)begin
                assert(action==A_RETIRE_FIND||action==A_RETIRE_CLOSE);
                assert(r_user==owner);
                assert(r_pool_base==packet_pool_base&&r_pool_bytes==packet_pool_bytes);
            end
        end
        // These are proved invariants, not assumptions about backend inputs.
        // They exclude impossible induction starts with a completed retirement
        // still in a directory transaction or a dirty cache after PREPARE.
        if(!rst)begin
            if(late_done)assert(late_active&&state==PACKET_RESULT);
            if(late_done_acked)assert(late_done);
            if(late_active&&!late_done)begin
                assert(retire_needed);
                assert(state==STORE_REQ||state==STORE_WAIT);
            end
            if(state==PREPARE_WAIT||state==PREPARED||state==DECISION||state==QUEUE_RESULT||state==PACKET_RESULT)
                assert(!cache_active);
            if(state==PACKET_RESULT)assert(!packet_active);
            if(retire_needed)begin
                assert(!packet_active&&!cache_active);
                assert(state==STORE_REQ||state==STORE_WAIT||state==CONTROL_RESULT||state==PACKET_RESULT||state==RECOVERY);
                if(state==STORE_REQ||state==STORE_WAIT)
                    assert(action==A_CONTROL||action==A_RETIRE_FIND||action==A_RETIRE_CLOSE);
            end
            if((state==STORE_REQ||state==STORE_WAIT)&&(action==A_RETIRE_FIND||action==A_RETIRE_CLOSE))
                assert(retire_needed);
        end
    end
'''
    text=source.read_text()
    assert text.count('endmodule')==1
    (folder/'ingress.v').write_text(text.replace('endmodule',assertions+'\nendmodule'))
    dependencies=['rtl/grpc_message_deframer.v','rtl/grpc_descriptor_queue.v','rtl/memory_command_slot.v']
    script='\n'.join([
        'read_verilog -formal -sv '+ ' '.join(dependencies)+ ' build/experiments/post-commit-retire/formal/ingress.v',
        'chparam -set ENABLE_POST_COMMIT_ABORT 1 grpc_external_directory_ingress',
        'prep -top grpc_external_directory_ingress','flatten','memory_map','opt',
        'sat -seq 2 -tempinduct -maxsteps 10 -prove-asserts -set-init-zero -verify -timeout 60',''])
    (folder/'proof.ys').write_text(script)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(generator_sha256=sha(Path(__file__)),actual_leaf_sha256=sha(source),
        dependency_sha256={n:sha(root/n) for n in dependencies},
        formal_sha256={n:sha(folder/n) for n in ('ingress.v','proof.ys')},
        feature_enabled=True,port_widths=dict(user=16,memory_address=23),
        arbitrary_inputs=True,initial_registers_zero=True,proof_completed=False)
    (folder/'generation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(folder)


if __name__=='__main__':main()
