"""Prove the SCU35 record-capacity guards and their capture invariant."""
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import z3


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    old=root/'build/validation/tokenizer_hyperram_rank_pipeline_candidate/sources/rtl/bpe_pretokenizer.v'
    candidate=root/'build/validation/tokenizer_hyperram_record_capacity_candidate'
    new=candidate/'sources/rtl/bpe_pretokenizer.v'
    original=old.read_text();revised=new.read_text()
    additions=[
        ('    // Complete eight-byte records that fit each independently checked limit.\n'
         '    // These limits are captured with the base/length, so request/error control\n'
         '    // does not depend on an address addition followed by an extent addition.\n'
         '    reg [MEMORY_ADDR_WIDTH:0] workspace_record_capacity,address_record_capacity;\n'),
        "            workspace_record_capacity<=0;address_record_capacity<=(64'd1<<MEMORY_ADDR_WIDTH)>>3;\n",
        ('                    workspace_record_capacity<=cfg_workspace_bytes>>3;\n'
         "                    address_record_capacity<=((64'd1<<MEMORY_ADDR_WIDTH)-{1'b0,cfg_workspace_base})>>3;\n")]
    restored=revised
    for addition in additions:
        assert restored.count(addition)==1;restored=restored.replace(addition,'')
    guards=[(
        '    wire write_good=MEMORY_ADDR_WIDTH<64?\n'
        '        scalar_count<workspace_record_capacity&&scalar_count<address_record_capacity:\n'
        "        new_write_end<=workspace_bytes&&write_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);",
        "    wire write_good=new_write_end<=workspace_bytes&&write_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);"),(
        '    wire split_read_good=split_rd_index<scalar_count&&(MEMORY_ADDR_WIDTH<64?\n'
        "        split_rd_index<address_record_capacity:split_read_address+8<=(64'd1<<MEMORY_ADDR_WIDTH));",
        "    wire split_read_good=split_rd_index<scalar_count&&split_read_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);")]
    for after,before in guards:
        assert restored.count(after)==1;restored=restored.replace(after,before)
    assert restored==original,'Unproved additional module changes'
    assert revised.count('workspace_record_capacity')==4 and revised.count('address_record_capacity')==5
    # The two capacities follow exactly the same reset/capture enables as the
    # original base/length. Complete-module restoration above checks this code.
    assert "if(rst)begin"in revised and 'if(s_axis_text_tvalid&&s_axis_text_tready)begin'in revised
    assert 'if(!sequence_active)begin'in revised
    parent=root/'build/validation/tokenizer_hyperram_rank_pipeline_candidate/report.json'
    baseline=json.loads(parent.read_text());prepared=json.loads((candidate/'report.json').read_text())
    changed=[name for name,digest in prepared['inputs_sha256'].items()if digest!=baseline['inputs_sha256'][name]]
    assert changed==['rtl/bpe_pretokenizer.v']
    for name,digest in prepared['inputs_sha256'].items():assert sha(candidate/'sources'/name)==digest
    # Scope is the actual MEMORY_ADDR_WIDTH=23 build. Registers/indices retain
    # their complete source widths, including invalid configuration values.
    cap=z3.BitVecVal(1<<23,64)
    base=z3.BitVec('base',23);size=z3.BitVec('size',24)
    count,index=z3.BitVecs('scalar_count split_index',32)
    address_capacity,workspace_capacity=z3.BitVecs('address_capacity workspace_capacity',24)
    extend=lambda value:z3.ZeroExt(64-value.size(),value)
    expected_address=(cap-extend(base))>>3
    expected_workspace=z3.LShR(extend(size),3)
    invariant=z3.And(extend(address_capacity)==expected_address,extend(workspace_capacity)==expected_workspace)
    old_write=z3.And(z3.ULE(8*extend(count)+8,extend(size)),z3.ULE(extend(base)+8*extend(count)+8,cap))
    new_write=z3.And(z3.ULT(extend(count),extend(workspace_capacity)),z3.ULT(extend(count),extend(address_capacity)))
    old_split=z3.And(z3.ULT(index,count),z3.ULE(extend(base)+8*extend(index)+8,cap))
    new_split=z3.And(z3.ULT(index,count),z3.ULT(extend(index),extend(address_capacity)))
    cfg_base=z3.BitVec('cfg_base',23);cfg_size=z3.BitVec('cfg_size',24);reset,capture=z3.Bools('reset capture')
    next_base=z3.If(reset,z3.BitVecVal(0,23),z3.If(capture,cfg_base,base))
    next_size=z3.If(reset,z3.BitVecVal(0,24),z3.If(capture,cfg_size,size))
    next_address=z3.If(reset,z3.BitVecVal((1<<23)>>3,24),z3.If(capture,z3.Extract(23,0,z3.LShR(cap-extend(cfg_base),3)),address_capacity))
    next_workspace=z3.If(reset,z3.BitVecVal(0,24),z3.If(capture,z3.LShR(cfg_size,3),workspace_capacity))
    next_invariant=z3.And(extend(next_address)==z3.LShR(cap-extend(next_base),3),
                          extend(next_workspace)==z3.LShR(extend(next_size),3))
    queries={
        'reset_establishes_invariant':z3.And(reset,z3.Not(next_invariant)),
        'capture_and_hold_preserve_invariant':z3.And(invariant,z3.Not(next_invariant)),
        'both_guards_equivalent':z3.And(invariant,z3.Or(z3.Xor(old_write,new_write),z3.Xor(old_split,new_split)))}
    smt={}
    for name,query in queries.items():
        solver=z3.SolverFor('QF_BV');solver.set(timeout=60000);solver.add(query)
        assert solver.check()==z3.unsat,(name,solver.check(),str(solver.model())if solver.check()==z3.sat else '')
        smt[name]=solver.to_smt2()
        replay=z3.SolverFor('QF_BV');replay.set(timeout=60000);replay.from_string(smt[name]);assert replay.check()==z3.unsat
    result=dict(phase='pretokenizer_record_capacity_guards_and_capture_invariant_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),candidate=candidate.name,parent_candidate=parent.parent.name,
        memory_address_width=23,base_bits=23,size_bits=24,count_and_index_bits=32,
        binary_input_values_unrestricted=True,additional_geometry_assumptions=[],
        queries={name:'unsat'for name in queries},complete_module_difference_audited=True,
        exact_only_core_rtl_change='rtl/bpe_pretokenizer.v',range_checks_preserved=True,
        state_and_handshake_updates_changed=False,cycle_latency_changed=False,
        old_module_sha256=sha(old),new_module_sha256=sha(new),
        z3_package_version=importlib.metadata.version('z3-solver'),z3_solver_version=z3.get_version_string(),
        netlist_equivalence_verified=False,whole_system_formal_induction_verified=False,
        new_candidate_functional_simulation_verified=False,full_system_complete=False,
        query_sha256={name:hashlib.sha256(text.encode()).hexdigest()for name,text in smt.items()},
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in(old,new,parent,candidate/'report.json',Path(__file__))})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/pretokenizer-record-capacity-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    for name,text in smt.items():(evidence/(name+'.smt2')).write_text(text)
    output=root/'build/validation/pretokenizer-record-capacity.json';output.write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(output,evidence/'verified.json');archive=evidence/'tools'/Path(__file__).name;archive.parent.mkdir();shutil.copy2(Path(__file__),archive)
    print(json.dumps({key:result[key]for key in('phase','key','queries','range_checks_preserved')}))


if __name__=='__main__':main()
