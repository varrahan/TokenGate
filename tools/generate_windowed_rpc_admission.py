"""Fence successful HEADERS admission on the real send-window commit."""
import hashlib
import json
from pathlib import Path

from generate_two_fpga_application import add_ports, rename
from generate_lifecycle_send_windows import replace_once

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    source=source_path(root, 'rtl/http2_rpc_admission.v');text=source.read_text()
    extra=[('input','[MEMORY_ADDR_WIDTH-1:0]','cfg_window_base'),('input','[MEMORY_ADDR_WIDTH:0]','cfg_window_bytes'),
        ('output','[MEMORY_ADDR_WIDTH-1:0]','control_pool_base'),('output','[MEMORY_ADDR_WIDTH:0]','control_pool_bytes'),
        ('output','','init_valid'),('input','','init_ready'),('output','[USER_WIDTH-1:0]','init_user'),
        ('output','[30:0]','init_stream'),('output','[31:0]','init_generation'),
        ('output','[MEMORY_ADDR_WIDTH-1:0]','init_record_address'),
        ('input','','init_result_valid'),('output','','init_result_ready'),
        ('input','[7:0]','init_status'),('input','[7:0]','init_memory_status'),
        ('input','','init_recovery_required'),('input','[MEMORY_ADDR_WIDTH-1:0]','init_recovery_address'),
        ('output','[7:0]','result_window_status')]
    for name in('context_base','stream_base','window_base','work_floor'):
        extra.append(('output','[MEMORY_ADDR_WIDTH-1:0]','init_cfg_'+name))
    for name in('context_bytes','stream_bytes','window_bytes'):
        extra.append(('output','[MEMORY_ADDR_WIDTH:0]','init_cfg_'+name))
    text=add_ports(text,'http2_rpc_admission',extra)
    text=rename(text,'http2_rpc_admission','http2_windowed_rpc_admission')
    for old,new in(
        ('SCRATCH_REQ=18,SCRATCH_WAIT=19,SCRATCH_CHECK=20;', 'SCRATCH_REQ=18,SCRATCH_WAIT=19,SCRATCH_CHECK=20,WINDOW_REQ=21,WINDOW_WAIT=22;'),
        ('reg [31:0] active_model,active_schema,',
         'reg [7:0] window_status;reg [MEMORY_ADDR_WIDTH-1:0] windows;reg [MEMORY_ADDR_WIDTH:0] window_bytes;\n    reg [31:0] active_model,active_schema,'),
        ('wire slot_fits=',
         "wire [63:0] windows_end={1'b0,windows}+{1'b0,window_bytes};\n"
         "    wire window_config_good=windows>=work_floor&&window_bytes>=(stream_bytes>>3)&&window_bytes[3:0]==0&&\n"
         "        windows_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&(windows_end<=contexts||contexts_end<=windows)&&\n"
         "        (windows_end<=streams||streams_end<=windows)&&(windows_end<=payload||payload_end<=windows);\n    wire slot_fits="),
        ('(scratch_end<=payload||slot_data[31:0]>=payload_end);',
         '(scratch_end<=payload||slot_data[31:0]>=payload_end)&&(scratch_end<=windows||slot_data[31:0]>=windows_end);'),
        ('assign reset_ready=',
         'assign control_pool_base=streams;assign control_pool_bytes=stream_bytes;\n'
         '    assign init_valid=!rst&&state==WINDOW_REQ;assign init_result_ready=state==WINDOW_WAIT;\n'
         '    assign init_user=owner;assign init_stream=stream_id;assign init_generation=rpc_generation;assign init_record_address=rpc_address;\n'
         '    assign init_cfg_context_base=contexts;assign init_cfg_context_bytes=context_bytes;\n'
         '    assign init_cfg_stream_base=streams;assign init_cfg_stream_bytes=stream_bytes;\n'
         '    assign init_cfg_window_base=windows;assign init_cfg_window_bytes=window_bytes;assign init_cfg_work_floor=work_floor;\n'
         '    assign result_window_status=window_status;\n    assign reset_ready='),
        ('state<=IDLE;action<=0;', 'state<=IDLE;action<=0;window_status<=0;windows<=0;window_bytes<=0;'),
        ('resetting<=reset_valid;reset_grant<=maintenance_grant;',
         'resetting<=reset_valid;reset_grant<=maintenance_grant;window_status<=0;windows<=cfg_window_base;window_bytes<=cfg_window_bytes;'),
        ('CHECK:if(!config_good)', 'CHECK:if(!config_good||!window_config_good)'),
        ('else if(word_index==7)publish;', 'else if(word_index==7)begin if(trailer)publish;else state<=WINDOW_REQ;end'),
        ('RESULT:if(result_ready)state<=IDLE;',
         'WINDOW_REQ:if(init_ready)state<=WINDOW_WAIT;\n'
         '            WINDOW_WAIT:if(init_result_valid)begin\n'
         '                window_status<=init_status;\n'
         '                if(init_status==0)publish;\n'
         "                else begin quarantine(init_recovery_required?init_recovery_address:rpc_address,8'd22,init_memory_status);\n"
         '                    action<=ACT_CLOSE;control_op<=3;state<=CONTROL_REQ;end\n'
         '            end\n            RESULT:if(result_ready)state<=IDLE;'),
    ):
        text=replace_once(text,old,new)
    text=text.replace('// The parent still owns packet commit, flow control and whole-RPC/GPU leases.',
        '// New-stream results publish only after actual send-window initialization ACK.\n'
        '// Existing trailers preserve their window. Failed initialization closes the tentative RPC.\n'
        '// The parent still owns connection-window bootstrap, packet commit, flow-control replay and image leases.')
    target=source_path(root, 'rtl/http2_windowed_rpc_admission.v');target.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/windowed-rpc-admission-generation.json').write_text(json.dumps(dict(
        phase='generated_window_commit_fenced_admission',input_sha256={source_relative(p, root).as_posix():sha(p)
        for p in(source,Path(__file__))},generated_sha256=sha(target),
        requires_shared_actual_window_service=True,connection_bootstrap_integrated=False,
        complete_forward_application_joined=False,full_system_complete=False),indent=2)+'\n')
    print('Generated actual HEADERS admission fenced on send-window commit, with rollback/quarantine')


if __name__=='__main__':
    main()
