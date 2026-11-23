"""Keep a second real connection live across fatal retirement and same-arena reuse."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/post-commit-retire/sim/rst_idle_stream/test_raw_grpc_duplex.py'
    folder=root/'build/experiments/post-retire-scope';folder.mkdir(exist_ok=True)
    text=replace(source.read_text(),'from test_raw_grpc_enveloped import Bench, varint',
        'from test_raw_grpc_enveloped import varint\nfrom post_retire_scope_bench import ScopedBench as Bench')
    text=replace(text,'    await b.gpu_offer(1, captured[0], 0, 0, 2)',
        '''    # Same HTTP/2 stream ID on another actual connection. No record
    # initialization or lookup callback is supplied by this fixture.
    await b.opening(1)
    await b.packet(1,100,b.other.data_to_send(),1)
    b.other.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    b.other.send_data(1,b'\\0'+len(body).to_bytes(4,'big')+body,end_stream=True)
    await b.packet(1,101,b.other.data_to_send(),1)
    await b.drain(1,1,101,reference['token_ids'])
    other_ids=list(b.received);other_address=b.handles[1,1];other_generation=b.bindings[1,1]
    assert other_ids==captured and other_address!=b.handles[0,1] and other_generation==2
    other_regions=[(other_address,128),(layout[19]+256,256),(0x7e5000+64,64),
        (0x7e6000+(other_address-layout[13])//4,32),(0x7f0000+(other_address-layout[13])//8,16)]
    other_snapshot=[bytes(image[a:a+n]) for a,n in other_regions]
    def check_other_intact():
        assert [bytes(image[a:a+n]) for a,n in other_regions]==other_snapshot
    await b.gpu_offer(1, captured[0], 0, 0, 2)''')
    text=replace(text,'    fatal_trace = list(trace)',
        '    check_other_intact()\n    fatal_trace = list(trace)')
    text=replace(text,'b.bindings[0, 1] == old_generation + 1','b.bindings[0, 1] == other_generation + 1')
    text=replace(text,"    assert b.client.outbound_flow_control_window == 65535",
        '''    assert b.client.outbound_flow_control_window == 65535
    check_other_intact()
    for ordinal,token in enumerate(other_ids):
        await b.other_gpu(token,ordinal,int(ordinal+1==len(other_ids)))
    assert ('StreamEnded',1) in b.other_events and bytes(b.other_response)==bytes(expected)
    await b.directory(3,1,1)
    assert b.other.outbound_flow_control_window==65535
    assert image[other_address:other_address+8]==bytes(8)''')
    text=replace(text,'        actual_post_commit_retirement=retirement.result(True),',
        '''        actual_other_connection_user=1,actual_other_stream=1,actual_other_rpc_address=other_address,
        actual_other_generation=other_generation,actual_other_captured_dma_ids=other_ids,
        actual_other_response_hex=bytes(b.other_response).hex(),actual_other_regions_unchanged_through_reopen=True,
        actual_other_rpc_closed_after_its_own_response=True,
        actual_post_commit_retirement=retirement.result(True),''')
    output=folder/'test_raw_grpc_duplex.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        witness_sha256=sha(root/'sim/cocotb/post_retire_scope_bench.py'),actual_execution_verified=False,
        actual_other_connection=1,same_http2_stream_id=1,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(output)


if __name__=='__main__':main()
