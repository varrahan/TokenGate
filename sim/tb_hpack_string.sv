`timescale 1ns/1ps
module tb_hpack_string;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [7:0] s_data=0;logic s_valid=0,s_block_last=0;logic [15:0] s_user=0;wire s_ready;
    wire [7:0] m_data;wire m_keep,m_valid,m_last,rsp_valid,rsp_block_last,idle;wire [15:0] m_user,rsp_user;
    logic m_ready=0,rsp_ready=0;wire [7:0] rsp_status,rsp_detail;wire [31:0] rsp_encoded_bytes,rsp_decoded_bytes;
    hpack_string_decoder dut(.*);
    integer encoded[0:32767],expected[0:32767],n=0,wanted=0,expected_status=0,expected_detail=0,expected_user=0;
    integer received=0,markers=0,total=0,successes=0,failures=0,exact_bytes=0;
    bit out_stalled=0,result_stalled=0;logic [26:0] held_out;logic [96:0] held_result;
    wire [96:0] result_bundle={rsp_status,rsp_detail,rsp_block_last,rsp_encoded_bytes,rsp_decoded_bytes,rsp_user};
    always @(negedge clk)m_ready=$urandom_range(0,3)==0;
    always @(posedge clk)if(!rst)begin
        if(out_stalled&&(!m_valid||held_out!=={m_user,m_last,m_keep,m_data}))$fatal(1,"String output unstable");
        out_stalled=m_valid&&!m_ready;held_out={m_user,m_last,m_keep,m_data};
        if(result_stalled&&(!rsp_valid||held_result!==result_bundle))$fatal(1,"String result unstable");
        result_stalled=rsp_valid&&!rsp_ready;held_result=result_bundle;
        if(m_valid&&m_ready)begin
            if(m_user!=expected_user)$fatal(1,"String output context mismatch");
            if(m_keep)begin
                if(m_last)$fatal(1,"String data carried EOF");
                if(expected_status==0&&(received>=wanted||m_data!=expected[received]))$fatal(1,"String output mismatch case=%0d byte=%0d",total,received);
                received++;
            end else begin
                if(!m_last||expected_status!=0||received!=wanted)$fatal(1,"String committed an invalid/incomplete sequence");markers++;
            end
        end
    end
    initial begin:driver
        integer fd,rc,status,detail,last,mode,payload_bytes,b;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No string vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d %d %d",n,wanted,status,detail,last,mode,payload_bytes);
            if(rc==7)begin
                if(n>32768||wanted>32768)$fatal(1,"String fixture overflow");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%h",b);if(rc!=1)$fatal(1,"Bad encoded string");encoded[i]=b;end
                for(integer i=0;i<wanted;i++)begin rc=$fscanf(fd,"%h",b);if(rc!=1)$fatal(1,"Bad decoded string");expected[i]=b;end
                expected_status=status;expected_detail=detail;expected_user=(total*37)&65535;received=0;markers=0;
                for(integer i=0;i<n;i++)begin
                    repeat($urandom_range(0,3))@(negedge clk);s_data=8'(encoded[i]);s_valid=1;s_block_last=i+1==n&&last;
                    s_user=16'(expected_user^((mode==1&&i==1)?1:0));
                    do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
                end
                wait(rsp_valid);repeat($urandom_range(2,9))@(negedge clk);
                if(rsp_status!=status||rsp_detail!=detail||rsp_block_last!=last||rsp_encoded_bytes!=payload_bytes||rsp_user!=expected_user||
                   rsp_decoded_bytes!=(status==0?wanted:0)||markers!=(status==0?1:0))
                    $fatal(1,"String result mismatch case=%0d status=%0d/%0d detail=%0d/%0d payload=%0d/%0d decoded=%0d/%0d",total,rsp_status,status,rsp_detail,detail,rsp_encoded_bytes,payload_bytes,rsp_decoded_bytes,wanted);
                if(status==0)begin successes++;exact_bytes+=wanted;end else failures++;
                rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;wait(idle);total++;
                if(total%200==0)$display("PROGRESS: %0d complete HPACK strings",total);
            end else if(!$feof(fd))$fatal(1,"Bad string vector header");
        end
        $fclose(fd);if(total<1500||failures!=10)$fatal(1,"String coverage failure %0d/%0d",total,failures);
        $display("PASS: HPACK complete strings: %0d valid/%0d rejected/%0d exact bytes; raw/Huffman prefix lengths, empty strings, block boundaries, overflow/truncation/EOS/padding/context errors, tentative output/EOF ordering, stalls and recovery",successes,failures,exact_bytes);$finish;
    end
    initial begin #100000000;$fatal(1,"String decoder timeout");end
endmodule
