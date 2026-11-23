"""Prove the two existing classifier address-width warnings cannot wrap.

This proves only address arithmetic under the classifier's accepted geometry.
It does not replace transport/cancellation testing or general RTL equivalence.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

import z3


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/validation/dual_fpga_hyperram_order_v4_20261122/sources/joint/rtl/http2_missing_stream_classifier.v'
    text=source.read_text();compact=re.sub(r'\s+','',re.sub(r'//[^\n]*','',text))
    # Bind the mathematical premises to the actual frozen source expressions.
    premises=[
        'geometry_good=context_bytes>=256&&contexts>=work_floor&&contexts_end<=(64\'d1<<MEMORY_ADDR_WIDTH)&&context_limit<=contexts_end;',
        "context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);",
        "context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;",
        "contexts_end<={1'b0,contexts}+{1'b0,context_bytes};",
        'context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];',
        '.req_addr(state==HW_REQ?context_address+160:context_address),.req_bytes(4\'d8)',
        "if(!geometry_good)fail(2,1);else if(!missing_key||fence_lost||!history_fence)fail(7,1);else if(stream_id==0)fail(4,1);else state<=RAW_REQ;",
    ]
    assert all(re.sub(r'\s+','',p) in compact for p in premises)
    assert compact.count('state<=RAW_REQ;')==compact.count('state<=HW_REQ;')==1
    assert compact.count('context_address<=')==compact.count('context_full<=')==2
    cases=[]
    for width in range(8,31):
        for user_width in range(1,17):
            base,capacity,owner,floor=z3.Ints('base capacity owner floor')
            full=base+owner*256;limit=full+256;end=base+capacity
            assumptions=[base>=0,base<2**width,capacity>=256,capacity<2**(width+1),
                owner>=0,owner<2**user_width,floor>=0,floor<2**width,base>=floor,
                end<=2**width,limit<=end]
            solver=z3.Solver();solver.set(timeout=10000);solver.add(*assumptions)
            assert solver.check()==z3.sat,'Accepted geometry must be feasible'
            raw=full%(2**width)
            warning_expr=((raw+160)%(2**32))%(2**width)
            bad=z3.Or(full<0,full>=2**width,full>=2**64,limit>=2**64,end>=2**64,
                raw!=full,warning_expr!=full+160,full+8>limit,full+168>limit,full+168>2**width)
            solver.add(bad)
            outcome=solver.check()
            assert outcome==z3.unsat,(width,user_width,str(outcome))
            cases.append(dict(address_width=width,user_width=user_width,accepted_geometry_feasible=True,address_violation='unsat'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='classifier_accepted_geometry_address_bounds_proven',verified_utc=datetime.now(timezone.utc).isoformat(),
        source_sha256=sha(source),verifier_sha256=sha(Path(__file__)),z3_version=z3.get_version_string(),
        source_expressions_checked=premises,supported_parameter_combinations=len(cases),cases=cases,
        raw_address_exact=True,high_water_address_exact=True,eight_byte_reads_within_256_byte_context=True,
        address_width_warnings_reviewed=2,production_sources_changed=False,
        encoding='Exact unsigned fixed-width arithmetic expressed with integer modulo',scope='Address arithmetic under accepted geometry; not whole-module temporal formal verification',full_system_complete=False)
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/classifier-address-bounds-evidence'/result['key'];target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(source,target/source.name);shutil.copy2(Path(__file__),target/Path(__file__).name)
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/classifier-address-bounds.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','supported_parameter_combinations','address_width_warnings_reviewed')}))


if __name__=='__main__':main()
