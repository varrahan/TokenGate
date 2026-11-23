`timescale 1ns/1ps
module tb_grpc_descriptors;
    localparam [22:0] POOL=23'h7c0003;
    localparam [31:0] MAGIC=32'h47524d31;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic cfg_valid=0,cfg_clear=0,cfg_result_ready=0;wire cfg_ready,cfg_result_valid;logic [22:0] cfg_base=POOL;logic [23:0] cfg_bytes=96;wire [7:0] cfg_status;
    logic begin_valid=0;wire begin_ready;logic [15:0] begin_user=16'h1234;logic [31:0] begin_tag=0;
    logic s_valid=0;wire s_ready;logic [15:0] s_user=0,s_application=0;logic [30:0] s_stream=0;logic s_protobuf=0;logic [22:0] s_base=0;logic [31:0] s_bytes=0,s_ordinal=0,s_generation=0;
    logic finish_valid=0,finish_commit=0,finish_result_ready=0;wire finish_ready,finish_result_valid,finish_committed;wire [7:0] finish_status,finish_detail,finish_memory_status;wire [15:0] finish_user;wire [31:0] finish_tag;
    wire m_valid;logic m_ready=0;wire [15:0] m_user,m_application;wire [30:0] m_stream;wire m_protobuf;wire [22:0] m_base;wire [31:0] m_bytes,m_ordinal,m_generation,m_packet_tag;
    wire transaction_active,transaction_failed,recovery_required,idle;wire [7:0] recovery_detail,recovery_memory_status;wire [31:0] queued_count,pending_count;
    wire [1:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [45:0] mem_addr;wire [7:0] mem_bytes;wire [143:0] mem_data,mem_rsp_data;logic [15:0] mem_rsp_status;
    wire [2:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [68:0] cmd_addr;wire [11:0] cmd_bytes;wire [215:0] cmd_data,response_data;wire [23:0] response_status;
    logic reader_enabled=1,consumer_enabled=1,manual_consumer=0,helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=4;logic [71:0] helper_data=0;
    integer fault_client=0,fault_target=-1,response_index=0;bit injected=0;
    grpc_descriptor_queue dut(.*);
    assign cmd_valid={helper_valid,mem_valid[1]&&reader_enabled,mem_valid[0]};assign cmd_write={1'b1,mem_write};assign cmd_addr={helper_addr,mem_addr};assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={helper_data,mem_data};
    assign mem_ready={cmd_ready[1]&&reader_enabled,cmd_ready[0]};assign mem_rsp_valid=response_valid[1:0];assign mem_rsp_data=response_data[143:0];assign response_ready={helper_rsp_ready,mem_rsp_ready};
    always @*begin mem_rsp_status=response_status[15:0];if(!injected&&response_index==fault_target)mem_rsp_status[fault_client*8+:8]=fault_client==0?8'h52:8'h63;end
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(3)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    logic [255:0] golden[0:2047],pending[0:31];integer golden_head=0,golden_tail=0,expected_pending=0,next_id=0,transactions=0,outputs=0,write_faults=0,read_faults=0,capacity_errors=0;
    reg [31:0] current_tag;
    wire [255:0] output_bundle={m_packet_tag,MAGIC,m_generation,9'd0,m_base,m_ordinal,m_bytes,m_protobuf,m_stream,m_application,m_user};
    bit output_stalled=0,result_stalled=0;logic [255:0] held_output;logic [72:0] held_result;logic [1:0] mem_stalled=0;logic [99:0] held_mem[0:1];
    wire [72:0] result_bundle={finish_committed,finish_status,finish_detail,finish_memory_status,finish_user,finish_tag};
    always @(negedge clk)if(!manual_consumer)m_ready=consumer_enabled&&$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(output_stalled&&(!m_valid||held_output!==output_bundle))$fatal(1,"Committed descriptor lease changed");output_stalled=m_valid&&!m_ready;held_output=output_bundle;
        if(result_stalled&&(!finish_result_valid||held_result!==result_bundle))$fatal(1,"Packet queue result changed");result_stalled=finish_result_valid&&!finish_result_ready;held_result=result_bundle;
        if((^{cfg_ready,cfg_result_valid,begin_ready,s_ready,finish_ready,finish_result_valid,m_valid,recovery_required,mem_valid,mem_rsp_ready})===1'bx)$fatal(1,"Unknown descriptor-queue handshake");
        if(m_valid&&((^output_bundle)===1'bx)||finish_result_valid&&((^result_bundle)===1'bx))$fatal(1,"Unknown descriptor metadata");
        for(integer c=0;c<2;c++)begin
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"Descriptor memory command changed");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&((^held_mem[c])===1'bx))$fatal(1,"Unknown descriptor memory command");
        end
        if(mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
        if(m_valid&&golden_head==golden_tail)$fatal(1,"Uncommitted descriptor escaped packet transaction");
        if(m_valid&&m_ready)begin
            if(output_bundle!==golden[golden_head])$fatal(1,"Descriptor ordering/metadata mismatch output=%0d actual=%h expected=%h",outputs,output_bundle,golden[golden_head]);
            golden_head++;outputs++;
        end
        if(pending_count+queued_count>3)$fatal(1,"Queue ownership exceeded configured three slots");
    end
    task configure(input bit clear,input [22:0] address,input integer bytes,input integer status);
        begin
            @(negedge clk);cfg_clear=clear;cfg_base=address;cfg_bytes=24'(bytes);cfg_valid=1;
            do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;cfg_base='1;cfg_bytes='1;
            wait(cfg_result_valid);if(cfg_status!=status)$fatal(1,"Queue configuration status");
            repeat(3)@(negedge clk);cfg_result_ready=1;@(posedge clk);@(negedge clk);cfg_result_ready=0;cfg_clear=0;
        end
    endtask
    task begin_packet;
        begin
            @(negedge clk);current_tag=32'h81000000+transactions;begin_tag=current_tag;begin_valid=1;expected_pending=0;
            do @(posedge clk);while(!begin_ready);@(negedge clk);begin_valid=0;begin_tag='1;
        end
    endtask
    task descriptor(input integer invalid_mode=0,input bit pop_together=0);
        begin
            @(negedge clk);s_user=invalid_mode==1?16'h1235:16'h1234;s_application=16'(16'h3000+next_id);s_stream=invalid_mode==2?0:31'(1+(next_id%17)*2);s_protobuf=next_id&1;
            s_base=invalid_mode==3?POOL:23'(24'h100003+next_id*64);s_bytes=invalid_mode==3?1:32'(next_id%33);s_ordinal=32'(next_id*9);s_generation=32'h44000000+next_id;s_valid=1;
            pending[expected_pending]={current_tag,MAGIC,s_generation,9'd0,s_base,s_ordinal,s_bytes,s_protobuf,s_stream,s_application,s_user};expected_pending++;next_id++;
            if(pop_together)m_ready=1;
            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;s_user='1;s_application='1;s_stream='1;s_base='1;s_bytes='1;s_ordinal='1;s_generation='1;
            if(pop_together)m_ready=0;
            wait(s_ready);
        end
    endtask
    task seal(input bit commit,input integer status,input integer detail=0,input integer memory_status=0);
        begin
            @(negedge clk);finish_valid=1;finish_commit=commit;
            do @(posedge clk);while(!finish_ready);
            if(commit&&status==0)for(integer i=0;i<expected_pending;i++)begin golden[golden_tail]=pending[i];golden_tail++;end
            @(negedge clk);finish_valid=0;finish_commit=0;
            wait(finish_result_valid);
            if(finish_committed!=(commit&&status==0)||finish_status!=status||finish_detail!=detail||finish_memory_status!=memory_status||finish_user!=16'h1234||finish_tag!=current_tag)$fatal(1,"Descriptor packet result transaction=%0d status=%0d/%0d detail=%0d/%0d mem=%0d/%0d",transactions,finish_status,status,finish_detail,detail,finish_memory_status,memory_status);
            repeat($urandom_range(2,10))@(negedge clk);finish_result_ready=1;@(posedge clk);@(negedge clk);finish_result_ready=0;transactions++;
        end
    endtask
    task fault_setup(input integer client,input integer target);
        begin @(negedge clk);fault_client=client;fault_target=target;response_index=0;injected=0;end
    endtask
    task corrupt_footer;
        begin
            @(negedge clk);helper_addr=POOL+24;helper_data=0;helper_valid=1;
            do @(posedge clk);while(!cmd_ready[2]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[2]);if(response_status[16+:8]!=0)$fatal(1,"Corruption helper write failed");
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);rst=0;
        configure(0,POOL,0,13);configure(0,23'h7ffff0,96,13);configure(0,POOL,95,13);configure(0,POOL,96,0);
        // Empty and aborted packets must not publish descriptors.
        begin_packet;seal(1,0);begin_packet;descriptor();descriptor();seal(0,0);wait(idle);
        // Older committed output is leased while a new pending transaction
        // appends; the ring wraps at a non-power-of-two slot count.
        consumer_enabled=0;begin_packet;descriptor();descriptor();seal(1,0);wait(m_valid);
        begin_packet;descriptor();seal(1,0);consumer_enabled=1;wait(idle);
        consumer_enabled=0;begin_packet;repeat(3)descriptor();seal(1,0);wait(m_valid);
        @(negedge clk);manual_consumer=1;m_ready=0;
        begin_packet;descriptor(0,1);seal(1,0);manual_consumer=0;consumer_enabled=1;wait(idle);
        for(integer t=0;t<100;t++)begin
            wait(queued_count<=1);begin_packet;descriptor();if(t%3)descriptor();seal(t%7!=0,0);
        end
        wait(idle);
        consumer_enabled=0;begin_packet;repeat(5)descriptor();if(!transaction_failed)$fatal(1,"Pending capacity did not fail without deadlocking");seal(1,8,3);capacity_errors++;consumer_enabled=1;wait(idle);
        for(integer mode=1;mode<=3;mode++)begin begin_packet;descriptor(mode);descriptor();seal(1,13,2);wait(idle);end
        // Failed writes target only pending slots and preserve an older held
        // committed descriptor. Subsequent packets work without global reset.
        for(integer target=0;target<4;target++)begin
            consumer_enabled=0;begin_packet;descriptor();seal(1,0);wait(m_valid);
            begin_packet;fault_setup(0,target);descriptor();descriptor();seal(1,13,target,82);
            if(!injected||recovery_required)$fatal(1,"Pending write fault recovery scope wrong");write_faults++;fault_setup(0,-1);consumer_enabled=1;wait(idle);
        end
        // Every committed read phase quarantines the queue and requires an
        // explicit clear after all memory commands have retired.
        for(integer target=0;target<4;target++)begin
            configure(1,POOL,96,0);reader_enabled=0;consumer_enabled=0;begin_packet;descriptor();seal(1,0);
            fault_setup(1,target);reader_enabled=1;wait(recovery_required);
            if(recovery_detail!=target||recovery_memory_status!=99||!injected||begin_ready||m_valid)$fatal(1,"Committed read fault not quarantined");read_faults++;fault_setup(1,-1);
            golden_head=golden_tail;configure(1,POOL,96,0);consumer_enabled=1;
        end
        configure(1,POOL,96,0);reader_enabled=0;consumer_enabled=0;begin_packet;descriptor();seal(1,0);
        begin_packet;descriptor();fault_setup(1,2);reader_enabled=1;wait(recovery_required);
        descriptor();seal(1,13,128,99);read_faults++;fault_setup(1,-1);golden_head=golden_tail;configure(1,POOL,96,0);consumer_enabled=1;
        configure(1,POOL,96,0);reader_enabled=0;consumer_enabled=0;begin_packet;descriptor();seal(1,0);corrupt_footer();reader_enabled=1;wait(recovery_required);
        if(recovery_detail!=4||recovery_memory_status!=0||m_valid)$fatal(1,"Corrupt committed descriptor escaped");golden_head=golden_tail;configure(1,POOL,96,0);consumer_enabled=1;
        begin_packet;descriptor();seal(1,0);wait(idle&&fabric_idle);
        if(golden_head!=golden_tail||write_faults!=4||read_faults!=5||capacity_errors!=1||outputs<100)$fatal(1,"Insufficient descriptor transaction coverage");
        $display("PASS: transactional external gRPC descriptor queue: %0d packets/%0d committed descriptors/%0d write faults/%0d read faults; pending visibility, abort, wrap, concurrent consumption, capacity drain, corruption quarantine and recovery",transactions,outputs,write_faults,read_faults);$finish;
    end
    initial begin #(64'd100000000);$fatal(1,"Descriptor queue timeout packet=%0d w=%0d r=%0d queued=%0d pending=%0d",transactions,dut.wstate,dut.rstate,queued_count,pending_count);end
endmodule
