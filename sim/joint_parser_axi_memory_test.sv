`timescale 1ps/1ps
module joint_parser_axi_memory_test;
reg app_clk=0,rst=1;
always #2000 app_clk=~app_clk;
reg [22:0] p_axi_araddr=0,p_axi_awaddr=0;
reg [7:0] p_axi_arlen=0,p_axi_awlen=0;
reg [2:0] p_axi_arsize=3,p_axi_awsize=3;
reg [1:0] p_axi_arburst=1,p_axi_awburst=1;
reg p_axi_arvalid=0,p_axi_arready=0,p_axi_rvalid=0,p_axi_rready=0,p_axi_rlast=0;
reg p_axi_awvalid=0,p_axi_awready=0,p_axi_wvalid=0,p_axi_wready=0,p_axi_wlast=0,p_axi_bvalid=0,p_axi_bready=0;
reg [63:0] p_axi_rdata=0,p_axi_wdata=0;
reg [7:0] p_axi_wstrb=0;
reg [1:0] p_axi_rresp=0,p_axi_bresp=0;
`include "joint_parser_axi_memory.svh"
byte unsigned reference[0:8388607];
bit accept_reads=0,r_stalled=0,b_stalled=0;
reg [66:0] r_saved;
reg [1:0] b_saved;
integer r_holds=0,b_holds=0,checked=0;
always @(negedge app_clk)p_axi_rready=accept_reads&&parser_memory_cycle%8>=4;
always @(posedge app_clk)if(!rst)begin
    if(r_stalled)assert(p_axi_rvalid&&r_saved=={p_axi_rdata,p_axi_rlast,p_axi_rresp})else $fatal(1,"AXI BFM held R changed");
    if(b_stalled)assert(p_axi_bvalid&&b_saved==p_axi_bresp)else $fatal(1,"AXI BFM held B changed");
    r_stalled=p_axi_rvalid&&!p_axi_rready;r_saved={p_axi_rdata,p_axi_rlast,p_axi_rresp};
    b_stalled=p_axi_bvalid&&!p_axi_bready;b_saved=p_axi_bresp;
    if(r_stalled)r_holds++;
    if(b_stalled)b_holds++;
end
task automatic read_bytes(input integer address,input integer beats);
    @(negedge app_clk);p_axi_araddr=23'(address);p_axi_arlen=8'(beats-1);p_axi_arsize=3;p_axi_arburst=1;p_axi_arvalid=1;
    do @(posedge app_clk);while(!p_axi_arready);
    @(negedge app_clk);p_axi_arvalid=0;p_axi_araddr='1;p_axi_arlen=255;p_axi_arsize=7;p_axi_arburst=3;accept_reads=1;
    for(integer beat=0;beat<beats;beat++)begin
        do @(posedge app_clk);while(!(p_axi_rvalid&&p_axi_rready));
        assert(p_axi_rresp==0&&p_axi_rlast==(beat+1==beats))else $fatal(1,"AXI BFM read metadata");
        for(integer lane=0;lane<8;lane++)begin
            assert(p_axi_rdata[lane*8+:8]==reference[address+beat*8+lane])else $fatal(1,"AXI BFM read differs from independent byte oracle");checked++;
        end
    end
    @(negedge app_clk);accept_reads=0;
endtask
task automatic write_bytes(input integer address,input integer beats,input integer seed);
    reg [1:0] status;
    @(negedge app_clk);p_axi_awaddr=23'(address);p_axi_awlen=8'(beats-1);p_axi_awsize=3;p_axi_awburst=1;p_axi_awvalid=1;
    do @(posedge app_clk);while(!p_axi_awready);
    @(negedge app_clk);p_axi_awvalid=0;p_axi_awaddr='1;p_axi_awlen=255;p_axi_awsize=7;p_axi_awburst=3;
    for(integer beat=0;beat<beats;beat++)begin
        for(integer lane=0;lane<8;lane++)begin
            p_axi_wdata[lane*8+:8]=8'(seed+beat*29+lane*7);p_axi_wstrb[lane]=(seed+beat+lane)%3!=0;
        end
        p_axi_wlast=beat+1==beats;p_axi_wvalid=1;
        do @(posedge app_clk);while(!p_axi_wready);
        for(integer lane=0;lane<8;lane++)if(p_axi_wstrb[lane])reference[address+beat*8+lane]=p_axi_wdata[lane*8+:8];
        @(negedge app_clk);p_axi_wvalid=0;p_axi_wdata='1;p_axi_wstrb=0;
        repeat(2)@(negedge app_clk);
    end
    while(!p_axi_bvalid)@(negedge app_clk);
    status=p_axi_bresp;
    repeat(11)begin @(negedge app_clk);assert(p_axi_bvalid&&p_axi_bresp==status)else $fatal(1,"BFM B backpressure");end
    assert(status==0)else $fatal(1,"AXI BFM B status");
    p_axi_bready=1;@(posedge app_clk);@(negedge app_clk);p_axi_bready=0;
endtask
initial begin
    for(integer i=0;i<8388608;i++)begin reference[i]=8'((i>>3)^i^8'hc3);parser_bank[i]=reference[i];end
    #20000;@(negedge app_clk);rst=0;
    fork
        begin for(integer i=0;i<12;i++)read_bytes(1024+512*i,1+(i*7)%16);end
        begin for(integer i=0;i<12;i++)write_bytes(7000000+512*i,1+(i*5)%16,93+i);end
    join
    for(integer i=0;i<12;i++)read_bytes(7000000+512*i,1+(i*5)%16);
    assert(parser_reads==24&&parser_writes==12&&checked>1000&&r_holds>100&&b_holds>=132)
        else $fatal(1,"BFM coverage counts reads=%0d writes=%0d checked=%0d Rholds=%0d Bholds=%0d",parser_reads,parser_writes,checked,r_holds,b_holds);
    for(integer i=0;i<8388608;i++)assert(parser_bank[i]==reference[i])else $fatal(1,"BFM unexpected byte write");
    $display("JOINT_PARSER_AXI_MEMORY_TEST_PASS reads=%0d writes=%0d checked=%0d Rholds=%0d Bholds=%0d",parser_reads,parser_writes,checked,r_holds,b_holds);$finish;
end
initial begin #(64'd100000000);$fatal(1,"BFM test watchdog");end
endmodule
