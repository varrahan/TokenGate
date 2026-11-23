"""Passively prove global response-progress writes use real held pool authority."""
import cocotb
from cocotb.triggers import RisingEdge
from test_http2_prefill import value
from window_format_witness import WindowFormatWitness


class ProgressFormatWitness(WindowFormatWitness):
    def __init__(self,d):
        super().__init__(d,progress_errors=True);self.progress_records=[];self.progress_active=None;self.progress_pending=None

    async def observe_progress(self):
        d=self.d;c=d.dut.core;owned=c.reverse.directory_service.owned
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):
                assert self.progress_active is None and self.progress_pending is None
                continue
            if value(d,'control_valid') and value(d,'control_ready') and value(d,'control_op')==4:
                assert self.progress_active is None
                self.progress_active=dict(base=value(d,'cfg_response_progress_base'),
                    bytes=value(d,'cfg_response_progress_bytes'),commands=[],acks=[],held_public_cycles=0)
            r=self.progress_active
            if r is None:continue
            if value(c,'progress_format_owner'):
                assert value(c,'rx_format_pending') and value(c,'rx_format_complete') and value(c,'rx_init_status')==0
                assert value(c,'tx_format_complete') and value(c,'service_window_rsp_status')==0
                assert value(c,'window_owner')==12 and value(owned,'directory_pool_lock_active')
                assert value(owned,'receive_admission_lock_active') and value(owned,'saved_req_global_format')
                assert value(owned.windows,'format_authority') and value(owned.windows,'op')==12
                assert not value(d,'control_result_valid') and not value(d,'s_axis_rx_tready')
                assert not value(d,'s_axis_generated_tready') and not value(d,'response_record_lease_active')
                if value(d,'mem_rsp_valid')>>20 & value(d,'mem_rsp_ready')>>20 & 1:
                    assert self.progress_pending is not None
                    a=self.progress_pending;self.progress_pending=None
                    a.update(status=value(d,'mem_rsp_status')>>160&255);r['acks'].append(a)
                if value(d,'mem_valid')>>20 & value(d,'mem_ready')>>20 & 1:
                    assert self.progress_pending is None
                    a=dict(address=value(d,'mem_addr')>>(23*20)&0x7fffff,
                        write=value(d,'mem_write')>>20&1,bytes=value(d,'mem_bytes')>>80&15,
                        data=value(d,'mem_data')>>(72*20)&((1<<72)-1))
                    assert a==dict(address=r['base']+8*len(r['commands']),write=1,bytes=8,data=0)
                    assert a['address']+8<=r['base']+r['bytes']
                    r['commands'].append(dict(a));self.progress_pending=a
            if value(d,'control_result_valid'):
                assert self.progress_pending is None
                status=[value(d,n)for n in('control_status','control_detail','control_memory_status')]
                if 'result'not in r:r['result']=status
                assert status==r['result']
                if status==[0,0,0]:
                    assert len(r['commands'])==len(r['acks'])==r['bytes']//8
                    assert all(a['status']==0 for a in r['acks'])
                elif status==[5,18,0x75]:
                    assert r['commands'] and len(r['commands'])==len(r['acks'])
                    assert [a['status']for a in r['acks']]==[0]*(len(r['acks'])-1)+[0x75]
                if value(d,'control_result_ready'):
                    self.progress_records.append(r);self.progress_active=None
                else:r['held_public_cycles']+=1

    async def observe(self):
        cocotb.start_soon(self.observe_progress())
        await super().observe()

    def result(self):
        records=super().result()
        assert self.progress_active is None and self.progress_pending is None
        assert len(records)==len(self.progress_records)
        return [dict(record,actual_progress_format=progress)for record,progress in zip(records,self.progress_records)]
