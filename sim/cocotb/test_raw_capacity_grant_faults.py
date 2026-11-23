"""Every real initial-capacity ACK fault under actual committed-packet ownership."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_prefill import value
from test_raw_open_rpc_credit import RecordingBench
from test_raw_reclaim_faults import observe_reclaim,arm_reclaim_fault
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def actual_initial_capacity_grant_ack_faults_retain_pool(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text());reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    core=d.dut.core;workers=[]
    clock=cocotb.start_soon(Clock(d.clk,4,unit='ns').start())
    capacity=layout[14]//128*(layout[18]+5);stream_capacity=layout[18]+5

    async def wait_private_idle():
        for _ in range(100000):
            if not value(core,'rc_pending') and not value(core,'rc_busy'):break
            await cycles(d)
        else:raise AssertionError(('Private capacity owner failed to drain',value(core.payload_reclaimer,'state')))
        await cycles(d,2)

    async def setup():
        nonlocal workers
        d.rst.value=1;await cycles(d,4)
        for worker in workers:worker.cancel()
        await cycles(d,2)
        image=bytearray(initial);memory=SeparateMemory(d,image);b=RecordingBench(d,layout,memory,reverse)
        b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_rx_tvalid=0,
            s_axis_generated_tvalid=0,control_valid=0,command_valid=0,queue_cfg_valid=0,stream_cfg_valid=0,
            cfg_schema_valid=0,cfg_unlock=0,control_result_ready=0,rsp_ready=0,completion_ready=0,
            response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
            packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
        b.configure();trace=dict(starts=0,commands=[],responses=[],credit_commands=[])
        workers=[cocotb.start_soon(worker)for worker in(memory.parser.run(),memory.tokenizer.run(),b.ready_driver(),
            b.observe(),b.actual_observer(),b.observe_generated(),observe_reclaim(d,trace))]
        await cycles(d,5);b.set(rst=0)
        for prefix in('queue','stream'):
            await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
            assert value(d,prefix+'_cfg_status')==0
            await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
        b.response_configuration(0);await b.directory(4);await b.open()
        await b.packet(0,1,b.client.data_to_send(),1);await wait_private_idle()
        assert trace['starts']==1 and len(trace['commands'])==3 and not trace['credit_commands']
        assert all(c['write']==0 and c['owner']=='compactor' for c in trace['commands'])
        preface_trace=json.loads(json.dumps(trace))
        trace.clear();trace.update(starts=0,commands=[],responses=[],credit_commands=[])
        return b,memory,image,trace,preface_trace

    async def admit(b,phase):
        armed=cocotb.start_soon(arm_reclaim_fault(d,phase))
        b.client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
        await b.packet(0,2,b.client.data_to_send(),1);await armed
        assert b.messages==b.ids==len(b.generated_accepts)==0

    b,memory,image,trace,preface=await setup();await admit(b,None);await wait_private_idle()
    assert trace['starts']==1 and trace['successful_result']==(0,0,0)
    commands=list(trace['commands']);responses=list(trace['responses']);ops=list(trace['credit_commands'])
    assert len(commands)==len(responses)==42 and all(r['status']==0 for r in responses)
    assert ops==[(4,0,1,b.bindings[0,1],b.handles[0,1],0),(4,0,0,0,0,0)]
    initial_wire=[raw.hex() for raw in b.wire if raw[3]==8]
    assert len(initial_wire)==2 and b.client.outbound_flow_control_window==capacity
    assert b.client.local_flow_control_window(1)==stream_capacity
    assert not any(c['write'] for c in commands if c['owner']=='compactor')
    progress=int.from_bytes(image[b.handles[0,1]+32:b.handles[0,1]+64],'little')
    assert progress==0,'Initial capacity announcement changed the live empty gRPC progress'
    # Actual subsequent traffic must still use the admitted stream, real BPE
    # and inverse path. Explicit host CLOSE retires the received bytes.
    body=b'\x0a\x0bhello world';record=b'\0'+len(body).to_bytes(4,'big')+body
    b.client.send_data(1,record,end_stream=True);await b.packet(0,3,b.client.data_to_send(),1)
    await b.drain(0,1,101,[15339,1917]);captured=list(b.received)
    for ordinal,token in enumerate(captured):await b.gpu(1,token,ordinal,int(ordinal==1),2)
    expected=b''.join(b'\0'+(len(raw)+3).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(raw)])+raw
        for chunk in reverse['cases'][0]['chunks'] for raw in [bytes.fromhex(chunk['bow_hex'])])
    assert bytes(b.response_records[1])==expected and ('StreamEnded',1)in b.client_events
    await b.directory(3,0,1)
    for _ in range(100000):
        if b.client.outbound_flow_control_window==capacity:break
        await cycles(d)
    else:raise AssertionError('Actual post-capacity CLOSE did not retire DATA credit')
    success=dict(actual_grant_commands=commands,actual_grant_responses=responses,actual_credit_commands=ops,
        actual_initial_window_updates=initial_wire,actual_preface_scan=preface,
        actual_captured_dma_ids_returned=captured,actual_ingress_packets=b.ingress_packets,
        actual_wire_frames=[raw.hex() for raw in b.wire],byte_exact_response_hex=expected.hex(),
        final_connection_credit=capacity,explicit_host_close=True)
    faults=[]
    for phase in range(len(commands)):
        d._log.info('Starting actual initial-capacity ACK fault %d/%d',phase+1,len(commands))
        b,memory,image,trace,preface=await setup();await admit(b,phase)
        for _ in range(100000):
            if value(core,'rc_recovery') and value(d,'receive_fault_valid'):break
            await cycles(d)
        else:raise AssertionError(('Initial capacity fault did not quarantine',phase,trace))
        await cycles(d,5)
        assert value(d,'fault_injected') and value(d,'receive_recovery_required')
        assert value(d,'receive_fault_memory_status')==0x75
        assert value(core,'rc_lock_active') and value(core,'receive_pool_active')
        assert trace['starts']==1 and len(trace['commands'])==len(trace['responses'])==phase+1
        assert trace['commands']==commands[:phase+1]
        assert [r['status'] for r in trace['responses']]==[0]*phase+[0x75]
        updates=[raw.hex() for raw in b.wire if raw[3]==8]
        assert updates==initial_wire[:len(updates)] and len(updates)<=2
        assert not any(b.pending) and not b.packet_bytes and b.ids==b.messages==len(b.generated_accepts)==0
        before=len(trace['commands']),len(b.wire),len(b.generated_accepts)
        b.configure();b.set(s_axis_rx_tdata=0x1122,s_axis_rx_tkeep=3,s_axis_rx_tlast=1,s_axis_rx_tuser=0,
            s_axis_rx_tag=99,s_axis_rx_tvalid=1,s_axis_generated_tdata=15339,s_axis_generated_tkeep=15,
            s_axis_generated_tlast=1,s_axis_generated_tuser=0,generated_stream=1,
            generated_generation=b.bindings[0,1],generated_model_epoch=23,generated_schema_epoch=9,
            generated_ordinal=0,s_axis_generated_tvalid=1,control_op=1,control_user=0,control_stream=1,control_valid=1)
        error=tuple(value(d,n)for n in('receive_fault_status','receive_fault_detail','receive_fault_memory_status'))
        for _ in range(23):
            await cycles(d)
            assert not value(d,'s_axis_rx_tready') and not value(d,'s_axis_generated_tready') and not value(d,'control_ready')
            assert value(core,'rc_lock_active') and value(d,'receive_recovery_required')
            assert error==tuple(value(d,n)for n in('receive_fault_status','receive_fault_detail','receive_fault_memory_status'))
        assert before==(len(trace['commands']),len(b.wire),len(b.generated_accepts))
        assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
        faults.append(dict(phase=phase,actual_commands=trace['commands'],actual_responses=trace['responses'],
            actual_credit_commands=trace['credit_commands'],actual_window_updates=updates,actual_error=error,
            actual_preface_scan=preface,actual_pool_retained=True,new_work_denied=True,model_prefixes_immutable=True))
    d.rst.value=1;await cycles(d,4)
    for worker in workers:worker.cancel()
    clock.cancel()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',success=success,
        every_actual_capacity_grant_ack_fault=faults,complete_model_bytes=len(initial),
        actual_committed_packet_and_shared_pool_authority=True,initial_grants_without_dma_or_release=True,
        complete_model_prefixes_immutable=True,native_vendor_runtime_verified=False,
        whole_system_retained_reset_verified=False,full_system_complete=False),indent=2)+'\n')
