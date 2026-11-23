`timescale 1ns/1ps
module tb_tokenizer_subsystem;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic update_req=0,commit=0,abort_update=0,tables_valid=1;wire cfg_unlock,vocabulary_valid,protocol_error,draining,idle;
    wire [31:0] epoch;
    logic cfg_valid=0,cfg_rsp_ready=0,inv=0;wire cfg_ready,cfg_rsp_valid,inv_ready;wire [7:0] cfg_rsp_status;
    logic [22:0] cfg_addr=0;logic [3:0] cfg_bytes=0;logic [71:0] cfg_data=0;
    integer cfg[0:12];logic [1:0] profile=0;
    logic [127:0] s_data=0;logic [15:0] s_keep=0,s_user=0;logic s_valid=0,s_last=0;wire s_ready;
    logic [31:0] generated=0;logic gen_valid=0,gen_last=0;logic [15:0] gen_user=0;wire gen_ready;
    wire [511:0] dma_data;wire [63:0] dma_keep;wire [15:0] dma_user;wire dma_valid,dma_last;logic dma_ready=0;
    wire [127:0] text_data;wire [15:0] text_keep,text_user;wire text_valid,text_last;logic text_ready=0;
    wire completion_valid,completion_failed;logic completion_ready=0;wire [31:0] completion_count;wire [15:0] completion_user;
    wire forward_error,reverse_error;wire [7:0] forward_stage,forward_detail,forward_status,reverse_code;
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [63:0] rdata,wdata;wire [1:0] rresp,bresp;
    integer raw[0:19999],expected[0:19999],reverse_ids[0:19999],reverse_bytes[0:39999];
    integer expected_count=0,reverse_count=0,reverse_length=0,expected_user=0,received=0,reconstructed=0;
    integer sequences=0,token_total=0,byte_total=0,forward_packets=0,reverse_packets=0,updates=0,write_count=0,protocol_errors=0;
    bit started_forward=0,started_reverse=0,request_update=0,dma_stalled=0,text_stalled=0,completion_stalled=0;
    logic [592:0] held_dma;logic [160:0] held_text;logic [48:0] held_completion;
    scu35_tokenizer_subsystem dut(
        .clk(clk),.rst(rst),.update_req(update_req),.commit(commit),.abort_update(abort_update),.tables_valid(tables_valid),
        .cfg_unlock(cfg_unlock),.epoch(epoch),.vocabulary_valid(vocabulary_valid),.protocol_error(protocol_error),.draining(draining),
        .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_bytes(cfg_bytes),.cfg_data(cfg_data),.cfg_rsp_valid(cfg_rsp_valid),.cfg_rsp_ready(cfg_rsp_ready),.cfg_rsp_status(cfg_rsp_status),
        .cfg_invalidate_valid(inv),.cfg_invalidate_ready(inv_ready),.cfg_profile(profile),.cfg_class_base(23'(cfg[0])),.cfg_hash_base(23'(cfg[1])),.cfg_node_base(23'(cfg[2])),.cfg_edge_base(23'(cfg[3])),
        .cfg_node_count(32'(cfg[4])),.cfg_edge_count(32'(cfg[5])),.cfg_work_floor(23'(cfg[6])),.cfg_scalar_base(23'(cfg[7])),.cfg_scalar_bytes(24'(cfg[8])),
        .cfg_merge_base(23'(cfg[9])),.cfg_merge_bytes(24'(cfg[10])),.cfg_commit_base(23'(cfg[11])),.cfg_commit_bytes(24'(cfg[12])),
        .directory_base(23'd0),.pool_base(23'h100000),.strip_special_tokens(1'b0),
        .s_axis_text_tdata(s_data),.s_axis_text_tkeep(s_keep),.s_axis_text_tvalid(s_valid),.s_axis_text_tready(s_ready),.s_axis_text_tlast(s_last),.s_axis_text_tuser(s_user),
        .m_axis_tokens_tdata(dma_data),.m_axis_tokens_tkeep(dma_keep),.m_axis_tokens_tvalid(dma_valid),.m_axis_tokens_tready(dma_ready),.m_axis_tokens_tlast(dma_last),.m_axis_tokens_tuser(dma_user),
        .completion_valid(completion_valid),.completion_ready(completion_ready),.completion_failed(completion_failed),.completion_count(completion_count),.completion_user(completion_user),
        .forward_error_valid(forward_error),.forward_error_ready(1'b1),.forward_error_stage(forward_stage),.forward_error_detail(forward_detail),.forward_error_status(forward_status),.forward_error_user(),
        .s_axis_generated_tdata(generated),.s_axis_generated_tvalid(gen_valid),.s_axis_generated_tready(gen_ready),.s_axis_generated_tlast(gen_last),.s_axis_generated_tuser(gen_user),
        .m_axis_text_tdata(text_data),.m_axis_text_tkeep(text_keep),.m_axis_text_tvalid(text_valid),.m_axis_text_tready(text_ready),.m_axis_text_tlast(text_last),.m_axis_text_tuser(text_user),
        .reverse_error_valid(reverse_error),.reverse_error_ready(1'b1),.reverse_error_code(reverse_code),.reverse_error_user(),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(idle));
    axi_external_memory_model memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    always @(negedge clk)begin dma_ready=$urandom_range(0,3)!=0;text_ready=$urandom_range(0,3)!=0;end
    always @(posedge clk)if(!rst)begin
        if(forward_error||reverse_error)$fatal(1,"Unexpected subsystem error forward=%0d/%0d/%0d reverse=%0d",forward_stage,forward_detail,forward_status,reverse_code);
        if(protocol_error)protocol_errors++;
        if(dma_stalled&&(!dma_valid||held_dma!=={dma_user,dma_last,dma_keep,dma_data}))$fatal(1,"Subsystem DMA unstable");
        dma_stalled=dma_valid&&!dma_ready;held_dma={dma_user,dma_last,dma_keep,dma_data};
        if(text_stalled&&(!text_valid||held_text!=={text_user,text_last,text_keep,text_data}))$fatal(1,"Subsystem reverse text unstable");
        text_stalled=text_valid&&!text_ready;held_text={text_user,text_last,text_keep,text_data};
        if(completion_stalled&&(!completion_valid||held_completion!=={completion_user,completion_failed,completion_count}))$fatal(1,"Subsystem completion unstable");
        completion_stalled=completion_valid&&!completion_ready;held_completion={completion_user,completion_failed,completion_count};
        if(completion_valid&&dma_valid)$fatal(1,"Completion overtook final DMA payload");
        if(dma_valid&&dma_ready)begin
            if(dma_user!=expected_user)$fatal(1,"Subsystem forward context");
            for(integer lane=0;lane<16;lane++)begin
                if(dma_keep[lane*4+:4]!=0&&dma_keep[lane*4+:4]!=15)$fatal(1,"Subsystem split token");
                if(dma_keep[lane*4+:4]==15)begin
                    if(received>=expected_count||dma_data[lane*32+:32]!=expected[received])$fatal(1,"Subsystem token sequence=%0d index=%0d",sequences,received);
                    received++;token_total++;
                end
            end
            if(dma_last)begin if(received!=expected_count)$fatal(1,"Subsystem final token count");forward_packets++;end
        end
        if(text_valid&&text_ready)begin
            if(text_user!=(expected_user^16'h8000))$fatal(1,"Subsystem reverse context");
            for(integer lane=0;lane<16;lane++)if(text_keep[lane])begin
                if(reconstructed>=reverse_length||text_data[lane*8+:8]!=reverse_bytes[reconstructed])$fatal(1,"Reverse bytes sequence=%0d index=%0d got=%0d expected=%0d",sequences,reconstructed,text_data[lane*8+:8],reverse_bytes[reconstructed]);
                reconstructed++;byte_total++;
            end
            if(text_last)begin if(reconstructed!=reverse_length)$fatal(1,"Subsystem final byte count");reverse_packets++;end
        end
    end
    task automatic start_update;
        @(negedge clk);update_req=1;wait(cfg_unlock);@(negedge clk);update_req=0;
    endtask
    task automatic commit_image;
        integer old_epoch;
        old_epoch=epoch;wait(idle);@(negedge clk);commit=1;@(posedge clk);@(negedge clk);commit=0;
        if(epoch!=old_epoch+1||!vocabulary_valid||cfg_unlock)$fatal(1,"Epoch commit failed");updates++;
    endtask
    task automatic send_text(input integer n);
        integer position_in;
        position_in=0;
        do begin
            @(negedge clk);s_data=0;s_keep=0;s_user=expected_user;
            for(integer lane=0;lane<16;lane++)if(position_in<n&&(lane==15||$urandom_range(0,2)!=0))begin s_data[lane*8+:8]=raw[position_in];s_keep[lane]=1;position_in++;end
            s_last=position_in==n;s_valid=1;do @(posedge clk);while(!s_ready);
            started_forward=1;@(negedge clk);s_valid=0;
        end while(position_in<n);
    endtask
    task automatic send_generated;
        for(integer i=0;i<reverse_count;i++)begin
            @(negedge clk);generated=reverse_ids[i];gen_user=expected_user^16'h8000;gen_last=i+1==reverse_count;gen_valid=1;
            do @(posedge clk);while(!gen_ready);started_reverse=1;@(negedge clk);gen_valid=0;
        end
    endtask
    task automatic run_case(input integer n);
        integer f_target,r_target;
        received=0;reconstructed=0;started_forward=0;started_reverse=0;
        f_target=forward_packets+1;r_target=reverse_packets+(reverse_count!=0);
        fork
            send_text(n);
            send_generated();
            begin
                if(request_update)begin
                    wait(started_forward&&(started_reverse||reverse_count==0));@(negedge clk);update_req=1;
                    repeat(4)begin @(negedge clk);if(cfg_unlock)$fatal(1,"Epoch grant before active sequences drain");end
                end
            end
        join
        wait(completion_valid&&forward_packets==f_target&&reverse_packets==r_target);@(negedge clk);
        if(completion_failed||completion_count!=expected_count||completion_user!=expected_user)$fatal(1,"Subsystem wrong completion");
        repeat(7)begin @(negedge clk);if(request_update&&cfg_unlock)$fatal(1,"Epoch grant before completion ACK");end
        completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;wait(idle);@(negedge clk);sequences++;
        if(request_update)begin wait(cfg_unlock);@(negedge clk);update_req=0;commit_image();end
    endtask
    task automatic write_runtime(input integer address_value,input integer count_value,input [71:0] data_value,input bit abort_and_recover);
        integer old_epoch;
        old_epoch=epoch;
        @(negedge clk);cfg_addr=address_value;cfg_bytes=count_value;cfg_data=data_value;cfg_valid=1;
        do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;
        if(abort_and_recover)begin
            commit=1;@(posedge clk);@(negedge clk);commit=0;
            if(!protocol_error||epoch!=old_epoch||!cfg_unlock)$fatal(1,"Pending loader command escaped commit barrier");
            abort_update=1;@(posedge clk);@(negedge clk);abort_update=0;update_req=1;
        end
        wait(cfg_rsp_valid);repeat(8)begin
            @(negedge clk);
            if(idle||cfg_ready||(abort_and_recover&&cfg_unlock))$fatal(1,"Held write completion escaped drain barrier");
        end
        if(cfg_rsp_status!=0)$fatal(1,"Runtime write failed %0d",cfg_rsp_status);
        cfg_rsp_ready=1;@(posedge clk);@(negedge clk);cfg_rsp_ready=0;write_count++;
        if(abort_and_recover)begin wait(cfg_unlock);@(negedge clk);update_req=0;end
    endtask
    initial begin:driver
        integer fd,rc,n,k,p,context_number,special_id,special_addr,special_len;
        integer old_special[0:63],new_special[0:63];reg [71:0] write_data;
        fd=$fopen("config.txt","r");if(!fd)$fatal(1,"Missing subsystem config");
        for(integer i=0;i<13;i++)begin rc=$fscanf(fd,"%d",cfg[i]);if(rc!=1)$fatal(1,"Bad subsystem config");end $fclose(fd);
        repeat(5)@(negedge clk);rst=0;
        // Verification memory starts with the complete image. This commit does
        // not claim that a host/MMIO bulk loader has programmed all 8 MiB.
        start_update();commit_image();
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing subsystem vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d",n,k,p,context_number);
            if(rc==4)begin
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",raw[i]);if(rc!=1)$fatal(1,"Missing raw bytes");reverse_bytes[i]=raw[i];end
                for(integer i=0;i<k;i++)begin rc=$fscanf(fd,"%d",expected[i]);if(rc!=1)$fatal(1,"Missing IDs");reverse_ids[i]=expected[i];end
                profile=p;expected_user=context_number;expected_count=k;reverse_count=k;reverse_length=n;request_update=sequences%25==1;
                run_case(n);if(sequences%50==0)$display("PROGRESS: %0d concurrent bidirectional tokenizer sequences",sequences);
            end else if(!$feof(fd))$fatal(1,"Bad subsystem fixture");
        end $fclose(fd);
        fd=$fopen("reload.txt","r");if(!fd)$fatal(1,"Missing reload fixture");rc=$fscanf(fd,"%d %d %d",special_id,special_addr,special_len);if(rc!=3||special_len>64)$fatal(1,"Bad reload header");
        for(integer i=0;i<special_len;i++)begin rc=$fscanf(fd,"%d",old_special[i]);if(rc!=1)$fatal(1,"Bad old special");end
        for(integer i=0;i<special_len;i++)begin rc=$fscanf(fd,"%d",new_special[i]);if(rc!=1)$fatal(1,"Bad new special");end $fclose(fd);
        profile=0;expected_user=16'h1234;expected_count=1;expected[0]=188;raw[0]=0;reverse_count=1;reverse_ids[0]=special_id;reverse_length=special_len;request_update=0;
        for(integer i=0;i<special_len;i++)reverse_bytes[i]=old_special[i];run_case(1);
        start_update();
        for(integer offset=0;offset<special_len;offset+=9)begin
            write_data=0;for(integer lane=0;lane<9&&offset+lane<special_len;lane++)write_data[lane*8+:8]=new_special[offset+lane];
            write_runtime(special_addr+offset,special_len-offset>=9?9:special_len-offset,write_data,offset==0);
        end
        @(negedge clk);inv=1;do @(posedge clk);while(!inv_ready);@(negedge clk);inv=0;commit_image();
        for(integer i=0;i<special_len;i++)reverse_bytes[i]=new_special[i];run_case(1);
        if(sequences!=275||token_total<24800||byte_total<30000||updates<10||write_count!=2||protocol_errors!=1)$fatal(1,"Subsystem coverage sequences=%0d tokens=%0d bytes=%0d updates=%0d writes=%0d protocol=%0d",sequences,token_total,byte_total,updates,write_count,protocol_errors);
        $display("PASS: shared bidirectional tokenizer: %0d sequences/%0d exact IDs/%0d exact decoded bytes, %0d epochs, %0d runtime writes; ten clients, ongoing-sequence drain, completion ordering, aborted-write recovery and native-reference special reload",sequences,token_total,byte_total,updates,write_count);$finish;
    end
    initial begin #(64'd20000000000);$fatal(1,"Shared tokenizer timeout fwd=%0d reverse=%0d epoch=%0d loader=%0d",dut.forward_engine.state,dut.reverse_engine.state,dut.epoch_control.state,dut.loader.state);end
endmodule
