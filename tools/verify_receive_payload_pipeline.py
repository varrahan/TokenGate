"""Independently bind the pipeline proof to the complete production controller."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from generate_receive_payload_pipeline import MODULE, NAME, edits
from run_receive_payload_pipeline_formal_wsl import proof_sources
from verify_registered_frame_select import source_gate as parent_gate
from verify_two_fpga_application import closure


def main():
    ap = argparse.ArgumentParser()
    modes=ap.add_mutually_exclusive_group()
    modes.add_argument('--smt',action='store_true')
    modes.add_argument('--compositional',action='store_true')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p:json.loads(p.read_text())
    parent, previous = parent_gate(root)
    candidate = root/'build/experiments'/NAME
    generation = read(candidate/'generation.json')
    assert generation['parent_generation_sha256'] == sha(parent/'generation.json')
    assert all(sha(candidate/n) == h for n,h in generation['outputs_sha256'].items())
    path = 'joint/rtl/'+MODULE+'.v'
    assert {n for n,h in previous['outputs_sha256'].items() if sha(candidate/n) != h} == {path}
    certificate = generation['source_edit_certificate']
    original = (parent/path).read_bytes().decode()
    replacements = edits()
    if '\r\n' in original:
        replacements = [(a.replace('\n','\r\n'),b.replace('\n','\r\n')) for a,b in replacements]
    assert certificate['replacements'] == [list(pair) for pair in replacements]
    assert certificate['path'] == path
    assert certificate['before_sha256'] == sha(parent/path)
    assert certificate['after_sha256'] == sha(candidate/path)
    expected = original
    for before,after in replacements:
        assert expected.count(before) == 1
        expected = expected.replace(before,after)
    assert expected == (candidate/path).read_bytes().decode()
    assert ports(original,MODULE) == ports(expected,MODULE)
    for top,key,count in (
        ('http2_schema_mmio_application','canonical_parser_sha256',79),
        ('http2_enveloped_parser_application','non_mmio_parser_sha256',78),
        ('tokenizer_chiplet__tokenizer_hyperram_subsystem','canonical_tokenizer_sha256',31)):
        actual = {n:sha(p) for n,p in closure(top,candidate/'joint').items()}
        assert actual == generation[key] and len(actual) == count
    assert generation['canonical_tokenizer_sha256'] == previous['canonical_tokenizer_sha256']
    folder = root/'build/wsl-reports'/('rpc_receive_payload_pipeline_compositional_v1_20261122'if args.compositional else 'rpc_receive_payload_pipeline_smt_v1_20261122' if args.smt else 'rpc_receive_payload_pipeline_v1_20261122')
    report = read(folder/'report.json')
    assert report['passed'] and report['phase'] == ('receive_payload_pipeline_compositional_equivalence_proven'if args.compositional else'receive_payload_pipeline_full_controller_equivalence_proven')
    assert report['candidate_generation_sha256'] == sha(candidate/'generation.json')
    assert report['parent_generation_sha256'] == sha(parent/'generation.json')
    assert read(folder/'generation.json') == generation
    for name,digest in report['inputs_sha256'].items():
        assert sha(folder/name) == digest
    for name,digest in report['artifacts_sha256'].items():
        assert sha(folder/name) == digest
    assert (folder/'reference-original.v').read_bytes() == (parent/path).read_bytes()
    assert (folder/'candidate-original.v').read_bytes() == (candidate/path).read_bytes()
    slot = (parent/'joint/rtl/memory_command_slot.v').read_text()
    assert slot == (candidate/'joint/rtl/memory_command_slot.v').read_text()
    if args.compositional:
        from run_receive_payload_pipeline_compositional_wsl import abstract_sources,proof_script
        sources,arithmetic_certificate,signals,outputs = abstract_sources(original.replace('\r\n','\n'),expected.replace('\r\n','\n'),slot)
        assert read(folder/'arithmetic-certificate.json') == json.loads(json.dumps(arithmetic_certificate))
        parent_proof=root/'build/wsl-reports/rpc_receive_payload_pipeline_v1_20261122'
        assert report['previous_sat_report_sha256']==sha(parent_proof/'report.json')
        assert not read(parent_proof/'report.json')['passed']
        assert 'Interrupted SAT solver: TIMEOUT!'in(parent_proof/'induction.log').read_text()
        tree=read(folder/'prepared.json')
        assert set(tree['modules'])=={'proof_top'}
        # No dynamic multiplier remains hidden in the controller proof.
        # Constant stride products may remain; they retain their real RTL.
        for cell in tree['modules']['proof_top']['cells'].values():
            if cell['type']=='$mul':
                assert any(all(bit in ('0','1') for bit in cell['connections'][port])for port in('A','B'))
        core=(candidate/'joint/rtl/http2_enveloped_parser_core.v').read_text()
        assert core.count('http2_keyed_receive_credit_store #(.ENABLE_CAPACITY(1),.ENABLE_STREAM_FORMAT(1),')==1
    else:
        sources,signals,outputs = proof_sources(original.replace('\r\n','\n'),expected.replace('\r\n','\n'),slot)
    for name,text in sources.items():
        assert (folder/name).read_text() == text
    assert report['compared_common_registers'] == [n for w,n in signals]
    assert report['all_public_outputs'] == [n for w,n in outputs]
    miter = (folder/'miter.sv').read_text()
    assert miter.count('assume(') == (6 if args.compositional else 1)
    assert 'always @*if(!past_valid)assume(rst);' in miter
    assert miter.count('assert(') == len(signals)+len(outputs)+(7 if args.compositional else 3)
    assert 'USER_WIDTH=16,MEMORY_ADDR_WIDTH=23' in miter
    assert 'if(new_internal_state==4||new_internal_state==7)assert(pipe_expected==reference_expected);' in miter
    if args.smt:
        from run_receive_payload_pipeline_smt_wsl import PREPARE
        parent_proof = root/'build/wsl-reports/rpc_receive_payload_pipeline_v1_20261122'
        assert report['previous_report_sha256'] == sha(parent_proof/'report.json') == sha(folder/'previous-sat-report.json')
        assert not read(parent_proof/'report.json')['passed']
        assert 'Interrupted SAT solver: TIMEOUT!' in (parent_proof/'induction.log').read_text()
        for name in sources:
            assert (folder/name).read_bytes() == (parent_proof/name).read_bytes()
        assert (folder/'prepare.ys').read_text() == PREPARE
        assert sha(folder/'model.smt2') == report['model_sha256']
        assert report['solver'] == 'z3' and report['bounded_base_steps'] == report['induction_steps'] == 12
        assert report['commands'][0] == ['yosys','-Q','-T','-s','prepare.ys']
        assert len(report['commands']) == 3
    for number,(label,induct) in enumerate((('reset-base',False),('induction',True)),1):
        if args.compositional:
            assert (folder/(label+'.ys')).read_text()==proof_script(induct)
            log=(folder/(label+'.log')).read_text()
            assert not re.search(r'^ERROR:',log,re.M)
            assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
            continue
        if args.smt:
            command = ['yosys-smtbmc','-s','z3','-t','12','--timeout','180','--noprogress','--presat']
            if induct:
                command.append('-i')
            command += ['--dump-vcd',label+'-counterexample.vcd','model.smt2']
            assert report['commands'][number] == command
            log = (folder/(label+'.log')).read_text()
            assert 'Status: PASSED' in log and 'Status: FAILED' not in log
            if induct:
                assert 'Temporal induction successful.' in log
            continue
        script = (folder/(label+'.ys')).read_text()
        expected_script = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1
prep -top proof_top -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 180'''
        if induct:
            expected_script += ' -tempinduct -maxsteps 10'
        assert script == expected_script+'\n'
        log = (folder/(label+'.log')).read_text()
        assert not re.search(r'^ERROR:',log,re.M)
        assert ('Induction step proven: SUCCESS!' if induct else 'SAT proof finished - no model found: SUCCESS!') in log
    result = dict(phase='receive_payload_pipeline_actual_controller_equivalence_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),candidate=NAME,
        generation_sha256=sha(candidate/'generation.json'),parent_generation_sha256=sha(parent/'generation.json'),
        sole_additional_changed_module=MODULE,all_public_outputs_compared=[n for w,n in outputs],
        common_scalar_registers_and_all_end_banks_compared=[n for w,n in signals],
        actual_unchanged_memory_command_slot_included=True,reset_base_verified=True,unbounded_induction_verified=True,
        initial_reset_required=True,later_resets_and_inputs_arbitrary=True,settling_invariants_proven=True,
        production_address_width=23,production_context_width=16,capacity_and_stream_format_enabled=True,
        word_level_smt=args.smt,earlier_sat_timeout_preserved=args.smt,
        compositional_arithmetic=args.compositional,
        other_parameter_configurations_verified=False,retained_memory_recovery_verified=False,
        actual_controller_runtime_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in folder.iterdir() if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    if args.compositional:
        result.update(phase='receive_payload_pipeline_compositional_equivalence_verified',
            earlier_sat_timeout_preserved=True,arithmetic_full_bitblast_proven=False,
            internal_arithmetic_congruence_assumptions=5,shared_arithmetic_operand_equalities_proven=True,
            source_bound_arithmetic_cut_certificate_verified=True,
            abstraction_scope='Three unchanged unsigned64 products shared over proved-equal operands; retimed unsigned64 product constrained only by same-argument consistency at same/adjacent samples. Actual multiplication is a subset. All production inputs remain arbitrary.',
            whole_controller_and_real_memory_slot_retained_except_certified_arithmetic=True)
    result['key'] = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence = root/'build/validation/receive-payload-pipeline-evidence'/result['key']
    evidence.mkdir(parents=True,exist_ok=False)
    for name in ('verify_receive_payload_pipeline.py','run_receive_payload_pipeline_formal_wsl.py',
                 'generate_receive_payload_pipeline.py','run_frame_fifo_equivalence_wsl.py'):
        shutil.copy2(root/'tools'/name,evidence/name)
    if args.smt:
        shutil.copy2(root/'tools/run_receive_payload_pipeline_smt_wsl.py',evidence/'run_receive_payload_pipeline_smt_wsl.py')
    if args.compositional:
        shutil.copy2(root/'tools/run_receive_payload_pipeline_compositional_wsl.py',evidence/'run_receive_payload_pipeline_compositional_wsl.py')
    for path in (evidence/'audit.json',root/'build/validation/receive-payload-pipeline.json'):
        path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'])))


if __name__ == '__main__':
    main()
