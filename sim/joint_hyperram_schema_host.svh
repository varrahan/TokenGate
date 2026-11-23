// Actual AXI-Lite host stimulus; the production peripheral drives the real CAM.
integer schema_file,total_schema_applies=0,total_schema_accepts=0;
always @(posedge app_clk)if(!rst)begin
    if(dut.parser.cfg_schema_valid&&dut.parser.cfg_schema_ready)begin
        total_schema_accepts++;
        $fwrite(schema_file,"ACCEPT %0d %0d %0d %0d %0d %064h\n",current_epoch,
            dut.parser.cfg_schema_index,dut.parser.cfg_schema_key_length,
            dut.parser.cfg_schema_field,{dut.parser.cfg_schema_proto_enable,dut.parser.cfg_schema_json_enable},
            dut.parser.cfg_schema_key);
    end
    if(parser_schema_row_committed)begin
        total_schema_applies++;
        $fwrite(schema_file,"DURABLE %0d %0d\n",current_epoch,parser_schema_row_epoch);
    end
end
task automatic schema_read(input integer address,input reg [31:0] expected);
    reg [31:0] saved;
    @(negedge app_clk);parser_s_axi_schema_araddr=16'(address);
    `JOINT_SEND(parser_s_axi_schema_arvalid,parser_s_axi_schema_arready)
    `JOINT_WAIT(parser_s_axi_schema_rvalid,2000000)
    saved=parser_s_axi_schema_rdata;
    assert(parser_s_axi_schema_rresp==0&&saved==expected)else $fatal(1,"Schema CSR read addr=%h got=%h expected=%h",address,saved,expected);
    repeat(11)begin @(negedge app_clk);
        assert(parser_s_axi_schema_rvalid&&parser_s_axi_schema_rresp==0&&parser_s_axi_schema_rdata==saved)
            else $fatal(1,"Held schema R changed");
    end
    $fwrite(schema_file,"READ %0d %04h %08h\n",current_epoch,address,saved);
    `JOINT_ACK(parser_s_axi_schema_rvalid,parser_s_axi_schema_rready,0)
endtask
task automatic schema_write(input integer address,input reg [31:0] data,input integer first);
    reg [1:0] saved;
    @(negedge app_clk);parser_s_axi_schema_awaddr=16'(address);
    parser_s_axi_schema_wdata=data;parser_s_axi_schema_wstrb=15;
    if(first==0)begin
        `JOINT_SEND(parser_s_axi_schema_awvalid,parser_s_axi_schema_awready)
        repeat(3)@(negedge app_clk);
        `JOINT_SEND(parser_s_axi_schema_wvalid,parser_s_axi_schema_wready)
    end else begin
        `JOINT_SEND(parser_s_axi_schema_wvalid,parser_s_axi_schema_wready)
        repeat(5)@(negedge app_clk);
        `JOINT_SEND(parser_s_axi_schema_awvalid,parser_s_axi_schema_awready)
    end
    `JOINT_WAIT(parser_s_axi_schema_bvalid,2000000)
    saved=parser_s_axi_schema_bresp;
    assert(saved==0)else $fatal(1,"Schema CSR write addr=%h rejected status=%0d quiet=%0d",address,saved,parser_cfg_quiescent);
    repeat(9)begin @(negedge app_clk);
        assert(parser_s_axi_schema_bvalid&&parser_s_axi_schema_bresp==saved)else $fatal(1,"Held schema B changed");
    end
    $fwrite(schema_file,"WRITE %0d %04h %08h\n",current_epoch,address,data);
    `JOINT_ACK(parser_s_axi_schema_bvalid,parser_s_axi_schema_bready,0)
endtask
task automatic program_runtime_schema;
    reg [255:0] key;
    integer field;
    assert(!parser_admit_packets&&!parser_admit_messages&&parser_maintenance_grant)
        else $fatal(1,"Schema programming without fenced host authority");
    @(negedge app_clk);parser_cfg_unlock=1;
    `JOINT_WAIT(parser_cfg_quiescent,2000000)
    schema_read(0,32'h50534331);schema_read(12,0);
    key=current_epoch==0 ? 256'h6567617373656d : 256'h746e65746e6f63;
    field=current_epoch==0 ? 37 : 2712;
    schema_write(16,0,0);schema_write(20,7,1);schema_write(24,3,0);schema_write(28,32'(field),1);
    for(integer word_index=0;word_index<8;word_index++)schema_write(32+word_index*4,key[word_index*32+:32],word_index%2);
    schema_write(8,1,0);schema_read(12,1);
    // Disable the second default selector, so only the new schema remains.
    schema_write(16,1,1);schema_write(20,0,0);schema_write(24,0,1);schema_write(28,0,0);
    for(integer word_index=0;word_index<8;word_index++)schema_write(32+word_index*4,0,word_index%2);
    schema_write(8,1,1);schema_read(12,2);
    assert(parser_schema_row_epoch==2&&!parser_schema_mmio_busy)else $fatal(1,"Schema apply was not durable");
    @(negedge app_clk);parser_cfg_unlock=0;
    $display("JOINT_SCHEMA_PROGRAMMED epoch=%0d key=%h field=%0d transport_schema_epoch=%0d",current_epoch,key,field,10+current_epoch);
    $fflush(schema_file);
endtask
