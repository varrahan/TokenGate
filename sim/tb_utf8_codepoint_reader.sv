`timescale 1ns/1ps
module tb_utf8_codepoint_reader;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [7:0] data=0;logic keep=0,valid=0,last=0;logic [15:0] user_id=0;
    wire ready,m_valid,m_keep,m_last,error_valid,idle;
    wire [20:0] cp;wire [31:0] bytes_out;wire [2:0] length;
    wire [15:0] m_user,error_user;wire [7:0] error_code;
    logic m_ready=0,error_ready=0;
    byte unsigned source[0:511];integer expected_cp[0:255],expected_length[0:255],expected_last[0:255];
    logic [31:0] expected_bytes[0:255];
    integer expected_count=0,index_out=0,expected_error=0,packets=0,errors=0,records=0,scalars=0,markers=0;
    logic [15:0] expected_user=0;bit expect_marker=0,stalled=0,error_stalled=0;
    logic [73:0] held;logic [23:0] error_held;
    utf8_codepoint_reader dut(
        .clk(clk),.rst(rst),.s_data(data),.s_keep(keep),.s_valid(valid),.s_ready(ready),.s_last(last),.s_user(user_id),
        .m_codepoint(cp),.m_bytes(bytes_out),.m_length(length),.m_keep(m_keep),.m_valid(m_valid),.m_ready(m_ready),.m_last(m_last),.m_user(m_user),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(idle));
    always @(negedge clk)m_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!m_valid||held!=={m_user,m_last,m_keep,length,bytes_out,cp}))$fatal(1,"Scalar output changed under stall");
        stalled=m_valid&&!m_ready;held={m_user,m_last,m_keep,length,bytes_out,cp};
        if(error_stalled&&(!error_valid||error_held!=={error_user,error_code}))$fatal(1,"UTF-8 error changed under stall");
        error_stalled=error_valid&&!error_ready;error_held={error_user,error_code};
        if(valid&&ready&&idle)$fatal(1,"Idle at new packet admission");
        if(m_valid&&m_ready)begin
            if(m_user!=expected_user)$fatal(1,"Scalar context mismatch");
            if(m_keep)begin
                if(index_out>=expected_count||cp!==expected_cp[index_out]||length!=expected_length[index_out]||bytes_out!==expected_bytes[index_out]||m_last!=expected_last[index_out])
                    $fatal(1,"Scalar mismatch packet=%0d index=%0d cp=%h length=%0d bytes=%h last=%0d",records,index_out,cp,length,bytes_out,m_last);
                index_out++;scalars++;
            end else begin
                if(!expect_marker||expected_error||cp!=0||bytes_out!=0||length!=0||!m_last)$fatal(1,"Unexpected EOF marker");
                markers++;
            end
            if(m_last)packets++;
        end
        if(error_valid&&error_ready)begin
            if(error_code!=expected_error||error_user!=expected_user)$fatal(1,"UTF-8 error mismatch %0d expected %0d",error_code,expected_error);
            errors++;
        end
    end
    task automatic send(input integer value,input bit byte_keep,input bit byte_last);
        repeat($urandom_range(0,2))@(negedge clk);
        @(negedge clk);data=value;keep=byte_keep;last=byte_last;valid=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);valid=0;
    endtask
    task automatic accept_error;
        wait(error_valid);
        repeat(6)begin @(negedge clk);if(!error_valid||error_code!=expected_error||error_user!=expected_user||ready||idle)$fatal(1,"Error not held until acknowledged");end
        error_ready=1;@(posedge clk);@(negedge clk);error_ready=0;
    endtask
    initial begin:driver
        integer fd,rc,n,count,status,marker,context_number,value,target_packets,target_errors;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing UTF-8 fixtures");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d",n,count,status,marker,context_number);
            if(rc==5)begin
                if(n>512||count>256)$fatal(1,"Fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",value);if(rc!=1)$fatal(1,"Missing input byte");source[i]=value;end
                for(integer i=0;i<count;i++)begin
                    rc=$fscanf(fd,"%d %d %h %d",expected_cp[i],expected_length[i],expected_bytes[i],expected_last[i]);if(rc!=4)$fatal(1,"Missing scalar");
                end
                expected_count=count;index_out=0;expected_error=status;expected_user=context_number;user_id=context_number;expect_marker=marker||n==0;
                target_packets=packets+(status==0);target_errors=errors+(status!=0);records++;
                for(integer i=0;i<n;i++)send(source[i],1,!marker&&i+1==n);
                if(marker||n==0)send(0,0,1);
                if(status)accept_error();else wait(packets==target_packets);
                @(negedge clk);
                if(index_out!=expected_count||errors!=target_errors||!idle)$fatal(1,"UTF-8 packet failed to retire cleanly");
            end else if(!$feof(fd))$fatal(1,"Invalid UTF-8 fixture");
        end
        $fclose(fd);
        // Context changes within a packet are rejected and drained.
        expected_user=16'heeee;user_id=expected_user;expected_error=3;expected_count=1;index_out=0;expect_marker=0;
        expected_cp[0]="A";expected_length[0]=1;expected_bytes[0]="A";expected_last[0]=0;
        send("A",1,0);user_id=16'heeef;send("B",1,0);send("Z",1,1);accept_error();
        if(!idle||index_out!=1||records<2000||errors<1000)$fatal(1,"Insufficient scalar-reader coverage");
        $display("PASS: UTF-8 scalar reader: %0d packets, %0d scalars, %0d EOF markers, %0d malformed/truncated/context errors; exact bytes, stalls, drain and recovery",records,scalars,markers,errors);
        $finish;
    end
    initial begin #20000000;$fatal(1,"UTF-8 scalar reader timeout");end
endmodule
