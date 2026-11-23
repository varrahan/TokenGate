"""Audit frame ordering, exact wire retirement and the registered-neighbor route."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports/axis_frame_arbiter_actual_wire_frame_arbiter_fairness';executed=archive/'execution-sources'
    inputs=json.loads((archive/'inputs.json').read_text());report=json.loads((archive/'report.json').read_text())
    accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and snapshot['exit_code']==0
    assert report['tests']==1 and report['failures']==0 and report['input_sha256']==inputs
    assert report['acceptance_sha256']==sha(archive/'acceptance.json')
    for n,h in inputs.items():assert sha(executed/n)==h
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='native_frames_never_interleave_and_retire_on_wire'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert accepted['native_frames']==accepted['output_frames']==160 and accepted['sustained_beats']==32
    assert all(accepted[k]>0 for k in('first_beat_stalls','locked_gap_cycles','fairness_boundaries','wire_retirement_checks'))
    assert all(accepted[k]for k in('no_frame_interleaving','input_acceptance_is_wire_retirement','held_first_beat_and_midframe_gap_verified'))
    assert accepted['hyperframe_version']=='6.1.0'and not accepted['full_system_complete']
    assert set(closure('axis_frame_arbiter',executed))=={'axis_frame_arbiter'}
    run='axis_frame_arbiter_scu35_initial';native=root/'build/implementation/xcsu35p-sbvb625-2-e'/run;frozen=native/'sources'
    provenance=json.loads((native/'source-provenance.json').read_text())
    for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
    name='rtl/axis_frame_arbiter.v';assert sha(frozen/name)==inputs[name]==sha(source_path(root, name))
    script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
    assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
        'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
    log=source_path(root, f'build/{run}-implementation.log');assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=axis_frame_arbiter PART=xcsu35p-sbvb625-2-e'in log.read_text()
    area=resources(native/'routed_utilization.rpt');clocks=timing(native/'routed_timing.rpt')
    assert area['registers']==3 and area['bram36']==area['bram18']==area['uram']==area['dsps']==0
    assert clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
    assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(native/'routed_drc.rpt').read_text(),re.M)
    files={Path('execution')/n:executed/n for n in inputs}
    files.update({Path('reports')/n:archive/n for n in('report.json','inputs.json','snapshot.json','acceptance.json','simulation.log','build.log','results.xml')})
    files[Path('verification/verify_axis_frame_arbiter.py')]=Path(__file__);files[Path('native/implementation.log')]=log
    for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/n]=native/n
    files[Path('native/sources')/name]=frozen/name
    for n in provenance['files']:
        if not n.startswith('rtl/'):files[Path('native/sources')/n]=frozen/n
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/axis-frame-arbiter-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='native_frame_retirement_and_timing_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,execution_inputs=len(inputs),native_run=run,resources=area,timing=clocks,
        native_exact_rtl_files=1,current_primary_active_rtl_matches=True,package_paths_excluded=True,
        registered_timing_neighbors=True,no_output_queue=True,full_system_complete=False,evidence_folder=str(evidence),
        verifier_sha256=sha(Path(__file__)),routed_checkpoint_sha256=sha(native/'routed.dcp'))
    (root/'build/validation/axis-frame-arbiter.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
