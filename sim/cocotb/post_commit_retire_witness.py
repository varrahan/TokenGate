"""Observe real FIND/CLOSE, receive retirement and held original packet results."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class PostCommitRetireWitness:
    def __init__(self, d, bench):
        self.d,self.b=d,bench
        self.clock=0
        self.original=None
        self.owner=self.tag=None
        self.last_find=None
        self.request=None
        self.trace=[]
        self.closes=[]
        self.held_cycles=0
        self.done_clock=self.original_ack=None
        self.available=None

    async def observe(self):
        d,b=self.d,self.b
        c=d.dut.core
        f=c.forward
        leaf=f.prefill.parser.ingress
        fields=('packet_committed','packet_status','packet_detail','packet_memory_status','packet_user','packet_tag')
        while True:
            await RisingEdge(d.clk)
            self.clock+=1
            if value(d,'rst'):continue
            if value(leaf,'post_abort_valid') and value(leaf,'post_abort_ready'):
                assert self.original is None
                assert value(leaf,'packet_result_valid') and not value(leaf,'packet_result_ready')
                self.original=tuple(value(leaf,n) for n in fields)
                assert self.original[0]==1
                self.owner=value(leaf,'post_abort_user');self.tag=value(leaf,'post_abort_tag')
                assert self.original[-2:]==(self.owner,self.tag)
                assert not value(d,'response_record_lease_active') and not value(c,'return_pending')
                assert not value(d,'payload_lease_active') and value(f.prefill.parser,'packet_busy')
                assert value(leaf,'packet_pool_base')==value(c,'receive_connection_rpc_base')==b.layout[13]
                assert value(leaf,'packet_pool_bytes')==value(c,'receive_connection_rpc_bytes')==b.layout[14]
                self.available=int.from_bytes(b.memory.data[0x7e5008:0x7e500c],'little')
                self.trace.append(dict(event='actual_post_commit_abort_request',clock=self.clock,user=self.owner,tag=self.tag))
            # This witness owns one fatal retirement. A later explicit OPEN may
            # initialize the same arena and legitimately change its credits.
            if self.original is None or self.original_ack is not None:continue
            assert int.from_bytes(b.memory.data[0x7e5008:0x7e500c],'little')==self.available
            if self.original_ack is None:
                assert value(leaf,'packet_result_valid')
                assert tuple(value(leaf,n) for n in fields)==self.original,'Original offered packet result changed'
                if value(leaf,'packet_result_ready'):
                    assert self.done_clock is not None and self.clock>self.done_clock
                    self.original_ack=self.clock
                    self.trace.append(dict(event='original_packet_result_ack',clock=self.clock))
                    continue
                else:self.held_cycles+=1
            if value(leaf,'dir_req_valid') and value(leaf,'dir_req_ready'):
                op=value(leaf,'dir_req_op')
                assert op in (3,6) and self.request is None
                assert value(leaf,'dir_req_user')==self.owner
                assert value(leaf,'dir_cfg_pool_base')==b.layout[13] and value(leaf,'dir_cfg_pool_bytes')==b.layout[14]
                self.request=dict(op=op,user=value(leaf,'dir_req_user'),stream=value(leaf,'dir_req_stream'),
                    generation=value(leaf,'dir_req_generation'),address=value(leaf,'dir_req_address'))
                if op==3:
                    assert self.last_find is not None
                    assert tuple(self.request[n] for n in ('user','stream','generation','address'))==self.last_find
                else:assert self.request['stream']==self.request['generation']==self.request['address']==0
                self.trace.append(dict(event='actual_directory_request',clock=self.clock,**self.request))
            if value(leaf,'dir_rsp_valid') and value(leaf,'dir_rsp_ready'):
                assert self.request is not None
                op=value(leaf,'dir_rsp_op');status=value(leaf,'dir_rsp_status')
                assert op==self.request['op'] and value(leaf,'dir_rsp_memory_status')==0
                record=tuple(value(leaf,'dir_rsp_'+n) for n in ('user','stream','generation','address'))
                if op==6 and status==0:
                    assert record[0]==self.owner and record[2]!=0
                    self.last_find=record
                elif op==6:
                    assert status==3
                    self.last_find=None
                else:
                    assert status==0 and record==self.last_find
                    address=record[-1]
                    assert b.memory.data[address:address+8]==bytes(8)
                    rx=0x7e6000+(address-b.layout[13])//4
                    assert int.from_bytes(b.memory.data[rx+8:rx+16],'little')>>63==1
                    self.closes.append(dict(user=record[0],stream=record[1],generation=record[2],address=address))
                    self.last_find=None
                self.trace.append(dict(event='actual_directory_result_ack',clock=self.clock,op=op,status=status,
                    user=record[0],stream=record[1],generation=record[2],address=record[3]))
                self.request=None
            if value(leaf,'post_abort_result_valid') and value(leaf,'post_abort_result_ready'):
                assert self.request is None and self.last_find is None and self.closes
                assert self.trace[-1]['event']=='actual_directory_result_ack' and self.trace[-1]['op']==6 and self.trace[-1]['status']==3
                assert (value(leaf,'post_abort_status'),value(leaf,'post_abort_memory_status'))==(0,0)
                self.done_clock=self.clock
                self.trace.append(dict(event='actual_post_commit_retirement_ack',clock=self.clock))

    def result(self, required=True):
        if not required:
            assert self.original is None
            return dict(actual_post_commit_request=False)
        assert self.original is not None and self.done_clock is not None and self.original_ack>self.done_clock
        assert self.request is None and self.held_cycles>17
        return dict(actual_post_commit_request=True,actual_directory_closes=self.closes,
            actual_scope_user=self.owner,actual_scope_tag=self.tag,actual_held_original_result=list(self.original),
            held_original_result_cycles=self.held_cycles,actual_trace=self.trace,
            actual_receive_streams_closed_before_directory_result_ack=True,
            actual_connection_available_not_refunded=True,original_packet_result_promise_preserved=True)
