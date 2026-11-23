"""Audit schema host registers with explicit native/portable evidence scopes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_two_fpga_application import closure


def varint(value):
    output=bytearray()
    while value>=128:output.append(value&127|128);value>>=7
    output.append(value);return bytes(output)


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    native=root/'build/validation/parser_schema_mmio_wrapper_native_20261122'
    linux=root/'build/wsl-reports/parser_schema_mmio_wrapper_wsl_20261122'
    n=read(native/'report.json');l=read(linux/'report.json')
    assert n['elaboration_verified'] and n['phase']=='native_parser_schema_mmio_elaborated'
    assert not n['passed'] and not n['simulation_executed']
    assert l['passed'] and l['phase']=='functional_parser_schema_mmio_verified' and l['portable_memory_backend']
    assert not l['native_vendor_runtime_verified'] and l['native_report_sha256']==sha(native/'report.json')
    assert n['inputs_sha256']==l['inputs_sha256'] and n['vectors_sha256']==l['vectors_sha256']
    for name,digest in n['inputs_sha256'].items():
        assert sha(native/'sources'/name)==sha(linux/'sources'/name)==digest,name
    assert sha(native/'schema-vectors.txt')==sha(linux/'schema-vectors.txt')==l['vectors_sha256']
    assert sha(native/'run_parser_schema_mmio_native.py')==n['driver_sha256']
    assert sha(linux/'run_parser_schema_mmio_wsl.py')==l['driver_sha256']
    modules=closure('parser_schema_mmio_decoder',native/'sources')
    assert len(modules)==13 and {'parser_schema_mmio','parser_schema_mmio_decoder','proto_json_decoder','schema_cam_lut'}<=modules.keys()
    assert n['default_decoder_parameters'] and n['decoder_modules']==11 and n['additional_mmio_modules']==2
    assert 'Built simulation snapshot parser_schema_mmio' in (native/'elaborate-stdout.log').read_text()
    assert not any('xsim.bat' in str(command) for command in n['commands'])
    assert '-DPARSER_PORTABLE_SIM' in l['commands'][0] and 'vvp'==l['commands'][1][0]
    log=(linux/'simulate.log').read_text();assert sha(linux/'simulate.log')==l['log_sha256']
    assert log.count('PARSER_SCHEMA_MMIO_TEST_PASS')==1 and not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',log,re.M)
    counts=list(map(int,re.search(r'packets=(\d+) applies=(\d+) commits=(\d+) AW_W_writes=(\d+) reads=(\d+) held_cfg=(\d+) held_tx=(\d+) held_B=(\d+) held_R=(\d+)',log).groups()))
    assert counts[:3]==[65,2,2] and counts[3]>=34 and counts[4]>=11 and counts[5]>=19 and min(counts[6:])>50
    references=read(native/'sources/reference_cases.json')['cases'];assert len(references)==16
    expected=[(0,b'{"prompt":"baseline"}',b'baseline')]
    for key,field in (('message',37),('content',2712)):
        for reference in references:
            text=bytes.fromhex(reference['prompt_utf8_hex'])
            body=json.dumps({'prompt':'old schema must not select this',key:text.decode(),'ignored':'x'*137},ensure_ascii=False,separators=(',',':')).encode()
            expected.append((0,body,text))
            expected.append((1,b'\x0a\x05wrong'+varint(field<<3|2)+varint(len(text))+text,text))
    words=iter(map(int,(linux/'schema-vectors.txt').read_text().split()));assert next(words)==65
    for mode,raw,text in expected:
        assert [next(words) for _ in range(3)]==[mode,len(raw),len(text)]
        assert bytes(next(words) for _ in range(len(raw)))==raw
        assert bytes(next(words) for _ in range(len(text)))==text
    assert next(words,None) is None and max(len(v[2]) for v in expected)==16200
    policy=root/'build/validation/parser-schema-mmio-native-policy.json';p=read(policy)
    assert p['phase']=='native_schema_simulation_execution_blocked' and not p['security_settings_changed']
    assert any(event['id']==3077 and 'parser_schema_mmio_native_v2_20261122' in event['message'] for event in p['events'])
    result=dict(phase='parser_schema_mmio_functional_and_native_elaboration_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        native_modules=13,functional_packets=65,original_prompt_references=16,schema_generations=2,maximum_prompt_bytes=16200,
        actual_axi_lite_to_decoder_schema_connected=True,independent_aw_w=True,partial_repeated_writes=True,
        held_b_r_cfg_and_text=True,invalid_apply_rejected=True,ack_after_all_cam_rows_durable=True,
        test_grant_revocation_before_schema_acceptance=True,production_decoder_defaults=True,
        native_elaboration_verified=True,native_vendor_runtime_verified=False,functional_memory_backend='PARSER_PORTABLE_SIM',
        native_execution_scope='Earlier component snapshot blocked by Code Integrity; wrapper compiled/elaborated without execution',
        full_http2_mmio_integration_verified=False,global_schema_maintenance_authority_verified=False,
        native_timing_verified=False,full_system_complete=False,counts=counts,
        compiled_rtl_sha256={name:sha(path) for name,path in modules.items()},
        native_report_sha256=sha(native/'report.json'),functional_report_sha256=sha(linux/'report.json'),
        vectors_sha256=l['vectors_sha256'],functional_log_sha256=l['log_sha256'],policy_evidence_sha256=sha(policy),
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/parser-schema-mmio-evidence'/result['key'];target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    for name,path in modules.items():
        output=target/'rtl'/path.name;output.parent.mkdir(exist_ok=True);shutil.copy2(path,output)
    shutil.copy2(linux/'simulate.log',target/'functional.log')
    shutil.copy2(linux/'schema-vectors.txt',target/'schema-vectors.txt')
    shutil.copy2(policy,target/policy.name)
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/parser-schema-mmio.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','functional_packets','native_elaboration_verified','native_vendor_runtime_verified')}))


if __name__=='__main__':main()
