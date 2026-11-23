`timescale 1ns/1ps
module tb_hpack_static_table;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic req_valid=0,rsp_ready=0,read_valid=0,byte_ready=0;logic [6:0] req_index=0;logic [15:0] req_user=0;logic [9:0] read_offset=0;
    wire req_ready,rsp_valid,rsp_invalid,read_ready,byte_valid,byte_invalid;wire [9:0] rsp_name_offset,rsp_value_offset;
    wire [4:0] rsp_name_bytes,rsp_value_bytes;wire [15:0] rsp_user;wire [7:0] byte_data;
    hpack_static_table dut(.*);
    integer expected[0:63],count=0,bytes_checked=0,invalid=0;
    bit rsp_stalled=0,byte_stalled=0;logic [46:0] held_rsp;logic [8:0] held_byte;
    always @(posedge clk)if(!rst)begin
        if(rsp_stalled&&(!rsp_valid||held_rsp!=={rsp_invalid,rsp_name_offset,rsp_value_offset,rsp_name_bytes,rsp_value_bytes,rsp_user}))$fatal(1,"Static descriptor unstable");
        rsp_stalled=rsp_valid&&!rsp_ready;held_rsp={rsp_invalid,rsp_name_offset,rsp_value_offset,rsp_name_bytes,rsp_value_bytes,rsp_user};
        if(byte_stalled&&(!byte_valid||held_byte!=={byte_invalid,byte_data}))$fatal(1,"Static byte unstable");
        byte_stalled=byte_valid&&!byte_ready;held_byte={byte_invalid,byte_data};
    end
    task read_byte(input integer offset,input integer expected_value,input bit expected_invalid);
        begin
            repeat($urandom_range(0,3))@(negedge clk);read_valid=1;read_offset=10'(offset);
            do @(posedge clk);while(!read_ready);@(negedge clk);read_valid=0;read_offset='1;
            wait(byte_valid);repeat($urandom_range(0,5))@(negedge clk);
            if(byte_data!=expected_value||byte_invalid!=expected_invalid)$fatal(1,"Static byte mismatch offset=%0d",offset);
            byte_ready=1;@(posedge clk);@(negedge clk);byte_ready=0;bytes_checked++;
        end
    endtask
    initial begin
        integer fd,rc,index,n,v,bad,b,name_offset,value_offset;
        repeat(5)@(negedge clk);rst=0;
        for(integer pass=0;pass<3;pass++)begin
            fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No static vectors");
            while(!$feof(fd))begin
                rc=$fscanf(fd,"%d %d %d %d",index,n,v,bad);
                if(rc==4)begin
                    for(integer i=0;i<n+v;i++)begin rc=$fscanf(fd,"%h",b);if(rc!=1)$fatal(1,"Bad static bytes");expected[i]=b;end
                    @(negedge clk);req_valid=1;req_index=7'(index);req_user=16'(count*37);
                    do @(posedge clk);while(!req_ready);@(negedge clk);req_valid=0;req_index='1;req_user=0;
                    wait(rsp_valid);repeat($urandom_range(1,5))@(negedge clk);
                    if(rsp_name_bytes!=n||rsp_value_bytes!=v||rsp_invalid!=bad||rsp_user!=16'(count*37))$fatal(1,"Static descriptor mismatch index=%0d",index);
                    name_offset=rsp_name_offset;value_offset=rsp_value_offset;
                    if(bad&&(name_offset!=0||value_offset!=0))$fatal(1,"Invalid static descriptor leaked pointers");
                    // The independent byte port remains usable while the descriptor stalls.
                    for(integer i=0;i<n;i++)read_byte(name_offset+i,expected[i],0);
                    for(integer i=0;i<v;i++)read_byte(value_offset+i,expected[n+i],0);
                    rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;count++;if(bad)invalid++;
                end else if(!$feof(fd))$fatal(1,"Bad static fixture");
            end
            $fclose(fd);
        end
        read_byte(1023,0,1);
        if(count!=384||invalid!=201)$fatal(1,"Static coverage failure");
        $display("PASS: HPACK static table: %0d descriptors/%0d invalid indices/%0d bytes, every RFC entry, independent byte/descriptor stalls and request snapshots",count,invalid,bytes_checked);$finish;
    end
    initial begin #10000000;$fatal(1,"Static table timeout");end
endmodule
