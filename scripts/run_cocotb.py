"""Run cocotb in the user-selected WSL workspace; retain test provenance."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from cocotb_tools.runner import get_runner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path, source_relative


def main():
    parser=argparse.ArgumentParser();parser.add_argument("suite",choices=("mmio","mmio_system","http2_prefill","generated_response","rpc_response","rpc_grpc","rpc_leased","rpc_durable","rpc_keyed","bidirectional","two_fpga","two_fpga_memory","two_fpga_framed","two_fpga_controlled","two_fpga_initialized","two_fpga_journaled","two_fpga_peer","two_fpga_classified","two_fpga_shutdown"));parser.add_argument("--simulator",default="icarus",choices=("icarus","verilator"))
    parser.add_argument('--test-module',choices=('test_two_fpga_initialized','test_two_fpga_bootstrap','test_raw_journaled_controls','test_raw_peer_controls','test_raw_classified_controls','test_raw_shutdown_controls','test_raw_shutdown_faults'))
    args=parser.parse_args();selected_suite=args.suite;shutdown_suite=selected_suite=='two_fpga_shutdown'
    # The shutdown join retains the classified profile's exact model/layout.
    if shutdown_suite:args.suite='two_fpga_classified'
    root=Path(__file__).resolve().parents[1];build=root/"build"/("cocotb-"+selected_suite);build.mkdir(parents=True,exist_ok=True)
    sources=[source_path(root, "rtl/tokenizer_mmio.v")];top="tokenizer_mmio";module="test_tokenizer_mmio";defines={}
    if args.suite=="mmio_system":
        from run_wsl_sv_tests import SUITES
        sources += [source_path(root, name) for name in SUITES["tokenizer_subsystem"][2]if name.startswith("rtl/")]
        sources.append(source_path(root, "rtl/scu35_tokenizer_mmio_subsystem.v"));top="scu35_tokenizer_mmio_subsystem";module="test_tokenizer_mmio_system";defines={"PARSER_PORTABLE_SIM":1}
    fixtures=[];extra_sources=[];extra_env={}
    if args.suite in('http2_prefill','bidirectional','two_fpga','two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
        from run_wsl_sv_tests import SUITES
        sources=[source_path(root, name) for name in SUITES["http2_prefill"][2]if name.startswith("rtl/")]
        joint=args.suite in('bidirectional','two_fpga','two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified')
        if joint:
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_bidirectional_application','rpc_generated_response','generated_response_chunk',
                'detokenizer_engine','utf8_serialized_chunk','utf8_chunk_decoder','proto_json_serializer','json_escape_encoder'))
            sources=list(dict.fromkeys(sources))
        top='cocotb_bidirectional_application_top'if joint else'cocotb_http2_prefill_top'
        sources.append(source_path(root, 'sim/'+top+'.sv'))
        module='test_bidirectional_application'if joint else'test_http2_prefill';defines={'PARSER_PORTABLE_SIM':1}
        fixture_root=source_path(root, 'build/bidirectional-fixtures'if joint else'build/cocotb-prefill-fixtures')
        fixtures=[fixture_root/name for name in("memory.mem","layout.txt","vectors.txt","runtime_plan.json","fixture_manifest.json","reference_cases.json")]
        if any(not path.is_file()for path in fixtures):raise SystemExit("Generate the complete native-reference cocotb prefill fixtures first")
        metadata=json.loads((fixture_root/"fixture_manifest.json").read_text())
        generator=root/"tools/generate_http2_prefill_vectors.py"
        if metadata["generator_sha256"]!=hashlib.sha256(generator.read_bytes()).hexdigest():raise SystemExit("Native reference fixtures do not match the current compiler")
        extra_sources=[source_path(root, name) for name in("sim/cocotb/test_tokenizer_mmio.py","sim/cocotb/test_tokenizer_mmio_system.py",
                       "tools/generate_cocotb_prefill_harness.py","tools/generate_http2_prefill_vectors.py","tools/runtime_memory_plan.py")]
        extra_env["PARSER_PREFILL_FIXTURES"]=str(fixture_root)
        if joint:
            fixtures.append(fixture_root/'response_reference.json')
            reverse=json.loads((fixture_root/'response_reference.json').read_text())
            generator=root/'tools/generate_bidirectional_vectors.py'
            if reverse['generator_sha256']!=hashlib.sha256(generator.read_bytes()).hexdigest():raise SystemExit('Native return references do not match compiler')
            extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_http2_prefill.py','tools/generate_bidirectional_application.py',
                'tools/generate_bidirectional_vectors.py','tools/generate_rpc_response_vectors.py'))
            extra_env['PARSER_BIDIRECTIONAL_FIXTURES']=str(fixture_root)
        if args.suite in('two_fpga','two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_bidirectional_application_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('grpc_prefill_parser_partition',
                'http2_parser_transport_partition','inverse_tokenizer_partition','rpc_response_parser_partition',
                'http2_parser_partition_core','http2_parser_fpga_application','tokenizer_fpga_application'))
            top='cocotb_two_fpga_application_top';module='test_two_fpga_application'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_bidirectional_application.py',
                'tools/generate_two_fpga_application.py','tools/generate_two_fpga_harness.py'))
        if args.suite in('two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_application_top.sv']
            sources.append(source_path(root, 'rtl/tokenizer_fpga_memory_subsystem.v'))
            top='cocotb_two_fpga_memory_top';module='test_two_fpga_memory'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_two_fpga_application.py','tools/generate_tokenizer_fpga_memory.py'))
        if args.suite in('two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_memory_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('grpc_http2_response_framer','rpc_grpc_parser_response',
                'grpc_leased_stream_store','rpc_grpc_leased_return','rpc_grpc_scheduled_return','grpc_external_directory_ingress',
                'grpc_shared_directory_parser','grpc_shared_directory_prefill','http2_shared_directory_transport',
                'http2_framed_parser_core','http2_framed_parser_application'))
            top='cocotb_two_fpga_framed_top';module='test_two_fpga_framed'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            fixtures.append(fixture_root/'framed_reference.json')
            extra_sources.extend(source_path(root, name) for name in('tools/generate_http2_framed_parser.py',
                'tools/generate_rpc_grpc_parser_response.py','tools/generate_leased_stream_store.py',
                'tools/generate_rpc_grpc_leased_return.py','tools/generate_two_fpga_framed_vectors.py'))
        if args.suite in('two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_framed_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_control_event_fork','http2_controlled_hpack_ingress',
                'http2_controlled_parser_transport','http2_controlled_parser_core','http2_controlled_parser_application'))
            top='cocotb_two_fpga_controlled_top';module='test_two_fpga_controlled'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_two_fpga_framed.py','tools/generate_controlled_hpack.py'))
        if args.suite in('two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_controlled_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_initialized_parser_transport',
                'http2_initialized_parser_core','http2_initialized_parser_application','http2_windowed_rpc_admission',
                'rpc_grpc_initialized_return','rpc_grpc_keyed_return','http2_keyed_frame_grants',
                'http2_keyed_send_window_store','http2_owned_keyed_windows','grpc_pool_locked_stream_store'))
            top='cocotb_two_fpga_initialized_top';module='test_two_fpga_initialized'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            extra_sources.extend(source_path(root, name) for name in('tools/generate_http2_initialized_parser.py',
                'tools/generate_windowed_rpc_admission.py','tools/generate_rpc_durable_return.py',
                'tools/generate_keyed_send_windows.py','tools/generate_pool_locked_store.py',
                'tools/generate_lifecycle_send_windows.py','sim/cocotb/test_two_fpga_controlled.py'))
        if args.suite in('two_fpga_journaled','two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_initialized_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_journaled_parser_transport','http2_journaled_parser_core',
                'http2_journaled_parser_application','http2_control_journal','http2_control_executor','http2_journaled_controls','axis_frame_arbiter'))
            top='cocotb_two_fpga_journaled_top';module='test_two_fpga_journaled'
            sources.append(source_path(root, 'sim/'+top+'.sv'));fixtures.append(fixture_root/'journaled_control_reference.json')
            extra_sources.extend(source_path(root, name) for name in('tools/generate_http2_journaled_parser.py','tools/generate_journaled_controls.py',
                'tools/generate_raw_journal_control_vectors.py','sim/cocotb/test_two_fpga_initialized.py','sim/cocotb/test_two_fpga_bootstrap.py'))
        if args.suite in('two_fpga_peer','two_fpga_classified'):
            sources=[p for p in sources if p.name!='cocotb_two_fpga_journaled_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_peer_parser_transport','http2_peer_parser_core',
                'http2_peer_parser_application','http2_peer_controls','http2_peer_state'))
            top='cocotb_two_fpga_peer_top';module='test_two_fpga_peer'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            extra_sources.extend(source_path(root, name) for name in('tools/generate_http2_peer_parser.py','tools/generate_peer_controls.py',
                'sim/cocotb/test_raw_journaled_controls.py','sim/cocotb/test_two_fpga_journaled.py'))
        if args.suite=='two_fpga_classified':
            sources=[p for p in sources if p.name!='cocotb_two_fpga_peer_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_classified_parser_transport','http2_classified_parser_core',
                'http2_classified_parser_application','http2_classified_peer_controls','http2_missing_stream_classifier'))
            top='cocotb_two_fpga_classified_top';module='test_two_fpga_classified'
            sources.append(source_path(root, 'sim/'+top+'.sv'));fixtures.append(root/'build/http2-classifier-fixtures/cases.json')
            extra_sources.extend(source_path(root, name) for name in('tools/generate_http2_classified_parser.py','tools/generate_classified_peer_controls.py',
                'tools/generate_missing_stream_vectors.py','sim/cocotb/test_raw_peer_controls.py','sim/cocotb/test_two_fpga_peer.py'))
        extra_sources.append(root/'scripts/run_wsl_sv_tests.py')
    if args.suite in('generated_response','rpc_response','rpc_grpc','rpc_leased','rpc_durable','rpc_keyed'):
        sources=[source_path(root, 'rtl/'+name+'.v')for name in(
            'generated_response_chunk','detokenizer_engine','bow_axi_bridge','axis_skid_buffer',
            'utf8_serialized_chunk','utf8_chunk_decoder','proto_json_serializer','axis_byte_unpacker',
            'axis_byte_packer','json_escape_encoder','programmable_table_ram','external_memory_cache',
            'external_memory_arbiter','external_memory_fabric')]
        rpc=args.suite in('rpc_response','rpc_grpc','rpc_leased','rpc_durable','rpc_keyed')
        if rpc:sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('rpc_generated_response','grpc_stream_store','memory_command_slot'))
        top='cocotb_rpc_response_top'if rpc else'cocotb_generated_response_top'
        sources.append(source_path(root, 'sim/'+top+'.sv'))
        module='test_rpc_response'if rpc else'test_generated_response';defines={'PARSER_PORTABLE_SIM':1}
        fixture_root=source_path(root, 'build/rpc-grpc-fixtures'if args.suite in('rpc_grpc','rpc_leased','rpc_durable','rpc_keyed')else'build/rpc-response-fixtures'if rpc else'build/generated-response-fixtures')
        fixtures=[fixture_root/name for name in(('memory.bin','model_manifest.json','rpc_cases.json')if rpc else('memory.bin','model_manifest.json','cases.json','fixture_manifest.json'))]
        if any(not path.is_file()for path in fixtures):raise SystemExit('Generate the complete native-reference response fixtures first')
        metadata=json.loads((fixture_root/('rpc_cases.json'if rpc else'fixture_manifest.json')).read_text())
        generator=source_path(root, 'tools/generate_rpc_response_vectors.py'if rpc else'tools/generate_token_response_vectors.py')
        if metadata['generator_sha256']!=hashlib.sha256(generator.read_bytes()).hexdigest():raise SystemExit('Native response fixtures do not match the current compiler')
        extra_sources=[source_path(root, name) for name in('sim/cocotb/test_tokenizer_mmio.py','sim/cocotb/test_tokenizer_mmio_system.py')]
        extra_sources.extend((generator,source_path(root, 'tools/generate_cocotb_rpc_response_harness.py'if rpc else'tools/generate_cocotb_response_harness.py')))
        extra_env['PARSER_RPC_RESPONSE_FIXTURES'if rpc else'PARSER_RESPONSE_FIXTURES']=str(fixture_root)
        if args.suite in('rpc_grpc','rpc_leased','rpc_durable','rpc_keyed'):
            sources=[p for p in sources if p.name!='cocotb_rpc_response_top.sv']
            sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('rpc_response_parser_partition',
                'inverse_tokenizer_partition','rpc_grpc_parser_response','grpc_http2_response_framer'))
            top='cocotb_rpc_grpc_top';module='test_rpc_grpc_response'
            sources.append(source_path(root, 'sim/'+top+'.sv'))
            fixture_root=root/'build/rpc-grpc-fixtures'
            fixtures=[fixture_root/name for name in('memory.bin','model_manifest.json','rpc_cases.json','frame_cases.json')]
            framing=json.loads((fixture_root/'frame_cases.json').read_text())
            frame_generator=root/'tools/generate_rpc_grpc_vectors.py'
            if framing['generator_sha256']!=hashlib.sha256(frame_generator.read_bytes()).hexdigest():raise SystemExit('Framed RPC references do not match compiler')
            extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_rpc_response.py','tools/generate_rpc_grpc_vectors.py',
                'tools/generate_cocotb_rpc_grpc_harness.py','tools/generate_rpc_grpc_parser_response.py','tools/generate_two_fpga_application.py'))
            extra_env['PARSER_RPC_RESPONSE_FIXTURES']=str(fixture_root)
            if args.suite in('rpc_leased','rpc_durable','rpc_keyed'):
                sources=[p for p in sources if p.name!='cocotb_rpc_grpc_top.sv']
                sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('grpc_leased_stream_store','rpc_grpc_leased_return'))
                top='cocotb_rpc_leased_top';module='test_rpc_leased_response'
                sources.append(source_path(root, 'sim/'+top+'.sv'))
                extra_sources.extend(source_path(root, name) for name in('sim/cocotb/test_rpc_grpc_response.py',
                    'tools/generate_leased_stream_store.py','tools/generate_rpc_grpc_leased_return.py','tools/generate_cocotb_rpc_leased_harness.py'))
            if args.suite in('rpc_durable','rpc_keyed'):
                sources=[p for p in sources if p.name!='cocotb_rpc_leased_top.sv']
                sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('grpc_pool_locked_stream_store',
                    'http2_owned_lifecycle_windows','http2_lifecycle_send_window_store',
                    'http2_durable_frame_grants','rpc_grpc_durable_return'))
                top='cocotb_rpc_durable_top';module='test_rpc_durable_response'
                sources.append(source_path(root, 'sim/'+top+'.sv'))
                extra_sources.extend(source_path(root, name) for name in('tools/generate_pool_locked_store.py',
                    'tools/generate_owned_send_windows.py','tools/generate_lifecycle_send_windows.py',
                    'tools/generate_durable_window_framer.py','tools/generate_rpc_durable_return.py',
                    'tools/generate_cocotb_rpc_durable_harness.py'))
            if args.suite=='rpc_keyed':
                replaced={'cocotb_rpc_durable_top.sv','http2_owned_lifecycle_windows.v',
                    'http2_lifecycle_send_window_store.v','http2_durable_frame_grants.v','rpc_grpc_durable_return.v'}
                sources=[p for p in sources if p.name not in replaced]
                sources.extend(source_path(root, 'rtl/'+name+'.v')for name in('http2_owned_keyed_windows',
                    'http2_keyed_send_window_store','http2_keyed_frame_grants','rpc_grpc_keyed_return'))
                top='cocotb_rpc_keyed_top';module='test_rpc_keyed_response'
                sources.append(source_path(root, 'sim/'+top+'.sv'))
                extra_sources.extend(source_path(root, name) for name in('tools/generate_keyed_send_windows.py','sim/cocotb/test_rpc_durable_response.py'))
                extra_sources.append(root/'tools/generate_registered_window_geometry.py')
    if shutdown_suite:
        top='cocotb_two_fpga_shutdown_top';module='test_two_fpga_shutdown'
        sources=[*sorted((root/'rtl').rglob('*.v')),root/'sim/cocotb_two_fpga_shutdown_top.sv']
        extra_sources +=[*sorted((root/'tools').glob('*.py')),*sorted((root/'sim/cocotb').glob('*.py'))]
        fixtures.append(root/'build/http2-shutdown-fixtures/cases.json')
    if args.test_module:
        assert args.suite in('two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'),'Directed override is limited to the actual raw Parser tops'
        module=args.test_module
    tests=root/"sim/cocotb";test=tests/(module+".py");report_path=build/"report.json"
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    report={"suite":selected_suite,"test_module":module,"simulator":args.simulator,"phase":"building",
            "started_utc":datetime.now(timezone.utc).isoformat(),"cocotb_version":importlib.metadata.version("cocotb"),
            "source_sha256":{str(source_relative(path, root)):sha(path)for path in [*sources,test,Path(__file__),root/'tools/rtl_paths.py',*extra_sources]},
            "fixture_sha256":{str(source_relative(path, root)):sha(path)for path in fixtures}}
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    runner=get_runner(args.simulator)
    sys.path.insert(0,str(tests))
    try:
        runner.build(sources=sources,hdl_toplevel=top,defines=defines,build_dir=build/"compile",timescale=("1ns","1ps"),always=True,log_file=build/"build.log")
    except Exception:
        report["phase"]="build_failed";report_path.write_text(json.dumps(report,indent=2)+"\n");raise
    report["phase"]="running";report_path.write_text(json.dumps(report,indent=2)+"\n")
    (build/"results.xml").unlink(missing_ok=True)
    if args.suite in('http2_prefill','generated_response','rpc_response','rpc_grpc','rpc_leased','rpc_durable','rpc_keyed','bidirectional','two_fpga','two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified'):(build/"acceptance.json").unlink(missing_ok=True)
    try:
        result=runner.test(hdl_toplevel=top,test_module=module,test_dir=build,results_xml="results.xml",log_file=build/"simulation.log",
                           seed=20261104,extra_env={"PYTHONPATH":str(tests)+os.pathsep+os.environ.get("PYTHONPATH",""),**extra_env})
    except Exception:
        report["phase"]="simulation_failed";report_path.write_text(json.dumps(report,indent=2)+"\n");raise
    if not result.exists():
        report.update(phase="failed",error="Simulator produced no test results");report_path.write_text(json.dumps(report,indent=2)+"\n")
        raise SystemExit("Simulator produced no cocotb results")
    tree=ET.parse(result);cases=tree.findall(".//testcase");failed=tree.findall(".//failure")+tree.findall(".//error")
    passed=bool(cases)and not failed
    changed=[name for name,digest in {**report['source_sha256'],**report['fixture_sha256']}.items()if not(source_path(root, name)).is_file()or sha(source_path(root, name))!=digest]
    if changed:passed=False;report['changed_inputs']=changed
    if args.suite in('http2_prefill','generated_response','rpc_response','rpc_grpc','rpc_leased','rpc_durable','rpc_keyed','bidirectional','two_fpga','two_fpga_memory','two_fpga_framed','two_fpga_controlled','two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified')and passed:
        acceptance=build/"acceptance.json"
        passed=acceptance.is_file()and json.loads(acceptance.read_text()).get("phase")=="passed"
        if passed:report['acceptance_sha256']=sha(acceptance)
    report.update(phase="passed"if passed else"failed",tests=len(cases),failures=len(failed),finished_utc=datetime.now(timezone.utc).isoformat());report_path.write_text(json.dumps(report,indent=2)+"\n")
    print((build/"simulation.log").read_text()[-3500:])
    if not passed:raise SystemExit("Cocotb regression failed")
    print(f"PASS: cocotb {selected_suite}: {len(cases)} test(s)")


if __name__=="__main__":main()
