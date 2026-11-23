`timescale 1ns/1ps
module tb_axis_conversion;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [511:0] sd=0;
    logic [63:0] sk=0;
    logic sv=0,sl=0;
    logic [15:0] su=0;
    wire sr;
    wire [511:0] fd;
    wire [63:0] fk;
    wire fv,fr,fl;
    wire [15:0] fu;
    wire [7:0] bd;
    wire bk,bv,br,bl;
    wire [15:0] bu;
    wire [127:0] md;
    wire [15:0] mk,mu;
    wire mv,ml;
    logic mr=0;
    byte unsigned expected[0:16383];
    integer lengths[0:99];
    integer written=0,read_idx=0,packet_idx=0,in_packet=0,stalls=0;
    logic held_valid=0;
    logic [160:0] held;
    rx_framing_fifo #(.DEPTH(16)) fifo_i (
        .clk(clk),.rst(rst),.s_axis_tdata(sd),.s_axis_tkeep(sk),.s_axis_tvalid(sv),
        .s_axis_tready(sr),.s_axis_tlast(sl),.s_axis_tuser(su),
        .m_axis_tdata(fd),.m_axis_tkeep(fk),.m_axis_tvalid(fv),.m_axis_tready(fr),
        .m_axis_tlast(fl),.m_axis_tuser(fu));
    axis_byte_unpacker unpack_i (.clk(clk),.rst(rst),.s_data(fd),.s_keep(fk),.s_valid(fv),
        .s_ready(fr),.s_last(fl),.s_user(fu),.m_data(bd),.m_keep(bk),.m_valid(bv),
        .m_ready(br),.m_last(bl),.m_user(bu));
    axis_byte_packer pack_i (.clk(clk),.rst(rst),.s_data(bd),.s_keep(bk),.s_valid(bv),
        .s_ready(br),.s_last(bl),.s_user(bu),.m_data(md),.m_keep(mk),.m_valid(mv),
        .m_ready(mr),.m_last(ml),.m_user(mu));
    task automatic send;
        @(negedge clk);sv=1;
        do @(posedge clk);while(!sr);
        @(negedge clk);sv=0;
    endtask
    always @(negedge clk) mr=$urandom_range(0,3)!=0;
    always @(posedge clk) if(!rst) begin
        if(sv&&!sr)stalls++;
        if(held_valid && (!mv || held!=={mu,ml,mk,md})) $fatal(1,"Converter changed output while stalled");
        held_valid=mv&&!mr;held={mu,ml,mk,md};
        if(mv&&mr) begin
            if(mu!=16'h1000+packet_idx) $fatal(1,"Converter context mismatch");
            if(mk!=0 && (({1'b0,mk}+1)&{1'b0,mk})!=0) $fatal(1,"Output keep is not compact");
            for(integer i=0;i<16;i++)if(mk[i])begin
                if(md[i*8+:8]!==expected[read_idx])$fatal(1,"Converter byte mismatch at %0d",read_idx);
                read_idx++;in_packet++;
            end
            if(ml)begin
                if(in_packet!=lengths[packet_idx])$fatal(1,"Packet length mismatch %0d got %0d expected %0d",packet_idx,in_packet,lengths[packet_idx]);
                packet_idx++;in_packet=0;
            end
        end
    end
    initial begin: driver
        integer remaining,value;
        repeat(5)@(negedge clk);rst=0;
        for(integer p=0;p<100;p++)begin
            case(p%10)
                0:lengths[p]=0;1:lengths[p]=1;2:lengths[p]=15;3:lengths[p]=16;
                4:lengths[p]=17;5:lengths[p]=32;6:lengths[p]=64;7:lengths[p]=65;
                default:lengths[p]=$urandom_range(0,180);
            endcase
            su=16'h1000+p;remaining=lengths[p];
            if(remaining==0)begin sk=0;sl=1;send();end
            else while(remaining>0)begin
                sd=0;sk=0;
                for(integer lane=0;lane<64;lane++)if(remaining>0&&$urandom_range(0,2)!=0)begin
                    value=$urandom_range(0,255);sd[lane*8+:8]=8'(value);sk[lane]=1;
                    expected[written]=8'(value);written++;remaining--;
                end
                sl=remaining==0;send();
            end
            // An empty non-final beat carries no bytes or packet event.
            if(p%7==0)begin sk=0;sl=0;send();end
        end
        while(packet_idx<100)@(negedge clk);
        repeat(5)@(negedge clk);
        if(read_idx!=written || stalls<10)$fatal(1,"Converter drain/coverage failure");
        $display("PASS: BRAM burst FIFO and 512-to-128 conversion: 100 packets, %0d bytes, %0d FIFO backpressure cycles",read_idx,stalls);
        $finish;
    end
    initial begin #1000000;$fatal(1,"Timeout");end
endmodule
