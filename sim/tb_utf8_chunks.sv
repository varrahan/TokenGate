`timescale 1ns/1ps
module tb_utf8_chunks;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0,start_eos=0,start_replace=0;wire start_ready;
    logic [15:0] start_user=0;logic [23:0] start_carry=0;logic [1:0] start_carry_count=0,start_format=0;
    logic [28:0] start_protobuf_field=0;
    logic [127:0] s_axis_text_tdata=0;logic [15:0] s_axis_text_tkeep=0,s_axis_text_tuser=0;
    logic s_axis_text_tvalid=0,s_axis_text_tlast=0,s_axis_text_abort=0;wire s_axis_text_tready;
    wire [511:0] m_axis_tx_tdata;wire [63:0] m_axis_tx_tkeep;wire [15:0] m_axis_tx_tuser;
    wire m_axis_tx_tvalid,m_axis_tx_tlast;logic m_axis_tx_tready=0;
    wire result_valid,idle;logic result_ready=0;wire [7:0] result_stage,result_status;
    wire [23:0] result_carry;wire [1:0] result_carry_count;wire [31:0] result_bytes;wire [15:0] result_user;
    utf8_serialized_chunk dut(.*);
    integer fields[0:15],source[0:32767],expected[0:131071];
    integer total=0,packets=0,errors=0,received=0,packet_target=0,stall_count=0,held_cycles=0;
    bit closed_waiting=0,stalled_once=0,held_valid=0;logic [592:0] held;
    logic [89:0] result_held;
    always @(negedge clk)begin
        if(!rst&&m_axis_tx_tvalid&&!stalled_once)begin stall_count=7;stalled_once=1;end
        m_axis_tx_tready=!rst&&stall_count==0&&$urandom_range(0,3)!=0;
        if(stall_count>0)stall_count--;
    end
    always @(posedge clk)if(!rst)begin
        if(closed_waiting&&s_axis_text_tready)$fatal(1,"Accepted another chunk before command/result ACK");
        if(held_valid&&(!m_axis_tx_tvalid||held!=={m_axis_tx_tuser,m_axis_tx_tlast,m_axis_tx_tkeep,m_axis_tx_tdata}))$fatal(1,"Chunk output changed under stall");
        held_valid=m_axis_tx_tvalid&&!m_axis_tx_tready;held={m_axis_tx_tuser,m_axis_tx_tlast,m_axis_tx_tkeep,m_axis_tx_tdata};
        if(m_axis_tx_tvalid)begin
            if(fields[11]!=0)$fatal(1,"Failed chunk emitted a response record=%0d",total);
            if(m_axis_tx_tuser!=fields[0])$fatal(1,"Chunk output context mismatch");
        end
        if(m_axis_tx_tvalid&&m_axis_tx_tready)begin
            if(m_axis_tx_tkeep!=0&&(({1'b0,m_axis_tx_tkeep}+1)&{1'b0,m_axis_tx_tkeep})!=0)$fatal(1,"Noncompact chunk keep");
            for(integer lane=0;lane<64;lane++)begin
                if(m_axis_tx_tkeep[lane])begin
                    if(received>=fields[12]||m_axis_tx_tdata[lane*8+:8]!==8'(expected[received]))$fatal(1,"Chunk byte mismatch case=%0d index=%0d",total,received);
                    received++;
                end else if(m_axis_tx_tdata[lane*8+:8]!==0)$fatal(1,"Chunk padding not zero");
            end
            if(m_axis_tx_tlast)begin if(received!=fields[12])$fatal(1,"Wrong chunk response length");packets++;end
        end
    end
    task send_beat;
        begin
            @(negedge clk);s_axis_text_tvalid=1;
            do @(posedge clk);while(!s_axis_text_tready);
            @(negedge clk);s_axis_text_tvalid=0;
        end
    endtask
    initial begin:driver
        integer fd,rc,scanned,offset,lane;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No incremental UTF-8 fixtures");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",scanned);
            if(rc==1)begin
                fields[0]=scanned;
                for(integer i=1;i<16;i++)begin rc=$fscanf(fd,"%d",scanned);if(rc!=1)$fatal;fields[i]=scanned;end
                for(integer i=0;i<fields[7];i++)begin rc=$fscanf(fd,"%d",scanned);if(rc!=1)$fatal;source[i]=scanned;end
                for(integer i=0;i<fields[12];i++)begin rc=$fscanf(fd,"%d",scanned);if(rc!=1)$fatal;expected[i]=scanned;end
                received=0;packet_target=packets+(fields[11]==0);stalled_once=0;
                @(negedge clk);start_user=16'(fields[0]);start_eos=fields[1];start_replace=fields[2];start_carry=24'(fields[3]);start_carry_count=2'(fields[4]);
                start_format=2'(fields[5]);start_protobuf_field=29'(fields[6]);start_valid=1;
                do @(posedge clk);while(!start_ready);
                @(negedge clk);start_valid=0;start_user='1;start_eos=~start_eos;start_replace=~start_replace;start_carry='1;start_carry_count='1;start_format=3;start_protobuf_field=0;
                offset=0;
                if(fields[7]==0)begin
                    s_axis_text_tdata=0;s_axis_text_tkeep=0;s_axis_text_tlast=1;s_axis_text_tuser=16'(fields[0]^(fields[9]!=0));s_axis_text_abort=fields[8];send_beat();
                end else while(offset<fields[7])begin
                    s_axis_text_tdata=0;s_axis_text_tkeep=0;
                    for(lane=0;lane<16;lane++)if(offset<fields[7]&&($urandom_range(0,3)!=0||lane==15))begin
                        s_axis_text_tdata[lane*8+:8]=8'(source[offset]);s_axis_text_tkeep[lane]=1;offset++;
                    end
                    s_axis_text_tlast=offset==fields[7];s_axis_text_tuser=16'(fields[0]^(fields[9]!=0));s_axis_text_abort=fields[8]&&s_axis_text_tlast;send_beat();
                end
                closed_waiting=1;s_axis_text_tdata='x;s_axis_text_tkeep='x;s_axis_text_tuser='x;s_axis_text_abort=0;
                wait(result_valid);@(negedge clk);
                if(!result_valid)$fatal(1,"Chunk completion VALID was transient");
                if(result_user!=fields[0]||result_stage!=fields[10]||result_status!=fields[11]||result_carry!=fields[13]||result_carry_count!=fields[14]||result_bytes!=fields[15])
                    $fatal(1,"Chunk result case=%0d stage=%0d/%0d status=%0d/%0d carry=%h/%h count=%0d/%0d bytes=%0d/%0d",total,result_stage,fields[10],result_status,fields[11],result_carry,fields[13],result_carry_count,fields[14],result_bytes,fields[15]);
                if(packets!=packet_target||received!=fields[12]||start_ready)$fatal(1,"Chunk completion before response case=%0d packets=%0d/%0d bytes=%0d/%0d ready=%b serializer=%0d",total,packets,packet_target,received,fields[12],start_ready,dut.serializer.state);
                result_held={result_user,result_bytes,result_carry_count,result_carry,result_status,result_stage};
                repeat(7)begin @(negedge clk);held_cycles++;if(!result_valid||result_held!=={result_user,result_bytes,result_carry_count,result_carry,result_status,result_stage}||start_ready)$fatal(1,"Chunk result/ownership changed before ACK");end
                if(result_status!=0)errors++;
                result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;closed_waiting=0;wait(idle);total++;
                if(total%200==0)$display("PROGRESS: %0d incremental UTF-8/serialized chunks",total);
            end else if(!$feof(fd))$fatal(1,"Malformed chunk fixture");
        end
        $fclose(fd);
        if(total<900||packets<400||errors<100||held_cycles!=total*7)$fatal(1,"Insufficient chunk coverage %0d/%0d/%0d",total,packets,errors);
        $display("PASS: incremental UTF-8 -> transactional JSON/SSE/Protobuf: %0d chunks/%0d responses/%0d failed chunks/%0d held-result cycles; strict/replacement, cross-chunk carry, malformed state, sparse lanes, rollback, upstream abort and production capacity",total,packets,errors,held_cycles);$finish;
    end
    initial begin #(64'd100000000);$fatal(1,"Chunk timeout case=%0d decoder=%0d serializer=%0d",total,dut.decoder.state,dut.serializer.state);end
endmodule
