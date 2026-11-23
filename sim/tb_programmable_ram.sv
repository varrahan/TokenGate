`timescale 1ns/1ps
module programmable_ram_case #(parameter integer LATENCY=2,WIDTH=64)(output bit done=0);
    logic clk=0,rst=1,unlock=1,cv=0,rv=0;always #2 clk=~clk;
    logic [4:0] ca=0,ra=0;logic [WIDTH-1:0] cd=0;wire cr,rr,rsp;wire [WIDTH-1:0] data_out;
    logic [WIDTH-1:0] golden[0:31],expected[0:4095];
    integer head=0,tail=0,checked=0,epoch=-1;
    programmable_table_ram #(.DATA_WIDTH(WIDTH),.ADDR_WIDTH(5),.READ_LATENCY(LATENCY),.MEMORY_PRIMITIVE("block")) dut(
        .clk(clk),.rst(rst),.cfg_unlock(unlock),.cfg_valid(cv),.cfg_ready(cr),.cfg_addr(ca),.cfg_data(cd),
        .rd_valid(rv),.rd_ready(rr),.rd_addr(ra),.rsp_valid(rsp),.rsp_data(data_out));
    always @(posedge clk)if(!rst)begin
        if(rsp)begin
`ifdef __ICARUS__
            if(epoch==-1&&!$isunknown(data_out))$fatal(1,"Portable RAM unexpectedly initialized storage");
`endif
            if(head>=tail||data_out!==expected[head])$fatal(1,"RAM latency/data mismatch latency=%0d width=%0d index=%0d",LATENCY,WIDTH,head);
            head++;checked++;
        end
        if(rv&&rr)begin expected[tail]=golden[ra];tail++;end
        if(cv&&cr)begin
            if(head!=tail)$fatal(1,"Configuration write accepted with reads pending");
            golden[ca]=cd;
        end
        if(unlock&&rr)$fatal(1,"Read admitted during quiesced configuration");
    end
    task automatic write_word(input integer address,input integer salt);
        @(negedge clk);ca=address;cd={32'(salt),32'(address),32'(address*37+salt)};cv=1;
        do @(posedge clk);while(!cr);
        @(negedge clk);cv=0;
    endtask
    initial begin
        repeat(4)@(negedge clk);rst=0;
        unlock=0;@(negedge clk);rv=1;ra=31;@(negedge clk);rv=0;
        wait(head==tail);@(negedge clk);
        for(epoch=0;epoch<2;epoch++)begin
            unlock=1;for(integer i=0;i<32;i++)write_word(i,epoch+11);
            @(negedge clk);unlock=0;
            for(integer i=0;i<1000;i++)begin
                @(negedge clk);rv=$urandom_range(0,3)!=0;ra=$urandom_range(0,31);
            end
            // Immediately request a write with the read pipeline still active.
            @(negedge clk);rv=0;unlock=1;write_word(0,epoch+91);
            wait(head==tail);@(negedge clk);
        end
        // Output reset does not initialize or erase programmable storage.
        rst=1;repeat(3)@(negedge clk);
        if(rsp||data_out!=0||cr||rr)$fatal(1,"RAM reset contract mismatch");
        rst=0;unlock=0;
        for(integer i=0;i<32;i++)begin @(negedge clk);rv=1;ra=i;end
        @(negedge clk);rv=0;wait(head==tail);@(negedge clk);
        if(checked<1400)$fatal(1,"RAM pipeline coverage missing");
        $display("PASS: portable RAM latency=%0d width=%0d, %0d checked reads; pipelining, writes, drain and reset retention",LATENCY,WIDTH,checked);done=1;
    end
endmodule
module tb_programmable_ram;
    wire one,two,three;
    programmable_ram_case #(.LATENCY(1),.WIDTH(8)) a(.done(one));
    programmable_ram_case #(.LATENCY(2),.WIDTH(64)) b(.done(two));
    programmable_ram_case #(.LATENCY(3),.WIDTH(72)) c(.done(three));
    initial begin wait(one&&two&&three);$display("PASS: portable programmable RAM configurations");$finish;end
    initial begin #1000000;$fatal(1,"Portable RAM timeout");end
endmodule
