"""Observe global FORMAT, real pool authority and every receive-memory ACK."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class ReceiveFormatWitness:
    fields=('control_status','control_detail','control_memory_status','control_result_op',
            'control_result_user','control_result_stream','control_result_generation','control_result_address')

    def __init__(self,d):
        self.d=d;self.clock=0;self.active=None;self.pending=None;self.records=[]

    async def observe(self):
        d=self.d;c=d.dut.core
        while True:
            await RisingEdge(d.clk);self.clock+=1
            if value(d,'rst'):
                assert self.active is None and self.pending is None
                continue
            if value(d,'control_valid') and value(d,'control_ready') and value(d,'control_op')==4:
                assert self.active is None
                self.active=dict(request_clock=self.clock,base=value(d,'cfg_receive_stream_base'),
                    bytes=value(d,'cfg_receive_stream_bytes'),rpc_base=value(d,'cfg_stream_base'),
                    rpc_bytes=value(d,'cfg_stream_bytes'),commands=[],acks=[],backend_requests=0,
                    held_public_cycles=0,held_directory_cycles=0)
            r=self.active
            if r is None:continue
            if value(c,'f_control_result_valid') and not value(c,'f_control_result_ready'):
                r['held_directory_cycles']+=1
            if value(c,'rx_request_valid') and value(c,'rx_request_ready'):
                assert value(c,'rx_request_op')==11
                assert not value(c,'rx_request_is_init') and not value(c,'rx_request_is_close')
                assert value(c,'receive_pool_active') and value(c,'rx_backend_authority')
                assert (value(c,'receive_request_pool_base'),value(c,'receive_request_pool_bytes'))==(r['rpc_base'],r['rpc_bytes'])
                r['backend_requests']+=1
            if value(d,'mem_rsp_valid')>>26 & value(d,'mem_rsp_ready')>>26 & 1:
                assert self.pending is not None
                record=self.pending;self.pending=None
                record.update(ack_clock=self.clock,status=value(d,'mem_rsp_status')>>(8*26)&255)
                r['acks'].append(record)
            if value(d,'mem_valid')>>26 & value(d,'mem_ready')>>26 & 1:
                assert self.pending is None and value(c,'receive_pool_active')
                assert value(c,'rx_backend_authority') and value(c,'rx_format_active')
                record=dict(clock=self.clock,address=value(d,'mem_addr')>>(23*26)&0x7fffff,
                    write=value(d,'mem_write')>>26&1,bytes=value(d,'mem_bytes')>>(4*26)&15,
                    data=value(d,'mem_data')>>(72*26)&((1<<72)-1))
                assert record['address']==r['base']+8*len(r['commands'])
                assert record['write']==1 and record['bytes']==8 and record['data']==0
                assert record['address']+8<=r['base']+r['bytes']
                self.pending=record;r['commands'].append(dict(record))
            if value(d,'control_result_valid'):
                result=tuple(value(d,n) for n in self.fields)
                assert self.pending is None
                if r.get('result') is None:
                    r['result']=result;r['first_offer_clock']=self.clock
                    if result[0]==0:
                        assert r['backend_requests']==1 and len(r['acks'])*8==r['bytes']
                        assert all(x['status']==0 for x in r['acks'])
                    elif r['acks']:
                        assert r['backend_requests']==1 and r['acks'][-1]['status']==0x75
                        assert result[:3]==(5,7,0x75)
                assert tuple(r['result'])==result,'Held global FORMAT result changed'
                if not value(d,'control_result_ready'):r['held_public_cycles']+=1
                else:
                    r['result_ack_clock']=self.clock
                    self.records.append(r);self.active=None

    def result(self):
        assert self.active is None and self.pending is None and self.records
        return self.records
