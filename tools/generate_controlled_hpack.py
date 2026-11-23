"""Add ordered full control events before the actual HPACK dispatcher."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports, instance, named_instance, rename

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    source_path=source_path(root, 'rtl/http2_hpack_ingress.v')
    fork_path=source_path(root, 'rtl/http2_control_event_fork.v')
    source=source_path.read_text()
    public=[]
    fork_connections=dict(clk='clk',rst='rst',idle='control_fork_idle')
    forward=[]
    for direction,width,name in ports(fork_path.read_text(),'http2_control_event_fork'):
        if name.startswith('s_'):
            fork_connections[name]='sem_'+name[2:]
        elif name.startswith('m_'):
            fork_connections[name]='dispatch_event_'+name[2:]
            forward.append(f'wire {width} dispatch_event_{name[2:]};')
        elif name.startswith('control_'):
            mapped='flow_event_'+name[8:]
            fork_connections[name]=mapped
            public.append((direction,width,mapped))
    start,end,params,dispatch=instance(source,'http2_header_dispatch','dispatcher')
    dispatch.update({n:'dispatch_event_'+n[2:]for n in dispatch if n.startswith('s_')})
    dispatch['finish_valid']='payload_result_valid&&control_fork_idle'
    source=source[:start]+named_instance('http2_header_dispatch',params,'dispatcher',dispatch)+source[end:]
    source=source.replace('assign idle=base_idle&&payload_idle&&dispatch_idle;',
        'assign idle=base_idle&&payload_idle&&dispatch_idle&&control_fork_idle;')
    source=source.replace('endmodule','\n'.join(['wire control_fork_idle;',*forward,
        named_instance('http2_control_event_fork','.USER_WIDTH(USER_WIDTH)','control_fork',fork_connections),'endmodule']))
    source=rename(add_ports(source,'http2_hpack_ingress',public),'http2_hpack_ingress','http2_controlled_hpack_ingress')
    target=source_path(root, 'rtl/http2_controlled_hpack_ingress.v');target.write_text(source)
    original=root/'sim/tb_http2_hpack.sv'
    bench=original.read_text().replace('module tb_http2_hpack;','module tb_http2_controlled_hpack;')
    declarations=[]
    for direction,width,name in public:
        width=width.replace('USER_WIDTH','16')
        declarations.append(f"{'logic' if direction=='input' else 'wire'} {width} {name}{'=0' if direction=='input' else ''};")
    old='http2_hpack_ingress #(.BLOCK_START_PORT(1)) dut(.*);'
    assert old in bench
    bench=bench.replace(old,'\n'.join(declarations)+'\nhttp2_controlled_hpack_ingress #(.BLOCK_START_PORT(1)) dut(.*);')
    monitor='''
    integer flow_cycle=0,flow_count=0,flow_stalls=0,flow_settings_ack=0,flow_ping_ack=0,flow_data_begin=0;
    reg flow_stalled=0;reg [162:0] held_flow;
    wire [162:0] flow_bundle={flow_event_kind,flow_event_data,flow_event_arg0,flow_event_arg1,
        flow_event_length,flow_event_type,flow_event_flags,flow_event_stream,flow_event_user};
    always @(negedge clk)begin flow_cycle++;flow_event_ready=flow_cycle%71>=43;end
    always @(posedge clk)if(!rst)begin
        if(flow_stalled&&(!flow_event_valid||held_flow!==flow_bundle))$fatal(1,"Control event changed while stalled");
        if(flow_event_valid&&((^flow_bundle)===1'bx))$fatal(1,"Unknown control metadata");
        if(rsp_valid&&!rsp_is_command&&!dut.control_fork_idle)$fatal(1,"Packet completed with pending control ownership");
        flow_stalled=flow_event_valid&&!flow_event_ready;held_flow=flow_bundle;
        if(flow_stalled)flow_stalls++;
        if(flow_event_valid&&flow_event_ready)begin
            flow_count++;
            if(flow_event_user!=fields[0])$fatal(1,"Control lost connection identity");
            if(flow_event_kind==3&&flow_event_type==4&&flow_event_flags[0])flow_settings_ack++;
            if(flow_event_kind==5&&flow_event_type==6&&flow_event_flags[0])flow_ping_ack++;
            if(flow_event_kind==0&&flow_event_type==0)flow_data_begin++;
        end
    end
'''
    bench=bench.replace('    localparam [191:0]',monitor+'\n    localparam [191:0]',1)
    marker='        if(total<2000||header_total<100'
    assert marker in bench
    index=bench.index(marker)
    bench=bench[:index]+'''        if(flow_count<100||flow_stalls==0||flow_settings_ack==0||flow_ping_ack==0||flow_data_begin==0)$fatal(1,"Insufficient full control coverage");
        $display("CONTROL_FORK: %0d exact-metadata actions/%0d stall cycles/%0d SETTINGS ACK/%0d PING ACK/%0d raw DATA begins",flow_count,flow_stalls,flow_settings_ack,flow_ping_ack,flow_data_begin);
'''+bench[index:]
    harness=root/'sim/tb_http2_controlled_hpack.sv';harness.write_text(bench)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/http2-controlled-hpack-generation.json').write_text(json.dumps(dict(
        phase='generated_controlled_hpack',inputs_sha256={source_relative(p, root).as_posix():sha(p)for p in(source_path,fork_path,original,Path(__file__))},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in(target,harness)},
        control_before_dispatch=True,credit_ledger_verified=False,full_system_complete=False),indent=2)+'\n')
    print('Generated actual HTTP/2/HPACK ingress with ordered full-metadata controls and completion fencing')


if __name__=='__main__':
    main()
