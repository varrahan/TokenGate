"""Isolate one qualified reset per clock domain for all four memory FIFOs."""
import hashlib
import json
import os
from pathlib import Path
import shutil


RESET_MODULE = '''
// One reset qualification point per domain, shared by all packet/control FIFOs.
// Both clocks free-run. Supply/PHY qualification is synchronous to mem_clk.
// Its registered failure indication and external rst each assert asynchronously
// into a vendor synchronizer; final FIFO reset is clock-synchronous locally.
module hyperram_shared_domain_reset(
    input wire app_clk,mem_clk,rst,power_good_mem,phy_ready_mem,
    output wire app_fifo_reset,mem_fifo_reset
);
    reg power_bad_mem=1'b1;
    always @(posedge mem_clk)power_bad_mem<=!power_good_mem||!phy_ready_mem;
    wire rst_app_async,rst_mem_async,power_app_async,power_mem_async;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) external_app_reset(
        .src_arst(rst),.dest_clk(app_clk),.dest_arst(rst_app_async));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) external_mem_reset(
        .src_arst(rst),.dest_clk(mem_clk),.dest_arst(rst_mem_async));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) power_app_reset(
        .src_arst(power_bad_mem),.dest_clk(app_clk),.dest_arst(power_app_async));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) power_mem_reset(
        .src_arst(power_bad_mem),.dest_clk(mem_clk),.dest_arst(power_mem_async));
    reg app_reset_reg=1'b1,mem_reset_reg=1'b1;
    always @(posedge app_clk)app_reset_reg<=rst_app_async||power_app_async;
    always @(posedge mem_clk)mem_reset_reg<=rst_mem_async||power_mem_async;
    assign app_fifo_reset=app_reset_reg;
    assign mem_fifo_reset=mem_reset_reg;
endmodule
'''


def replace_once(text, old, new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=root/'build/validation/hyperram_async_windows_full_image_wide_timeout'
    baseline=json.loads((root/'build/validation/hyperram-async-native.json').read_text())
    assert baseline['key']=='cdd643b6c5c660c7'
    experiment=root/'build/experiments/hyperram-shared-reset'
    outputs={}
    for name,digest in baseline['inputs_sha256'].items():
        assert sha(parent/'sources'/name)==digest
        if not name.startswith(('rtl/','sim/')):continue
        target=experiment/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(parent/'sources'/name,target)
    fifo=experiment/'rtl/cdc_packet_fifo.v';text=fifo.read_text()
    text=replace_once(text,'input wire s_clk,m_clk,reset_request,','input wire s_clk,m_clk,s_fifo_reset,m_fifo_reset,')
    start=text.index('    // Async assertion enters a vendor reset synchronizer.')
    end=text.index('    wire wr_busy,rd_busy,full,empty;',start)
    text=text[:start]+'''    // Inputs are shared, locally clock-qualified FIFO resets. The aliases
    // retain the pre-existing startup diagnostic names, not extra reset logic.
    wire s_reset_async=s_fifo_reset,m_reset_async=m_fifo_reset;
'''+text[end:]
    text=text.replace('// Reset assertion/release is local-clock qualified; reset_request aborts outstanding work.',
                      '// Reset assertion/release is local-clock qualified; shared reset aborts outstanding work.')
    text=text.replace('// free-run. Hold reset_request through at least two edges of the slower clock.',
                      '// free-run. Hold shared reset through at least two edges of the slower clock.')
    text=text.replace('`default_nettype wire',RESET_MODULE+'`default_nettype wire')
    fifo.write_text(text)
    bridge=experiment/'rtl/hyperram_clock_bridge.v';text=bridge.read_text()
    text=replace_once(text,'module hyperram_clock_bridge(','module hyperram_clock_bridge #(parameter SHARED_DOMAIN_RESETS=0)(')
    text=replace_once(text,'input wire app_clk,mem_clk,reset_request,',
        'input wire app_clk,mem_clk,reset_request,\n    input wire app_domain_reset,mem_domain_reset,')
    marker='    wire cmd_app_reset,cmd_mem_reset,rsp_mem_reset,rsp_app_reset;'
    text=replace_once(text,marker,'''    wire app_fifo_reset,mem_fifo_reset;
    generate if(SHARED_DOMAIN_RESETS)begin:external_resets
        assign app_fifo_reset=app_domain_reset;
        assign mem_fifo_reset=mem_domain_reset;
    end else begin:standalone_resets
        hyperram_shared_domain_reset reset_domains(
            .app_clk(app_clk),.mem_clk(mem_clk),.rst(reset_request),
            .power_good_mem(1'b1),.phy_ready_mem(1'b1),
            .app_fifo_reset(app_fifo_reset),.mem_fifo_reset(mem_fifo_reset));
    end endgenerate
'''+marker)
    text=replace_once(text,'.s_clk(app_clk),.m_clk(mem_clk),.reset_request(reset_request),',
        '.s_clk(app_clk),.m_clk(mem_clk),.s_fifo_reset(app_fifo_reset),.m_fifo_reset(mem_fifo_reset),')
    text=replace_once(text,'.s_clk(mem_clk),.m_clk(app_clk),.reset_request(reset_request),',
        '.s_clk(mem_clk),.m_clk(app_clk),.s_fifo_reset(mem_fifo_reset),.m_fifo_reset(app_fifo_reset),')
    bridge.write_text(text)
    top=experiment/'rtl/axi_hyperram_async_controller.v';text=top.read_text()
    marker='wire reset_request=rst||!power_good_mem||!phy_ready_mem;'
    text=replace_once(text,marker,marker+'''
// Common request is diagnostic only. No combinational mixture of reset causes
// enters the domain synchronizers or packet handshakes.
wire shared_app_fifo_reset,shared_mem_fifo_reset;
hyperram_shared_domain_reset reset_domains(
    .app_clk(app_clk),.mem_clk(mem_clk),.rst(rst),
    .power_good_mem(power_good_mem),.phy_ready_mem(phy_ready_mem),
    .app_fifo_reset(shared_app_fifo_reset),.mem_fifo_reset(shared_mem_fifo_reset));''')
    text=replace_once(text,'hyperram_clock_bridge clock_bridge(',
        'hyperram_clock_bridge #(.SHARED_DOMAIN_RESETS(1)) clock_bridge(\n'
        '    .app_domain_reset(shared_app_fifo_reset),.mem_domain_reset(shared_mem_fifo_reset),')
    text=replace_once(text,'.s_clk(app_clk),.m_clk(mem_clk),.reset_request(reset_request),',
        '.s_clk(app_clk),.m_clk(mem_clk),.s_fifo_reset(shared_app_fifo_reset),.m_fifo_reset(shared_mem_fifo_reset),')
    text=replace_once(text,'.s_clk(mem_clk),.m_clk(app_clk),.reset_request(reset_request),',
        '.s_clk(mem_clk),.m_clk(app_clk),.s_fifo_reset(shared_mem_fifo_reset),.m_fifo_reset(shared_app_fifo_reset),')
    assert text.count('.SRC_INPUT_REG(0)')==3
    text=text.replace('.SRC_INPUT_REG(0)','.SRC_INPUT_REG(1)')
    top.write_text(text)
    test=experiment/'sim/tb_hyperram_clock_bridge.sv';shutil.copy2(root/'sim/tb_hyperram_clock_bridge.sv',test)
    text=test.read_text();text=replace_once(text,'hyperram_clock_bridge dut(.*);',
        "wire app_domain_reset=1'b1,mem_domain_reset=1'b1;\n    hyperram_clock_bridge dut(.*);")
    test.write_text(text)
    # Keep the proven independent device/AXI model and host unchanged for the
    # first comparison. Separate supply/PHY-loss scenarios follow this pass.
    for name in ('check_async_hyperram_windows','elaborate_async_hyperram_windows','run_async_hyperram_windows',
                 'run_hyperram_cdc_windows','generate_hyperram_async_timing_harness','generate_hyperram_cdc_timing_harness'):
        path=root/'tools'/(name+'.py');target=experiment/'tools'/path.name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    image_sha=baseline['image_sha256']
    image=root/'build/frozen-hyperram-images'/image_sha/'external_memory.bin'
    target=experiment/'build/frozen-hyperram-images'/image_sha/'external_memory.bin'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert os.path.samefile(image,target)
    else:os.link(image,target)
    for path in experiment.rglob('*'):
        if path.is_file()and path.parts[-2]in('rtl','sim','tools'):outputs[path.relative_to(experiment).as_posix()]=sha(path)
    report=dict(parent_audit_key=baseline['key'],parent_inputs_sha256=baseline['inputs_sha256'],
        generator_sha256=sha(Path(__file__)),outputs_sha256=outputs,primary_rtl_modified=False,
        shared_clock_qualified_resets=True,registered_supply_phy_failure_source=True,
        external_reset_synchronized_separately=True,status_registered_before_crossing=True,
        functional_verification_complete=False,native_verification_complete=False,full_system_complete=False)
    (experiment/'generation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(experiment=str(experiment),outputs=len(outputs),primary_rtl_modified=False)))


if __name__=='__main__':main()
