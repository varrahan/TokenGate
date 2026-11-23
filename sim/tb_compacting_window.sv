`timescale 1ns/1ps
module tb_compacting_window;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [511:0] s_data=0;logic [63:0] s_keep=0;
    logic s_valid=0,s_last=0;logic [15:0] s_user=0;wire s_ready;
    wire [63:0] m_data;wire [3:0] m_count;wire m_valid,m_last,idle;wire [15:0] m_user;
    logic m_ready=0;logic [3:0] m_consumed=0;
    logic [511:0] expected_data[0:4999];integer expected_count[0:4999];
    logic expected_last[0:4999];logic [15:0] expected_user[0:4999];
    integer rd=0,wr=0,accepted=0,completed=0,byte_count=0,ends=0,resets=0,discarded=0,source_holds=0,sink_holds=0;
    integer position=0;bit done=0,stalled=0;logic [84:0] held;
    axis_compacting_window dut(.*);
    always @(negedge clk)begin
        m_ready=!rst&&$urandom_range(0,4)!=0;
        m_consumed=m_count==0?0:$urandom_range(0,m_count);
    end
    always @(posedge clk)begin : scoreboard
        integer count,valid_count;reg [511:0] packed_bytes;
        if(rst)begin discarded=discarded+wr-rd;rd=wr;position=0;stalled=0;end
        else begin
            if(stalled)assert(m_valid&&held==={m_data,m_count,m_last,m_user})else $fatal(1,"Window changed under stall");
            stalled=m_valid&&(!m_ready||(m_count!=0&&m_consumed==0));held={m_data,m_count,m_last,m_user};
            if(s_valid&&!s_ready)source_holds++;
            if(m_valid&&!m_ready)sink_holds++;
            if(s_valid&&s_ready)begin
                packed_bytes=0;count=0;
                for(integer lane=0;lane<64;lane++)if(s_keep[lane])begin packed_bytes[count*8+:8]=s_data[lane*8+:8];count++;end
                accepted++;
                if(count!=0||s_last)begin
                    assert(wr<5000)else $fatal(1,"Scoreboard overflow");
                    expected_data[wr]=packed_bytes;expected_count[wr]=count;expected_last[wr]=s_last;expected_user[wr]=s_user;wr++;
                end
            end
            if(m_valid)begin
                assert(rd<wr)else $fatal(1,"Unexpected output after reset/drop");
                count=expected_count[rd]-position;valid_count=count>8?8:count;
                assert(m_count==valid_count&&m_user==expected_user[rd]&&m_last==(count==0&&expected_last[rd]))
                    else $fatal(1,"Window metadata/count mismatch %0d/%0d",rd,position);
                for(integer lane=0;lane<8;lane++)begin
                    if(lane<valid_count)assert(m_data[lane*8+:8]===expected_data[rd][(position+lane)*8+:8])else $fatal(1,"Byte order mismatch");
                    else assert(m_data[lane*8+:8]===0)else $fatal(1,"Invalid lanes not zero padded");
                end
                if(m_ready)begin
                    if(count==0)begin ends++;rd++;position=0;completed++;end
                    else if(m_consumed!=0)begin
                        byte_count+=m_consumed;position+=m_consumed;
                        if(position==expected_count[rd]&&!expected_last[rd])begin rd++;position=0;completed++;end
                    end
                end
            end
        end
    end
    task automatic send(input [63:0] mask,input bit last_value,input integer serial);
        @(negedge clk);s_keep=mask;s_last=last_value;s_user=serial;s_valid=1;
        for(integer lane=0;lane<64;lane++)s_data[lane*8+:8]=serial*13+lane*7;
        do @(posedge clk);while(!s_ready);
        @(negedge clk);s_valid=0;
    endtask
    initial begin
        repeat(40)@(negedge clk);rst=0;
        for(integer lane=0;lane<64;lane++)send(64'd1<<lane,1,lane);
        send(0,0,64);send(0,1,65);send(64'hffffffffffffffff,1,66);
        send(64'haaaaaaaaaaaaaaaa,1,67);send(64'h5555555555555555,1,68);
        for(integer serial=69;serial<4096;serial++)begin
            case(serial%11)
                0:send(0,serial%3==0,serial);
                1:send(64'hffffffffffffffff,serial%3==0,serial);
                default:send({$urandom,$urandom},serial%3==0,serial);
            endcase
        end
        done=1;wait(rd==wr&&idle);repeat(20)@(negedge clk);
        assert(accepted==4096&&resets==3&&discarded>0&&source_holds>100&&sink_holds>100)
            else $fatal(1,"Incomplete coverage %0d %0d %0d %0d %0d",accepted,resets,discarded,source_holds,sink_holds);
        $display("COMPACT_WINDOW_PASS source_words=%0d completed_words=%0d bytes=%0d packet_ends=%0d resets=%0d discarded_words=%0d source_holds=%0d sink_holds=%0d",accepted,completed,byte_count,ends,resets,discarded,source_holds,sink_holds);$finish;
    end
    initial begin
        wait(accepted>=250);@(negedge clk);rst=1;repeat(5)@(negedge clk);rst=0;resets++;
        wait(accepted>=1500);@(negedge clk);rst=1;repeat(9)@(negedge clk);rst=0;resets++;
        wait(accepted>=3000);@(negedge clk);rst=1;repeat(7)@(negedge clk);rst=0;resets++;
    end
    initial begin #(64'd10000000);$fatal(1,"Window watchdog");end
endmodule
