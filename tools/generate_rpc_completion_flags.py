"""Replace measured response state-class decodes with exact registered flags."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def edits():
    return [
        ('wire base_complete=state==RESULT||state>=T_CHECK;', 'reg base_complete,transport_active;'),
        ('assign transport_busy=state>=T_CHECK;', 'assign transport_busy=transport_active;'),
        ('state<=IDLE;transport_operation<=0;', 'state<=IDLE;base_complete<=0;transport_active<=0;transport_operation<=0;'),
        ('RELEASE:if(!directory_held||directory_result_valid)begin directory_held<=0;state<=RESULT;end',
         'RELEASE:if(!directory_held||directory_result_valid)begin directory_held<=0;base_complete<=1;state<=RESULT;end'),
        ('RESULT:if(base_ack_pending||base_ack)begin base_ack_pending<=0;state<=IDLE;end',
         'RESULT:if(base_ack_pending||base_ack)begin base_ack_pending<=0;base_complete<=0;state<=IDLE;end'),
        ('transport_operation<=transport_req_op;private_abort_proof<=transport_private_abort_proof;',
         'transport_active<=1;transport_operation<=transport_req_op;private_abort_proof<=transport_private_abort_proof;'),
        ('T_RESULT:if(transport_rsp_ready)state<=RESULT;',
         'T_RESULT:if(transport_rsp_ready)begin transport_active<=0;state<=RESULT;end'),
        ('default:state<=IDLE;', 'default:begin base_complete<=0;transport_active<=0;state<=IDLE;end'),
    ]


def main():
    root = Path(__file__).resolve().parents[1]
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    corpus = read(root / 'build/validation/payload-event-buffer-corpus.json')
    native = read(root / 'build/validation/payload-event-buffer-parser-native.json')
    assert corpus['key'] == 'f50480b11ead03b3' and corpus['full_native_corpus_verified']
    assert native['key'] == '56d9fecac3bc5087' and native['setup_slack_ns'] == -1.142 and not native['timing_met']
    parent = root / 'build/experiments/payload-event-buffer'
    target = root / 'build/experiments/rpc-completion-flags'
    target.mkdir(parents=True, exist_ok=False)
    for name, digest in corpus['executed_parser_sha256'].items():
        p = parent / 'rtl' / (name + '.v')
        assert sha(p) == digest
        destination = target / 'rtl' / p.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    p = target / 'rtl/rpc_http2_response_partition.v'
    original = p.read_bytes().decode()
    newline = '\r\n' if '\r\n' in original else '\n'
    old = original.replace('\r\n', '\n')
    text = old
    for before, after in edits():
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    inverse = text
    for before, after in reversed(edits()):
        assert inverse.count(after) == 1, after
        inverse = inverse.replace(after, before)
    assert inverse.replace('\n', newline).encode() == original.encode()
    assert ports(text, 'rpc_http2_response_partition') == ports(old, 'rpc_http2_response_partition')
    p.write_bytes(text.replace('\n', newline).encode())
    actual = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', target).items()}
    assert len(actual) == 77 and {n for n in actual if actual[n] != corpus['executed_parser_sha256'][n]} == {'rpc_http2_response_partition'}
    result = dict(phase='rpc_completion_flags_generated', parent_corpus_audit_key=corpus['key'],
        parent_native_audit_key=native['key'], exact_parser_modules=77,
        only_changed_existing_module='rpc_http2_response_partition', added_module=None,
        source_edit_certificate=edits(), original_newline=newline, exact_source_inverse_verified=True,
        external_ports_unchanged=True, state_and_handshake_statements_preserved=True,
        completion_flag_reference='state==RESULT||state>=T_CHECK', transport_flag_reference='state>=T_CHECK',
        functional_verified=False, native_timing_verified=False, full_system_complete=False,
        outputs_sha256={'rtl/' + n + '.v': h for n, h in actual.items()}, generator_sha256=sha(Path(__file__)))
    (target / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    print(json.dumps(dict(phase=result['phase'], exact_parser_modules=77)))


if __name__ == '__main__':
    main()
