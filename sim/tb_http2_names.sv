`timescale 1ns/1ps
module tb_http2_names;
    logic clk=0,rst=1,cancel=0;always #2 clk=~clk;
    logic start_valid=0,s_valid=0,s_keep=0,s_last=0,result_ready=0;
    logic [7:0] s_data=0;wire start_ready,s_ready,result_valid,idle;wire [3:0] result_code;
    http2_name_classifier dut(.*);
    integer raw[0:65535],cases=0,checked=0,stalls=0,cancellations=0;
    task begin_name;
        begin @(negedge clk);start_valid=1;do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;end
    endtask
    task octet(input integer value,input bit keep,input bit last);
        begin
            repeat($urandom_range(0,2))@(negedge clk);
            s_data=8'(value);s_keep=keep;s_last=last;s_valid=1;
            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
        end
    endtask
    task finish_name(input integer expected);
        begin
            wait(result_valid);if(result_code!=expected)$fatal(1,"Header-name ROM mismatch case=%0d got=%0d expected=%0d",checked,result_code,expected);
            repeat(7)begin @(negedge clk);stalls++;if(!result_valid||result_code!=expected||idle||start_ready)$fatal(1,"Name result/lease changed under stall");end
            result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;
        end
    endtask
    task fresh_method;
        begin
            begin_name();octet(58,1,0);octet(109,1,0);octet(101,1,0);octet(116,1,0);octet(104,1,0);octet(111,1,0);octet(100,1,1);finish_name(1);
        end
    endtask
    initial begin:driver
        integer fd,rc,length,expected,scanned;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No header-name vectors");rc=$fscanf(fd,"%d",cases);if(rc!=1)$fatal;
        for(integer index=0;index<cases;index++)begin
            rc=$fscanf(fd,"%d %d",length,expected);if(rc!=2||length>65536)$fatal;
            for(integer n=0;n<length;n++)begin rc=$fscanf(fd,"%d",scanned);raw[n]=scanned;if(rc!=1)$fatal;end
            begin_name();
            for(integer n=0;n<length;n++)octet(raw[n],1,index%2&&n==length-1);
            if(length==0||index%2==0)octet(0,0,1);
            finish_name(expected);checked++;
        end
        $fclose(fd);
        // Abandon each internal search stage, including an already held
        // result, then prove a fresh lookup cannot see stale ROM progress.
        for(integer phase=0;phase<8;phase++)begin
            if(phase==0)begin if(!idle)$fatal;end
            else begin
                begin_name();
                if(phase>=4)octet(58,1,phase==7);
            end
            while(dut.state!=phase)@(negedge clk);
            cancel=1;@(posedge clk);@(negedge clk);cancel=0;
            if(!idle||result_valid)$fatal(1,"Header-name cancellation left a result");cancellations++;fresh_method();
        end
        if(checked<500||stalls==0||cancellations!=8)$fatal(1,"Insufficient name ROM coverage");
        $display("PASS: exact ROM header names %0d cases/%0d result stall cycles/%0d state cancellations; prefixes, suffixes, case, forbidden/unknown/long names and fresh recovery",checked,stalls,cancellations);$finish;
    end
    initial begin #100000000;$fatal(1,"Header-name lookup timeout state=%0d case=%0d",dut.state,checked);end
endmodule
