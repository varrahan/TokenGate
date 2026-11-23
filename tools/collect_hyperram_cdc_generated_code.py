"""Preserve generated-code evidence for the simulator's unused-pop fixture bug."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1];approved=Path.home()/'development/hardware/parser'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();records={}
    for label,name,count in (('failing_fixture','native_xpm_packet_order_trace',0),
        ('corrected_fixture','native_xpm_synchronized_reset',1)):
        obj=approved/'build/hyperram-cdc-tests'/name/'build/test/obj'
        archive=root/'build/wsl-reports'/('hyperram_cdc_'+name)
        report=json.loads((archive/'report.json').read_text())
        assert sha(obj/'Vtb_hyperram_clock_bridge')==report['binary_sha256']
        found=[p for p in obj.glob('*.cpp')if 'expected_commands.pop_front()'in p.read_text()]
        assert len(found)==1;source=found[0];text=source.read_text()
        actual=text.count('pending_responses.pop_front()');assert actual==count
        folder=root/'build/validation/hyperram-cdc-generated-code';folder.mkdir(parents=True,exist_ok=True)
        target=folder/(label+'.cpp')
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
        records[label]=dict(snapshot=name,binary_sha256=report['binary_sha256'],cpp_sha256=sha(source),
            cpp_file=source_relative(target, root).as_posix(),pending_response_pop_calls=actual,
            source_inputs_sha256=json.loads((archive/'inputs.json').read_text()))
    record=dict(phase='generated_testbench_queue_pop_difference_verified',
        observed_utc=datetime.now(timezone.utc).isoformat(),records=records,
        collector_sha256=sha(Path(__file__)),production_fifo_corruption_claimed=False)
    (root/'build/validation/hyperram-cdc-generated-code.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(phase=record['phase'],failed_pop_calls=0,corrected_pop_calls=1)))


if __name__=='__main__':main()
