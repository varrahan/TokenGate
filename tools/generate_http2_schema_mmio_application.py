"""Mount the audited AXI-Lite schema peripheral on the complete HTTP/2 Parser.

The established application body is copied exactly. Only its eight manual
schema pins become internal wires, driven by the real MMIO peripheral.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure

from rtl_paths import source_path


MANUAL = {'cfg_schema_valid', 'cfg_schema_ready', 'cfg_schema_index', 'cfg_schema_key',
    'cfg_schema_key_length', 'cfg_schema_json_enable', 'cfg_schema_field', 'cfg_schema_proto_enable'}
BUS = [
    ('input','[15:0]','s_axi_schema_awaddr'), ('input','','s_axi_schema_awvalid'), ('output','','s_axi_schema_awready'),
    ('input','[31:0]','s_axi_schema_wdata'), ('input','[3:0]','s_axi_schema_wstrb'),
    ('input','','s_axi_schema_wvalid'), ('output','','s_axi_schema_wready'),
    ('output','[1:0]','s_axi_schema_bresp'), ('output','','s_axi_schema_bvalid'), ('input','','s_axi_schema_bready'),
    ('input','[15:0]','s_axi_schema_araddr'), ('input','','s_axi_schema_arvalid'), ('output','','s_axi_schema_arready'),
    ('output','[31:0]','s_axi_schema_rdata'), ('output','[1:0]','s_axi_schema_rresp'),
    ('output','','s_axi_schema_rvalid'), ('input','','s_axi_schema_rready'),
    ('output','[31:0]','schema_row_epoch'), ('output','','schema_row_committed'), ('output','','schema_mmio_busy')]


def render(source):
    old_ports = ports(source, 'http2_enveloped_parser_application')
    assert MANUAL <= {n for _,_,n in old_ports}
    interface = [p for p in old_ports if p[2] not in MANUAL] + BUS
    end = source.index(');') + 2
    prefix = source[:source.index(')(\n')+3]
    prefix = prefix.replace('module http2_enveloped_parser_application', 'module http2_schema_mmio_application')
    header = prefix + ',\n'.join(f'{d} wire {w} {n}' for d,w,n in interface) + '\n);'
    declarations = '\n'.join(f'wire {w} {n};' for d,w,n in old_ports if n in MANUAL)
    mapping = dict(clk='clk', rst='rst', cfg_unlock='schema_mmio_authority', cfg_quiescent='cfg_quiescent',
        schema_epoch='schema_row_epoch', schema_committed='schema_row_committed', busy='schema_mmio_busy')
    mapping.update({n:n for n in sorted(MANUAL)})
    mapping.update({n.replace('s_axi_schema_', 's_axi_'):n for _,_,n in BUS if n.startswith('s_axi_schema_')})
    mount = '''
// Host must fence and drain all local/remote schema users before granting
// maintenance. This peripheral does not infer whole-system lease ownership.
// schema_row_epoch counts durable row applies. cfg_schema_epoch remains the
// host-published image identity: update route records under the same fence,
// then publish the matching identity before admitting the next request.
wire schema_mmio_authority;
assign schema_mmio_authority=maintenance_grant&&cfg_unlock&&!admit_packets&&!admit_messages;
parser_schema_mmio schema_registers(
''' + ',\n'.join(f'    .{n}({v})' for n,v in mapping.items()) + '\n);\n'
    # No established application handshake, state machine or data connection
    # is rewritten. The copied body includes its real core/envelope owners.
    result = header + '\n' + declarations + mount + source[end:]
    assert result.endswith(source[end:])
    assert ports(result, 'http2_schema_mmio_application') == interface
    return result, interface, source[end:]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True); args = ap.parse_args()
    assert args.name.replace('-','').replace('_','').isalnum()
    root = Path(__file__).resolve().parents[1]
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p:json.loads(p.read_text())
    audit = read(root/'build/validation/joint-hyperram-grpc.json')
    assert audit['key'] == '2e24ad59fccef5f2' and audit['both_full_models_verified']
    native = root/'build/validation/joint_hyperram_grpc_full_v5_20261122'
    report = read(native/'report.json')
    assert sha(native/'report.json') == audit['report_sha256']
    dependencies = closure('http2_enveloped_parser_application', native/'joint')
    assert len(dependencies) == 76
    for path in dependencies.values():
        assert sha(path) == report['inputs_sha256'][path.relative_to(native).as_posix()]
    mmio = source_path(root, 'rtl/parser_schema_mmio.v')
    component = read(root/'build/validation/parser-schema-mmio.json')
    assert component['key'] == '43a8b7a78f950e37'
    assert sha(mmio) == component['compiled_rtl_sha256']['parser_schema_mmio']
    parent = dependencies['http2_enveloped_parser_application']
    generated, interface, body = render(parent.read_text())
    target = root/'build/experiments'/args.name
    target.mkdir(parents=True,exist_ok=False)
    (target/'rtl').mkdir()
    for name,path in dependencies.items():
        if name != 'http2_enveloped_parser_application':shutil.copy2(path,target/'rtl'/path.name)
    shutil.copy2(mmio,target/'rtl'/mmio.name)
    output = target/'rtl/http2_schema_mmio_application.v'
    output.write_bytes(generated.encode())
    dependencies_new = closure('http2_schema_mmio_application',target)
    assert len(dependencies_new) == 77
    assert set(dependencies_new) == (set(dependencies)-{'http2_enveloped_parser_application'}) | {'http2_schema_mmio_application','parser_schema_mmio'}
    for name,path in dependencies_new.items():
        if name not in ('http2_schema_mmio_application','parser_schema_mmio'):assert sha(path) == sha(dependencies[name])
    published = source_path(root, Path('rtl') / (output.name))
    if published.exists():assert published.read_bytes() == output.read_bytes(), 'Preserve a different existing implementation'
    else:shutil.copy2(output,published)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    result = dict(phase='complete_http2_schema_mmio_application_generated',parent_joint_audit_key=audit['key'],
        component_audit_key=component['key'],parent_top_sha256=sha(parent),generated_top_sha256=sha(output),
        unchanged_application_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        removed_manual_schema_ports=sorted(MANUAL),forwarded_ports=[n for _,_,n in interface if n not in {p[2] for p in BUS}],
        new_ports=BUS,exact_parser_modules=77,host_published_schema_epoch_preserved=True,
        global_schema_maintenance_authority_verified=False,native_elaboration_verified=False,
        full_http2_mmio_integration_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)),outputs_sha256={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()})
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','exact_parser_modules','unchanged_application_body_sha256')}))


if __name__ == '__main__':main()
