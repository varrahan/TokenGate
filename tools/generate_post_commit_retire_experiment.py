"""Retire actual RPC records after a late control failure, preserving held results."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import add_ports, instance, named_instance


POST = [('input','','post_abort_valid'),('output','','post_abort_ready'),
    ('input','[USER_WIDTH-1:0]','post_abort_user'),('input','[31:0]','post_abort_tag'),
    ('output','','post_abort_result_valid'),('input','','post_abort_result_ready'),
    ('output','[7:0]','post_abort_status'),('output','[7:0]','post_abort_detail'),
    ('output','[7:0]','post_abort_memory_status')]


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/semantic-drain/rtl'
    folder=root/'build/experiments/post-commit-retire'
    target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={}
    for p in previous.glob('*.v'):
        shutil.copy2(p,target/p.name);inputs[p.relative_to(root).as_posix()]=sha(p)

    def read(name):
        p=previous/(name+'.v')
        if not p.exists():p=root/'rtl'/(name+'.v')
        inputs[p.relative_to(root).as_posix()]=sha(p)
        return p.read_text()

    def feature(text,name):
        return replace(add_ports(text,name,POST),'module '+name+' #(',
            'module '+name+' #(parameter integer ENABLE_POST_COMMIT_ABORT=0,')

    def connect(text,child,label,mapping,enable):
        a,b,params,c=instance(text,child,label);c.update(mapping)
        return text[:a]+named_instance(child,'.ENABLE_POST_COMMIT_ABORT('+enable+'),'+params,label,c)+text[b:]

    name='grpc_external_directory_ingress'
    text=feature(read(name),name)
    text=replace(text,'    wire store_ready,store_valid,store_idle;',
        '    reg late_active,late_done,late_done_acked;\n'
        '    reg shadow_committed;reg [7:0] shadow_status,shadow_detail,shadow_memory;\n'
        '    assign post_abort_ready=ENABLE_POST_COMMIT_ABORT&&!rst&&state==PACKET_RESULT&&!late_active&&committed&&!packet_result_ready&&!retire_needed;\n'
        '    assign post_abort_result_valid=ENABLE_POST_COMMIT_ABORT&&late_active&&late_done&&!late_done_acked;\n'
        '    assign post_abort_status=late_active?status:0;assign post_abort_detail=late_active?detail:0;\n'
        '    assign post_abort_memory_status=late_active?memory_status:0;\n'
        '    wire store_ready,store_valid,store_idle;')
    text=replace(text,
        'assign packet_result_valid=state==PACKET_RESULT;assign packet_committed=committed;assign packet_status=status;assign packet_detail=detail;assign packet_memory_status=memory_status;',
        'assign packet_result_valid=late_active?!result_delivered:state==PACKET_RESULT;\n'
        '    assign packet_committed=late_active?shadow_committed:committed;\n'
        '    assign packet_status=late_active?shadow_status:status;assign packet_detail=late_active?shadow_detail:detail;\n'
        '    assign packet_memory_status=late_active?shadow_memory:memory_status;')
    text=replace(text,'            state<=READY;action<=0;reason<=0;',
        '            late_active<=0;late_done<=0;late_done_acked<=0;shadow_committed<=0;shadow_status<=0;shadow_detail<=0;shadow_memory<=0;\n'
        '            state<=READY;action<=0;reason<=0;')
    text=replace(text,'if(store_status==3)begin retire_needed<=0;state<=result_delivered?READY:PACKET_RESULT;end',
        'if(store_status==3)begin retire_needed<=0;\n'
        '                                if(late_active)begin late_done<=1;state<=PACKET_RESULT;end\n'
        '                                else state<=result_delivered?READY:PACKET_RESULT;end')
    old='fatal_store;state<=result_delivered?RECOVERY:PACKET_RESULT;'
    assert text.count(old)==2
    text=text.replace(old,'fatal_store;if(late_active)begin late_done<=1;state<=PACKET_RESULT;end else state<=result_delivered?RECOVERY:PACKET_RESULT;')
    text=replace(text,'                PACKET_RESULT:if(packet_result_ready)begin result_delivered<=1;state<=retire_needed?RECOVERY:READY;end',
        '''                PACKET_RESULT:if(post_abort_valid&&post_abort_ready)begin
                    // Original COMMITTED/result fields were already offered. Preserve
                    // that promise while a separate, actual error owner retires RPCs.
                    late_active<=1;late_done<=0;late_done_acked<=0;result_delivered<=0;
                    shadow_committed<=committed;shadow_status<=status;shadow_detail<=detail;shadow_memory<=memory_status;
                    packet_fatal<=1;retire_needed<=1;status<=0;detail<=0;memory_status<=0;
                    if(post_abort_user!=owner||post_abort_tag!=tag)begin
                        status<=7;detail<=8'h30;late_done<=1;
                    end else retire_search;
                end else if(!late_active&&packet_result_ready)begin result_delivered<=1;state<=retire_needed?RECOVERY:READY;end''')
    text=replace(text,'            endcase\n        end\n    end',
        '''            endcase
            if(late_active)begin
                if(packet_result_valid&&packet_result_ready)result_delivered<=1;
                if(post_abort_result_valid&&post_abort_result_ready)late_done_acked<=1;
                if(late_done&&(late_done_acked||post_abort_result_valid&&post_abort_result_ready)&&
                    (result_delivered||packet_result_valid&&packet_result_ready))begin
                    late_active<=0;late_done<=0;late_done_acked<=0;
                    state<=retire_needed?RECOVERY:READY;
                end
            end
        end
    end''')
    (target/(name+'.v')).write_text(text)

    name='grpc_shared_directory_parser'
    text=feature(read(name),name)
    mapping={n:n for _,_,n in POST}
    mapping.update(post_abort_valid='post_abort_valid&&normal_mode',post_abort_ready='engine_post_abort_ready')
    text=connect(text,'grpc_external_directory_ingress','ingress',mapping,'ENABLE_POST_COMMIT_ABORT')
    text=replace(text,'    wire engine_idle,app_idle,',
        '    wire engine_post_abort_ready;\n    assign post_abort_ready=normal_mode&&engine_post_abort_ready;\n    wire engine_idle,app_idle,')
    (target/(name+'.v')).write_text(text)

    name='grpc_shared_directory_prefill'
    text=feature(read(name),name)
    text=connect(text,'grpc_shared_directory_parser','parser',{n:n for _,_,n in POST},'ENABLE_POST_COMMIT_ABORT')
    (target/(name+'.v')).write_text(text)

    name='http2_classified_parser_transport'
    text=read(name)
    mapping={n:'p_'+n for _,_,n in POST}
    mapping.update(post_abort_user='packet_owner',post_abort_tag='packet_number')
    text=connect(text,'grpc_shared_directory_prefill','prefill',mapping,'1')
    declarations='\n'.join('wire '+w+' p_'+n+';' for _,w,n in POST if n not in ('post_abort_user','post_abort_tag'))
    declarations+='''
assign p_post_abort_valid=state==POST_ABORT_SEND;
assign p_post_abort_result_ready=state==POST_ABORT_WAIT;
'''
    text=replace(text,'CONTROL_FINISH_WAIT=26;',
        'CONTROL_FINISH_WAIT=26,POST_ABORT_DRAIN=27,POST_ABORT_SEND=28,POST_ABORT_WAIT=29;')
    text=replace(text,'WAIT_PACKET:if(p_packet_result_valid)state<=control_early_failed?CLOSE_SEND:CONTROL_FINISH_SEND;',
        'WAIT_PACKET:if(p_packet_result_valid)state<=control_early_failed?(p_packet_committed?POST_ABORT_DRAIN:CLOSE_SEND):CONTROL_FINISH_SEND;')
    text=replace(text,'CONTROL_FINISH_SEND:if(control_early_failed)state<=CLOSE_SEND;',
        'CONTROL_FINISH_SEND:if(control_early_failed)state<=p_packet_committed?POST_ABORT_DRAIN:CLOSE_SEND;')
    text=replace(text,'state<=ctl_result_status==0&&p_packet_committed?PACKET_RESULT:CLOSE_SEND;end',
        'state<=ctl_result_status==0&&p_packet_committed?PACKET_RESULT:ctl_result_status!=0&&p_packet_committed?POST_ABORT_DRAIN:CLOSE_SEND;end')
    text=replace(text,'                CLOSE_SEND:if(r_command_ready)state<=CLOSE_WAIT;',
        '''                POST_ABORT_DRAIN:if(connection_failure_drained&&!p_payload_lease_active)state<=POST_ABORT_SEND;
                POST_ABORT_SEND:if(p_post_abort_ready)state<=POST_ABORT_WAIT;
                POST_ABORT_WAIT:if(p_post_abort_result_valid)begin
                    if(p_post_abort_status!=0)begin
                        packet_control_error<=p_post_abort_status;packet_control_cause<=p_post_abort_detail;
                        packet_control_memory<=p_post_abort_memory_status;raw_status<=11;
                        raw_detail<=p_post_abort_detail;raw_memory<=p_post_abort_memory_status;raw_h2<=2;
                    end
                    state<=CLOSE_SEND;
                end
                CLOSE_SEND:if(r_command_ready)state<=CLOSE_WAIT;''')
    text=replace(text,'endmodule\n',declarations+'\nendmodule\n')
    (target/(name+'.v')).write_text(text)
    sim=folder/'sim';sim.mkdir(exist_ok=True)
    witness=root/'sim/cocotb/post_commit_retire_witness.py'
    inputs[witness.relative_to(root).as_posix()]=sha(witness)
    cases=root/'build/experiments/local-semantic-cases'
    case_manifest=json.loads((cases/'generation.json').read_text())
    inputs[(cases/'generation.json').relative_to(root).as_posix()]=sha(cases/'generation.json')
    for name,case in case_manifest['cases'].items():
        p=cases/name/'test_raw_grpc_duplex.py';inputs[p.relative_to(root).as_posix()]=sha(p)
        text=replace(p.read_text(),'from test_two_fpga_application import SeparateMemory',
            'from test_two_fpga_application import SeparateMemory\nfrom post_commit_retire_witness import PostCommitRetireWitness')
        text=replace(text,'    trace = []','    trace = []\n    retirement = PostCommitRetireWitness(d,b)')
        text=replace(text,'workers = [b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()]',
            'workers = [b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), retirement.observe()]')
        text=replace(text,'        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,',
            '        actual_post_commit_retirement=retirement.result('+str(case['expected_packet_status']==11)+'),\n'
            '        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,')
        destination=sim/name/'test_raw_grpc_duplex.py';destination.parent.mkdir(exist_ok=True);destination.write_text(text)
    p=root/'build/experiments/local-cancel/sim/test_raw_grpc_enveloped.py'
    inputs[p.relative_to(root).as_posix()]=sha(p)
    text=replace(p.read_text(),'import cocotb\n','import cocotb\nfrom post_commit_retire_witness import PostCommitRetireWitness\n')
    text=replace(text,'    b.configure();cocotb.start_soon(',
        '    retirement=PostCommitRetireWitness(d,b);cocotb.start_soon(retirement.observe())\n    b.configure();cocotb.start_soon(') if '    b.configure();cocotb.start_soon(' in text else replace(text,
        '    pool=pool_counts();', '    retirement=PostCommitRetireWitness(d,b);cocotb.start_soon(retirement.observe())\n    pool=pool_counts();')
    text=replace(text,"    accepted['actual_receive_pool_ownership']=pool",
        "    accepted['actual_post_commit_retirement']=retirement.result()\n    accepted['actual_receive_pool_ownership']=pool")
    (sim/'test_raw_grpc_enveloped.py').write_text(text)
    result=dict(phase='actual_post_commit_connection_retirement_generated',generator_sha256=sha(Path(__file__)),input_sha256=inputs,
        generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        sim_sha256={p.relative_to(sim).as_posix():sha(p) for p in sim.rglob('*.py')},
        actual_find_connection_and_close_backend_used=True,original_packet_result_promise_preserved=True,
        actual_gpu_and_payload_lease_drain_required=True,control_journal_commit_order_preserved=True,
        legacy_extension_disabled_by_default=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
