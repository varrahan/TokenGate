`timescale 1ns/1ps
module tb_protobuf_wire;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [63:0] sd=0;
    logic [3:0] sc=0;
    logic sv=0,sl=0;
    logic [15:0] su=0;
    wire sr;
    wire [3:0] consumed;
    wire [28:0] field_number;
    wire [7:0] md,status;
    wire mk,mv,ml,idle;
    wire [15:0] mu;
    logic mr=0;
    integer source[0:4095],expected[0:4095],actual[0:4095];
    integer expected_len=0,expected_status=0,index=0,records=0,packets=0;
    logic held_valid=0;
    logic [33:0] held;
    protobuf_wire_fsm #(.MAX_FIELD_BYTES(256),.MAX_GROUP_DEPTH(4)) dut (
        .clk(clk),.rst(rst),.s_data(sd),.s_count(sc),.s_valid(sv),.s_ready(sr),
        .s_last(sl),.s_user(su),.consumed(consumed),.field_number(field_number),
        .field_selected(field_number==1 || field_number==17),
        .m_data(md),.m_keep(mk),.m_valid(mv),.m_ready(mr),.m_last(ml),.m_user(mu),
        .packet_status(status),.idle(idle));
    always @(negedge clk)mr=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(held_valid && (!mv || held!=={mu,status,ml,mk,md}))$fatal(1,"Protobuf output changed under stall");
        held_valid=mv&&!mr;held={mu,status,ml,mk,md};
        if(mv&&mr)begin
            if(mu!=16'h3000+records)$fatal(1,"Protobuf context mismatch");
            if(mk)begin actual[index]=md;index++;end
            if(ml)begin
                if(status!=expected_status)$fatal(1,"Protobuf status mismatch record=%0d got=%0d expected=%0d",records,status,expected_status);
                if(status==0)begin
                    if(index!=expected_len)$fatal(1,"Protobuf text length mismatch");
                    for(integer i=0;i<index;i++)if(actual[i]!=expected[i])$fatal(1,"Protobuf extracted byte mismatch");
                end
                packets++;
            end
        end
    end
    initial begin: driver
        integer fd,result,nraw,ntext,error,unused,offset,n,used,target;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("protobuf_vectors.txt","r");if(!fd)$fatal(1,"Missing Protobuf vectors");
        result=$fscanf(fd,"%d %d %d",nraw,ntext,error);
        while(result==3)begin
            for(integer i=0;i<nraw;i++)unused=$fscanf(fd,"%d",source[i]);
            for(integer i=0;i<ntext;i++)unused=$fscanf(fd,"%d",expected[i]);
            expected_len=ntext;expected_status=error;index=0;offset=0;target=packets+1;
            su=16'h3000+records;
            while(offset<nraw)begin
                n=$urandom_range(1,8);if(n>nraw-offset)n=nraw-offset;
                @(negedge clk);sd=0;sc=4'(n);sv=1;sl=0;
                for(integer i=0;i<n;i++)sd[i*8+:8]=8'(source[offset+i]);
                do @(posedge clk);while(!sr);
                used=consumed;if(used<1 || used>n)$fatal(1,"Invalid window consumption");
                offset+=used;
                @(negedge clk);sv=0;
            end
            @(negedge clk);sd=0;sc=0;sv=1;sl=1;
            do @(posedge clk);while(!sr);
            @(negedge clk);sv=0;
            while(packets<target)@(negedge clk);
            if(!idle)begin @(negedge clk);if(!idle)$fatal(1,"Protobuf FSM did not reset after packet");end
            records++;
            result=$fscanf(fd,"%d %d %d",nraw,ntext,error);
        end
        $fclose(fd);if(records!=35)$fatal(1,"Insufficient wire-format coverage");
        $display("PASS: 35 Protobuf packets: wire types, groups, selected UTF-8 fields, wide varints, bounds, malformed/truncated messages, stalls");
        $finish;
    end
    initial begin #2000000;$fatal(1,"Timeout");end
endmodule
