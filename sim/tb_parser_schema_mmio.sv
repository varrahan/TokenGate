`timescale 1ns/1ps
module tb_parser_schema_mmio;
reg clk=0,rst=1;
always #2 clk=~clk;
glbl glbl();
reg [15:0] awaddr=0,araddr=0;
reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
wire awready,wready,bvalid,arready,rvalid;
reg [31:0] wdata=0;
reg [3:0] wstrb=0;
wire [1:0] bresp,rresp;
wire [31:0] rdata,epoch;
reg grant=0;
wire cfg_valid,decoder_cfg_ready,cfg_ready,quiet,committed,busy;
wire [3:0] cfg_index;
wire [255:0] cfg_key;
wire [5:0] cfg_length;
wire cfg_json,cfg_proto;
wire [28:0] cfg_field;
assign cfg_valid=dut.cfg_schema_valid;
assign cfg_ready=dut.cfg_schema_ready;
assign cfg_index=dut.cfg_schema_index;
assign cfg_key=dut.cfg_schema_key;
assign cfg_length=dut.cfg_schema_key_length;
assign cfg_json=dut.cfg_schema_json_enable;
assign cfg_proto=dut.cfg_schema_proto_enable;
assign cfg_field=dut.cfg_schema_field;
reg mode=0,rxvalid=0,rxlast=0,accept_output=1;
reg [511:0] rxdata=0;
reg [63:0] rxkeep=0;
reg [15:0] rxuser=0;
wire rxready,txvalid,txlast,error_valid;
wire [127:0] txdata;
wire [15:0] txkeep,txuser;
reg txready=0;
wire [7:0] error_code;
parser_schema_mmio_decoder dut(.clk(clk),.rst(rst),.cfg_protobuf(mode),.schema_maintenance_grant(grant),
    .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
    .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
    .schema_epoch(epoch),.schema_committed(committed),.schema_cfg_busy(busy),
    .s_axis_rx_tdata(rxdata),.s_axis_rx_tkeep(rxkeep),.s_axis_rx_tvalid(rxvalid),.s_axis_rx_tready(rxready),
    .s_axis_rx_tlast(rxlast),.s_axis_rx_tuser(rxuser),.s_axis_rx_abort(1'b0),
    .m_axis_text_tdata(txdata),.m_axis_text_tkeep(txkeep),.m_axis_text_tvalid(txvalid),.m_axis_text_tready(txready),
    .m_axis_text_tlast(txlast),.m_axis_text_tuser(txuser),.error_valid(error_valid),.error_ready(1'b1),
    .error_code(error_code),.error_user(),.idle(quiet));
byte unsigned raw_pool[0:1048575],text_pool[0:524287];
integer raw_base[0:64],raw_length[0:64],text_base[0:64],text_length[0:64],format[0:64];
integer response_idx=0,text_idx=0,cycles=0,applies=0,commits=0,write_count=0,read_count=0;
integer held_tx=0,held_cfg=0,held_b=0,held_r=0;
bit tx_stalled=0,cfg_stalled=0,b_stalled=0,r_stalled=0;
reg [160:0] saved_tx;
reg [296:0] saved_cfg;
reg [1:0] saved_b;
reg [33:0] saved_r;
wire [296:0] cfg_snapshot={cfg_index,cfg_key,cfg_length,cfg_json,cfg_field,cfg_proto};
always @(negedge clk)txready=!rst&&accept_output&&cycles%11>=4;
always @(posedge clk)begin
    cycles++;
    if(rst)begin tx_stalled=0;cfg_stalled=0;b_stalled=0;r_stalled=0;end
    else begin
        assert(!error_valid)else $fatal(1,"MMIO schema decoder rejected packet %0d code=%0d",response_idx,error_code);
        if(tx_stalled)assert(txvalid&&saved_tx=={txdata,txkeep,txlast,txuser})else $fatal(1,"Held text changed");
        if(cfg_stalled)assert(cfg_valid&&saved_cfg==cfg_snapshot)else $fatal(1,"Held schema command changed");
        if(b_stalled)assert(bvalid&&saved_b==bresp)else $fatal(1,"Held B changed");
        if(r_stalled)assert(rvalid&&saved_r=={rresp,rdata})else $fatal(1,"Held R changed");
        tx_stalled=txvalid&&!txready;saved_tx={txdata,txkeep,txlast,txuser};
        cfg_stalled=cfg_valid&&!cfg_ready;saved_cfg=cfg_snapshot;
        b_stalled=bvalid&&!bready;saved_b=bresp;r_stalled=rvalid&&!rready;saved_r={rresp,rdata};
        if(tx_stalled)held_tx++;
        if(cfg_stalled)held_cfg++;
        if(b_stalled)held_b++;
        if(r_stalled)held_r++;
        if(cfg_valid&&cfg_ready)begin assert(grant&&quiet)else $fatal(1,"Schema applied without quiescence/grant");applies++;end
        if(committed)begin assert(quiet&&!dut.decoder.schema_programming)else $fatal(1,"Reported schema commit before durable CAM rows");commits++;end
        if(bvalid&&bresp==0&&dut.mmio.address==8&&dut.mmio.write_strobes!=0)assert(!dut.decoder.schema_programming)else $fatal(1,"Apply B preceded durable CAM");
        if(txvalid&&txready)begin
            assert(response_idx<65&&txuser==16'h4000+response_idx)else $fatal(1,"Decoded packet/context order");
            for(integer lane=0;lane<16;lane++)if(txkeep[lane])begin
                assert(text_idx<text_length[response_idx]&&txdata[lane*8+:8]==text_pool[text_base[response_idx]+text_idx])
                    else $fatal(1,"Configured-schema extraction mismatch packet=%0d offset=%0d",response_idx,text_idx);
                text_idx++;
            end
            if(txlast)begin assert(text_idx==text_length[response_idx])else $fatal(1,"Extracted length");text_idx=0;response_idx++;end
        end
    end
end
task automatic wait_quiet;
    integer guard;guard=0;
    while(!quiet)begin @(negedge clk);guard++;assert(guard<1000000)else $fatal(1,"Decoder idle timeout");end
endtask
task automatic write_register(input integer address,input reg [31:0] data,input reg [3:0] strobes=15,input integer expected=0);
    integer order;
    order=write_count%3;write_count++;
    fork
        begin
            repeat(order)@(negedge clk);
            @(negedge clk);awaddr=16'(address);awvalid=1;
            do @(posedge clk);while(!awready);
            @(negedge clk);awvalid=0;awaddr='1;
        end
        begin
            repeat(2-order)@(negedge clk);
            @(negedge clk);wdata=data;wstrb=strobes;wvalid=1;
            do @(posedge clk);while(!wready);
            @(negedge clk);wvalid=0;wdata='1;wstrb=0;
        end
    join
    while(!bvalid)@(negedge clk);
    assert(bresp==expected)else $fatal(1,"Schema MMIO B status addr=%0h got=%0d expected=%0d",address,bresp,expected);
    repeat(7)@(negedge clk);
    bready=1;@(posedge clk);@(negedge clk);bready=0;
endtask
task automatic read_register(input integer address,input reg [31:0] expected,input integer status=0);
    @(negedge clk);araddr=16'(address);arvalid=1;
    do @(posedge clk);while(!arready);
    @(negedge clk);arvalid=0;araddr='1;
    while(!rvalid)@(negedge clk);
    assert(rdata==expected&&rresp==status)else $fatal(1,"Schema MMIO R mismatch address=%0h got=%0h expected=%0h",address,rdata,expected);
    repeat(9)@(negedge clk);
    rready=1;@(posedge clk);@(negedge clk);rready=0;read_count++;
endtask
task automatic packet(input integer index);
    integer offset,beat,guard;
    offset=0;beat=0;mode=1'(format[index]);
    while(offset<raw_length[index])begin
        @(negedge clk);rxdata=0;rxkeep=0;
        for(integer lane=0;lane<64;lane++)if(offset<raw_length[index]&&((lane+beat)%5!=0||lane==63))begin
            rxdata[lane*8+:8]=raw_pool[raw_base[index]+offset];rxkeep[lane]=1;offset++;
        end
        rxuser=beat==0?16'h4000+16'(index):16'hbad0;rxlast=offset==raw_length[index];rxvalid=1;guard=0;
        do begin @(posedge clk);guard++;assert(guard<1000000)else $fatal(1,"Schema decoder RX timeout");end while(!rxready);
        @(negedge clk);rxvalid=0;rxdata='1;rxkeep=0;beat++;
    end
endtask
task automatic finish_packet(input integer index);
    integer guard;guard=0;
    while(response_idx<=index)begin @(negedge clk);guard++;assert(guard<1000000)else $fatal(1,"Schema decoder completion timeout packet=%0d",index);end
    wait_quiet();
endtask
task automatic stage_schema(input integer generation);
    write_register(16'h10,0);write_register(16'h14,7);write_register(16'h18,3);write_register(16'h1c,generation==0?37:2712);
    // Repeated same-address partial writes must merge from the latest shadow.
    write_register(16'h20,32'hdeadbeef);
    if(generation==0)begin
        write_register(16'h20,32'h0073006d,5);write_register(16'h20,32'h73006500,10);
        write_register(16'h24,32'h00656761,7);
        read_register(16'h20,32'h7373656d);read_register(16'h24,32'h00656761);
    end else begin
        write_register(16'h20,32'h006e0063,5);write_register(16'h20,32'h74006f00,10);
        write_register(16'h24,32'h00746e65,7);
        read_register(16'h20,32'h746e6f63);read_register(16'h24,32'h00746e65);
    end
endtask
initial begin : test
    integer file,count,raw_offset,text_offset,result,byte_value;
    file=$fopen("schema-vectors.txt","r");assert(file!=0)else $fatal(1,"Missing complete schema fixtures");
    result=$fscanf(file,"%d",count);assert(result==1&&count==65)else $fatal(1,"Reduced schema corpus");
    raw_offset=0;text_offset=0;
    for(integer p=0;p<count;p++)begin
        result=$fscanf(file,"%d %d %d",format[p],raw_length[p],text_length[p]);assert(result==3)else $fatal(1,"Schema vector header");
        raw_base[p]=raw_offset;text_base[p]=text_offset;
        for(integer i=0;i<raw_length[p];i++)begin result=$fscanf(file,"%d",byte_value);assert(result==1)else $fatal(1,"Raw schema vector");raw_pool[raw_offset++]=8'(byte_value);end
        for(integer i=0;i<text_length[p];i++)begin result=$fscanf(file,"%d",byte_value);assert(result==1)else $fatal(1,"Text schema vector");text_pool[text_offset++]=8'(byte_value);end
    end
    $fclose(file);
    repeat(50)@(negedge clk);rst=0;wait_quiet();
    read_register(0,32'h50534331);read_register(12,0);read_register(16'h40,0,3);read_register(1,0,3);
    write_register(0,123,15,2);write_register(16'h40,123,15,3);write_register(17,0,15,2);
    accept_output=0;packet(0);while(!txvalid)@(negedge clk);
    stage_schema(0);write_register(8,1,15,2);assert(epoch==0&&applies==0)else $fatal(1,"Ungrant applied schema");
    repeat(17)@(negedge clk);accept_output=1;finish_packet(0);
    @(negedge clk);grant=1;
    write_register(8,0,0,0);assert(epoch==0)else $fatal(1,"Zero-strobe apply");
    write_register(16'h14,33);write_register(8,1,15,2);write_register(16'h14,1);write_register(8,1,15,2);write_register(16'h14,7);
    write_register(16'h10,16);write_register(8,1,15,2);write_register(16'h10,0);
    write_register(16'h1c,0);write_register(8,1,15,2);write_register(16'h1c,37);
    fork
        write_register(8,1);
        begin
            while(!cfg_valid)@(negedge clk);
            grant=0;
            repeat(19)begin @(negedge clk);assert(!bvalid&&cfg_valid)else $fatal(1,"Schema issue stall ordering");end
            read_register(4,5);@(negedge clk);grant=1;
        end
    join
    assert(epoch==1&&applies==1&&commits==1)else $fatal(1,"First durable schema epoch");
    read_register(12,1);@(negedge clk);grant=0;
    for(integer p=1;p<=32;p++)begin packet(p);finish_packet(p);end
    @(negedge clk);grant=1;stage_schema(1);write_register(8,1);read_register(12,2);
    @(negedge clk);grant=0;
    for(integer p=33;p<65;p++)begin packet(p);finish_packet(p);end
    assert(response_idx==65&&epoch==2&&applies==2&&commits==2&&held_cfg>=19&&held_tx>100&&held_b>100&&held_r>50)
        else $fatal(1,"Schema MMIO coverage packets=%0d epochs=%0d applies=%0d commits=%0d",response_idx,epoch,applies,commits);
    $display("PARSER_SCHEMA_MMIO_TEST_PASS packets=%0d applies=%0d commits=%0d AW_W_writes=%0d reads=%0d held_cfg=%0d held_tx=%0d held_B=%0d held_R=%0d",response_idx,applies,commits,write_count,read_count,held_cfg,held_tx,held_b,held_r);$finish;
end
initial begin #10000000;$fatal(1,"Schema MMIO watchdog");end
endmodule
