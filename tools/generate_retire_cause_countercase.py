"""Isolate the first observed cause-erasure defect without claiming reset recovery."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1];source=root/'sim/cocotb/test_raw_shutdown_faults.py'
    folder=root/'build/experiments/retire-cause-countercase';folder.mkdir(exist_ok=True)
    text=replace(source.read_text(),'from cocotb.triggers import with_timeout','from cocotb.triggers import with_timeout,RisingEdge')
    observer='''
async def observe_actual_causes(d,causes):
    f=d.dut.core.forward
    while True:
        await RisingEdge(d.clk)
        if value(d,'rst'):continue
        if value(f,'ctl_result_valid') and value(f,'ctl_result_ready') and value(f,'ctl_result_memory_status'):
            causes['original']=[value(f,n) for n in ('ctl_result_status','ctl_result_detail','ctl_result_memory_status')]
        if value(f,'p_post_abort_result_valid') and value(f,'p_post_abort_result_ready'):
            causes['cleanup']=[value(f,n) for n in ('p_post_abort_status','p_post_abort_detail','p_post_abort_memory_status')]

'''
    text=replace(text,'async def bootstrap(b,reference):',observer+'async def bootstrap(b,reference):')
    text=replace(text,'    await cycles(d,5);cases=[]','    await cycles(d,5);cases=[];causes={}\n    cocotb.start_soon(observe_actual_causes(d,causes))')
    text=replace(text,"for kind,client,count in(('directory',0,9),('window',22,14),('peer',24,18)):",
        "for kind,client,count in(('directory',0,1),):")
    marker='    # A final explicit reset plus real FORMAT/OPEN proves the prior quarantined'
    assert text.count(marker)==1
    text=text.split(marker)[0]+'''
    assert len(cases)==1 and cases[0]['service']=='directory' and cases[0]['phase']==0
    assert causes['original'][2]==0x75 and causes['cleanup']==[13,0x86,0]
    public=[value(d,n) for n in ('packet_control_status','packet_control_detail','packet_control_memory_status')]
    assert public==causes['original']
    assert value(d,'transport_packet_memory_status')==0x75 and value(d,'transport_packet_http2_error')==2
    assert value(d,'stream_recovery_required') and value(d,'shutdown_recovery_required')
    assert value(d.dut.core.forward.prefill.parser.ingress,'retirement_pending')
    assert not any(b.pending) and value(d,'fabric_idle') and not value(d,'response_record_lease_active')
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data==initial
    accepted=dict(phase='passed',actual_directory_close_ack_fault=0,
        actual_original_control_error=causes['original'],actual_later_cleanup_rejection=causes['cleanup'],
        actual_public_control_error=public,actual_transport_memory_status=0x75,actual_transport_http2_error=2,
        original_cause_preserved_after_no_memory_cleanup_rejection=True,
        actual_retirement_pending_and_recovery_retained=True,new_admission_fenced=True,
        actual_memory_and_wire_promises_drained=True,reset_recovery_verified=False,
        complete_model_prefix_immutable=True,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\\n')
'''
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        one_original_counterexample_case_only=True,reset_recovery_claimed=False,actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':main()
