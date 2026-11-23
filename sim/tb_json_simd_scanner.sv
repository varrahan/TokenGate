`timescale 1ns/1ps
module tb_json_simd_scanner;
    logic [63:0] data=0;logic [3:0] count=0;
    wire [7:0] quote,backslash,colon,comma,object_open,object_close,array_open,array_close;
    wire [7:0] whitespace,control,non_ascii,structural,plain_ascii;wire [3:0] leading_whitespace,leading_plain_ascii;
    logic [12:0] classes[0:255];integer windows=0;
    json_simd_scanner dut(.*);
    task automatic check;
        integer prefix,plain;bit stopped,plain_stopped;reg [12:0] expected,actual;
        #1;prefix=0;plain=0;stopped=0;plain_stopped=0;
        for(integer lane=0;lane<8;lane++)begin
            expected=lane<count?classes[data[lane*8+:8]]:0;
            actual={plain_ascii[lane],structural[lane],non_ascii[lane],control[lane],whitespace[lane],array_close[lane],array_open[lane],
                object_close[lane],object_open[lane],comma[lane],colon[lane],backslash[lane],quote[lane]};
            assert(actual===expected)else $fatal(1,"Parallel class mismatch lane=%0d byte=%0d count=%0d",lane,data[lane*8+:8],count);
            if(!stopped&&lane<count&&expected[8])prefix++;else stopped=1;
            if(!plain_stopped&&lane<count&&expected[12])plain++;else plain_stopped=1;
        end
        assert(leading_whitespace==prefix)else $fatal(1,"Whitespace prefix mismatch");windows++;
        assert(leading_plain_ascii==plain)else $fatal(1,"Plain ASCII prefix mismatch");
    endtask
    initial begin
        $readmemh("json-classes.hex",classes);
        for(integer length=0;length<=8;length++)begin data=64'h2020202020202020;count=length;check();end
        for(integer lane=0;lane<8;lane++)for(integer value=0;value<256;value++)for(integer length=0;length<=8;length++)begin
            data=64'h2020202020202020;data[lane*8+:8]=value;count=length;check();
        end
        assert(windows==18441)else $fatal(1,"Incomplete scanner coverage");
        $display("JSON_SCANNER_PASS windows=%0d lanes=8 byte_values=256 counts=9",windows);$finish;
    end
endmodule
