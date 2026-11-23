"""Pipeline the measured receive-ledger payload-address validation path."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_registered_frame_select import require_unit_audit, source_gate
from verify_two_fpga_application import closure


MODULE = 'http2_receive_credit_store'
NAME = 'rpc-receive-payload-pipeline-v1'


def edits():
    return [
        ('wire [63:0] expected_rpc_payload;',
         'reg [63:0] expected_rpc_payload;\nreg [63:0] rpc_payload_index,rpc_payload_product;'),
        ("    assign expected_rpc_payload={1'b0,payloads}+(({1'b0,rpc_address}-{1'b0,rpcs})>>7)*{1'b0,payload_slot_bytes};",
         '''    // Captured command geometry is stable throughout the memory reads.
    // Split subtraction, multiply and addition before RPC_CHECK consumes it.
    // Each assignment retains the original unsigned 64-bit expression width.
    always @(posedge clk)begin
        if(rst)begin rpc_payload_index<=0;rpc_payload_product<=0;expected_rpc_payload<=0;end
        else begin
            rpc_payload_index<=({1'b0,rpc_address}-{1'b0,rpcs})>>7;
            rpc_payload_product<=rpc_payload_index*{1'b0,payload_slot_bytes};
            expected_rpc_payload<={1'b0,payloads}+rpc_payload_product;
        end
    end''')]


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    parent, generation = source_gate(root)
    unit = require_unit_audit(root)
    target = root/'build/experiments'/NAME
    target.mkdir(parents=True, exist_ok=False)
    for name, digest in generation['outputs_sha256'].items():
        assert sha(parent/name) == digest
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(parent/name, path)
    name = 'joint/rtl/'+MODULE+'.v'
    original = (parent/name).read_bytes().decode()
    replacements = edits()
    if '\r\n' in original:
        replacements = [(a.replace('\n','\r\n'),b.replace('\n','\r\n')) for a,b in replacements]
    updated = original
    for before, after in replacements:
        assert updated.count(before) == 1
        updated = updated.replace(before, after)
    inverse = updated
    for before, after in reversed(replacements):
        assert inverse.count(after) == 1
        inverse = inverse.replace(after, before)
    assert inverse == original and ports(updated, MODULE) == ports(original, MODULE)
    (target/name).write_bytes(updated.encode())
    assert {n for n,h in generation['outputs_sha256'].items() if sha(target/n) != h} == {name}
    shutil.copy2(Path(__file__), target/Path(__file__).name)
    maps = {}
    for top,key,count in (
        ('http2_schema_mmio_application','canonical_parser_sha256',79),
        ('http2_enveloped_parser_application','non_mmio_parser_sha256',78),
        ('tokenizer_chiplet__tokenizer_hyperram_subsystem','canonical_tokenizer_sha256',31)):
        actual = {n:sha(p) for n,p in closure(top,target/'joint').items()}
        assert len(actual) == count
        maps[key] = actual
    assert maps['canonical_tokenizer_sha256'] == generation['canonical_tokenizer_sha256']
    report = dict(phase='receive_payload_pipeline_generated_unverified',
        parent_candidate='rpc-registered-frame-select-v1', parent_generation_sha256=sha(parent/'generation.json'),
        parent_unit_audit_key=unit['key'],
        source_edit_certificate=dict(path=name,before_sha256=sha(parent/name),after_sha256=sha(target/name),replacements=replacements),
        parser_modules=79,non_mmio_parser_modules=78,tokenizer_modules=31, **maps,
        original_command_states_and_handshake_equations_unchanged=True,
        expected_geometry_settling_cycles=3,functional_equivalence_verified=False,
        functional_runtime_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)))
    report['outputs_sha256'] = {p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    (target/'generation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('phase','parser_modules','tokenizer_modules')}))


if __name__ == '__main__':
    main()
