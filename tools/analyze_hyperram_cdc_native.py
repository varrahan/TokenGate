"""Preserve native CDC/timing findings; routing completion is not CDC signoff."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    assert re.fullmatch(r'hyperram_clock_bridge_[A-Za-z0-9_]+',args.run)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.run
    provenance=json.loads((folder/'source-provenance.json').read_text())
    for name,record in provenance['files'].items():assert sha(folder/'sources'/name)==record['sha256']
    text=(folder/'routed_cdc.rpt').read_text();counts={};groups=defaultdict(Counter);samples=defaultdict(list)
    source=destination=None
    for line in text.splitlines():
        match=re.fullmatch(r'(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.+)',line.strip())
        if match:counts[match[1]]=dict(severity=match[2],count=int(match[3]),description=match[4])
        if line.startswith('Source Clock: '):source=line.split(': ',1)[1]
        if line.startswith('Destination Clock: '):destination=line.split(': ',1)[1]
        row=re.match(r'^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+',line)
        if row:
            key=source+' -> '+destination;groups[key][row[1]]+=1
            label=key+' / '+row[1]
            if len(samples[label])<2 and row[2]=='Critical':
                fields=line.split();samples[label].append(dict(source=fields[-2],destination=fields[-1]))
    timing=(folder/'routed_timing.rpt').read_text()
    row=re.search(r'^\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s*$',timing,re.M)
    assert row
    result=dict(phase='hyperram_native_cdc_findings_recorded',observed_utc=datetime.now(timezone.utc).isoformat(),
        run=args.run,setup_slack_ns=float(row[1]),hold_slack_ns=float(row[5]),setup_failing_endpoints=int(row[3]),
        timing_met='All user specified timing constraints are met.'in timing,
        cdc_counts=counts,clock_pair_counts={k:dict(v)for k,v in groups.items()},critical_samples=dict(samples),
        source_provenance=provenance,artifacts_sha256={n:sha(folder/n)for n in('source-provenance.json',
            'routed.dcp','routed_cdc.rpt','routed_timing.rpt','routed_bus_skew.rpt','routed_exceptions.rpt',
            'routed_utilization.rpt','route_status.rpt','routed_drc.rpt')},
        cdc_signoff_verified=False,application_instantiation_verified=False,full_system_complete=False,
        analyzer_sha256=sha(Path(__file__)))
    (root/'build/validation'/(args.run+'-findings.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('run','setup_slack_ns','hold_slack_ns','timing_met','clock_pair_counts')}))


if __name__=='__main__':main()
