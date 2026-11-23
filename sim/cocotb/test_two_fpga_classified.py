"""Full data workload with actual history classification after directory retirement."""
import cocotb
from cocotb.triggers import RisingEdge
from hyperframe.frame import WindowUpdateFrame
from test_bidirectional_application import run_bidirectional
from test_http2_prefill import Bench as RawBench,value
from test_two_fpga_application import SeparateMemory
from test_two_fpga_peer import PeerBench,acceptance as peer_acceptance
from test_tokenizer_mmio import cycles


class ClassifiedBench(PeerBench):
    def __init__(self,*args):
        super().__init__(*args);self.closed_probe=None;self.closed_probes=0;self.missing_window_results=0
        self.history_results=0;self.history_pending=None;self.history_read_acks=0
    async def flow_observer(self):
        fields=('kind','data','arg0','arg1','length','type','flags','stream','user');held=None
        cocotb.start_soon(self.peer_observer());cocotb.start_soon(self.history_observer())
        while True:
            await RisingEdge(self.d.clk)
            if value(self.d,'rst'):held=None;continue
            valid=value(self.d,'flow_event_valid');ready=value(self.d,'flow_event_ready')
            record=tuple(value(self.d,'flow_event_'+n)for n in fields)if valid else None
            if held is not None:assert record==held
            held=record if valid and not ready else None
            if valid:
                if not ready:self.flow_stalls+=1
                else:
                    self.flow_count+=1;kind,_,arg0,_,length,typ,flags,stream,user=record
                    if kind==0 and typ==0:self.flow_data_begins+=1
                    if kind==7:
                        assert length==4 and typ==8 and flags==0
                        if self.closed_probe==(user,stream,arg0):continue
                        assert self.gpu_owned and value(self.d,'response_record_lease_active');self.flow_updates.append([user,stream,arg0])
            assert not value(self.d,'cancel_valid')
    def observe_windows(self):
        w=self.windows
        if value(w,'window_rsp_valid')and value(w,'window_rsp_ready')and value(w,'window_rsp_status')==3:
            assert self.pending_window is not None and self.closed_probe is not None
            op,user,stream,generation,address,amount=self.pending_window
            assert op==9 and(user,stream,amount)==self.closed_probe and value(w,'window_rsp_detail')==10
            assert self.window_write_acks==0;self.pending_window=None;self.window_commands+=1;self.missing_window_results+=1
            return
        super().observe_windows()
    async def peer_observer(self):
        d=self.d;p=d.dut.core.controls.controls.peer
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(p,'req_valid')and value(p,'req_ready'):
                assert self.pending_peer is None;self.pending_peer=tuple(value(p,'req_'+n)for n in('op','user','setting','value','payload'));self.peer_write_acks=0
            if value(d,'mem_valid')>>24&value(d,'mem_ready')>>24&value(d,'mem_write')>>24&1:
                assert not self.peer_write_pending;self.peer_write_pending=True
            if value(d,'mem_rsp_valid')>>24&value(d,'mem_rsp_ready')>>24&1 and self.peer_write_pending:
                assert value(d,'mem_rsp_status')>>(24*8)&255==0;self.peer_write_pending=False;self.peer_write_acks+=1
            if not(value(p,'rsp_valid')and value(p,'rsp_ready')):continue
            assert self.pending_peer is not None and value(p,'rsp_status')==0
            op,user,setting,amount,payload=self.pending_peer;self.pending_peer=None;self.peer_commands+=1
            assert self.peer_write_acks==9 and not self.peer_write_pending
            if op==0:self.peer_pending[user]=self.peer_acks[user]=0;self.peer_formats+=1
            elif op==2:
                assert value(p,'rsp_wire_retired')and self.server_frames[-1][0]==user
                self.peer_pending[user]+=1;self.peer_sends+=1
            elif op==4:
                assert setting in(1,2,3,6);self.peer_settings+=1
                field={1:'header_table_size',2:'enable_push',3:'max_concurrent_streams',6:'max_header_list_size'}[setting]
                assert value(p,'rsp_'+field)==amount
            elif op==5:
                assert value(p,'rsp_ack_matched')and self.peer_pending[user]>0
                self.peer_pending[user]-=1;self.peer_acks[user]+=1;self.peer_received_acks+=1
            else:raise AssertionError(('Unexpected peer op',op))
            assert value(p,'rsp_settings_pending')==self.peer_pending[user]and value(p,'rsp_settings_acks')==self.peer_acks[user]
    async def history_observer(self):
        d=self.d;c=d.dut.core.controls.classifier;f=d.dut.core.forward;pending_read=False
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(c,'req_valid')and value(c,'req_ready'):
                assert self.history_pending is None and self.closed_probe is not None
                self.history_pending=(value(c,'req_user'),value(c,'req_stream'));self.history_read_acks=0
                assert self.history_pending==self.closed_probe[:2]
            if self.history_pending is not None:
                assert value(c,'history_fence')and value(f,'state')==26 and value(f,'p_packet_committed')and value(f,'p_packet_result_valid')
                assert all(value(f,n)for n in('a_idle','r_idle','h_idle'))
            if value(d,'mem_valid')>>25&value(d,'mem_ready')>>25&1:
                assert self.history_pending is not None and not pending_read and not(value(d,'mem_write')>>25&1);pending_read=True
            if value(d,'mem_rsp_valid')>>25&value(d,'mem_rsp_ready')>>25&1:
                assert pending_read and value(d,'mem_rsp_status')>>(25*8)&255==0;pending_read=False;self.history_read_acks+=1
            if value(c,'rsp_valid')and value(c,'rsp_ready'):
                assert self.history_pending==(value(c,'rsp_user'),value(c,'rsp_stream'))and value(c,'rsp_status')==0 and value(c,'rsp_closed')
                assert self.history_read_acks==2 and not pending_read
                self.history_pending=None;self.history_results+=1
    async def directory(self,op,user=0,stream=0):
        await super().directory(op,user,stream)
        if op==3 and self.closed_probes<3:
            address=self.layout[19]+user*256;header=int.from_bytes(self.memory.data[address:address+8],'little')
            if header&0xffffffff==0x48324331 and header>>32&1:
                self.closed_probe=(user,stream,123)
                update=WindowUpdateFrame(stream);update.window_increment=123
                await RawBench.packet(self,user,0xf030+self.closed_probes,update.serialize(),1);self.extra_packets+=1;self.closed_probes+=1
                assert self.history_results==self.closed_probes==self.missing_window_results
                self.closed_probe=None


def acceptance(memory,tested,initial):
    result=peer_acceptance(memory,tested,initial)
    assert tested.closed_probes==3 and tested.history_results==tested.missing_window_results==3
    assert tested.history_pending is None and tested.closed_probe is None
    result.update(parser_memory_clients=17,actual_missing_key_classification=True,no_classification_fixture=True,
        closed_stream_probe_packets=tested.closed_probes,actual_history_results=tested.history_results,
        actual_packet_admission_fence_verified=True,read_only_history_before_results=True)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def full_raw_dma_returns_and_actual_missing_stream_classification(d):
    await run_bidirectional(d,bench_factory=ClassifiedBench,memory_factory=SeparateMemory,extra_result=acceptance)
