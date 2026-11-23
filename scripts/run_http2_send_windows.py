"""Freeze and run native-referenced durable send-window transactions in WSL."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


SOURCES=('rtl/http2_send_window_store.v','rtl/memory_command_slot.v','sim/cocotb/test_http2_send_windows.py',
    'sim/cocotb/test_tokenizer_mmio.py','tools/generate_http2_send_window_vectors.py','scripts/run_http2_send_windows.py',
    'build/http2-send-window-fixtures/model.bin','build/http2-send-window-fixtures/cases.json', 'tools/rtl_paths.py')
OWNED_SOURCES=SOURCES+('rtl/http2_owned_send_windows.v','rtl/grpc_pool_locked_stream_store.v',
    'rtl/grpc_stream_store.v','rtl/grpc_leased_stream_store.v','tools/generate_pool_locked_store.py',
    'tools/generate_owned_send_windows.py','sim/cocotb/test_http2_owned_windows.py')
LIFECYCLE_SOURCES=OWNED_SOURCES+('rtl/http2_owned_lifecycle_windows.v','rtl/http2_lifecycle_send_window_store.v',
    'tools/generate_lifecycle_send_windows.py','sim/cocotb/test_http2_lifecycle_windows.py')
KEYED_SOURCES=LIFECYCLE_SOURCES+('rtl/http2_keyed_send_window_store.v','rtl/http2_owned_keyed_windows.v',
    'tools/generate_keyed_send_windows.py','tools/generate_registered_window_geometry.py','sim/cocotb/test_http2_keyed_windows.py')
ADMISSION_SOURCES=KEYED_SOURCES+('rtl/http2_rpc_admission.v','rtl/http2_windowed_rpc_admission.v',
    'tools/generate_windowed_rpc_admission.py','tools/generate_cocotb_windowed_admission.py',
    'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
    'sim/cocotb_windowed_admission_top.sv','sim/cocotb/test_windowed_rpc_admission.py')
DURABLE_SOURCES=LIFECYCLE_SOURCES+('rtl/grpc_durable_window_framer.v','rtl/grpc_http2_response_framer.v',
    'rtl/axis_byte_unpacker.v','rtl/axis_byte_packer.v','tools/generate_durable_window_framer.py',
    'tools/generate_durable_framer_vectors.py','sim/cocotb/test_grpc_durable_window_framer.py',
    'build/http2-durable-framer-fixtures/frames.json')
JOURNAL_SOURCES=SOURCES+('rtl/http2_control_journal.v','sim/cocotb/test_http2_control_journal.py',
    'sim/cocotb/test_http2_owned_windows.py')
JOURNALED_SOURCES=tuple(dict.fromkeys(KEYED_SOURCES+JOURNAL_SOURCES+(
    'rtl/http2_control_executor.v','rtl/http2_journaled_controls.v','tools/generate_journaled_controls.py',
    'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
    'sim/cocotb_journaled_controls_top.sv','sim/cocotb/test_journaled_controls.py')))
ARBITER_SOURCES=SOURCES+('rtl/axis_frame_arbiter.v','sim/cocotb/test_axis_frame_arbiter.py')
CANCELLABLE_ARBITER_SOURCES=ARBITER_SOURCES+('rtl/axis_cancellable_frame_arbiter.v','tools/generate_cancellable_frame_arbiter.py',
    'tools/generate_lifecycle_send_windows.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
    'sim/cocotb/test_cancellable_frame_arbiter.py')
PEER_SOURCES=SOURCES+('rtl/http2_peer_state.v','sim/cocotb/test_http2_peer_state.py')
CLASSIFIER_SOURCES=SOURCES+('rtl/http2_missing_stream_classifier.v','sim/cocotb/test_missing_stream_classifier.py',
    'tools/generate_missing_stream_vectors.py','build/http2-classifier-fixtures/cases.json')
CANCEL_SOURCES=KEYED_SOURCES+('rtl/http2_keyed_frame_grants.v','rtl/http2_cancel_send_window_store.v','rtl/http2_owned_cancel_windows.v','rtl/http2_cancel_frame_grants.v',
    'tools/generate_cancel_send_windows.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
    'sim/cocotb/test_cancel_send_windows.py','sim/cocotb/test_cancel_frame_grants.py')
FENCED_FRAMER_SOURCES=tuple(dict.fromkeys(CANCEL_SOURCES+CANCELLABLE_ARBITER_SOURCES+(
    'rtl/http2_fenced_frame_grants.v','rtl/grpc_cancellable_window_framer.v','rtl/grpc_http2_response_framer.v',
    'rtl/axis_byte_unpacker.v','rtl/axis_byte_packer.v','tools/generate_fenced_frame_grants.py',
    'sim/cocotb/test_grpc_durable_window_framer.py','sim/cocotb/test_fenced_window_framer.py')))
REGISTERED_FRAMER_SOURCES=FENCED_FRAMER_SOURCES+('rtl/grpc_registered_input_framer.v','rtl/grpc_cancellable_registered_framer.v',
    'rtl/axis_skid_buffer.v','tools/generate_registered_input_framer.py','sim/cocotb/test_grpc_response_frames.py',
    'tools/generate_grpc_response_frame_vectors.py','build/grpc-response-frame-fixtures/cases.json')
PIPELINED_FRAMER_SOURCES=REGISTERED_FRAMER_SOURCES+('rtl/http2_pipelined_cancel_window_store.v',
    'rtl/http2_owned_pipelined_cancel_windows.v','rtl/http2_fenced_pipelined_grants.v',
    'rtl/grpc_cancellable_pipelined_framer.v','tools/generate_pipelined_cancel_framer.py')
PEER_CONTROL_SOURCES=tuple(dict.fromkeys(JOURNALED_SOURCES+PEER_SOURCES+(
    'rtl/http2_peer_controls.v','rtl/axis_frame_arbiter.v','tools/generate_peer_controls.py',
    'sim/cocotb_peer_controls_top.sv','sim/cocotb/test_peer_controls.py')))
RECEIVE_CREDIT_SOURCES=SOURCES+('rtl/http2_receive_credit_store.v','sim/cocotb/test_receive_credit_store.py')
KEYED_RECEIVE_CREDIT_SOURCES=RECEIVE_CREDIT_SOURCES+('rtl/http2_keyed_receive_credit_store.v',
    'tools/generate_keyed_receive_credit_store.py','tools/generate_bidirectional_application.py',
    'sim/cocotb/test_keyed_receive_credits.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name')
    parser.add_argument('--execute',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--owned',action='store_true')
    parser.add_argument('--lifecycle',action='store_true')
    parser.add_argument('--durable-framer',action='store_true')
    parser.add_argument('--keyed',action='store_true')
    parser.add_argument('--admission',action='store_true')
    parser.add_argument('--rtl-override',type=Path,help='Replace one RTL basename in the isolated snapshot')
    parser.add_argument('--control-journal',action='store_true')
    parser.add_argument('--journaled-controls',action='store_true')
    parser.add_argument('--frame-arbiter',action='store_true')
    parser.add_argument('--peer-state',action='store_true')
    parser.add_argument('--peer-controls',action='store_true')
    parser.add_argument('--classifier',action='store_true')
    parser.add_argument('--cancel-windows',action='store_true')
    parser.add_argument('--cancel-grants',action='store_true')
    parser.add_argument('--cancellable-arbiter',action='store_true')
    parser.add_argument('--fenced-framer',action='store_true')
    parser.add_argument('--registered-framer',action='store_true')
    parser.add_argument('--registered-fenced-framer',action='store_true')
    parser.add_argument('--pipelined-windows',action='store_true')
    parser.add_argument('--pipelined-fenced-framer',action='store_true')
    parser.add_argument('--receive-credits',action='store_true')
    parser.add_argument('--keyed-receive-credits',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    sources=OWNED_SOURCES if args.owned else SOURCES
    directory='http2-owned-window-tests' if args.owned else 'http2-send-window-tests'
    label='http2_owned_windows_' if args.owned else 'http2_send_windows_'
    top='http2_owned_send_windows' if args.owned else 'http2_send_window_store'
    test='test_http2_owned_windows' if args.owned else 'test_http2_send_windows'
    if args.receive_credits:
        sources=RECEIVE_CREDIT_SOURCES;directory='http2-receive-credit-tests';label='http2_receive_credits_'
        top='http2_receive_credit_store';test='test_receive_credit_store'
    if args.keyed_receive_credits:
        assert not args.receive_credits
        sources=KEYED_RECEIVE_CREDIT_SOURCES;directory='http2-keyed-receive-credit-tests';label='http2_keyed_receive_credits_'
        top='http2_keyed_receive_credit_store';test='test_keyed_receive_credits'
    if args.lifecycle:
        sources=LIFECYCLE_SOURCES;directory='http2-lifecycle-window-tests';label='http2_lifecycle_windows_'
        top='http2_owned_lifecycle_windows';test='test_http2_lifecycle_windows'
    if args.durable_framer:
        sources=DURABLE_SOURCES;directory='grpc-durable-framer-tests';label='grpc_durable_framer_'
        top='grpc_durable_window_framer';test='test_grpc_durable_window_framer'
    if args.keyed:
        sources=KEYED_SOURCES;directory='http2-keyed-window-tests';label='http2_keyed_windows_'
        top='http2_owned_keyed_windows';test='test_http2_keyed_windows'
    if args.admission:
        sources=ADMISSION_SOURCES;directory='http2-windowed-admission-tests';label='http2_windowed_admission_'
        top='cocotb_windowed_admission_top';test='test_windowed_rpc_admission'
    if args.control_journal:
        sources=JOURNAL_SOURCES;directory='http2-control-journal-tests';label='http2_control_journal_'
        top='http2_control_journal';test='test_http2_control_journal'
    if args.journaled_controls:
        sources=JOURNALED_SOURCES;directory='http2-journaled-control-tests';label='http2_journaled_controls_'
        top='cocotb_journaled_controls_top';test='test_journaled_controls'
    if args.frame_arbiter:
        sources=ARBITER_SOURCES;directory='axis-frame-arbiter-tests';label='axis_frame_arbiter_'
        top='axis_frame_arbiter';test='test_axis_frame_arbiter'
    if args.peer_state:
        sources=PEER_SOURCES;directory='http2-peer-state-tests';label='http2_peer_state_'
        top='http2_peer_state';test='test_http2_peer_state'
    if args.peer_controls:
        sources=PEER_CONTROL_SOURCES;directory='http2-peer-control-tests';label='http2_peer_controls_'
        top='cocotb_peer_controls_top';test='test_peer_controls'
    if args.classifier:
        sources=CLASSIFIER_SOURCES;directory='http2-classifier-tests';label='http2_classifier_'
        top='http2_missing_stream_classifier';test='test_missing_stream_classifier'
    if args.cancel_windows or args.cancel_grants:
        sources=CANCEL_SOURCES;directory='http2-cancel-window-tests';label='http2_cancel_windows_'
        top='http2_owned_cancel_windows';test='test_cancel_send_windows'
        if args.cancel_grants:
            directory='http2-cancel-grant-tests';label='http2_cancel_grants_';top='http2_cancel_frame_grants';test='test_cancel_frame_grants'
    if args.cancellable_arbiter:
        sources=CANCELLABLE_ARBITER_SOURCES;directory='axis-cancellable-arbiter-tests';label='axis_cancellable_arbiter_'
        top='axis_cancellable_frame_arbiter';test='test_cancellable_frame_arbiter'
    if args.fenced_framer:
        sources=FENCED_FRAMER_SOURCES;directory='grpc-fenced-framer-tests';label='grpc_fenced_framer_'
        top='grpc_cancellable_window_framer';test='test_fenced_window_framer'
    if args.registered_framer or args.registered_fenced_framer:
        assert not(args.registered_framer and args.registered_fenced_framer)
        sources=REGISTERED_FRAMER_SOURCES;directory='grpc-registered-framer-tests';label='grpc_registered_framer_'
        top='grpc_registered_input_framer';test='test_grpc_response_frames'
        if args.registered_fenced_framer:
            directory='grpc-registered-fenced-tests';label='grpc_registered_fenced_';top='grpc_cancellable_registered_framer';test='test_fenced_window_framer'
    if args.pipelined_windows or args.pipelined_fenced_framer:
        assert not(args.pipelined_windows and args.pipelined_fenced_framer)
        sources=PIPELINED_FRAMER_SOURCES;directory='http2-pipelined-window-tests';label='http2_pipelined_windows_'
        top='http2_owned_pipelined_cancel_windows';test='test_cancel_send_windows'
        if args.pipelined_fenced_framer:
            directory='grpc-pipelined-fenced-tests';label='grpc_pipelined_fenced_';top='grpc_cancellable_pipelined_framer';test='test_fenced_window_framer'
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build'/directory/args.name;target.mkdir(parents=True,exist_ok=False);inputs={}
        for name in sources:
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source_path(root, name),destination);inputs[name]=sha(destination)
        if args.receive_credits or args.keyed_receive_credits:
            site=root/'.venv312/Lib/site-packages'
            for package in('h2','hpack','hyperframe'):
                paths=[p for p in(site/package).rglob('*')if p.is_file()and '__pycache__'not in p.parts]
                metadata=list(site.glob(package+'-*.dist-info'));assert len(metadata)==1
                paths +=[p for p in metadata[0].rglob('*')if p.is_file()and p.name!='RECORD']
                for p in paths:
                    name='native-vendor/'+p.relative_to(site).as_posix();destination=target/name
                    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination);inputs[name]=sha(destination)
        override=None
        if args.rtl_override:
            candidate=args.rtl_override.resolve();assert candidate.is_file()and candidate.suffix=='.v'
            matches=[name for name in sources if name.startswith('rtl/')and Path(name).name==candidate.name]
            assert len(matches)==1,'Override must replace exactly one frozen RTL file'
            name=matches[0];override=dict(destination=name,original_sha256=inputs[name],candidate_sha256=sha(candidate),source=str(candidate))
            shutil.copy2(candidate,target/name);inputs[name]=sha(target/name)
        fixture=json.loads((target/'build/http2-send-window-fixtures/cases.json').read_text())
        assert fixture['phase']=='native_send_window_references_passed'
        assert fixture['generator_sha256']==inputs['tools/generate_http2_send_window_vectors.py']
        assert fixture['original_image_sha256']==inputs['build/http2-send-window-fixtures/model.bin']
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen send-window test: '+str(target),flush=True)
        child_flags=['--receive-credits']if args.receive_credits else ['--keyed-receive-credits']if args.keyed_receive_credits else []
        completed=subprocess.run([sys.executable,str(target/'scripts/run_http2_send_windows.py'),'--execute',*child_flags,
            *(['--pipelined-fenced-framer']if args.pipelined_fenced_framer else['--pipelined-windows']if args.pipelined_windows else['--registered-fenced-framer']if args.registered_fenced_framer else['--registered-framer']if args.registered_framer else['--fenced-framer']if args.fenced_framer else['--cancellable-arbiter']if args.cancellable_arbiter else['--cancel-grants']if args.cancel_grants else['--cancel-windows']if args.cancel_windows else['--classifier']if args.classifier else['--peer-controls']if args.peer_controls else['--peer-state']if args.peer_state else['--frame-arbiter']if args.frame_arbiter else['--journaled-controls']if args.journaled_controls else['--control-journal']if args.control_journal else['--admission']if args.admission else['--keyed']if args.keyed else['--durable-framer']if args.durable_framer else['--lifecycle']if args.lifecycle else['--owned']if args.owned else[])],check=False)
        assert all(sha(target/name)==digest for name,digest in inputs.items())
        archive=root/'build/wsl-reports'/(label+args.name);archive.mkdir(parents=True,exist_ok=False)
        for name in inputs:
            destination=archive/'execution-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target/name,destination)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for name in('report.json','results.xml','acceptance.json','simulation.log','build.log'):
            if(target/'build/test'/name).is_file():shutil.copy2(target/'build/test'/name,archive/name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=completed.returncode,
            isolated_rtl_override=override,
            current_primary_changed_inputs=[name for name,digest in inputs.items()if not(source_path(root, name)).is_file()or sha(source_path(root, name))!=digest],
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived send-window execution: '+str(archive),flush=True);raise SystemExit(completed.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build'/directory
    from cocotb_tools.runner import get_runner
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, name))==digest for name,digest in inputs.items())
    build=root/'build/test';build.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(root/'sim/cocotb'))
    runner=get_runner('icarus');record=dict(phase='running',simulator='icarus',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, name) for name in sources if name.endswith(('.v','.sv'))],hdl_toplevel=top,build_dir=build,always=True,log_file=build/'build.log')
        runner.test(hdl_toplevel=top,test_module=test,test_dir=build,build_dir=build,
            results_xml=build/'results.xml',extra_env={'PARSER_HTTP2_SEND_WINDOW_FIXTURES':str(root/'build/http2-send-window-fixtures'),
                'PARSER_GRPC_FRAME_FIXTURES':str(root/'build/grpc-response-frame-fixtures'),
                'PARSER_DURABLE_FRAMER_FIXTURES':str(root/'build/http2-durable-framer-fixtures')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        accepted=json.loads((build/'acceptance.json').read_text());assert accepted['phase']=='passed'
        assert all(sha(source_path(root, name))==digest for name,digest in inputs.items())
        record.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'),finished_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        record.update(phase='failed',error=str(error),finished_utc=datetime.now(timezone.utc).isoformat());raise
    finally:
        (build/'report.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    main()
