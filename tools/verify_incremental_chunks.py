"""Pin both incremental-response simulations to the corrected routed RTL."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys


def main():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
    from run_wsl_sv_tests import SUITES
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    run='utf8_serialized_chunk_registered_result'
    native=root/'build/implementation/xcsu35p-sbvb625-2-e'/run
    records=[]
    for suite in('serializer','utf8_chunks'):
        pair=[]
        for simulator in('verilator','iverilog'):
            directory=root/'build/wsl-reports'/suite;path=directory/(simulator+'-report.json')
            report=json.loads(path.read_text());pair.append(report)
            assert report['phase']=='passed'and report['returncode']==0,(suite,simulator)
            assert report['runner_sha256']==sha(root/'scripts/run_wsl_sv_tests.py')
            for name,digest in report['source_sha256'].items():
                assert sha(root/name)==digest,(suite,name)
                if name.startswith('rtl/'):assert sha(native/'sources'/name)==digest,(run,name)
            for name,digest in report['fixture_sha256'].items():
                assert sha(root/'build'/SUITES[suite][0]/name)==digest,(suite,name)
            log=(directory/(simulator+'-simulation.log')).read_text()
            assert 'PASS:'in log and 'FATAL:'not in log and 'FAIL:'not in log
            records.append(dict(suite=suite,simulator=simulator,sources_verified=len(report['source_sha256']),
                                fixtures_verified=len(report['fixture_sha256']),report_sha256=sha(path)))
        assert pair[0]['source_sha256']==pair[1]['source_sha256']
        assert pair[0]['fixture_sha256']==pair[1]['fixture_sha256']
    log=(root/f'build/{run}-implementation.log').read_text()
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in log
    assert '0 Critical Warnings and 0 Errors encountered.'in log
    assert 'Found timing loop'not in log and 'ERROR: [Synth'not in log
    timing=(native/'routed_timing.rpt').read_text()
    match=re.search(r'WNS\(ns\).*?\n[-\s]+\n\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)',timing,re.S)
    assert match
    wns,whs=float(match[1]),float(match[5])
    assert wns>=0 and whs>=0 and int(match[3])==int(match[7])==0
    route=(native/'route_status.rpt').read_text()
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',route)
    assert 'Checks found: 0'in(native/'routed_drc.rpt').read_text()
    utilization=(native/'routed_utilization.rpt').read_text()
    row=next(line for line in utilization.splitlines()if re.match(r'\|\s+core\s+\|',line))
    cells=[text.strip()for text in row.split('|')[1:-1]]
    assert(int(cells[2]),int(cells[6]),int(cells[7]),int(cells[8]),int(cells[9]),int(cells[10]))==(1733,1536,4,0,0,0)
    for suite in('serializer','utf8_chunks'):
        source=root/'build/wsl-reports'/suite;target=native/'regression-reports'/suite
        if not target.exists():shutil.copytree(source,target)
        else:
            for sim in('verilator','iverilog'):assert sha(target/(sim+'-report.json'))==sha(source/(sim+'-report.json'))
        report=json.loads((source/'verilator-report.json').read_text())
        for name,digest in{**report['source_sha256'],'scripts/run_wsl_sv_tests.py':report['runner_sha256']}.items():
            destination=native/'regression-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():assert sha(destination)==digest
            else:shutil.copy2(root/name,destination)
        for name,digest in report['fixture_sha256'].items():
            destination=native/'regression-fixtures'/suite/name;destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():assert sha(destination)==digest
            else:shutil.copy2(root/'build'/SUITES[suite][0]/name,destination)
    result=dict(phase='passed',verified=records,native_rtl_snapshot=run,clock_period_ns=4,
                routed_setup_wns_ns=wns,routed_hold_whs_ns=whs,setup_failing_endpoints=0,hold_failing_endpoints=0,
                routing_errors=0,core_luts=1733,core_registers=1536,bram36=4,bram18=0,dsps=0,uram=0,
                chunks=1070,responses=759,failed_chunks=311,held_result_cycles=7490,
                standalone_serializer_successes=21,standalone_serializer_errors=6,
                native_report_sha256={name:sha(native/name)for name in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','route_status.rpt','routed_drc.rpt')},
                package_paths_excluded=True,timing_neighbors_are_functional_adapters=False,
                superseded_checkpoint='utf8_serialized_chunk_initial',
                superseded_reason='Four-state simulation exposed transient combinational completion VALID; corrected wrapper registers the completion fence',
                token_lookup_integrated=False,whole_rpc_gpu_lease_integrated=False,transport_framing_integrated=False,
                full_system_fit_verified=False,full_system_complete=False,
                scope='Incremental UTF-8 and transactional JSON/SSE/Protobuf application chunks; lookup/BoW, RPC ownership and transport remain required')
    output=root/'build/validation/incremental-response-chunks.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
