"""Check that external window commands cannot invoke private global FORMAT."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/window-format/sim/test_raw_shutdown_faults.py'
    text=source.read_text();text=text[:text.index('    before=b.commands[22]')]
    text=replace(text,'actual_window_format_ack_faults_and_same_scope_retry','external_window_format_requires_private_transaction_authority')
    text+='''    await b.formatting();cases=[]
    for maintenance in (1,0):
        b.phase=f'external FORMAT opcode with maintenance {maintenance}'
        before=b.commands[22]
        b.set(window_req_op=12,window_req_maintenance=maintenance,window_req_user=0,window_req_stream=0,
            window_req_generation=0,window_req_record_address=0,window_req_amount=0,
            window_cfg_context_base=layout[19],window_cfg_context_bytes=layout[20],
            window_cfg_stream_base=layout[13],window_cfg_stream_bytes=layout[14],
            window_cfg_window_base=0x7f0000,window_cfg_window_bytes=layout[14]//8,window_cfg_work_floor=layout[6])
        await b.send('window_req_valid','window_req_ready');await b.wait('window_rsp_valid')
        result=tuple(value(d,n) for n in ('window_rsp_status','window_rsp_detail','window_rsp_memory_status'))
        actual=(*result,b.commands[22]-before)
        Path('failure.json').write_text(json.dumps(dict(actual_external_result=actual,maintenance=maintenance),indent=2)+'\\n')
        assert actual==(7,16,0,0),('External command reached private global FORMAT',actual)
        for _ in range(13):
            await cycles(d)
            assert value(d,'window_rsp_valid') and result==tuple(value(d,n) for n in ('window_rsp_status','window_rsp_detail','window_rsp_memory_status'))
        await b.ack('window_rsp_valid','window_rsp_ready',0)
        cases.append(dict(maintenance=maintenance,result=result,memory_commands=0))
    await b.formatting();await b.open()
    await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1);await b.admit_headers(reference,2,1)
    assert not value(d,'window_recovery_required') and not value(d,'receive_recovery_required')
    assert not any(b.pending) and image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data==initial
    result=dict(phase='passed',actual_external_format_denials=cases,actual_format_transactions=witness.result(),
        actual_authorized_format_and_admission_after_denial=True,external_denials_issue_no_window_memory=True,
        complete_model_prefix_immutable=True,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\\n')
'''
    folder=root/'build/experiments/window-authority-case';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        witness_sha256=sha(root/'sim/cocotb/window_format_witness.py'),actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':main()
