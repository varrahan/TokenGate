"""Bind parallel-byte unit tests, complete decoder comparisons and routed RTL."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text());artifacts={Path(__file__)}
    parent_path=root/'build/validation/progress-format-corpus.json';parent=read(parent_path)
    assert parent['key']=='6dd529d376e06926';artifacts.add(parent_path)
    generation_path=root/'build/experiments/json-simd/generation.json';generation=read(generation_path)
    experiment=generation_path.parent;assert generation['parent_corpus_audit_key']==parent['key']
    for name,digest in generation['outputs_sha256'].items():
        path=experiment/name;assert sha(path)==digest;artifacts.add(path)
    for name,digest in generation['inputs_sha256'].items():assert sha(root/name)==digest
    generator=root/'tools/generate_json_simd_experiment.py';assert sha(generator)==generation['generator_sha256'];artifacts.update((generator,generation_path))
    modules=closure('http2_enveloped_parser_application',experiment);assert len(modules)==76
    changed=sorted(name for name,path in modules.items()if name in parent['executed_parser_sha256']and sha(path)!=parent['executed_parser_sha256'][name])
    assert changed==['json_string_normalizer','proto_json_decoder','speculative_json_fsm']
    assert sorted(set(modules)-parent['executed_parser_sha256'].keys())==['axis_compacting_window','json_simd_scanner']
    assert sorted(parent['executed_parser_sha256'].keys()-set(modules))==['axis_byte_window']
    original=root/'build/wsl-reports/raw_envelope_progress_format_full_native_corpus/execution-sources/rtl'
    normalizer=(experiment/'rtl/json_string_normalizer.v').read_text()
    restored=normalizer.replace('output wire [7:0] packet_status,output wire ascii_discard_ready\n','output wire [7:0] packet_status\n')
    restored=restored.replace('    assign ascii_discard_ready=!rst&&state==NORMAL&&pending_count==0&&utf8_remaining==0&&status==0;\n','')
    assert restored==(original/'json_string_normalizer.v').read_text()
    old=(original/'proto_json_decoder.v').read_text();new=(experiment/'rtl/proto_json_decoder.v').read_text()
    assert old.split('    localparam ',1)[0]==new.split('    localparam ',1)[0]
    body=(experiment/'rtl/speculative_json_fsm.v').read_text()
    assert 'state==STRING&&!str_key&&!str_target&&!raw_escape&&'in body
    assert 'norm_ascii_discard_ready&&scan_plain_count!=0'in body and '!plain_discard),.s_ready(norm_ready)'in body
    for name in changed:assert sha(root/'rtl'/(name+'.v'))==parent['executed_parser_sha256'][name]
    # Rebuild the overlay from its exact input files in a short workspace path.
    with tempfile.TemporaryDirectory(prefix='js-',dir=root/'build')as temporary:
        replay=Path(temporary);assert replay.resolve().is_relative_to((root/'build').resolve())
        for name in generation['inputs_sha256']:
            destination=replay/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,destination)
        for path in(generator,root/'tools/verify_two_fpga_application.py',
                    root/'tools/generate_two_fpga_application.py',
                    root/'tools/generate_bidirectional_application.py',parent_path):
            destination=replay/path.relative_to(root);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
        rebuilt=subprocess.run([sys.executable,str(replay/'tools/generate_json_simd_experiment.py')],capture_output=True,text=True)
        assert rebuilt.returncode==0,(rebuilt.stdout,rebuilt.stderr)
        assert read(replay/'build/experiments/json-simd/generation.json')['outputs_sha256']==generation['outputs_sha256']
    unit_runs={'window':'json_simd_components_native','scanner':'json_simd_plain_scanner_native'};unit_acceptance={}
    for label,name in unit_runs.items():
        folder=root/'build/validation'/name;report=read(folder/'report.json');assert report['passed']
        rtl_name='rtl/axis_compacting_window.v'if label=='window'else'rtl/json_simd_scanner.v'
        assert report['inputs_sha256'][rtl_name]==generation['outputs_sha256'][rtl_name]
        for relative,digest in report['inputs_sha256'].items():
            path=folder/'sources'/relative;assert sha(path)==digest;artifacts.add(path)
        driver=folder/'run_json_simd_units_windows.py';assert sha(driver)==report['driver_sha256'];artifacts.add(driver)
        assert sha(folder/'json-classes.hex')==report['class_table_sha256'];artifacts.update((folder/'report.json',folder/'json-classes.hex'))
        unit_acceptance[label]=report['acceptance']['compact_window'if label=='window'else'json_scanner']
        if label=='scanner':
            assert report['only_scanner']and report['phase']=='native_json_scanner_passed'
            assert sha(folder/'report-original.json')==report['original_report_sha256'];artifacts.add(folder/'report-original.json')
        for path in folder.glob('*.log'):
            text=path.read_text(errors='replace');assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),path;artifacts.add(path)
    assert unit_acceptance['window']['source_words']==4096 and unit_acceptance['window']['resets']==3
    assert unit_acceptance['scanner']==dict(windows=18441,lanes=8,byte_values=256,counts=9)
    comparisons={}
    for case_set,name in(('mixed','json_simd_decoder_mixed_native'),('full','json_simd_decoder_full_native')):
        folder=root/'build/validation'/name;report=read(folder/'report.json')
        assert report['passed']and report['phase']=='native_scalar_and_simd_decoders_passed'
        assert sha(folder/'decoder_vectors.mem')==report['fixture_sha256'];artifacts.update((folder/'report.json',folder/'decoder_vectors.mem'))
        driver=folder/'run_json_simd_decoder_windows.py';assert sha(driver)==report['driver_sha256'];artifacts.add(driver)
        for revision,state in report['revisions'].items():
            assert state['passed']and state['phase']=='passed';frozen=folder/revision/'sources'
            for relative,digest in state['inputs_sha256'].items():
                path=frozen/relative;assert sha(path)==digest;artifacts.add(path)
                if relative.startswith('rtl/'):
                    expected=generation['outputs_sha256'][relative]if revision=='candidate'else parent['executed_parser_sha256'][Path(relative).stem]
                    assert digest==expected
                if relative.startswith('vendor/xpm_'):
                    macro=Path(relative).stem;installed=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/macro/'hdl'/(macro+'.sv')
                    assert sha(installed)==digest
            for path in(folder/revision).glob('*.log'):
                text=path.read_text(errors='replace');assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),path;artifacts.add(path)
            assert state['acceptance']['packets']==report['expected']['packets']
        baseline=report['revisions']['baseline'];candidate=report['revisions']['candidate']
        assert baseline['error_results']==candidate['error_results']and baseline['acceptance']['rx_beats']==candidate['acceptance']['rx_beats']
        assert candidate['acceptance']['max_step']==8 and candidate['acceptance']['white_bulk']>0 and candidate['acceptance']['plain_bulk']>0
        comparisons[case_set]=dict(expected=report['expected'],baseline=baseline['acceptance'],candidate=candidate['acceptance'],
            scalar_to_simd_cycle_ratio=baseline['acceptance']['cycles']/candidate['acceptance']['cycles'])
    assert comparisons['mixed']['expected']['packets']==290 and comparisons['full']['expected']['maximum_text_bytes']==16200
    native_path=root/'build/validation/json-simd-decoder-native.json';native=read(native_path)
    assert native['timing_met']and native['resource_fit']and native['exact_core_modules']==11
    assert native['run']=='decoder_au15p_json_simd_20261122'
    for name,digest in native['artifacts_sha256'].items():
        path=root/name
        if not path.exists()or sha(path)!=digest:path=root/'build/validation/json-simd-decoder-native-evidence'/native['key']/name
        assert sha(path)==digest,name
    artifacts.add(root/'build/validation/json-simd-decoder-native-evidence'/native['key']/'verified.json')
    result=dict(phase='isolated_parallel_json_decoder_functional_and_native_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_corpus_audit_key=parent['key'],exact_experimental_parser_modules=76,exact_decoder_modules=11,
        changed_parent_modules=changed,new_modules=['axis_compacting_window','json_simd_scanner'],unit_acceptance=unit_acceptance,
        comparisons=comparisons,actual_parallel_consumption_verified=True,maximum_bytes_consumed_per_clock=8,
        scalar_normalizer_existing_state_updates_unchanged=True,parser_public_ports_unchanged=True,generator_replay_verified=True,
        native_audit_key=native['key'],native_timing_verified=True,setup_slack_ns=native['setup_slack_ns'],hold_slack_ns=native['hold_slack_ns'],
        core_resources=native['core_resources'],selected_text_normalization_still_scalar=True,
        full_experimental_http2_corpus_verified=False,full_protocol_matrix_verified=False,sustained_line_rate_verified=False,
        package_timing_verified=False,physical_interfaces_verified=False,primary_existing_parser_modules_modified=False,
        full_system_complete=False,artifacts_sha256={path.relative_to(root).as_posix():sha(path)for path in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/json-simd-decoder.json';target.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/json-simd-decoder-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    for name,digest in result['artifacts_sha256'].items():
        if name.startswith('tools/'):
            destination=evidence/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,destination);assert sha(destination)==digest
    shutil.copy2(target,evidence/'verified.json')
    print(json.dumps({key:result[key]for key in('phase','key','maximum_bytes_consumed_per_clock','native_audit_key','setup_slack_ns','hold_slack_ns')}))


if __name__=='__main__':main()
