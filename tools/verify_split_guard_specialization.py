"""Prove the exact splitter-guard specialization for all binary input values.

This is a combinational QF_BV proof plus a complete source-difference/consumer
audit. It is not a netlist equivalence check or whole-system formal proof.
"""
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import z3


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent_path=root/'build/validation/tokenizer-hyperram-evidence/ef4d3480a8ac97d9/verified.json';parent=json.loads(parent_path.read_text())
    assert parent['key']=='ef4d3480a8ac97d9'
    old=root/'build/validation'/parent['simulation']/'sources/rtl/bpe_pretokenizer.v'
    candidate=root/'build/validation/tokenizer_hyperram_split_guard_candidate'
    new=candidate/'sources/rtl/bpe_pretokenizer.v'
    baseline=old.read_text();revised=new.read_text()
    addition=('    // The splitter guard is consumed only in SPLIT. Keep its address separate\n'
              '    // from emit reads so an emit index cannot feed splitter control timing.\n'
              "    wire [63:0] split_read_address=workspace_base+64'd8*split_rd_index;\n")
    assert revised.count(addition)==1
    restored=revised.replace(addition,'').replace('split_rd_index<scalar_count&&split_read_address+8',
                                                 'split_rd_index<scalar_count&&read_address+8')
    assert restored==baseline,'An additional unproved module change exists'
    assert sha(old)==parent['inputs_sha256']['rtl/bpe_pretokenizer.v']
    prepared=json.loads((candidate/'report.json').read_text())
    changed=[name for name,digest in prepared['inputs_sha256'].items()if digest!=parent['inputs_sha256'][name]]
    assert changed==['rtl/bpe_pretokenizer.v']
    for name,digest in prepared['inputs_sha256'].items():assert sha(candidate/'sources'/name)==digest
    for source in(baseline,revised):
        assert source.count('split_read_good')==4
        assert 'SPLIT=6'in source and 'WRITE_REQ=3'in source and 'EMIT_READ_REQ=7'in source
        assert "wire [63:0] read_address=workspace_base+64'd8*(state==SPLIT?split_rd_index:record_index);"in source
        assert 'assign mem_valid=!rst&&(state==WRITE_REQ||state==EMIT_READ_REQ||(state==SPLIT&&split_rd_valid&&split_read_good));'in source
        assert 'assign split_rd_ready=state==SPLIT&&mem_ready&&split_read_good;'in source
        block=re.search(r'\n                SPLIT:begin(.*?)\n                EMIT_READ_REQ:',source,re.S)[1]
        assert 'else if(split_rd_valid&&!split_read_good)'in block
    assert "wire split_read_good=split_rd_index<scalar_count&&read_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);"in baseline
    assert "wire split_read_good=split_rd_index<scalar_count&&split_read_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);"in revised

    state=z3.BitVec('state',4);base=z3.BitVec('workspace_base_extended',64)
    split_index=z3.BitVec('split_rd_index',32);record_index=z3.BitVec('record_index',32);count=z3.BitVec('scalar_count',32)
    # An arbitrary 64-bit limit is stronger than the actual constant
    # 64'd1 << MEMORY_ADDR_WIDTH, and permits arithmetic overflow too.
    limit=z3.BitVec('memory_limit',64)
    rst,request,ready,split_error=z3.Bools('rst split_rd_valid mem_ready split_error')
    in_split=state==6
    old_address=base+z3.BitVecVal(8,64)*z3.ZeroExt(32,z3.If(in_split,split_index,record_index))
    new_address=base+z3.BitVecVal(8,64)*z3.ZeroExt(32,split_index)
    old_good=z3.And(z3.ULT(split_index,count),z3.ULE(old_address+8,limit))
    new_good=z3.And(z3.ULT(split_index,count),z3.ULE(new_address+8,limit))
    def consumers(good):
        return [z3.And(z3.Not(rst),z3.Or(state==3,state==7,z3.And(in_split,request,good))),
                z3.And(in_split,ready,good),z3.And(in_split,z3.Not(split_error),request,z3.Not(good))]
    solver=z3.Solver();solver.set(timeout=10000)
    solver.add(z3.Or(*[z3.Xor(a,b)for a,b in zip(consumers(old_good),consumers(new_good))]))
    smt=solver.to_smt2();answer=solver.check();assert answer==z3.unsat,str(answer)
    verified=z3.Solver();verified.from_string(smt);verified.set(timeout=10000);assert verified.check()==z3.unsat
    result=dict(phase='splitter_range_guard_specialization_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_functional_audit_key=parent['key'],candidate=candidate.name,old_module_sha256=sha(old),new_module_sha256=sha(new),
        exact_only_core_rtl_change='rtl/bpe_pretokenizer.v',full_module_source_difference_checked=True,
        every_guard_consumer_audited=True,consumer_count=3,state_values_covered=16,
        address_bits=64,index_bits=32,arbitrary_memory_limit=True,geometry_assumptions=[],solver_result=str(answer),
        z3_package_version=importlib.metadata.version('z3-solver'),z3_solver_version=z3.get_version_string(),
        query_sha256=hashlib.sha256(smt.encode()).hexdigest(),
        method='QF_BV miter of all changed control decisions plus exact source/consumer audit',
        clock_cycle_latency_changed=False,reset_and_state_updates_changed=False,range_check_preserved=True,
        netlist_formal_equivalence_verified=False,whole_system_formal_induction_verified=False,full_system_complete=False,
        artifacts_sha256={path.relative_to(root).as_posix():sha(path)for path in(old,new,parent_path,candidate/'report.json',Path(__file__))})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/split-guard-specialization-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'proof.smt2').write_text(smt)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    (root/'build/validation/split-guard-specialization.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key]for key in('phase','key','solver_result','consumer_count','z3_solver_version')}))


if __name__=='__main__':main()
