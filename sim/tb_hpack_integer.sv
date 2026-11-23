`timescale 1ns/1ps
module tb_hpack_integer;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [7:0] s_data=0;logic [3:0] s_prefix_bits=0;logic s_valid=0,s_block_last=0;logic [15:0] s_user=0;wire s_ready;
    wire rsp_valid,rsp_block_last,idle;logic rsp_ready=0;wire [31:0] rsp_value;wire [7:0] rsp_status;wire [15:0] rsp_user;
    integer bytes_in[0:15],expected_status=0,expected_last=0,expected_user=0,completed=0,values=0,errors=0;
    reg [31:0] expected_value=0;bit stalled=0;logic [56:0] held;
    hpack_integer_decoder dut(.*);
    always @(negedge clk)rsp_ready=$urandom_range(0,3)==0;
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!rsp_valid||held!=={rsp_user,rsp_block_last,rsp_status,rsp_value}))$fatal(1,"HPACK integer response unstable");
        stalled=rsp_valid&&!rsp_ready;held={rsp_user,rsp_block_last,rsp_status,rsp_value};
        if(rsp_valid&&rsp_ready)begin
            if(rsp_value!=expected_value||rsp_status!=expected_status||rsp_block_last!=expected_last||rsp_user!=expected_user)$fatal(1,"HPACK integer mismatch index=%0d got=%0d/%0d/%0d expected=%0d/%0d/%0d",completed,rsp_value,rsp_status,rsp_block_last,expected_value,expected_status,expected_last);
            if(rsp_status==0)values++;else errors++;completed++;
        end
    end
    initial begin:driver
        integer fd,rc,n,bits,status,last,context_number,mode,target;reg [31:0] value;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No integer vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d %d %d",n,bits,value,status,last,context_number,mode);
            if(rc==7)begin
                if(n>16||n<1)$fatal(1,"Bad integer fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",bytes_in[i]);if(rc!=1)$fatal(1,"Missing integer byte");end
                expected_value=value;expected_status=status;expected_last=last;expected_user=context_number;target=completed+1;
                for(integer i=0;i<n;i++)begin
                    @(negedge clk);s_data=8'(bytes_in[i]);s_prefix_bits=i==0?4'(bits):4'd15;s_block_last=i+1==n&&last!=0;s_user=context_number^((mode!=0&&i!=0)?1:0);s_valid=1;
                    do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
                end
                wait(completed==target);wait(idle);@(negedge clk);
            end else if(!$feof(fd))$fatal(1,"Bad integer vector header");
        end
        $fclose(fd);if(values!=8591||errors!=51)$fatal(1,"Integer coverage failure values=%0d errors=%0d",values,errors);
        $display("PASS: HPACK integers: %0d exact values/%0d bounded errors; every prefix width, first-byte values, 32-bit extremes, truncation/length/context rejection, metadata/prefix snapshots, stalls and recovery",values,errors);$finish;
    end
    initial begin #10000000;$fatal(1,"HPACK integer timeout");end
endmodule
