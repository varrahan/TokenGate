`timescale 1ns/1ps
module tb_tokenizer_mmio_bulk;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [15:0] s_axi_awaddr=0,s_axi_araddr=0;logic s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
    logic [31:0] s_axi_wdata=0;logic [3:0] s_axi_wstrb=0;wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;wire [1:0] s_axi_bresp,s_axi_rresp;wire [31:0] s_axi_rdata;
    logic [127:0] s_axis_text_tdata=0;logic [15:0] s_axis_text_tkeep=0,s_axis_text_tuser=0;logic s_axis_text_tvalid=0,s_axis_text_tlast=0;wire s_axis_text_tready;
    wire [511:0] m_axis_tokens_tdata;wire [63:0] m_axis_tokens_tkeep;wire [15:0] m_axis_tokens_tuser;wire m_axis_tokens_tvalid,m_axis_tokens_tlast;logic m_axis_tokens_tready=0;
    wire completion_valid,completion_failed;logic completion_ready=0;wire [31:0] completion_count;wire [15:0] completion_user;
    wire forward_error_valid;wire [7:0] forward_error_stage,forward_error_detail,forward_error_status;wire [15:0] forward_error_user;wire forward_error_ready=1;
    logic [31:0] s_axis_generated_tdata=0;logic s_axis_generated_tvalid=0,s_axis_generated_tlast=0;logic [15:0] s_axis_generated_tuser=0;wire s_axis_generated_tready;
    wire [127:0] m_axis_text_tdata;wire [15:0] m_axis_text_tkeep,m_axis_text_tuser;wire m_axis_text_tvalid,m_axis_text_tlast;logic m_axis_text_tready=0;
    wire reverse_error_valid;wire [7:0] reverse_error_code;wire [15:0] reverse_error_user;wire reverse_error_ready=1;
    wire [22:0] m_axi_araddr,m_axi_awaddr;wire [7:0] m_axi_arlen,m_axi_awlen,m_axi_wstrb;wire [2:0] m_axi_arsize,m_axi_awsize;wire [1:0] m_axi_arburst,m_axi_awburst;
    wire m_axi_arvalid,m_axi_arready,m_axi_rvalid,m_axi_rready,m_axi_rlast,m_axi_awvalid,m_axi_awready,m_axi_wvalid,m_axi_wready,m_axi_wlast,m_axi_bvalid,m_axi_bready;
    wire [63:0] m_axi_rdata,m_axi_wdata;wire [1:0] m_axi_rresp,m_axi_bresp;wire idle;
    byte unsigned reference[0:8388607];integer raw[0:8191],expected[0:8191];
    integer expected_count=0,expected_length=0,expected_user=0,received=0,reconstructed=0,forward_packets=0,reverse_packets=0;
    integer models=0,cases=0,total_ids=0,total_bytes=0,total_weights=0,total_operations=0,host_writes=0;
    bit dma_stalled=0,text_stalled=0;logic [592:0] held_dma;logic [160:0] held_text;
    scu35_tokenizer_mmio_subsystem dut(.*);
    // The model starts with unrelated data. No vocabulary initialization file
    // is supplied to the DUT's memory; all model bytes must traverse MMIO/AXI.
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(m_axi_araddr),.arlen(m_axi_arlen),.arsize(m_axi_arsize),.arburst(m_axi_arburst),.arvalid(m_axi_arvalid),.arready(m_axi_arready),.rdata(m_axi_rdata),.rresp(m_axi_rresp),.rlast(m_axi_rlast),.rvalid(m_axi_rvalid),.rready(m_axi_rready),
        .awaddr(m_axi_awaddr),.awlen(m_axi_awlen),.awsize(m_axi_awsize),.awburst(m_axi_awburst),.awvalid(m_axi_awvalid),.awready(m_axi_awready),.wdata(m_axi_wdata),.wstrb(m_axi_wstrb),.wlast(m_axi_wlast),.wvalid(m_axi_wvalid),.wready(m_axi_wready),
        .bresp(m_axi_bresp),.bvalid(m_axi_bvalid),.bready(m_axi_bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    always @(negedge clk)begin m_axis_tokens_tready=$urandom_range(0,3)!=0;m_axis_text_tready=$urandom_range(0,3)!=0;end
    always @(posedge clk)if(!rst)begin
        if(forward_error_valid||reverse_error_valid)$fatal(1,"Bulk model error forward=%0d/%0d/%0d reverse=%0d",forward_error_stage,forward_error_detail,forward_error_status,reverse_error_code);
        if(dma_stalled&&(!m_axis_tokens_tvalid||held_dma!=={m_axis_tokens_tuser,m_axis_tokens_tlast,m_axis_tokens_tkeep,m_axis_tokens_tdata}))$fatal(1,"Bulk DMA unstable");
        dma_stalled=m_axis_tokens_tvalid&&!m_axis_tokens_tready;held_dma={m_axis_tokens_tuser,m_axis_tokens_tlast,m_axis_tokens_tkeep,m_axis_tokens_tdata};
        if(text_stalled&&(!m_axis_text_tvalid||held_text!=={m_axis_text_tuser,m_axis_text_tlast,m_axis_text_tkeep,m_axis_text_tdata}))$fatal(1,"Bulk inverse output unstable");
        text_stalled=m_axis_text_tvalid&&!m_axis_text_tready;held_text={m_axis_text_tuser,m_axis_text_tlast,m_axis_text_tkeep,m_axis_text_tdata};
        if(completion_valid&&m_axis_tokens_tvalid)$fatal(1,"Bulk completion overtook DMA");
        if(m_axis_tokens_tvalid&&m_axis_tokens_tready)begin
            if(m_axis_tokens_tuser!=expected_user)$fatal(1,"Bulk forward context");
            for(integer lane=0;lane<16;lane++)begin
                if(m_axis_tokens_tkeep[lane*4+:4]!=0&&m_axis_tokens_tkeep[lane*4+:4]!=15)$fatal(1,"Bulk split ID");
                if(m_axis_tokens_tkeep[lane*4+:4]==15)begin
                    if(received>=expected_count||m_axis_tokens_tdata[lane*32+:32]!=expected[received])$fatal(1,"Bulk token model=%0d case=%0d index=%0d got=%0d expected=%0d",models,cases,received,m_axis_tokens_tdata[lane*32+:32],expected[received]);
                    received++;total_ids++;
                end
            end
            if(m_axis_tokens_tlast)begin if(received!=expected_count)$fatal(1,"Bulk final ID count");forward_packets++;end
        end
        if(m_axis_text_tvalid&&m_axis_text_tready)begin
            if(m_axis_text_tuser!=(expected_user^16'h8000))$fatal(1,"Bulk reverse context");
            for(integer lane=0;lane<16;lane++)if(m_axis_text_tkeep[lane])begin
                if(reconstructed>=expected_length||m_axis_text_tdata[lane*8+:8]!=raw[reconstructed])$fatal(1,"Bulk inverse bytes model=%0d case=%0d index=%0d",models,cases,reconstructed);
                reconstructed++;total_bytes++;
            end
            if(m_axis_text_tlast)begin if(reconstructed!=expected_length)$fatal(1,"Bulk final byte count");reverse_packets++;end
        end
    end
    task automatic write32(input [15:0] address_value,input [31:0] data_value);
        bit aw_done,w_done;
        aw_done=0;w_done=0;
        @(negedge clk);s_axi_awaddr=address_value;s_axi_wdata=data_value;s_axi_wstrb=15;s_axi_awvalid=1;s_axi_wvalid=1;s_axi_bready=1;
        do begin
            @(posedge clk);if(s_axi_awvalid&&s_axi_awready)aw_done=1;if(s_axi_wvalid&&s_axi_wready)w_done=1;
            @(negedge clk);s_axi_awvalid=!aw_done;s_axi_wvalid=!w_done;
        end while(!aw_done||!w_done);
        do @(posedge clk);while(!s_axi_bvalid);
        if(s_axi_bresp!=0)$fatal(1,"MMIO write failed addr=%h data=%h resp=%0d",address_value,data_value,s_axi_bresp);
        @(negedge clk);s_axi_bready=0;host_writes++;
    endtask
    task automatic read32(input [15:0] address_value,output [31:0] result_value);
        @(negedge clk);s_axi_araddr=address_value;s_axi_arvalid=1;s_axi_rready=1;
        do @(posedge clk);while(!s_axi_arready);@(negedge clk);s_axi_arvalid=0;
        do @(posedge clk);while(!s_axi_rvalid);
        if(s_axi_rresp!=0)$fatal(1,"MMIO read failed");result_value=s_axi_rdata;
        @(negedge clk);s_axi_rready=0;
    endtask
    task automatic run_plan(input string filename);
        integer fd,rc,polls;reg [63:0] operation;reg [31:0] result_value;
        fd=$fopen(filename,"rb");if(!fd)$fatal(1,"Missing programming plan %s",filename);
        while(!$feof(fd))begin
            rc=$fread(operation,fd);
            if(rc==8)begin
                case(operation[63:48])
                    1:write32(operation[47:32],operation[31:0]);
                    2:begin
                        polls=0;
                        do begin read32(operation[47:32],result_value);polls++;if(polls>1000)$fatal(1,"Bulk epoch poll timeout");end
                        while((result_value&{16'd0,operation[31:16]})!={16'd0,operation[15:0]});
                    end
                    3:begin read32(operation[47:32],result_value);if(result_value!=operation[31:0])$fatal(1,"Bulk MMIO assertion failed addr=%h got=%h expected=%h",operation[47:32],result_value,operation[31:0]);end
                    default:$fatal(1,"Invalid programming operation");
                endcase
                total_operations++;if(total_operations%500000==0)begin $display("PROGRESS: model %0d, %0d complete MMIO operations",models,total_operations);$fflush();end
            end else if(rc!=0)$fatal(1,"Truncated programming plan");
        end
        $fclose(fd);
    endtask
    task automatic send_text(input integer n);
        integer position_in;
        position_in=0;
        do begin
            @(negedge clk);s_axis_text_tdata=0;s_axis_text_tkeep=0;s_axis_text_tuser=expected_user;
            for(integer lane=0;lane<16;lane++)if(position_in<n&&(lane==15||$urandom_range(0,2)!=0))begin s_axis_text_tdata[lane*8+:8]=raw[position_in];s_axis_text_tkeep[lane]=1;position_in++;end
            s_axis_text_tlast=position_in==n;s_axis_text_tvalid=1;do @(posedge clk);while(!s_axis_text_tready);@(negedge clk);s_axis_text_tvalid=0;
        end while(position_in<n);
    endtask
    task automatic send_generated(input integer n);
        for(integer i=0;i<n;i++)begin
            @(negedge clk);s_axis_generated_tdata=expected[i];s_axis_generated_tlast=i+1==n;s_axis_generated_tuser=expected_user^16'h8000;s_axis_generated_tvalid=1;
            do @(posedge clk);while(!s_axis_generated_tready);@(negedge clk);s_axis_generated_tvalid=0;
        end
    endtask
    initial begin:driver
        integer list_fd,image_fd,vectors_fd,rc,weight_bytes,n,k,context_number,f_target,r_target;
        string image_name,plan_name,vectors_name;reg [63:0] expected_word;
        repeat(5)@(negedge clk);rst=0;
        list_fd=$fopen("models.txt","r");if(!list_fd)$fatal(1,"No bulk models");
        while(!$feof(list_fd))begin
            rc=$fscanf(list_fd,"%s %s %s %d",image_name,plan_name,vectors_name,weight_bytes);
            if(rc==4)begin
                image_fd=$fopen(image_name,"rb");if(!image_fd)$fatal(1,"No golden model");rc=$fread(reference,image_fd);$fclose(image_fd);if(rc!=8388608||weight_bytes%8!=0)$fatal(1,"Bad golden image");
                run_plan(plan_name);wait(idle);
                // Compare every protected byte, including empty hash slots,
                // invalid directory entries and padding, after real writes.
                for(integer word_index=0;word_index<weight_bytes/8;word_index++)begin
                    expected_word=0;for(integer lane=0;lane<8;lane++)expected_word[lane*8+:8]=reference[word_index*8+lane];
                    if(memory_model.memory[word_index]!==expected_word)$fatal(1,"Bulk image mismatch model=%0d address=%h",models,word_index*8);
                end
                total_weights+=weight_bytes;
                vectors_fd=$fopen(vectors_name,"r");if(!vectors_fd)$fatal(1,"No model references");
                while(!$feof(vectors_fd))begin
                    rc=$fscanf(vectors_fd,"%d %d %d",n,k,context_number);
                    if(rc==3)begin
                        if(n>8192||k>8192)$fatal(1,"Bulk vector capacity");
                        for(integer i=0;i<n;i++)begin rc=$fscanf(vectors_fd,"%d",raw[i]);if(rc!=1)$fatal(1,"Bad raw vector");end
                        for(integer i=0;i<k;i++)begin rc=$fscanf(vectors_fd,"%d",expected[i]);if(rc!=1)$fatal(1,"Bad ID vector");end
                        expected_count=k;expected_length=n;expected_user=context_number;received=0;reconstructed=0;f_target=forward_packets+1;r_target=reverse_packets+(k!=0);
                        fork send_text(n);send_generated(k);join
                        wait(completion_valid&&forward_packets==f_target&&reverse_packets==r_target);@(negedge clk);
                        if(completion_failed||completion_count!=k||completion_user!=context_number)$fatal(1,"Bulk completion mismatch");
                        repeat(5)@(negedge clk);completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;wait(idle);@(negedge clk);cases++;
                    end else if(!$feof(vectors_fd))$fatal(1,"Bad model vector header");
                end
                $fclose(vectors_fd);models++;$display("PROGRESS: full model %0d loaded and checked, %0d protected bytes/%0d bidirectional cases",models,weight_bytes,cases);$fflush();
            end else if(!$feof(list_fd))$fatal(1,"Bad models list");
        end
        $fclose(list_fd);
        if(models!=3||cases!=30||total_weights<16000000||total_ids<300||total_operations<8000000)$fatal(1,"Bulk coverage models=%0d cases=%0d weights=%0d IDs=%0d ops=%0d",models,cases,total_weights,total_ids,total_operations);
        $display("PASS: full MMIO cold load and model replacement: %0d complete models/%0d protected bytes/%0d MMIO operations, %0d bidirectional native-reference packets/%0d IDs/%0d decoded bytes; initial memory unrelated, every model byte verified, cl100k/r50k/HuggingFace weights replaced without synthesis",models,total_weights,total_operations,cases,total_ids,total_bytes);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Bulk MMIO timeout register=%0d forward=%0d epoch=%0d",dut.registers.state,dut.tokenizer.forward_engine.state,dut.tokenizer.epoch_control.state);end
endmodule
