"""Real FORMAT waits for private credit, and an earlier LOAD keeps its promise."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_prefill import value
from test_raw_grpc_enveloped import varint
from test_raw_open_rpc_credit import RecordingBench
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def actual_format_serializes_with_private_owner_and_preserves_load_offer(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little') for word in (folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    image=bytearray(initial);memory=SeparateMemory(d,image);b=RecordingBench(d,layout,memory,reverse)
    core=d.dut.core
    b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_generated_tvalid=0,
        response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure()
    for worker in (Clock(d.clk,4,unit='ns').start(),memory.parser.run(),memory.tokenizer.run(),
        b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated()):cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in ('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    b.response_configuration(0);await b.directory(4);await b.open()
    await b.packet(0,1,b.client.data_to_send(),1)
    b.ready_wire=False
    def headers(stream):
        b.client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    headers(1);await b.packet(0,2,b.client.data_to_send(),1)
    await b.wait('m_axis_tx_tvalid')
    assert value(core,'rc_lock_active') and value(core,'rc_credit_owner') and value(core,'receive_pool_active')
    held=tuple(value(d,n) for n in ('m_axis_tx_tdata','m_axis_tx_tkeep','m_axis_tx_tlast','m_axis_tx_tuser'))
    assert held[0]>>24&255==8 and held[1]==(1<<13)-1 and held[2:]==(1,0)
    b.set(maintenance_grant=1)
    formatting=cocotb.start_soon(b.directory(4))
    await cycles(d,2)
    before=dict(reads=memory.reads,writes=memory.writes,commands=list(b.commands),wire=len(b.wire))
    samples=[]
    for _ in range(23):
        await cycles(d)
        sample=dict(control_valid=value(d,'control_valid'),control_ready=value(d,'control_ready'),
            forward_control_valid=value(core,'f_control_valid'),private_lock=value(core,'rc_lock_active'),
            pool_lock=value(core,'receive_pool_active'),private_busy=value(core,'rc_busy'))
        assert sample==dict(control_valid=1,control_ready=0,forward_control_valid=0,private_lock=1,pool_lock=1,private_busy=1)
        assert tuple(value(d,n) for n in ('m_axis_tx_tdata','m_axis_tx_tkeep','m_axis_tx_tlast','m_axis_tx_tuser'))==held
        assert value(d,'m_axis_tx_tvalid') and not value(d,'control_result_valid')
        assert (memory.reads,memory.writes,b.commands,len(b.wire))==(before['reads'],before['writes'],before['commands'],before['wire'])
        samples.append(sample)
    b.ready_wire=True
    await formatting
    assert b.messages==b.ids==len(b.generated_accepts)==0
    assert all(image[layout[13]+128*i:layout[13]+128*i+8]==bytes(8) for i in range(layout[14]//128))
    assert image[0x7e6000:0x7e6000+layout[14]//4]==bytes(layout[14]//4)
    after_format=dict(wire=[raw.hex() for raw in b.wire],receive_trace_count=len(b.receive_trace),
        rpc_markers=[image[layout[13]+128*i:layout[13]+128*i+8].hex() for i in range(layout[14]//128)])
    # The ordinary first-message drain helper offers LOAD and a connection
    # command while DMA completion is held, then requires both to complete
    # after the DMA ACK. The ACK also requests private reclamation.
    headers(3);body=b'\x0a\x0bhello world';record=b'\0'+len(body).to_bytes(4,'big')+body
    b.client.send_data(3,record);await b.packet(0,3,b.client.data_to_send(),1)
    async def inspect_arbitration():
        snapshots=[]
        for waited in range(0,100001,5000):
            snapshots.append(dict(waited_cycles=waited,phase=b.phase,messages=b.messages,
                core={n:value(core,n) for n in ('rc_pending','rc_busy','rc_start','rc_ack','rc_recovery','rc_lock_active',
                    'shutdown_control_offered','f_control_valid','f_control_ready','f_control_result_valid','control_result_valid',
                    'rx_format_pending','rx_format_failed','queued_count','pending_count','retirement_pending','payload_lease_active',
                    'completion_valid','f_idle','rx_active','rx_granted','receive_controller_idle','receive_pool_gate_idle',
                    'rc_backend_idle','shutdown_busy','cancel_valid','receive_fault_valid','receive_recovery_required',
                    'journal_recovery_required','response_recovery_required','allow_config')},
                external={n:value(d,n) for n in ('control_valid','control_ready','control_op','command_valid','command_ready','completion_ready')},
                forward={n:value(core.forward,n) for n in ('state','control_owner','p_control_valid','p_control_ready','external_request_locked',
                    'command_valid','control_valid','external_control_allowed','p_idle','r_idle','a_idle')}))
            Path('ownership_progress.json').write_text(json.dumps(snapshots,indent=2)+'\n')
            if b.messages:break
            await cycles(d,5000)
    watching=cocotb.start_soon(inspect_arbitration())
    await b.drain(0,3,101,[15339,1917]);captured=list(b.received)
    watching.cancel()
    for _ in range(100000):
        if not value(core,'rc_pending') and not value(core,'rc_busy'):break
        await cycles(d)
    else:raise AssertionError('Earlier LOAD offer or following private ACK failed to drain')
    capacity=layout[14]//128*(layout[18]+5)
    assert b.client.outbound_flow_control_window==capacity and not b.generated_accepts
    address=b.handles[0,3];progress=int.from_bytes(image[address+32:address+64],'little')
    assert (progress&0xffffffff,progress>>32&0xffffffff,progress>>128&0xffffffff,progress>>165&((1<<33)-1))==(0,0,1,1)
    b.client.send_data(3,b'',end_stream=True);await b.packet(0,4,b.client.data_to_send(),1)
    for ordinal,token in enumerate(captured):await b.gpu(3,token,ordinal,int(ordinal==1),2)
    expected=b''.join(b'\0'+(len(raw)+3).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(raw)])+raw
        for chunk in reverse['cases'][0]['chunks'] for raw in [bytes.fromhex(chunk['bow_hex'])])
    assert bytes(b.response_records[3])==expected and ('StreamEnded',3) in b.client_events
    await b.directory(3,0,3)
    assert b.client.outbound_flow_control_window==capacity
    b.save_wire_evidence()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',blocked_format_samples=samples,
        held_wire_snapshot=list(held),held_memory_counters=before,after_actual_format=after_format,
        actual_captured_dma_ids_returned=captured,actual_generated_descriptors=b.generated_accepts,
        byte_exact_response_hex=expected.hex(),final_connection_credit=capacity,
        actual_existing_load_offer_retired=True,actual_dma_ack_reclaimed_record=True,
        model_prefixes_immutable=image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]],
        full_system_complete=False),indent=2)+'\n')
