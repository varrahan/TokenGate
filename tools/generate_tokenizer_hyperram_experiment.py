"""Connect the actual Tokenizer/cache to the tested dual-clock word controller.

An explicit external image grant is still required from the whole-RPC/model
owner. Local idle alone must never grant a mutable vocabulary update.
"""
import hashlib
import json
from pathlib import Path
import shutil
from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    experiment=root/'build/experiments/tokenizer-hyperram'
    baseline=json.loads((root/'build/validation/hyperram-shared-reset.json').read_text())
    assert baseline['key']=='07002b9a4dd73fb7'
    backend=root/'build/experiments/hyperram-shared-reset/build/validation/shared_reset_full_image/sources'
    dependencies=closure('tokenizer_fpga_memory_subsystem')
    for source in set(dependencies.values()):
        target=experiment/'rtl'/source.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name,digest in baseline['inputs_sha256'].items():
        assert sha(backend/name)==digest
        if name.startswith('rtl/'):
            target=experiment/name;assert target.name not in {p.name for p in dependencies.values()},'Unexpected RTL overlap'
            shutil.copy2(backend/name,target)
    application=experiment/'rtl/tokenizer_fpga_memory_subsystem.v'
    controller=experiment/'rtl/axi_hyperram_async_controller.v'
    ap=ports(application.read_text(),'tokenizer_fpga_memory_subsystem')
    cp=ports(controller.read_text(),'axi_hyperram_async_controller')
    public=[(d,w.replace('MEMORY_ADDR_WIDTH','23'),n)for d,w,n in ap if n not in('clk','rst')and not n.startswith('m_axi_')]
    public += [(d,w,n)for d,w,n in cp]
    public += [('input','','external_image_grant'),('input','','maintenance_begin_valid'),
               ('output','','maintenance_begin_ready'),('output','','image_active'),
               ('output','','application_reset'),('output','','local_quiescent'),('output','','reload_rejected'),
               ('output','','maintenance_draining')]
    assert len({n for _,_,n in public})==len(public)
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Generated isolated integration: actual Tokenizer, cache and memory controller.',
        '// external_image_grant must cover all RPC/GPU/model leases, beyond local idle.',
        '// Host validates every image byte before reload_ack; no hardware digest is implied.',
        '// Package DDR/RWDS and physical inter-FPGA/PCIe adapters are separate.',
        'module tokenizer_hyperram_subsystem #(',
        '    parameter USER_WIDTH=16,MAX_TEXT_BYTES=16384,CACHE_LOG_LINES=6',')(',
        ',\n'.join(f'    {d} wire {w} {n}'for d,w,n in public),');',
        'localparam BOOT=0,RELOAD=1,ACTIVE=2,DRAIN=3;',
        'reg [1:0] state=BOOT;',
        'reg reload_grant_lost=0;',
        'assign reload_rejected=reload_grant_lost;',
        'wire controller_idle,controller_ack_ready,controller_done_valid;',
        'wire controller_ack_valid,controller_done_ready;',
        'wire base_active=(state==ACTIVE||state==DRAIN)&&!app_reset&&!contents_lost_app;',
        'wire maintenance_request=maintenance_begin_valid&&external_image_grant;',
        'wire admit_new_sequences=base_active&&state==ACTIVE&&!maintenance_request;',
        'assign maintenance_draining=state==DRAIN;',
        'wire app_memory_idle,app_bpe_idle,app_pack_idle,app_inverse_idle;',
        '// Sample each unit separately, cutting request/address validation out',
        '// of the image-state CE path. A full DRAIN cycle qualifies the sample.',
        'reg [3:0] idle_sample=0;',
        'reg drain_qualified=0;',
        'always @(posedge app_clk)begin',
        '    if(app_reset)begin idle_sample<=0;drain_qualified<=0;end',
        '    else begin',
        '        idle_sample<={app_memory_idle,app_bpe_idle,app_pack_idle,app_inverse_idle};',
        '        drain_qualified<=state==DRAIN&&maintenance_request&&!cfg_invalidate_valid;',
        '    end',
        'end',
        'assign local_quiescent=(&idle_sample)&&link_s_idle;',
        'assign maintenance_begin_ready=base_active&&state==DRAIN&&drain_qualified&&external_image_grant&&local_quiescent&&controller_idle&&!cfg_invalidate_valid;',
        'wire maintenance_fire=maintenance_begin_valid&&maintenance_begin_ready;',
        'assign image_active=base_active;',
        '// The synchronous application reset takes effect with the state change.',
        '// Request admission is independent of idle, avoiding a ready/idle loop.',
        '// Already-admitted forward bytes, DMA output and inverse chunks drain.',
        'assign application_reset=!base_active;',
        'assign controller_ack_valid=state==BOOT&&external_image_grant&&reload_ack_valid;',
        'assign reload_ack_ready=state==BOOT&&external_image_grant&&controller_ack_ready;',
        'assign reload_done_valid=state==RELOAD&&controller_done_valid;',
        'assign controller_done_ready=state==RELOAD&&reload_done_ready;',
        'always @(posedge app_clk)begin',
        '    if(app_reset)begin state<=BOOT;reload_grant_lost<=0;end',
        '    else case(state)',
        '        BOOT:if(reload_ack_valid&&reload_ack_ready)begin state<=RELOAD;reload_grant_lost<=0;end',
        '        RELOAD:begin',
        '            if(!external_image_grant)reload_grant_lost<=1;',
        '            if(reload_done_valid&&reload_done_ready)state<=reload_grant_lost||!external_image_grant?BOOT:ACTIVE;',
        '        end',
        '        ACTIVE:if(maintenance_request)state<=DRAIN;',
        '        DRAIN:if(!maintenance_request)state<=ACTIVE;else if(maintenance_fire)state<=BOOT;',
        '        default:state<=BOOT;',
        '    endcase','end']
    # Distinct internal names avoid sharing APP-side and host-side AXI owners.
    axi=[(d,w,n)for d,w,n in ap if n.startswith('m_axi_')]
    for _,w,n in axi:lines.append(f'wire {w.replace("MEMORY_ADDR_WIDTH","23")} app_{n};')
    for _,w,n in cp:
        if n.startswith('s_axi_'):lines.append(f'wire {w} controller_{n};')
    for d,w,n in axi:
        host='s_axi_'+n[6:];shared='controller_'+host;app='app_'+n
        if d=='output':
            lines.append(f'assign {shared}=state==BOOT?{host}:'+f'(image_active?{app}:0);')
        else:
            lines.append(f'assign {app}=image_active?{shared}:0;')
            lines.append(f'assign {host}=state==BOOT?{shared}:0;')
    mapping={n:n for _,_,n in ap};mapping.update(clk='app_clk',rst='application_reset',memory_idle='app_memory_idle',
        link_f_bpe_idle='app_bpe_idle',link_f_pack_idle='app_pack_idle',link_r_idle='app_inverse_idle')
    for d,w,n in ap:
        if n.startswith('m_axi_'):mapping[n]='app_'+n;continue
        if n in('clk','rst','memory_idle','link_f_bpe_idle','link_f_pack_idle','link_r_idle'):continue
        handshake=n.endswith(('valid','ready'))or n in('link_f_bpe_admit_sequences','link_s_s_axis_text_abort')
        if handshake:
            # Explicit invalidation excludes maintenance admission, avoiding a
            # combinational loop through the fabric's invalidate-aware idle.
            active='admit_new_sequences'if n in('link_f_bpe_admit_sequences','link_r_s_axis_tokens_tvalid','link_r_s_axis_tokens_tready')else'base_active'
            if d=='input':mapping[n]=n+'&&'+active
            else:
                lines.append(f'wire app_{n};');mapping[n]='app_'+n
                lines.append(f'assign {n}=app_{n}&&{active};')
    lines += ['assign memory_idle=app_memory_idle;','assign link_f_bpe_idle=app_bpe_idle;',
        'assign link_f_pack_idle=app_pack_idle;','assign link_r_idle=app_inverse_idle;',
        'tokenizer_fpga_memory_subsystem #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(23),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.CACHE_LOG_LINES(CACHE_LOG_LINES)) application(',
        ',\n'.join(f'    .{n}({mapping[n]})'for _,_,n in ap),');']
    mapping={n:('controller_'+n if n.startswith('s_axi_')else n)for _,_,n in cp}
    mapping.update(reload_ack_valid='controller_ack_valid',reload_ack_ready='controller_ack_ready',
        reload_done_valid='controller_done_valid',reload_done_ready='controller_done_ready',idle_app='controller_idle')
    lines += ['assign idle_app=controller_idle;','axi_hyperram_async_controller memory(',
        ',\n'.join(f'    .{n}({mapping[n]})'for _,_,n in cp),');','endmodule','`default_nettype wire','']
    target=experiment/'rtl/tokenizer_hyperram_subsystem.v';target.write_text('\n'.join(lines))
    result=dict(phase='actual_tokenizer_cache_and_hyperram_assembly_generated',
        generator_sha256=sha(Path(__file__)),controller_functional_audit_key=baseline['key'],
        application_modules=list(dependencies),inputs_sha256={source_relative(p, root).as_posix():sha(p)for p in set(dependencies.values())},
        outputs_sha256={p.relative_to(experiment).as_posix():sha(p)for p in(experiment/'rtl').glob('*.v')},
        actual_tokenizer_and_cache_instantiated=True,exclusive_host_loader_axi=True,
        image_activation_fences_application=True,maintenance_requires_external_grant_and_local_idle=True,
        cache_reset_before_reactivation=True,whole_rpc_external_grant_implementation_verified=False,
        registered_local_idle_samples=True,full_drain_cycle_required_before_maintenance_ack=True,
        functional_verification_complete=False,native_timing_verified=False,physical_phy_verified=False,full_system_complete=False)
    (experiment/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],rtl_files=len(result['outputs_sha256']),application_modules=len(dependencies))))


if __name__=='__main__':main()
