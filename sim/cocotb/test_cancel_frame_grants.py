"""A key close wakes the actual parked grant scheduler without a shadow lease."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_owned_windows import Bench,Memory
from test_cancel_send_windows import close_key
from test_tokenizer_mmio import cycles


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def actual_key_close_wakes_parked_sender_and_preserves_cached_load(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image,ref['layout']);b=Bench(d,m,ref['layout'])
    b.set(rst=1,req_valid=0,rsp_ready=0,lease_valid=0,lease_rsp_ready=0,window_req_valid=0,window_rsp_ready=0,
        start_valid=0,frame_req_valid=0,finish_valid=0,credit_error_ready=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());await b.fresh()
    await b.directory(0,1);await b.window(0);await b.window(1,1);await b.window(3,amount=0);await b.lease(1)
    a=b.a;b.set(start_user=0,start_stream=1,frame_cfg_context_base=a['context_base'],frame_cfg_context_bytes=a['context_bytes'],
        frame_cfg_stream_base=a['stream_base'],frame_cfg_stream_bytes=a['stream_bytes'],frame_cfg_window_base=a['window_base'],frame_cfg_window_bytes=a['window_bytes'],frame_cfg_work_floor=a['work_floor'])
    await b.send('start_valid','start_ready')
    b.set(start_user=65535,start_stream=0x7fffffff,frame_cfg_context_base=0x7fffff,frame_cfg_context_bytes=0,
        frame_cfg_stream_base=0x7fffff,frame_cfg_stream_bytes=0,frame_cfg_window_base=0x7fffff,frame_cfg_window_bytes=0,
        frame_req_valid=1,frame_req_user=0,frame_req_stream=1,frame_req_max_bytes=16384)
    await b.wait('credit_parked');before=len(m.trace)
    for _ in range(23):await cycles(d);assert int(d.credit_parked.value)and not int(d.frame_req_ready.value)and len(m.trace)==before
    cached=tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
    await close_key(b,1);await b.wait('credit_error_valid')
    assert int(d.credit_error_status.value)==8 and int(d.credit_error_http2_error.value)==5 and not int(d.credit_error_connection_error.value)
    assert int(d.credit_error_user.value)==0 and int(d.credit_error_stream.value)==1 and int(d.frame_grant_bytes.value)==0
    assert int(d.lease_rsp_valid.value)and cached==tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
    before=len(m.trace)
    for _ in range(19):await cycles(d);assert int(d.credit_error_valid.value)and not int(d.frame_req_ready.value)and len(m.trace)==before
    b.set(credit_error_ready=1);await b.wait('frame_req_ready');await cycles(d);b.set(frame_req_valid=0,credit_error_ready=0)
    await b.wait('finish_ready');await b.send('finish_valid','finish_ready');assert not int(d.credit_binding_active.value)
    await b.retire('lease_rsp_ready');await cycles(d,5);assert int(d.idle.value)and not any(m.pending)
    assert m.data[:a['work_floor']]==image[:a['work_floor']]
    accepted=dict(phase='passed',key_close_wakes_actual_parked_scheduler=True,actual_cached_load_held_until_finish=True,
        closed_reservation_no_positive_grant=True,typed_stream_closed_error_verified=True,error_and_result_backpressure_verified=True,
        actual_pool_lock_and_memory_verified=True,model_prefix_immutable=True,actual_rpc_return_integrated=False,
        actual_rst_controller_integrated=False,inflight_wire_frame_drain_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
