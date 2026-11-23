"""Supply runtime progress geometry to existing complete protocol regressions."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sources={
        'native':('native','build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py'),
        'other_connection':('duplex','build/experiments/post-retire-scope/test_raw_grpc_duplex.py'),
        'owned_gpu_drain':('shutdown-faults','build/experiments/window-authority/drain/test_raw_shutdown_faults.py'),
        'external_denial':('shutdown-faults','build/experiments/window-authority/external/test_raw_shutdown_faults.py'),
        'retained_shutdown':('shutdown-faults','build/experiments/retained-window-reset/test_raw_shutdown_faults.py'),
        'full_native_corpus':('workload','build/experiments/local-cancel/sim/test_raw_grpc_workload.py')}
    directory_cases=json.loads((root/'build/experiments/post-retire-fault-matrix/generation.json').read_text())['cases']
    sources.update({'retire_fault_'+name:('duplex','build/experiments/post-retire-fault-matrix/'+name+'/test_raw_grpc_duplex.py')for name in directory_cases})
    folder=root/'build/experiments/progress-format/regressions';folder.mkdir(parents=True,exist_ok=True);records={}
    for label,(profile,n)in sources.items():
        source=root/n;text=source.read_text();changes={}
        needle='await b.directory(4)'
        if needle in text:
            changes['public_directory_format_calls']=text.count(needle)
            text=text.replace(needle,"b.set(cfg_response_progress_base=b.reverse['response_progress']['base'],cfg_response_progress_bytes=b.reverse['response_progress']['bytes']);"+needle)
        needle='        self.configure();self.set(maintenance_grant=int(maintenance),control_maintenance=1,'
        if needle in text:
            assert text.count(needle)==1;changes['manual_format_methods']=1
            text=text.replace(needle,'        self.response_configuration(0);self.set(maintenance_grant=int(maintenance),control_maintenance=1,')
        assert changes,label
        needle='from private_window_format_witness import PrivateWindowFormatWitness as ReceiveFormatWitness'
        if needle in text:
            assert text.count(needle)==1;changes['passive_progress_witness']=1
            text=text.replace(needle,'from progress_format_witness import ProgressFormatWitness as ReceiveFormatWitness')
        fixture=folder/label/source.name;fixture.parent.mkdir(parents=True,exist_ok=True);fixture.write_text(text)
        records[label]=dict(profile=profile,source=n,source_sha256=sha(source),fixture=str(fixture.relative_to(root)).replace('\\','/'),
            fixture_sha256=sha(fixture),changes=changes)
    result=dict(generator_sha256=sha(Path(__file__)),cases=records,
        full_original_protocol_and_fault_stimulus_preserved=True,host_supplies_new_global_progress_geometry=True,
        witness_sha256=sha(root/'sim/cocotb/progress_format_witness.py'),full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(cases=len(records))))


if __name__=='__main__':main()
