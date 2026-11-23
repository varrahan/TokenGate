`timescale 1ns/1ps
module tb_serializer;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [1:0] mode=0;
    logic [28:0] field=1;
    logic [127:0] sd=0;
    logic [15:0] sk=0,su=0;
    logic sv=0,sl=0,abort_chunk=0;
    wire sr;
    wire [511:0] md;
    wire [63:0] mk;
    wire [15:0] mu;
    wire mv,ml,idle,error_valid;
    logic mr=0;
    wire [7:0] error_code;
    wire [15:0] error_user;
    integer source[0:4095],expected[0:4095];
    integer expected_len=0,expected_error=0,index=0,record_id=0,packets=0,errors=0;
    logic held_valid=0;
    logic [592:0] held;
    proto_json_serializer #(.MAX_TEXT_BYTES(256),.ABORT_SUPPORT(1)) dut (
        .clk(clk),.rst(rst),.cfg_format(mode),.cfg_protobuf_field(field),
        .s_axis_text_tdata(sd),.s_axis_text_tkeep(sk),.s_axis_text_tvalid(sv),
        .s_axis_text_tready(sr),.s_axis_text_tlast(sl),.s_axis_text_tuser(su),.s_axis_text_abort(abort_chunk),
        .m_axis_tx_tdata(md),.m_axis_tx_tkeep(mk),.m_axis_tx_tvalid(mv),
        .m_axis_tx_tready(mr),.m_axis_tx_tlast(ml),.m_axis_tx_tuser(mu),
        .error_valid(error_valid),.error_ready(1'b1),.error_code(error_code),
        .error_user(error_user),.idle(idle));
    always @(negedge clk)mr=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(held_valid && (!mv || held!=={mu,ml,mk,md}))$fatal(1,"Serializer output changed under stall");
        held_valid=mv&&!mr;held={mu,ml,mk,md};
        if(error_valid)begin
            if(error_code!=expected_error || error_user!=16'h2000+record_id)$fatal(1,"Serializer error/context mismatch");
            errors++;
        end
        if(mv&&mr)begin
            if(expected_error!=0 || mu!=16'h2000+record_id)$fatal(1,"Unexpected output/context");
            if(mk!=0 && (({1'b0,mk}+1)&{1'b0,mk})!=0)$fatal(1,"Noncontiguous output keep");
            for(integer lane=0;lane<64;lane++)if(mk[lane])begin
                if(index>=expected_len || md[lane*8+:8]!=expected[index])
                    $fatal(1,"Serializer mismatch record=%0d index=%0d got=%h expected=%h",record_id,index,md[lane*8+:8],expected[index]);
                index++;
            end
            if(ml)begin
                if(index!=expected_len)$fatal(1,"Serializer length mismatch");
                packets++;
            end
        end
    end
    task automatic send_beat;
        @(negedge clk);sv=1;
        do @(posedge clk);while(!sr);
        // Change host config immediately after admission. This packet must
        // continue to use the format/field captured on its first handshake.
        @(negedge clk);sv=0;mode=3;field=0;
    endtask
    initial begin: driver
        integer fd,status,nraw,nout,format_id,field_id,error_id,unused,packet_target,error_target;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("serializer_vectors.txt","r");if(!fd)$fatal(1,"Missing serializer vectors");
        status=$fscanf(fd,"%d %d %d %d %d",format_id,field_id,nraw,nout,error_id);
        while(status==5)begin
            for(integer i=0;i<nraw;i++)unused=$fscanf(fd,"%d",source[i]);
            for(integer i=0;i<nout;i++)unused=$fscanf(fd,"%d",expected[i]);
            @(negedge clk);mode=2'(format_id);field=29'(field_id);su=16'h2000+record_id;
            expected_len=nout;expected_error=error_id;index=0;
            packet_target=packets+(error_id==0);error_target=errors+(error_id!=0);
            if(nraw==0)begin sd=0;sk=0;sl=1;abort_chunk=error_id==4;send_beat();end
            else for(integer offset=0;offset<nraw;offset+=16)begin
                sd=0;sk=0;
                for(integer lane=0;lane<16;lane++)if(offset+lane<nraw)begin
                    sd[lane*8+:8]=8'(source[offset+lane]);sk[lane]=1;
                end
                sl=offset+16>=nraw;abort_chunk=error_id==4&&sl;
                if(error_id==3&&offset>=16)su=16'h4000+record_id;
                send_beat();
            end
            while(packets<packet_target || errors<error_target || !idle)@(negedge clk);
            if(error_id==0&&index!=nout)$fatal(1,"Packet not checked completely");
            record_id++;
            status=$fscanf(fd,"%d %d %d %d %d",format_id,field_id,nraw,nout,error_id);
        end
        $fclose(fd);
        if(packets!=21 || errors!=6)$fatal(1,"Serializer coverage failure packets=%0d errors=%0d",packets,errors);
        $display("PASS: 21 byte-exact JSON/SSE/Protobuf packets, empty/Unicode/control payloads, 29-bit tags, 6 error cases including context/abort, config snapshot and stalls");
        $finish;
    end
    initial begin #2000000;$fatal(1,"Timeout");end
endmodule
