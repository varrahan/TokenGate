`timescale 1ns/1ps
module tb_external_detokenizer;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [22:0] directory_base=0,pool_base=23'h100000;
    logic [31:0] token=0;
    logic token_valid=0,token_last=0,strip=0;
    logic [15:0] user_id=1;
    wire token_ready,text_valid,text_last,idle,error_valid;
    wire [127:0] text_data;
    wire [15:0] text_keep,text_user,error_user;
    wire [7:0] error_code;
    logic text_ready=0,error_ready=0;
    logic inv=0;
    wire inv_ready;
    logic wv=0,cfg_unlock=0,wrr=1;
    wire wr,wrv;
    logic [22:0] wa=0;
    logic [71:0] wd=0;
    wire [7:0] ws;
    wire [22:0] araddr,awaddr;
    wire [7:0] arlen,awlen,wstrb;
    wire [2:0] arsize,awsize;
    wire [1:0] arburst,awburst;
    wire arvalid,rready,awvalid,wvalid,wlast,bready;
    wire [63:0] wdata;
    logic arready=0,rvalid=0,rlast=0,awready=0,wready=0,bvalid=0;
    logic [63:0] rdata=0;
    logic [1:0] rresp=0;
    logic [63:0] memory[0:262143];
    byte unsigned expected[0:32767];
    integer ids[0:127];
    integer expected_len=0,read_idx=0,packets=0,errors=0,expected_error=0;
    integer token_count=0,read_bursts=0,write_bursts=0;
    bit read_active=0,read_accepted=0,aw_have=0,w_have=0,b_accepted=0;
    integer read_word=0,read_beat=0,write_word=0;
    logic [63:0] buffered_write;
    logic [7:0] buffered_strobes;
    logic fault_enable=0,fault_latched=0;
    logic [22:0] fault_line=0;
    bit was_stalled=0,error_stalled=0;
    logic [160:0] held;
    logic [23:0] error_held;
    scu35_detokenizer_subsystem dut(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(wv),.cfg_ready(wr),
        .cfg_addr(wa),.cfg_bytes(4'd8),.cfg_data(wd),.cfg_rsp_valid(wrv),.cfg_rsp_ready(wrr),.cfg_rsp_status(ws),
        .cfg_invalidate_valid(inv),.cfg_invalidate_ready(inv_ready),
        .strip_special_tokens(strip),.s_axis_tokens_tdata(token),.s_axis_tokens_tvalid(token_valid),
        .s_axis_tokens_tready(token_ready),.s_axis_tokens_tlast(token_last),.s_axis_tokens_tuser(user_id),
        .m_axis_text_tdata(text_data),.m_axis_text_tkeep(text_keep),.m_axis_text_tvalid(text_valid),
        .m_axis_text_tready(text_ready),.m_axis_text_tlast(text_last),.m_axis_text_tuser(text_user),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(idle),
        .directory_base(directory_base),.pool_base(pool_base),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
        .m_axi_bresp(2'd0),.m_axi_bvalid(bvalid),.m_axi_bready(bready));
    // Independent AXI channels, random latency, read faults and output stalls.
    // The image is preloaded into the emulated memory, not the FPGA's BRAM.
    always @(negedge clk)begin
        text_ready=$urandom_range(0,3)!=0;error_ready=$urandom_range(0,3)!=0;
        arready=!read_active&&!rvalid&&$urandom_range(0,3)!=0;
        if(!rvalid||read_accepted)begin
            rvalid=read_active&&$urandom_range(0,3)!=0;
            if(rvalid)begin rdata=memory[read_word+read_beat];rlast=read_beat==7;rresp=fault_latched&&read_beat==3?2:0;end
        end
        awready=!aw_have&&!bvalid&&$urandom_range(0,2)!=0;
        wready=!w_have&&!bvalid&&$urandom_range(0,2)!=0;
        if(b_accepted)bvalid=0;
        else if(aw_have&&w_have&&!bvalid&&$urandom_range(0,2)!=0)bvalid=1;
    end
    always @(posedge clk)begin
        read_accepted=rvalid&&rready;b_accepted=bvalid&&bready;
        if(!rst)begin
            if(was_stalled&&(!text_valid||held!=={text_user,text_last,text_keep,text_data}))$fatal(1,"Text changed under stall");
            was_stalled=text_valid&&!text_ready;held={text_user,text_last,text_keep,text_data};
            if(error_stalled&&(!error_valid||error_held!=={error_user,error_code}))$fatal(1,"Error changed under stall");
            error_stalled=error_valid&&!error_ready;error_held={error_user,error_code};
            if(error_valid&&error_ready)begin
                if(error_code!=expected_error||error_user!=user_id)$fatal(1,"Unexpected error %0d expected %0d",error_code,expected_error);
                errors++;
            end
            if(text_valid&&text_ready)begin
                if(text_user!=user_id)$fatal(1,"Text context mismatch");
                for(integer i=0;i<16;i++)if(text_keep[i])begin
                    if(read_idx>=expected_len||text_data[i*8+:8]!==expected[read_idx])
                        $fatal(1,"External detokenizer mismatch packet=%0d byte=%0d got=%h expected=%h",packets,read_idx,text_data[i*8+:8],expected[read_idx]);
                    read_idx++;
                end
                if(text_last)packets++;
            end
            if(arvalid&&arready)begin
                if(araddr>=23'h200000||araddr[5:0]!=0||arlen!=7||arsize!=3||arburst!=1)$fatal(1,"Invalid external read");
                read_word=araddr>>3;read_beat=0;read_active=1;read_bursts++;
                fault_latched=fault_enable&&araddr==fault_line;
            end
            if(read_accepted)begin if(rlast)read_active=0;else read_beat++;end
            if(b_accepted)begin
                for(integer lane=0;lane<8;lane++)if(buffered_strobes[lane])memory[write_word][lane*8+:8]=buffered_write[lane*8+:8];
                aw_have=0;w_have=0;write_bursts++;
            end
            if(awvalid&&awready)begin
                if(awaddr>=23'h200000||awlen!=0||awsize!=3||awburst!=1)$fatal(1,"Invalid write");
                aw_have=1;write_word=awaddr>>3;
            end
            if(wvalid&&wready)begin
                if(!wlast)$fatal(1,"Expected single write beat");
                w_have=1;buffered_write=wdata;buffered_strobes=wstrb;
            end
        end
    end
    task automatic send_token(input integer value,input bit last);
        @(negedge clk);token=value;token_last=last;token_valid=1;
        do @(posedge clk);while(!token_ready);
        token_count++;
        @(negedge clk);token_valid=0;
    endtask
    task automatic finish_packet(input integer target);
        wait(packets==target);@(negedge clk);
        if(read_idx!=expected_len||!idle)$fatal(1,"Packet did not finish cleanly %0d/%0d",read_idx,expected_len);
        read_idx=0;expected_len=0;
    endtask
    task automatic invalidate;
        @(negedge clk);inv=1;cfg_unlock=1;
        do @(posedge clk);while(!inv_ready);
        @(negedge clk);inv=0;cfg_unlock=0;
    endtask
    task automatic write_directory(input logic[63:0] value);
        @(negedge clk);wa=0;wd={8'd0,value};wv=1;wrr=0;
        repeat(3)begin @(posedge clk);if(wr||idle||token_ready)$fatal(1,"Write admitted without grant, or pending write did not block commit/admission");end
        @(negedge clk);cfg_unlock=1;
        do @(posedge clk);while(!wr);
        @(negedge clk);wv=0;cfg_unlock=0;
        while(!wrv)begin @(negedge clk);if(token_ready||idle)$fatal(1,"Admission/commit before external write completed");end
        if(ws!=0)$fatal(1,"Runtime write failed");
        repeat(6)begin @(negedge clk);if(!wrv||ws!=0||token_ready||idle)$fatal(1,"Write completion/backpressure lost");end
        wrr=1;@(posedge clk);
        @(negedge clk);
    endtask
    initial begin:driver
        integer fd,n,length,context_number,strip_number,rc,byte_value,target,before_reads,before_errors;
        logic[63:0] original_entry;
        $readmemh("memory.mem",memory);
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing external vectors");
        target=0;
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d",n,length,context_number,strip_number);
            if(rc!=4)begin if(!$feof(fd))$fatal(1,"Bad vector header");end
            else begin
                if(n<1||n>128||length>32768)$fatal(1,"Vector capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",ids[i]);if(rc!=1)$fatal(1,"Missing ID");end
                for(integer i=0;i<length;i++)begin rc=$fscanf(fd,"%d",byte_value);if(rc!=1)$fatal(1,"Missing byte");expected[i]=byte_value;end
                user_id=context_number;strip=strip_number;expected_len=length;
                for(integer i=0;i<n;i++)send_token(ids[i],i+1==n);
                target++;finish_packet(target);
            end
        end
        $fclose(fd);
        if(token_count!=100266||errors!=0)$fatal(1,"Incomplete full-vocabulary coverage tokens=%0d",token_count);
        // Base addresses and special-token policy are held for a full sequence.
        user_id=16'hbeef;strip=1;expected[0]="!";expected[1]="\"";expected_len=2;
        send_token(0,0);directory_base=23'h7fffff;pool_base=23'h7fffff;strip=0;
        send_token(100257,0);send_token(1,1);target++;finish_packet(target);
        directory_base=0;pool_base=23'h100000;
        // Runtime cache writes must invalidate stale directory lines.
        original_entry=memory[0];write_directory(memory[1]);
        expected[0]="\"";expected_len=1;send_token(0,1);target++;finish_packet(target);
        write_directory(original_entry);
        expected[0]="!";expected_len=1;send_token(0,1);target++;finish_packet(target);
        // Error reporting retains context and suppresses failed lookup bytes.
        for(integer fault=0;fault<6;fault++)begin
            before_errors=errors;before_reads=read_bursts;
            invalidate();fault_enable=0;
            case(fault)
                0:begin expected_error=1;token=131072;end
                1:begin expected_error=2;token=100256;end
                2:begin expected_error=4;token=0;fault_enable=1;fault_line=0;end
                3:begin expected_error=5;token=0;fault_enable=1;fault_line=23'h100000;end
                4:begin expected_error=6;token=0;directory_base=23'h7fffff;end
                5:begin expected_error=6;token=0;pool_base=23'h7fffff;end
            endcase
            send_token(token,1);target++;finish_packet(target);
            if(errors!=before_errors+1)$fatal(1,"Missing lookup error");
            if((fault==0||fault==4)&&read_bursts!=before_reads)$fatal(1,"Invalid address escaped to memory");
            directory_base=0;pool_base=23'h100000;
        end
        if(write_bursts!=2)$fatal(1,"Missing runtime reload writes");
        $display("PASS: external detokenizer: all 100256 ordinary + 5 special tokens, %0d packets, %0d refills; dynamic cache writes, per-sequence configuration, bounds/memory faults and stalls",packets,read_bursts);
        $finish;
    end
    initial begin #100000000;$fatal(1,"External detokenizer timeout");end
endmodule
