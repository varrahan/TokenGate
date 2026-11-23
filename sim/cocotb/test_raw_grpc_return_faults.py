"""Every return metadata ACK fault behind real raw HTTP/2 admission."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-vendor'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from h2.config import H2Configuration
from h2.connection import H2Connection
from test_raw_grpc_enveloped import Bench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class FaultBench(Bench):
    window_base=0x7f0000
    def configure(self):
        super().configure();self.set(cfg_window_base=self.window_base)


async def bootstrap(b,index):
    d=b.d;a=b.layout
    assert not any(b.pending)and not b.packet_bytes and value(d,'fabric_idle')
    assert not value(d,'m_axis_tx_tvalid')and not value(d,'response_record_lease_active')
    assert not value(d.dut.core,'return_pending')and not value(d,'response_result_retirement_pending')
    b.window_base=0x7f0000+index*64;progress=0x7e8000+index*128
    assert b.memory.data[b.window_base:b.window_base+a[14]//8]==bytes(a[14]//8)
    assert b.memory.data[progress:progress+96]==bytes(96)
    b.reverse['response_progress']['base']=progress
    b.set(rst=1,fault_client=-1,fault_arm=0,window_req_valid=0,window_rsp_ready=0,
        s_axis_generated_tvalid=0,response_result_ready=0,queue_cfg_clear=1,maintenance_grant=1)
    b.current=None;b.closed.clear();b.client_events.clear();b.response_records.clear()
    b.client=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'));b.client.initiate_connection()
    b.configure();await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0;await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    await b.directory(4);await b.open();await b.packet(0,1,b.client.data_to_send(),1)
    b.client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json'),
        ('content-type','application/grpc+json'),('te','trailers')])
    await b.packet(0,2,b.client.data_to_send(),1)


@cocotb.test(timeout_time=50,timeout_unit='ms')
async def raw_admitted_return_metadata_faults_keep_real_ownership(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reverse=json.loads((folder/'response_reference.json').read_text());manifest=json.loads((folder/'fixture_manifest.json').read_text())
    image=bytearray(b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==manifest['loaded_image_sha256']
    initial=bytes(image);memory=SeparateMemory(d,image);b=FaultBench(d,layout,memory,reverse);b.allow_quarantine=True
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated()):cocotb.start_soon(worker)
    await cycles(d,5);cases=[]
    for phase in range(20):
        await bootstrap(b,phase);b.phase=f'raw return metadata ACK fault {phase}';before=len(b.wire)
        await b.gpu_offer(1,15339,0,1,0)
        for _ in range(100000):
            if value(d.dut.core.reverse.response.rpc,'state')==12:break
            await FallingEdge(d.clk)
        else:raise AssertionError('Actual initial progress commit did not start')
        assert b.pending[20]is None;start=b.commands[20]
        b.set(fault_client=20,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        await b.wait('response_result_valid')
        fields=('response_result_stage','response_result_status','response_result_memory_status','response_result_cancelled')
        expected=(5 if phase<5 else 20,3,0x75,0)
        assert tuple(value(d,n)for n in fields)==expected
        expected_types=[]if phase<5 else[1]if phase<10 else[1,0]if phase<15 else[1,0,1]
        assert [raw[3]for raw in b.wire[before:]]==expected_types
        assert value(d,'fault_injected')and value(d,'response_recovery_required')
        assert b.commands[20]-start==phase+1
        for _ in range(13):
            await cycles(d);assert tuple(value(d,n)for n in fields)==expected
            assert value(d,'response_result_valid')and value(d,'response_record_lease_active')
        b.set(response_result_ready=1);await cycles(d);b.set(response_result_ready=0)
        for _ in range(100000):
            if not value(d.dut.core,'return_pending')and not value(d,'response_record_lease_active')and value(d,'fabric_idle'):break
            await cycles(d)
        else:raise AssertionError('Actual cached LOAD did not retire after GPU ACK')
        b.current=None;a=layout
        b.set(window_req_op=6,window_req_maintenance=0,window_req_user=0,window_req_stream=0,window_req_generation=0,
            window_req_record_address=0,window_req_amount=0,window_req_valid=1,
            window_cfg_context_base=a[19],window_cfg_context_bytes=a[20],window_cfg_stream_base=a[13],window_cfg_stream_bytes=a[14],
            window_cfg_window_base=b.window_base,window_cfg_window_bytes=a[14]//8,window_cfg_work_floor=a[6])
        windows=b.commands[22]
        for _ in range(19):
            await cycles(d)
            assert not any(value(d,n)for n in('window_req_ready','s_axis_rx_tready','s_axis_generated_tready','control_ready'))
            assert b.commands[22]==windows and b.commands[20]-start==phase+1
            assert [raw[3]for raw in b.wire[before:]]==expected_types
        assert not any(b.pending)and not b.packet_bytes and not value(d,'response_result_retirement_pending')
        cases.append(dict(phase=phase,memory_commands=phase+1,wire_types=expected_types,gpu_stage=expected[0],
            progress_base=reverse['response_progress']['base'],window_base=b.window_base))
        d._log.info('Verified raw return fault %d: %s',phase,expected_types)
    await bootstrap(b,20);before=len(b.wire);await b.gpu(1,15339,0,1,0)
    assert [raw[3]for raw in b.wire[before:]]==[1,0,1]and('StreamEnded',1)in b.client_events
    assert not value(d,'response_recovery_required')and not any(b.pending)
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    assert len(b.generated_accepts)==21
    accepted=dict(phase='passed',actual_return_metadata_faults=cases,actual_memory_error=0x75,
        actual_gpu_descriptors_accepted=21,actual_header_bindings=b.headers,actual_raw_packets=b.packets,
        native_wire_frames=len(b.wire),parser_memory_clients=17,tokenizer_memory_clients=9,
        real_raw_headers_and_native_response_client=True,applied_write_errors=True,
        held_gpu_results_retain_actual_load=True,cached_load_retires_after_actual_gpu_ack=True,
        no_repeated_wire_after_uncertain_metadata=True,new_public_work_fenced=True,
        global_reset_only_after_actual_owners_drained=True,fresh_window_and_progress_arenas_per_reset=True,
        successful_gpu_return_after_explicit_root_reinitialization=True,retained_arenas_warm_reset_verified=False,
        fault_descriptors_are_explicit_generated_gpu_stimuli=True,forward_dma_workload_verified=False,
        raw_reset_concurrent_with_every_return_fault_verified=False,complete_model_prefix_immutable=True,
        physical_interfaces_verified=False,whole_rpc_gpu_image_lease_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
