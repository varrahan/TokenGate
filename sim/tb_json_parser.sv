`timescale 1ns/1ps
module tb_json_parser;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [7:0] sd=0;
    logic sk=0,sv=0,sl=0;
    logic [15:0] su=0;
    wire sr;
    wire [7:0] md,status;
    wire mk,mv,ml,idle;
    wire [15:0] mu;
    logic mr=0;
    wire [7:0] key_data;
    wire key_start_valid,key_start_ready,key_valid,key_ready,key_keep,key_last,key_result_valid,key_result_ready;
    wire key_selected,proto_selected;
    logic cfg_unlock=0,cfg_valid=0,cfg_json=0,cfg_proto=0;
    logic [3:0] cfg_index=0;
    logic [255:0] cfg_key=0;
    logic [5:0] cfg_len=0;
    logic [28:0] cfg_field=0;
    wire cfg_ready;
    integer source[0:16383],expected[0:16383],actual[0:16383];
    integer expected_len=0,expected_bad=0,index=0,records=0,packets=0,bad_count=0;
    logic stalled=0;
    logic [33:0] held;
    schema_cam_lut schema_i (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),
        .cfg_index(cfg_index),.cfg_key(cfg_key),.cfg_key_length(cfg_len),
        .cfg_json_enable(cfg_json),.cfg_field(cfg_field),.cfg_proto_enable(cfg_proto),
        .key_start_valid(key_start_valid),.key_start_ready(key_start_ready),.key_valid(key_valid),.key_ready(key_ready),
        .key_data(key_data),.key_keep(key_keep),.key_last(key_last),.key_result_valid(key_result_valid),.key_result_ready(key_result_ready),.json_selected(key_selected),
        .proto_field(29'd17),.proto_selected(proto_selected),.programming(),.idle());
    speculative_json_fsm #(.MAX_DEPTH(8)) dut (
        .clk(clk),.rst(rst),.s_data(sd),.s_keep(sk),.s_valid(sv),.s_ready(sr),.s_last(sl),.s_user(su),
        .key_start_valid(key_start_valid),.key_start_ready(key_start_ready),.key_valid(key_valid),.key_ready(key_ready),
        .key_data(key_data),.key_keep(key_keep),.key_last(key_last),.key_result_valid(key_result_valid),.key_result_ready(key_result_ready),.key_selected(key_selected),
        .m_data(md),.m_keep(mk),.m_valid(mv),.m_ready(mr),.m_last(ml),.m_user(mu),
        .packet_status(status),.idle(idle));
    always @(negedge clk)mr=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(stalled && (!mv || held!=={mu,status,ml,mk,md}))$fatal(1,"JSON output changed under stall");
        stalled=mv&&!mr;held={mu,status,ml,mk,md};
        if(mv&&mr)begin
            if(mu!=16'h4000+records)$fatal(1,"JSON context mismatch");
            if(mk)begin actual[index]=md;index++;end
            if(ml)begin
                if((status!=0)!=(expected_bad!=0))$fatal(1,"JSON validity mismatch record=%0d status=%0d expected_bad=%0d",records,status,expected_bad);
                if(status==0)begin
                    if(index!=expected_len)$fatal(1,"JSON extraction length mismatch record=%0d actual=%0d expected=%0d",records,index,expected_len);
                    for(integer i=0;i<index;i++)if(actual[i]!=expected[i])$fatal(1,"JSON extracted UTF-8 mismatch record=%0d byte=%0d actual=%h expected=%h",records,i,actual[i],expected[i]);
                end else bad_count++;
                packets++;
            end
        end
    end
    task automatic send(input integer value,input bit keep,input bit last);
        repeat($urandom_range(0,1))@(negedge clk);
        @(negedge clk);sd=8'(value);sk=keep;sl=last;sv=1;
        do @(posedge clk);while(!sr);
        @(negedge clk);sv=0;
    endtask
    task automatic write_schema(input integer entry,input logic[255:0] key,input integer length,input bit enabled,input integer field_id,input bit proto);
        @(negedge clk);cfg_valid=1;cfg_index=4'(entry);cfg_key=key;cfg_len=6'(length);
        cfg_json=enabled;cfg_field=29'(field_id);cfg_proto=proto;
        do @(posedge clk);while(!cfg_ready);
        @(negedge clk);cfg_valid=0;
    endtask
    initial begin: driver
        integer fd,result,profile,nraw,ntext,bad,unused,target,current_profile;
        repeat(5)@(negedge clk);rst=0;current_profile=0;
        // An attempted write without the quiesced grant must not alter defaults.
        @(negedge clk);cfg_valid=1;cfg_index=0;cfg_key=0;cfg_len=0;cfg_json=0;
        @(negedge clk);if(cfg_ready)$fatal(1,"Unquiesced schema write accepted");cfg_valid=0;
        fd=$fopen("json_parser_vectors.txt","r");if(!fd)$fatal(1,"Missing JSON vectors");
        result=$fscanf(fd,"%d %d %d %d",profile,nraw,ntext,bad);
        while(result==4)begin
            for(integer i=0;i<nraw;i++)unused=$fscanf(fd,"%d",source[i]);
            for(integer i=0;i<ntext;i++)unused=$fscanf(fd,"%d",expected[i]);
            if(profile!=current_profile)begin
                if(!idle)$fatal(1,"Schema reload attempted before drain");
                cfg_unlock=1;
                write_schema(0,256'h746e65746e6f63,7,1,17,1);
                write_schema(1,{32{8'h78}},32,1,0,0);
                @(negedge clk);cfg_unlock=0;
                if(!proto_selected)$fatal(1,"Programmable Protobuf CAM update failed");
                current_profile=profile;
            end
            expected_len=ntext;expected_bad=bad;index=0;target=packets+1;su=16'h4000+records;
            for(integer i=0;i<nraw;i++)send(source[i],1,0);
            send(0,0,1);
            while(packets<target)@(negedge clk);
            if(!idle)begin @(negedge clk);if(!idle)$fatal(1,"JSON parser did not return idle");end
            records++;
            result=$fscanf(fd,"%d %d %d %d",profile,nraw,ntext,bad);
        end
        $fclose(fd);
        if(records<200 || bad_count<50)$fatal(1,"Insufficient JSON coverage");
        $display("PASS: %0d JSON grammar/schema packets, %0d rejected; Unicode scalar normalization, UTF-8, nesting, numbers/literals, dynamic CAM and stalls",records,bad_count);
        $finish;
    end
    initial begin #10000000;$fatal(1,"Timeout");end
endmodule
