"""Passively capture real directory/receive ACK positions during late cleanup."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class PostRetireMemoryWitness:
    def __init__(self,d):
        self.d=d;self.clock=0;self.started=False;self.finished=False
        self.pending={};self.acks={0:[],26:[]};self.operations=[]

    async def observe(self):
        d=self.d;c=d.dut.core;leaf=c.forward.prefill.parser.ingress
        while True:
            await RisingEdge(d.clk);self.clock+=1
            if value(d,'rst'):continue
            if value(leaf,'post_abort_valid') and value(leaf,'post_abort_ready'):
                assert not self.started and not self.pending
                self.started=True
            for client in (0,26):
                if value(d,'mem_rsp_valid')>>client & value(d,'mem_rsp_ready')>>client & 1:
                    assert client in self.pending
                    record=self.pending.pop(client)
                    if self.started:
                        assert record['after_retirement_request']
                        record.update(ack_clock=self.clock,status=value(d,'mem_rsp_status')>>(8*client)&255,
                            response_data=value(d,'mem_rsp_data')>>(72*client)&((1<<72)-1))
                        assert record['status']==0
                        self.acks[client].append(record)
                if value(d,'mem_valid')>>client & value(d,'mem_ready')>>client & 1:
                    assert client not in self.pending
                    self.pending[client]=dict(command_clock=self.clock,after_retirement_request=self.started,
                        write=value(d,'mem_write')>>client&1,address=value(d,'mem_addr')>>(23*client)&0x7fffff,
                        bytes=value(d,'mem_bytes')>>(4*client)&15,data=value(d,'mem_data')>>(72*client)&((1<<72)-1))
            if self.started:
                for label,service in (('directory',leaf),('receive',c.receive_credits)):
                    prefix='dir_req_' if label=='directory' else 'req_'
                    if value(service,prefix+'valid') and value(service,prefix+'ready'):
                        self.operations.append(dict(service=label,clock=self.clock,op=value(service,prefix+'op')))
                if value(leaf,'packet_result_valid') and value(leaf,'packet_result_ready'):
                    assert not self.pending
                    self.finished=True
                    return

    def result(self):
        assert self.started and self.finished and not self.pending
        assert self.acks[0] and self.acks[26]
        return dict(actual_logical_client_acks={str(n):v for n,v in self.acks.items()},
            actual_service_requests=self.operations,all_actual_acks_successful=True,
            captured_from_private_request_through_original_packet_ack=True)
