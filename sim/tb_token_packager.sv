`timescale 1ns/1ps
module tb_token_packager;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [31:0] token=0;logic keep=0,valid=0,last=0;logic [15:0] user_id=0;
    wire ready,out_valid,out_last,idle;wire [511:0] out_data;wire [63:0] out_keep;wire [15:0] out_user;
    logic out_ready=0;bit force_ready=0;integer expected[0:255];integer count=0,received=0,packets=0,beats=0,records=0,total_ids=0;
    bit stalled=0;logic [592:0] held;
    token_packager dut(
        .clk(clk),.rst(rst),.s_token(token),.s_keep(keep),.s_valid(valid),.s_ready(ready),.s_sequence_last(last),.s_user(user_id),
        .m_axis_tokens_tdata(out_data),.m_axis_tokens_tkeep(out_keep),.m_axis_tokens_tvalid(out_valid),.m_axis_tokens_tready(out_ready),
        .m_axis_tokens_tlast(out_last),.m_axis_tokens_tuser(out_user),.idle(idle));
    always @(negedge clk)out_ready=force_ready||$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!out_valid||held!=={out_user,out_last,out_keep,out_data}))$fatal(1,"C2H beat changed under backpressure");
        stalled=out_valid&&!out_ready;held={out_user,out_last,out_keep,out_data};
        if(valid&&ready&&idle)$fatal(1,"Packager idle during new admission");
        if(out_valid&&out_ready)begin
            if(out_user!=user_id)$fatal(1,"C2H context mismatch");
            for(integer lane=0;lane<16;lane++)begin
                if(out_keep[lane*4+:4]!=0&&out_keep[lane*4+:4]!=15)$fatal(1,"Partial token byte mask");
                if(out_keep[lane*4+:4]==15)begin
                    if(received>=count||out_data[lane*32+:32]!==32'(expected[received]))$fatal(1,"C2H token mismatch");
                    received++;total_ids++;
                end else begin
                    if((out_keep>>(lane*4))!=0)$fatal(1,"Noncontiguous token mask");
                    if(out_data[lane*32+:32]!==32'd0)$fatal(1,"Unused token lane retained old data");
                end
            end
            beats++;
            if(out_last)begin if(received!=count)$fatal(1,"C2H length mismatch");packets++;end
            else if(out_keep!=64'hffffffffffffffff)$fatal(1,"Nonfinal C2H beat is not full");
        end
    end
    task automatic send(input integer value,input bit byte_keep,input bit eos);
        repeat($urandom_range(0,2))@(negedge clk);
        @(negedge clk);token=value;keep=byte_keep;last=eos;valid=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);valid=0;
    endtask
    initial begin
        integer n,target;bit explicit_end;
        repeat(5)@(negedge clk);rst=0;
        for(integer sequence_number=0;sequence_number<500;sequence_number++)begin
            case(sequence_number)
                0:n=0;1:n=1;2:n=15;3:n=16;4:n=17;5:n=31;6:n=32;7:n=33;
                default:n=$urandom_range(0,255);
            endcase
            count=n;received=0;user_id=sequence_number+1;target=packets+1;explicit_end=$urandom_range(0,1);records++;
            for(integer i=0;i<n;i++)expected[i]=$urandom;
            for(integer i=0;i<n;i++)begin
                if($urandom_range(0,5)==0)send(0,0,0);
                send(expected[i],1,!explicit_end&&i+1==n);
            end
            if(explicit_end||n==0)send(0,0,1);
            wait(packets==target);@(negedge clk);if(!idle)$fatal(1,"Packager did not drain final beat");
        end
        // Continuous source/sink: bank capture and pending emission must not
        // insert a READY bubble between full groups.
        force_ready=1;repeat(2)@(negedge clk);count=256;received=0;user_id=16'h5010;target=packets+1;records++;
        for(integer i=0;i<256;i++)expected[i]=$urandom;
        for(integer i=0;i<256;i++)begin
            @(negedge clk);token=expected[i];keep=1;last=i==255;valid=1;
            @(posedge clk);if(!ready)$fatal(1,"Packager lost one-token-per-clock acceptance");
        end
        @(negedge clk);valid=0;wait(packets==target);@(negedge clk);if(!idle)$fatal(1,"Continuous packet did not retire");
        // Reset before a completed group can leave its pending/output slot.
        count=16;received=0;user_id=16'hdead;
        for(integer i=0;i<16;i++)begin expected[i]=i;send(i,1,0);end
        rst=1;repeat(2)@(negedge clk);rst=0;
        count=1;received=0;user_id=16'h5011;expected[0]=32'h12345678;target=packets+1;records++;
        send(expected[0],1,1);wait(packets==target);@(negedge clk);if(!idle)$fatal(1,"Reset recovery did not retire");
        if(total_ids<50000||beats<3000)$fatal(1,"Insufficient packager coverage");
        $display("PASS: token packager: %0d sequences, %0d complete token IDs/%0d C2H beats; empty/exact/partial groups, EOF, metadata and stalls",records,total_ids,beats);
        $finish;
    end
    initial begin #10000000;$fatal(1,"Token packager timeout");end
endmodule
