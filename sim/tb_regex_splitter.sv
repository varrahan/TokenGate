`timescale 1ns/1ps
module tb_regex_splitter;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic valid=0;wire ready;logic [31:0] count=0;logic [1:0] profile=0;logic [15:0] user_id=0;
    wire rv,rrr,m_valid,m_last,error_valid,idle;logic rr=0,rrv=0,m_ready=0,error_ready=0;
    wire [31:0] ri,start_out,count_out;logic [63:0] rd=0;logic [7:0] rs=0;
    wire [15:0] m_user,error_user;wire [7:0] error_code,error_status;
    logic [63:0] memory[0:262143];
    integer expected_start[0:255],expected_count[0:255],expected_last[0:255];
    integer total_count=0,span_count=0,span_index=0,expected_user=0,packets=0,sequences=0,spans=0,reads=0;
    integer fault_index=-1,delay_cycles=0;
    bit model_busy=0,accepted_response=0,packet_active=0,allow_error=0;
    logic [63:0] pending_data;logic [7:0] pending_status;
    bit rd_stalled=0,out_stalled=0,error_stalled=0;
    logic [31:0] held_index;logic [80:0] held_span;logic [31:0] held_error;
    regex_splitter_fsm dut(
        .clk(clk),.rst(rst),.s_valid(valid),.s_ready(ready),.s_count(count),.s_profile(profile),.s_user(user_id),
        .rd_valid(rv),.rd_ready(rr),.rd_index(ri),.rd_rsp_valid(rrv),.rd_rsp_ready(rrr),.rd_rsp_record(rd),.rd_rsp_status(rs),
        .m_valid(m_valid),.m_ready(m_ready),.m_start(start_out),.m_count(count_out),.m_sequence_last(m_last),.m_user(m_user),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_status(error_status),.error_user(error_user),.idle(idle));
    always @(negedge clk)begin
        m_ready=$urandom_range(0,3)!=0;
        rr=!rst&&!model_busy&&$urandom_range(0,3)!=0;
        if(accepted_response)rrv=0;
        if(model_busy&&!rrv)begin
            if(delay_cycles>0)delay_cycles--;
            else begin rrv=1;rd=pending_data;rs=pending_status;end
        end
    end
    always @(posedge clk)begin
        accepted_response=rrv&&rrr;
        if(rst)model_busy=0;
        else begin
            if(rv&&rr)begin
                if(ri>=total_count||model_busy)$fatal(1,"Out-of-range/overlapping scalar read %0d count=%0d",ri,total_count);
                model_busy=1;delay_cycles=$urandom_range(0,4);pending_data=memory[ri];pending_status=ri==fault_index?8'h7b:0;reads++;
            end
            if(accepted_response)model_busy=0;
            if(rd_stalled&&(!rv||ri!==held_index))$fatal(1,"Scalar address changed under stall");
            rd_stalled=rv&&!rr;held_index=ri;
            if(out_stalled&&(!m_valid||held_span!=={m_user,m_last,start_out,count_out}))$fatal(1,"Span changed under stall");
            out_stalled=m_valid&&!m_ready;held_span={m_user,m_last,start_out,count_out};
            if(error_stalled&&(!error_valid||held_error!=={error_user,error_code,error_status}))$fatal(1,"Error changed under stall");
            error_stalled=error_valid&&!error_ready;held_error={error_user,error_code,error_status};
            if(error_valid&&!allow_error)$fatal(1,"Unexpected splitter error");
            if(valid&&ready&&idle)$fatal(1,"Early idle during descriptor admission");
            if(m_valid&&m_ready)begin
                if(!packet_active||span_index>=span_count||m_user!=expected_user||start_out!=expected_start[span_index]||count_out!=expected_count[span_index]||m_last!=expected_last[span_index])
                    $fatal(1,"Splitter mismatch seq=%0d span=%0d got=(%0d,%0d,%0d) expected=(%0d,%0d,%0d)",sequences,span_index,start_out,count_out,m_last,expected_start[span_index],expected_count[span_index],expected_last[span_index]);
                if(count_out==0&&total_count!=0)$fatal(1,"Empty nonempty-sequence span");
                span_index++;spans++;
                if(m_last)begin packets++;packet_active=0;end
            end
        end
    end
    task automatic descriptor(input integer n,input integer p,input integer context_number);
        @(negedge clk);count=n;profile=p;user_id=context_number;valid=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);valid=0;count=32'hffffffff;profile=3;user_id=16'hdead;
    endtask
    initial begin:driver
        integer fd,rc,n,p,context_number,number_of_spans,target,before_reads;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing splitter vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d",n,p,context_number,number_of_spans);
            if(rc==4)begin
                if(n>262144||number_of_spans>256)$fatal(1,"Splitter fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%h",memory[i]);if(rc!=1)$fatal(1,"Missing scalar record");end
                for(integer i=0;i<number_of_spans;i++)begin rc=$fscanf(fd,"%d %d %d",expected_start[i],expected_count[i],expected_last[i]);if(rc!=3)$fatal(1,"Missing expected span");end
                total_count=n;span_count=number_of_spans;span_index=0;expected_user=context_number;packet_active=1;sequences++;target=packets+1;
                descriptor(n,p,context_number);wait(packets==target);@(negedge clk);
                if(span_index!=span_count||!idle||model_busy)$fatal(1,"Splitter did not retire cleanly");
            end else if(!$feof(fd))$fatal(1,"Invalid splitter fixture");
        end
        $fclose(fd);allow_error=1;expected_user=16'hcafe;total_count=20;
        for(integer fault=0;fault<2;fault++)begin
            before_reads=reads;
            for(integer i=0;i<20;i++)memory[i]=(64'd1<<55)|(64'd1<<53)|(64'd97<<32)|64'd97;
            fault_index=fault==0?-1:5;
            descriptor(20,fault==0?3:0,16'hcafe);wait(error_valid);
            repeat(8)begin @(negedge clk);if(!error_valid||error_user!=16'hcafe||error_code!=(fault==0?1:2)||error_status!=(fault==0?0:8'h7b)||idle||ready)$fatal(1,"Splitter error status/context retention");end
            if(fault==0&&reads!=before_reads)$fatal(1,"Unsupported profile issued scalar reads");
            error_ready=1;@(posedge clk);@(negedge clk);error_ready=0;if(!idle)$fatal(1,"Splitter error recovery failed");
        end
        if(sequences<30000||spans<100000||!idle)$fatal(1,"Insufficient splitter coverage");
        $display("PASS: RTL regex splitter: %0d three-profile sequences, %0d exact spans, %0d variable-latency reads; long runs, case folding, Unicode, context snapshots, faults and stalls",sequences,spans,reads);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"Splitter timeout");end
endmodule
