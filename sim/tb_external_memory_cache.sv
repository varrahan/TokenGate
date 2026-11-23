`timescale 1ns/1ps
module tb_external_memory_cache;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic inv=0,rv=0,wv=0;
    wire inv_ready,rr,wr,idle,rrv,wrv;
    logic rrr=0,wrr=0;
    logic [11:0] ra=0,wa=0;
    logic [3:0] rn=0,wn=0;
    logic [71:0] wd=0;
    wire [71:0] rdata;
    wire [7:0] rstatus,wstatus;
    wire [11:0] araddr,awaddr;
    wire [7:0] arlen,awlen,wstrb;
    wire [2:0] arsize,awsize;
    wire [1:0] arburst,awburst;
    wire arvalid,awvalid,wvalid,wlast,rready,bready;
    logic arready=0,awready=0,wready=0,rvalid=0,rlast=0,bvalid=0;
    logic [63:0] axi_rdata=0;
    wire [63:0] axi_wdata;
    logic [1:0] rresp=0,bresp=0;
    byte unsigned memory[0:4095],golden[0:4095];
    integer read_fault=0,write_fault=0;
    integer ar_count=0,aw_count=0,w_before_aw=0,reads=0,writes=0;
    bit read_active=0,read_accepted=0,b_accepted=0,aw_have=0,w_last_have=0,b_pending=0;
    integer read_base=0,read_beat=0,read_last_beat=7,read_fault_latched=0;
    integer write_base=0,write_beats=0,w_count=0,write_fault_latched=0;
    logic [63:0] w_buffer[0:1];
    logic [7:0] strobe_buffer[0:1];
    bit last_buffer[0:1];
    bit ar_stalled=0,aw_stalled=0,w_stalled=0,read_stalled=0,write_stalled=0;
    logic [24:0] ar_held,aw_held;
    logic [72:0] w_held;
    logic [79:0] read_held;
    logic [7:0] write_held;
    external_memory_cache #(.ADDR_WIDTH(12),.CACHE_LOG_LINES(2)) dut (
        .clk(clk),.rst(rst),.invalidate_valid(inv),.invalidate_ready(inv_ready),
        .rd_valid(rv),.rd_ready(rr),.rd_addr(ra),.rd_bytes(rn),
        .rd_rsp_valid(rrv),.rd_rsp_ready(rrr),.rd_rsp_data(rdata),.rd_rsp_status(rstatus),
        .wr_valid(wv),.wr_ready(wr),.wr_addr(wa),.wr_bytes(wn),.wr_data(wd),
        .wr_rsp_valid(wrv),.wr_rsp_ready(wrr),.wr_rsp_status(wstatus),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
        .m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(axi_rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),
        .m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(axi_wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
        .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(idle));
    // Adversarial legal AXI slave: AWREADY can wait for WVALID or buffered W,
    // while WREADY can wait for AWVALID or buffered AW. Channels are independent.
    always @(negedge clk)begin
        rrr=$urandom_range(0,3)!=0;wrr=$urandom_range(0,3)!=0;
        arready=!read_active&&!rvalid&&$urandom_range(0,2)!=0;
        awready=!aw_have&&!b_pending&&!bvalid&&(wvalid||w_count>0)&&$urandom_range(0,2)!=0;
        wready=!w_last_have&&!b_pending&&!bvalid&&(awvalid||aw_have)&&$urandom_range(0,2)!=0;
        if(!rvalid || read_accepted)begin
            rvalid=read_active&&$urandom_range(0,3)!=0;
            if(rvalid)begin
                for(integer lane=0;lane<8;lane++)axi_rdata[lane*8+:8]=memory[read_base+read_beat*8+lane];
                rlast=read_beat==read_last_beat;
                rresp=(read_fault_latched==1&&read_beat==3)?2:0;
            end
        end
        if(b_accepted)bvalid=0;
        else if(!bvalid&&b_pending&&$urandom_range(0,2)!=0)begin bvalid=1;bresp=write_fault_latched?2:0;end
    end
    always @(posedge clk)begin
        read_accepted=rvalid&&rready;b_accepted=bvalid&&bready;
        if(!rst)begin
            if(ar_stalled&&(!arvalid||ar_held!=={araddr,arlen,arsize,arburst}))$fatal(1,"AR changed while stalled");
            if(aw_stalled&&(!awvalid||aw_held!=={awaddr,awlen,awsize,awburst}))$fatal(1,"AW changed while stalled");
            if(w_stalled&&(!wvalid||w_held!=={axi_wdata,wstrb,wlast}))$fatal(1,"W changed while stalled");
            if(read_stalled&&(!rrv||read_held!=={rstatus,rdata}))$fatal(1,"Read response changed while stalled");
            if(write_stalled&&(!wrv||write_held!==wstatus))$fatal(1,"Write response changed while stalled");
            ar_stalled=arvalid&&!arready;ar_held={araddr,arlen,arsize,arburst};
            aw_stalled=awvalid&&!awready;aw_held={awaddr,awlen,awsize,awburst};
            w_stalled=wvalid&&!wready;w_held={axi_wdata,wstrb,wlast};
            read_stalled=rrv&&!rrr;read_held={rstatus,rdata};
            write_stalled=wrv&&!wrr;write_held=wstatus;
            if(arvalid&&arready)begin
                if(arlen!=7||arsize!=3||arburst!=1||araddr[5:0]!=0)$fatal(1,"Invalid cache refill burst");
                ar_count++;read_active=1;read_base=araddr;read_beat=0;read_fault_latched=read_fault;
                read_last_beat=read_fault==2?3:read_fault==3?8:7;
            end
            if(read_accepted)begin
                if(rlast)read_active=0;else read_beat++;
            end
            if(b_accepted)begin b_pending=0;aw_have=0;w_last_have=0;w_count=0;end
            if(awvalid&&awready)begin
                if(awlen>1||awsize!=3||awburst!=1||awaddr[2:0]!=0)$fatal(1,"Invalid write burst");
                if(w_count>0)w_before_aw++;
                aw_count++;aw_have=1;write_base=awaddr;write_beats=awlen+1;write_fault_latched=write_fault;
            end
            if(wvalid&&wready)begin
                if(w_count>=2)$fatal(1,"Too many write beats");
                w_buffer[w_count]=axi_wdata;strobe_buffer[w_count]=wstrb;last_buffer[w_count]=wlast;
                w_count++;if(wlast)w_last_have=1;
            end
            if(aw_have&&w_last_have&&!b_pending)begin
                if(w_count!=write_beats)$fatal(1,"Write length does not match AWLEN");
                for(integer beat=0;beat<w_count;beat++)begin
                    if(last_buffer[beat]!=(beat+1==w_count))$fatal(1,"Incorrect WLAST placement");
                    if(!write_fault_latched)for(integer lane=0;lane<8;lane++)if(strobe_buffer[beat][lane])
                        memory[write_base+beat*8+lane]=w_buffer[beat][lane*8+:8];
                end
                b_pending=1;
            end
        end
    end
    task automatic invalidate;
        @(negedge clk);inv=1;
        do @(posedge clk);while(!inv_ready);
        @(negedge clk);inv=0;
    endtask
    task automatic read_command(input integer address,input integer count,input integer expected_status);
        logic [71:0] expected_data;
        begin
            expected_data=0;
            if(expected_status==0)for(integer lane=0;lane<count;lane++)expected_data[lane*8+:8]=golden[address+lane];
            @(negedge clk);ra=12'(address);rn=4'(count);rv=1;
            do @(posedge clk);while(!rr);
            @(negedge clk);rv=0;
            do @(posedge clk);while(!(rrv&&rrr));
            if(rstatus!=expected_status || (expected_status==0 && rdata!==expected_data))
                $fatal(1,"Cache read mismatch addr=%h bytes=%0d data=%h expected=%h status=%0d expected_status=%0d",address,count,rdata,expected_data,rstatus,expected_status);
            reads++;
            @(negedge clk);
        end
    endtask
    task automatic write_command(input integer address,input integer count,input logic[71:0] value,input integer expected_status);
        @(negedge clk);wa=12'(address);wn=4'(count);wd=value;wv=1;
        do @(posedge clk);while(!wr);
        @(negedge clk);wv=0;
        do @(posedge clk);while(!(wrv&&wrr));
        if(wstatus!=expected_status)$fatal(1,"Cache write status mismatch");
        if(expected_status==0)for(integer lane=0;lane<count;lane++)golden[address+lane]=value[lane*8+:8];
        writes++;
        @(negedge clk);
    endtask
    initial begin: driver
        integer before_count,address,count;
        logic[71:0] value;
        for(integer i=0;i<4096;i++)begin memory[i]=8'(i*37+(i>>5)*19+(i>>8)*11+7);golden[i]=memory[i];end
        repeat(5)@(negedge clk);rst=0;
        read_command(63,9,0);before_count=ar_count;
        read_command(63,9,0);if(ar_count!=before_count)$fatal(1,"Repeated hit performed external refill");
        for(integer offset=0;offset<64;offset++)for(integer n=1;n<=9;n++)read_command(512+offset,n,0);
        read_command(0,8,0);read_command(256,8,0);before_count=ar_count;
        read_command(0,8,0);if(ar_count==before_count)$fatal(1,"Conflicting cache tag was not checked");
        for(integer i=0;i<200;i++)begin
            count=$urandom_range(1,9);address=$urandom_range(0,4096-count);
            value={$urandom,$urandom,$urandom};
            write_command(address,count,value,0);read_command(address,count,0);
        end
        // Explicit cross-line write invalidates both cached lines.
        read_command(63,9,0);write_command(63,9,72'h123456789abcdef012,0);read_command(63,9,0);
        before_count=ar_count;invalidate();read_command(63,9,0);
        if(ar_count==before_count)$fatal(1,"Global invalidation did not force refill");
        read_command(4095,9,1);read_command(0,0,1);read_command(0,10,1);
        write_command(4095,9,0,1);write_command(0,0,0,1);write_command(0,10,0,1);
        for(integer fault=1;fault<=3;fault++)begin
            invalidate();read_fault=fault;read_command(1024,9,fault==1?2:3);
            read_fault=0;read_command(1024,9,0);
        end
        write_fault=1;write_command(1024,9,72'hffffffffffffffffff,4);
        write_fault=0;read_command(1024,9,0);
        if(w_before_aw==0 || !idle || reads<750 || writes<200)$fatal(1,"Insufficient AXI/cache coverage");
        $display("PASS: external BRAM cache: %0d reads, %0d writes, %0d W-before-AW transactions; word/line crossings, tags, invalidation, AXI faults and stalls",reads,writes,w_before_aw);
        $finish;
    end
    initial begin #5000000;$fatal(1,"AXI/cache timeout");end
endmodule
