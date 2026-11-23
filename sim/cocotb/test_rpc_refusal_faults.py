"""Fault every actual memory ACK of a queued refused-DATA transaction."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame
from test_http2_prefill import value
from test_rpc_admission_fence import FenceBench,headers,settled
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


class FaultBench(FenceBench):
    release_packet=True
    trace=None
    async def wait(self,name):
        for _ in range(100000):
            if value(self.d,name):return
            await FallingEdge(self.d.clk)
        self.save_state('timeout-'+name)
        raise AssertionError(('Refusal transaction timeout',name,self.phase))
    async def ack(self,valid,ready,hold=3):
        if valid=='packet_result_valid':
            while not self.release_packet:await FallingEdge(self.d.clk)
        return await super().ack(valid,ready,hold)
    def save_state(self,label):
        c=self.d.dut.core
        record=dict(label=label,phase=self.phase,trace=self.trace,
            core={n:value(c,n) for n in ('rc_pending','rc_busy','rx_active','rx_granted','rx_drop_valid','rx_drop_done',
                'receive_fault_valid','receive_recovery_required','receive_controller_idle')},
            forward_state=value(c.forward,'state'),receive_state=value(c.receive_flow,'state'),
            receive_operation=value(c.receive_flow,'operation'),backend_state=value(c.receive_credits,'state'),
            credit_store_state=value(c.receive_credits.controller,'state'),
            fault_injected=value(self.d,'fault_injected'),wire=[raw.hex() for raw in self.wire],
            ingress_packets=self.ingress_packets)
        Path('fault-state-'+label+'.json').write_text(json.dumps(record,indent=2)+'\n')


async def memory_trace(b,trace):
    d=b.d;c=d.dut.core;pending=None
    while True:
        await RisingEdge(d.clk)
        if value(d,'rst'):
            assert pending is None
            continue
        if not trace['active']:continue
        if value(d,'mem_valid')>>26&value(d,'mem_ready')>>26&1:
            assert pending is None and not value(c,'rc_busy')
            entry=dict(index=len(trace['commands']),clock=b.clocks,
                address=value(d,'mem_addr')>>(26*23)&0x7fffff,
                write=value(d,'mem_write')>>26&1,bytes=value(d,'mem_bytes')>>(26*4)&15,
                data_hex=format(value(d,'mem_data')>>(26*72)&((1<<72)-1),'018x'),
                flow_operation=value(c.receive_flow,'operation'),backend_state=value(c.receive_credits,'state'),
                store_state=value(c.receive_credits.controller,'state'))
            trace['commands'].append(entry);pending=entry
        if value(d,'mem_rsp_valid')>>26&value(d,'mem_rsp_ready')>>26&1:
            assert pending is not None
            trace['responses'].append(dict(index=pending['index'],clock=b.clocks,
                status=value(d,'mem_rsp_status')>>(26*8)&255,
                data_hex=format(value(d,'mem_rsp_data')>>(26*72)&((1<<72)-1),'018x')))
            pending=None
        if value(c,'rx_m_axis_tx_tvalid')and value(c,'rx_m_axis_tx_tready'):
            trace['wire_updates'].append(dict(clock=b.clocks,ack_count=len(trace['responses'])))
        if value(d,'fault_injected')and not trace.get('fault_saved'):
            trace['fault_saved']=True;b.save_state('injected')


def shape(entry):
    return {k:entry[k]for k in ('address','write','bytes','data_hex','flow_operation','backend_state','store_state')}


@cocotb.test(timeout_time=200,timeout_unit='ms')
async def every_refused_data_ack_fault_preserves_wire_and_quarantine(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text());reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    workers=[];previous=None;results=[]
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start())

    async def setup():
        nonlocal workers,previous
        if previous is not None:
            assert not any(previous.pending)and not previous.packet_bytes and value(d,'fabric_idle')
            assert not value(d,'m_axis_tx_tvalid')and not value(d.dut.core,'return_pending')
            assert len(previous.generated_accepts)==0
        d.rst.value=1;await cycles(d,4)
        for worker in workers:worker.cancel()
        await cycles(d,2)
        image=bytearray(initial);memory=SeparateMemory(d,image);b=FaultBench(d,layout,memory,reverse)
        b.expected_fence_stream=None;b.fence_rejections=[];b.allow_quarantine=True;b.release_packet=True
        b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_rx_tvalid=0,
            s_axis_generated_tvalid=0,control_valid=0,command_valid=0,queue_cfg_valid=0,stream_cfg_valid=0,
            cfg_schema_valid=0,cfg_unlock=0,control_result_ready=0,rsp_ready=0,completion_ready=0,
            response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
            packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
            admit_new_rpcs=1,rpc_error_ready=1,queue_cfg_clear=1)
        b.configure()
        workers=[cocotb.start_soon(w)for w in(memory.parser.run(),memory.tokenizer.run(),b.ready_driver(),
            b.observe(),b.actual_observer(),b.observe_generated(),b.observe_private_credit())]
        await cycles(d,5);b.set(rst=0)
        for prefix in ('queue','stream'):
            await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
            assert value(d,prefix+'_cfg_status')==0
            await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
        b.response_configuration(0);await b.directory(4);await b.open()
        await b.packet(0,1,b.client.data_to_send(),1)
        await b.packet(0,2,headers(1,b.client),1);await settled(b)
        record=b'\0\0\0\0\r\x0a\x0bhello world'
        b.client.send_data(1,record[:7]);await b.packet(0,3,b.client.data_to_send(),1);await settled(b)
        b.set(admit_new_rpcs=0);b.expected_fence_stream=3
        raw=headers(3,b.client)
        b.client.send_data(3,record,pad_length=7,end_stream=True);raw+=b.client.data_to_send()
        assert not any(b.pending)and not value(d.dut.core,'rc_pending')and not value(d.dut.core,'rc_busy')
        trace=dict(active=False,commands=[],responses=[],wire_updates=[]);b.trace=trace
        workers.append(cocotb.start_soon(memory_trace(b,trace)))
        previous=b
        return b,memory,image,raw,trace

    async def transaction(phase,baseline=None):
        b,memory,image,raw,trace=await setup();b.phase='refused DATA ACK '+str(phase)
        before=len(b.wire);b.ready_wire=False;b.release_packet=False
        if phase is not None:
            b.set(fault_client=26,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        trace['active']=True
        sending=cocotb.start_soon(b.packet(0,4,raw,int(phase is None)))
        await b.wait('m_axis_tx_tvalid')
        snapshot=tuple(value(d,'m_axis_tx_'+n)for n in ('tdata','tkeep','tlast','tuser'))
        wire=snapshot[0].to_bytes(64,'little')[:snapshot[1].bit_count()]
        frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
        assert frame.type==3 and frame.stream_id==3 and frame.error_code==7
        held=0
        # Release the held reset only after the memory fault or a queued credit
        # frame. Post-wire retirement faults must be allowed to reach the wire.
        for _ in range(100000):
            await FallingEdge(d.clk);held+=1
            assert value(d,'m_axis_tx_tvalid')and not value(d,'m_axis_tx_tready')
            assert tuple(value(d,'m_axis_tx_'+n)for n in ('tdata','tkeep','tlast','tuser'))==snapshot
            if held>=37 and (value(d,'fault_injected')or value(d.dut.core,'rx_m_axis_tx_tvalid')):break
        else:
            b.save_state('held-reset-timeout');raise AssertionError('Refused DATA neither faulted nor offered credit')
        b.ready_wire=True
        await b.wait('packet_result_valid')
        trace['active']=False
        assert len(trace['commands'])==len(trace['responses'])and not any(b.pending)
        result=tuple(value(d,n)for n in ('packet_committed','packet_status','packet_detail',
            'packet_memory_status','transport_packet_memory_status','packet_control_memory_status'))
        for _ in range(17):
            await cycles(d)
            assert value(d,'packet_result_valid')and result==tuple(value(d,n)for n in ('packet_committed','packet_status','packet_detail',
                'packet_memory_status','transport_packet_memory_status','packet_control_memory_status'))
        frames=[]
        for raw_wire in b.wire[before:]:
            f,size=Frame.parse_frame_header(memoryview(raw_wire[:9]));f.parse_body(memoryview(raw_wire[9:]));frames.append(f)
        assert [(f.stream_id,f.error_code)for f in frames if f.type==3]==[(3,7)]
        updates=[(f.stream_id,f.window_increment)for f in frames if f.type==8]
        if phase is None:
            assert result[0]==1 and all(r['status']==0 for r in trace['responses'])
            assert updates==[(0,26)] and len(trace['wire_updates'])==1
            assert [value(d,n)for n in ('receive_recovery_required','receive_fault_valid')]==[0,0]
            assert {entry['flow_operation']for entry in trace['commands']}=={1,6,7}
        else:
            assert value(d,'fault_injected')and value(d,'receive_recovery_required')and value(d,'receive_fault_valid')
            assert value(d,'receive_fault_memory_status')==0x75
            assert result[0]==0
            assert [r['index']for r in trace['responses']if r['status']]==[phase]
            assert trace['responses'][phase]['status']==0x75
            assert [shape(e)for e in trace['commands'][:phase+1]]==[shape(e)for e in baseline['commands'][:phase+1]]
            wire_already_accepted=phase>=baseline['wire_updates'][0]['ack_count']
            assert updates==([(0,26)]if wire_already_accepted else[])
            assert len(trace['wire_updates'])==int(wire_already_accepted)
        assert b.ids==len(b.generated_accepts)==value(d,'queued_count')==value(d,'pending_count')==value(d,'m_axis_tokens_tvalid')==0
        assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data==initial
        b.save_state('completed-'+str(phase));b.save_wire_evidence()
        record=dict(phase=phase,memory_commands=trace['commands'],memory_responses=trace['responses'],
            actual_wire_updates=trace['wire_updates'],wire_frames=[w.hex()for w in b.wire[before:]],
            held_reset_cycles=held,packet_result=result,complete_model_prefixes_immutable=True)
        Path('refusal-fault-'+str(phase)+'.json').write_text(json.dumps(record,indent=2)+'\n')
        b.release_packet=True;await sending
        for _ in range(100000):
            if value(d,'fabric_idle')and not any(b.pending)and not value(d,'m_axis_tx_tvalid')and not value(d.dut.core,'rx_active'):break
            await cycles(d)
        else:
            b.save_state('drain-timeout');raise AssertionError('Memory/wire ownership did not drain before root reset')
        await cycles(d,3)
        return record

    baseline=await transaction(None)
    count=len(baseline['memory_commands']);assert count>32
    assert all(r['status']==0 for r in baseline['memory_responses'])
    trace_baseline=dict(commands=baseline['memory_commands'],wire_updates=baseline['actual_wire_updates'])
    # Start with the most exposed post-wire ACK, then cover every earlier ACK.
    for phase in [count-1]+list(range(count-1)):
        result=await transaction(phase,trace_baseline);results.append(result)
        d._log.info('Verified refused DATA memory ACK %d/%d',phase,count)
    final=await transaction(None)
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',
        actual_injected_refused_data_ack_faults=count,all_actual_memory_response_positions_verified=True,
        baseline=baseline,cases=results,successful_fresh_root_recovery=final,
        actual_error_status=0x75,applied_write_ack_errors=True,
        held_reset_promise_preserved=True,no_duplicate_credit_after_uncertain_retirement=True,
        complete_model_prefixes_immutable=True,root_resets_only_after_memory_and_wire_drained=True,
        no_gpu_descriptors_accepted=True,native_vendor_runtime_verified=False,
        full_protocol_fault_matrix_verified=False,whole_rpc_gpu_maintenance_authority_verified=False,
        full_system_complete=False),indent=2)+'\n')
