"""Capture both real ledger-clear paths and their public FORMAT ordering."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class WindowFormatWitness:
    fields=('control_status','control_detail','control_memory_status','control_result_op',
            'control_result_user','control_result_stream','control_result_generation','control_result_address')

    def __init__(self,d,*,progress_errors=False):
        self.d=d;self.clock=0;self.active=None;self.pending={};self.records=[]
        self.progress_errors=progress_errors

    async def observe(self):
        d=self.d;c=d.dut.core;owned=c.reverse.directory_service.owned
        while True:
            await RisingEdge(d.clk);self.clock+=1
            if value(d,'rst'):
                assert self.active is None and not self.pending
                continue
            if value(d,'control_valid') and value(d,'control_ready') and value(d,'control_op')==4:
                assert self.active is None
                self.active=dict(request_clock=self.clock,rpc_base=value(d,'cfg_stream_base'),rpc_bytes=value(d,'cfg_stream_bytes'),
                    bases={'26':value(d,'cfg_receive_stream_base'),'22':value(d,'cfg_window_base')},
                    sizes={'26':value(d,'cfg_receive_stream_bytes'),'22':value(d,'cfg_window_bytes')},
                    acks={'26':[],'22':[]},commands={'26':[],'22':[]},requests=[],held_public_cycles=0)
            r=self.active
            if r is None:continue
            if value(c,'rx_request_valid') and value(c,'rx_request_ready'):
                assert value(c,'rx_request_op')==11 and value(c,'receive_pool_active') and value(c,'rx_backend_authority')
                assert not value(c,'rx_request_is_init') and not value(c,'rx_request_is_close')
                r['requests'].append(dict(client=26,op=11,clock=self.clock))
            if value(c,'service_window_req_valid') and value(c,'service_window_req_ready'):
                assert value(c,'service_window_req_op')==12 and value(c,'window_owner')==11
                assert len(r['acks']['26'])*8==r['sizes']['26'] and not self.pending
                assert all(a['status']==0 for a in r['acks']['26'])
                r['requests'].append(dict(client=22,op=12,clock=self.clock))
            for client in (26,22):
                key=str(client)
                if value(d,'mem_rsp_valid')>>client & value(d,'mem_rsp_ready')>>client & 1:
                    assert client in self.pending
                    record=self.pending.pop(client)
                    record.update(ack_clock=self.clock,status=value(d,'mem_rsp_status')>>(8*client)&255)
                    r['acks'][key].append(record)
                if value(d,'mem_valid')>>client & value(d,'mem_ready')>>client & 1:
                    assert client not in self.pending
                    record=dict(clock=self.clock,address=value(d,'mem_addr')>>(23*client)&0x7fffff,
                        write=value(d,'mem_write')>>client&1,bytes=value(d,'mem_bytes')>>(4*client)&15,
                        data=value(d,'mem_data')>>(72*client)&((1<<72)-1))
                    assert record['address']==r['bases'][key]+8*len(r['commands'][key])
                    assert record['write']==1 and record['bytes']==8 and record['data']==0
                    assert record['address']+8<=r['bases'][key]+r['sizes'][key]
                    if client==26:assert value(c,'receive_pool_active') and value(c,'rx_backend_authority')
                    else:
                        assert value(owned,'directory_pool_lock_active') and value(owned,'receive_admission_lock_active')
                        assert value(owned.windows,'authority') and value(owned.windows,'op')==12
                        assert (value(owned.directory,'locked_base'),value(owned.directory,'locked_bytes'))==(r['rpc_base'],r['rpc_bytes'])
                        assert not (value(d,'mem_valid') & value(d,'mem_ready') & 1)
                    self.pending[client]=record;r['commands'][key].append(dict(record))
            if value(d,'control_result_valid'):
                result=tuple(value(d,n) for n in self.fields)
                assert not self.pending
                if r.get('result') is None:
                    r['result']=result;r['first_offer_clock']=self.clock
                    if result[0]==0:
                        for key in ('26','22'):
                            assert len(r['acks'][key])*8==r['sizes'][key] and all(a['status']==0 for a in r['acks'][key])
                    elif self.progress_errors and result[:3]==(5,18,0x75):
                        for key in ('26','22'):
                            assert len(r['acks'][key])*8==r['sizes'][key]
                            assert all(a['status']==0 for a in r['acks'][key])
                    elif result[2]==0x75:
                        failed=[key for key in ('26','22') if r['acks'][key] and r['acks'][key][-1]['status']==0x75]
                        assert len(failed)==1
                        assert result[:3]==(5,7 if failed[0]=='26' else 2,0x75)
                        if failed[0]=='26':assert not r['commands']['22'] and not r['acks']['22']
                assert tuple(r['result'])==result
                if not value(d,'control_result_ready'):r['held_public_cycles']+=1
                else:
                    r['result_ack_clock']=self.clock;self.records.append(r);self.active=None

    def result(self):
        assert self.active is None and not self.pending and self.records
        return self.records
