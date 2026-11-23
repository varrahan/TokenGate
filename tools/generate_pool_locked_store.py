"""Add an exclusive pool owner to the actual cached-lease directory service."""
import hashlib
import json
from pathlib import Path

from generate_two_fpga_application import add_ports, rename


def main():
    root=Path(__file__).resolve().parents[1]
    original=root/'rtl/grpc_leased_stream_store.v';source=original.read_text()
    public=[('input','','pool_lock_valid'),('output','','pool_lock_ready'),
        ('input','[MEMORY_ADDR_WIDTH-1:0]','pool_lock_base'),('input','[MEMORY_ADDR_WIDTH:0]','pool_lock_bytes'),
        ('output','','pool_lock_result_valid'),('input','','pool_lock_result_ready'),
        ('output','[7:0]','pool_lock_status'),('output','','pool_lock_active'),
        ('input','','pool_unlock_valid'),('output','','pool_unlock_ready')]
    source=add_ports(source,'grpc_leased_stream_store',public)
    source=rename(source,'grpc_leased_stream_store','grpc_pool_locked_stream_store')
    start='assign req_ready=!rst&&state==IDLE&&!rsp_valid&&(!lease_candidate||!prefer_lease);'
    assert start in source
    source=source.replace(start,start.replace('!rst&&','!rst&&!pool_gate&&'))
    start='assign lease_ready=!rst&&state==IDLE&&!lease_rsp_valid&&(!control_candidate||prefer_lease);'
    assert start in source
    source=source.replace(start,start.replace('!rst&&','!rst&&!pool_gate&&'))
    start='assign idle=state==IDLE&&backend_idle&&!rsp_valid&&!lease_rsp_valid&&!req_valid&&!lease_valid;'
    assert start in source
    source=source.replace(start,start.replace('state==IDLE&&','pool_state==POOL_IDLE&&!pool_lock_valid&&state==IDLE&&'))
    declaration='''
// Pool ownership waits for all previously accepted backend operations, while
// cached result slots can remain held or retire. Neither frontend can admit
// a new operation between lock acceptance and the explicit release handshake.
localparam POOL_IDLE=0,POOL_CHECK=1,POOL_DRAIN=2,POOL_HELD=3,POOL_ERROR=4;
reg [2:0] pool_state;
reg [MEMORY_ADDR_WIDTH-1:0] locked_base;
reg [MEMORY_ADDR_WIDTH:0] locked_bytes;
reg [7:0] locked_status;
reg pool_result_acked;
wire pool_gate=pool_state!=POOL_IDLE||pool_lock_valid;
wire [63:0] locked_end={1'b0,locked_base}+{1'b0,locked_bytes};
wire lock_layout_good=locked_bytes>=128&&locked_bytes[6:0]==0&&locked_end<=(64'd1<<MEMORY_ADDR_WIDTH);
assign pool_lock_ready=!rst&&pool_state==POOL_IDLE;
assign pool_lock_active=pool_state==POOL_HELD;
assign pool_lock_result_valid=!rst&&(pool_state==POOL_ERROR||pool_state==POOL_HELD&&!pool_result_acked);
assign pool_lock_status=locked_status;
assign pool_unlock_ready=!rst&&pool_state==POOL_HELD&&pool_result_acked;
always @(posedge clk)begin
    if(rst)begin pool_state<=POOL_IDLE;locked_base<=0;locked_bytes<=0;locked_status<=0;pool_result_acked<=0;end
    else case(pool_state)
        POOL_IDLE:if(pool_lock_valid&&pool_lock_ready)begin
            locked_base<=pool_lock_base;locked_bytes<=pool_lock_bytes;locked_status<=0;pool_result_acked<=0;pool_state<=POOL_CHECK;
        end
        POOL_CHECK:if(!lock_layout_good)begin locked_status<=1;pool_state<=POOL_ERROR;end else pool_state<=POOL_DRAIN;
        POOL_DRAIN:if(state==IDLE&&backend_idle)begin
            if(recovery_required)begin locked_status<=3;pool_state<=POOL_ERROR;end
            else if(lease_active&&(locked_base!=held_pool_base||locked_bytes!=held_pool_bytes))begin locked_status<=2;pool_state<=POOL_ERROR;end
            else pool_state<=POOL_HELD;
        end
        POOL_HELD:begin
            if(pool_lock_result_valid&&pool_lock_result_ready)pool_result_acked<=1;
            if(pool_unlock_valid&&pool_unlock_ready)begin pool_state<=POOL_IDLE;pool_result_acked<=0;end
        end
        POOL_ERROR:if(pool_lock_result_ready)pool_state<=POOL_IDLE;
        default:pool_state<=POOL_IDLE;
    endcase
end
'''
    # Put declarations before the original arbitration expressions.
    source=source.replace('wire control_candidate=req_valid&&!rsp_valid;',declaration+'\nwire control_candidate=req_valid&&!rsp_valid;')
    target=root/'rtl/grpc_pool_locked_stream_store.v';target.write_text(source)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/pool-locked-store-generation.json').write_text(json.dumps(dict(
        phase='generated_pool_exclusion',inputs_sha256={p.relative_to(root).as_posix():sha(p)for p in(original,Path(__file__))},
        generated_sha256=sha(target),single_actual_directory=True,whole_rpc_image_leases_verified=False,
        full_system_complete=False),indent=2)+'\n')
    print('Generated one actual directory with cached return authority and explicit backend-quiescent pool ownership')


if __name__=='__main__':
    main()
