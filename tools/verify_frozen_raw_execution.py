"""Validate executed full-model snapshots and their exact logical RTL closures."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


_closures={}


def verify_execution(root,name,profile,*,passed=True):
    root=Path(root);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state=(read(n) for n in ('inputs.json','report.json','snapshot.json'))
    assert state['exit_code']==(0 if passed else 1)
    assert report['phase']==('passed' if passed else 'failed') and report['profile']==state['profile']==profile
    assert report['input_sha256']==inputs
    for n,h in inputs.items():
        assert sha(source/n)==h,(name,n)
        if n.startswith('native-vendor/'):assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1])==h
    xml=ET.parse(archive/'results.xml');assert len(xml.findall('.//testcase'))==1
    if passed:
        assert not xml.findall('.//failure') and not xml.findall('.//error')
        accepted=read('acceptance.json')
        assert accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
        assert report['acceptance_sha256']==sha(archive/'acceptance.json')
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
    else:
        assert xml.findall('.//failure') and not (archive/'acceptance.json').exists()
        accepted=None
    signature=tuple(sorted((n,h) for n,h in inputs.items() if n.startswith('rtl/') and n.endswith('.v')))
    if signature not in _closures:
        _closures[signature]={top:{n:p.relative_to(source) for n,p in closure(top,source).items()}
            for top in ('http2_enveloped_parser_application','tokenizer_fpga_memory_subsystem')}
    hashes={}
    for top,label,size in (('http2_enveloped_parser_application','parser',75),('tokenizer_fpga_memory_subsystem','tokenizer',22)):
        dag=_closures[signature][top];assert len(dag)==size
        hashes[label+'_sha256']={n:sha(source/p) for n,p in dag.items()}
    record=dict(snapshot=name,profile=profile,passed=passed,inputs_sha256=inputs,acceptance=accepted,
        archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()},**hashes)
    return record,archive,source
