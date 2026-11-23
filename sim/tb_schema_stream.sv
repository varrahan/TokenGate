`timescale 1ns/1ps
module schema_stream_scenario #(parameter ENTRIES=16,KEY_BYTES=32)(input wire clk,output reg done=0);
    localparam IW=ENTRIES>1?$clog2(ENTRIES):1,LW=$clog2(KEY_BYTES+2);
    logic rst=1,cfg_unlock=0,cfg_valid=0,cfg_json_enable=0,cfg_proto_enable=0;
    logic [IW-1:0] cfg_index=0;logic [KEY_BYTES*8-1:0] cfg_key=0;logic [LW-1:0] cfg_key_length=0;logic [28:0] cfg_field=0;
    wire cfg_ready,programming,idle;
    logic key_start_valid=0,key_valid=0,key_keep=0,key_last=0,key_result_ready=0;logic [7:0] key_data=0;
    wire key_start_ready,key_ready,key_result_valid,json_selected,proto_selected;logic [28:0] proto_field=0;
    schema_cam_lut #(.ENTRIES(ENTRIES),.KEY_BYTES(KEY_BYTES)) dut(.*);
    reg [KEY_BYTES*8-1:0] golden_keys[0:ENTRIES-1];integer golden_lengths[0:ENTRIES-1],golden_fields[0:ENTRIES-1];
    bit golden_json[0:ENTRIES-1],golden_proto[0:ENTRIES-1];
    integer queries=0,writes=0,stalls=0;
    task defaults;
        begin
            for(integer e=0;e<ENTRIES;e++)begin golden_keys[e]=0;golden_lengths[e]=0;golden_fields[e]=0;golden_json[e]=0;golden_proto[e]=0;end
            golden_keys[0]=48'h74706d6f7270;golden_lengths[0]=6&((1<<LW)-1);golden_fields[0]=1;golden_json[0]=1;golden_proto[0]=1;
            if(ENTRIES>1)begin golden_keys[1]=32'h74786574;golden_lengths[1]=4&((1<<LW)-1);golden_json[1]=1;end
        end
    endtask
    task check_proto(input integer field_id);
        bit expected_selection;
        begin
            expected_selection=0;for(integer e=0;e<ENTRIES;e++)if(golden_proto[e]&&golden_fields[e]==field_id)expected_selection=1;
            @(negedge clk);proto_field=29'(field_id);#1;if(proto_selected!==expected_selection)$fatal(1,"Schema protobuf selection changed field=%0d",field_id);
        end
    endtask
    task configure(input integer index,input reg [KEY_BYTES*8-1:0] value,input integer length,input bit json_enable,input integer field_id,input bit proto_enable);
        integer waited;
        begin
            @(negedge clk);cfg_unlock=1;cfg_valid=1;cfg_index=IW'(index);cfg_key=value;cfg_key_length=LW'(length);cfg_json_enable=json_enable;cfg_field=29'(field_id);cfg_proto_enable=proto_enable;
            do @(posedge clk);while(!cfg_ready);
            @(negedge clk);cfg_valid=0;cfg_unlock=0;cfg_index='1;cfg_key='1;cfg_key_length='1;cfg_json_enable=!json_enable;cfg_field='1;cfg_proto_enable=!proto_enable;
            if(!programming||key_start_ready||cfg_ready)$fatal(1,"Schema did not fence captured programming");
            waited=0;
            while(programming)begin @(negedge clk);waited++;if(waited>KEY_BYTES+2)$fatal(1,"Schema programming never committed");end
            golden_keys[index]=value;golden_lengths[index]=length&((1<<LW)-1);golden_fields[index]=field_id;
            golden_json[index]=json_enable&&length<=KEY_BYTES;golden_proto[index]=proto_enable&&field_id!=0;
            writes++;
        end
    endtask
    task query(input reg [KEY_BYTES*8-1:0] value,input integer length,input bit last_on_data,input bit deferred_write=0);
        reg [KEY_BYTES*8-1:0] padded_value;bit expected_selection;integer cursor;
        begin
            padded_value=0;for(integer n=0;n<KEY_BYTES;n++)if(n<length)padded_value[n*8+:8]=value[n*8+:8];
            expected_selection=0;
            for(integer e=0;e<ENTRIES;e++)if(golden_json[e]&&golden_lengths[e]==length&&length<=KEY_BYTES&&golden_keys[e]==padded_value)expected_selection=1;
            @(negedge clk);
            if(deferred_write)begin
                cfg_valid=1;cfg_unlock=0;cfg_index=0;cfg_key=0;cfg_key_length=0;cfg_json_enable=1;cfg_field=9003;cfg_proto_enable=1;
            end
            key_start_valid=1;do @(posedge clk);while(!key_start_ready);@(negedge clk);key_start_valid=0;
            for(cursor=0;cursor<length;cursor++)begin
                repeat($urandom_range(0,2))@(negedge clk);
                key_data=value[(cursor%KEY_BYTES)*8+:8];key_keep=1;key_last=last_on_data&&cursor==length-1;key_valid=1;
                do @(posedge clk);while(!key_ready);@(negedge clk);key_valid=0;
            end
            if(!last_on_data||length==0)begin
                key_keep=0;key_last=1;key_valid=1;do @(posedge clk);while(!key_ready);@(negedge clk);key_valid=0;
            end
            wait(key_result_valid);
            if(json_selected!==expected_selection)$fatal(1,"Schema streamed key mismatch entries=%0d bytes=%0d length=%0d got=%0d expected=%0d query=%0d writes=%0d value=%h padded=%h row0=%h enabled=%0d stored_length=%0d mask=%h",ENTRIES,KEY_BYTES,length,json_selected,expected_selection,queries,writes,value,padded_value,golden_keys[0],golden_json[0],golden_lengths[0],dut.match_mask);
            // A complete result retains the lookup lease and excludes writes.
            cfg_unlock=1;
            repeat(5)begin @(negedge clk);stalls++;if(!key_result_valid||json_selected!==expected_selection||cfg_ready||idle)$fatal(1,"Schema result/lease changed under stall");end
            key_result_ready=1;@(posedge clk);@(negedge clk);key_result_ready=0;
            if(deferred_write)begin
                do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;cfg_unlock=0;cfg_key='1;cfg_field='1;
                wait(!programming);golden_keys[0]=0;golden_lengths[0]=0;golden_json[0]=1;golden_fields[0]=9003;golden_proto[0]=1;writes++;
            end
            cfg_unlock=0;queries++;
        end
    endtask
    initial begin:driver
        reg [KEY_BYTES*8-1:0] value;
        repeat(5)@(negedge clk);rst=0;wait(idle);defaults();
        query(48'h74706d6f7270,6,0);query(32'h74786574,4,1);check_proto(1);check_proto(0);
        query(48'h74706d6f7270,6,0,1);query(0,0,1);check_proto(9003);
        for(integer e=0;e<ENTRIES;e++)begin
            value=0;for(integer n=0;n<KEY_BYTES;n++)value[n*8+:8]=8'(33+(e*11+n)%90);
            configure(e,value,KEY_BYTES,1,100+e,1);query(value,KEY_BYTES,e%2);query(value^1,KEY_BYTES,0);check_proto(100+e);
        end
        // Re-query older columns after every row has been populated. A
        // broken byte-enable that overwrites neighbors cannot pass merely
        // by returning the most recently programmed key correctly.
        for(integer e=0;e<ENTRIES;e++)query(golden_keys[e],golden_lengths[e],e%2);
        for(integer n=0;n<=KEY_BYTES;n++)begin
            value=0;for(integer c=0;c<n;c++)value[c*8+:8]=8'($urandom_range(0,255));
            configure(n%ENTRIES,value,n,1,1000+n,n%2);query(value,n,n%2);query(value,n+1,0);check_proto(1000+n);
        end
        for(integer e=0;e<ENTRIES;e++)query(golden_keys[e],golden_lengths[e],e%2);
        // Padding is part of the old whole-key equality contract. A key with
        // hidden nonzero padding must not become newly selectable.
        if(KEY_BYTES>1)begin value=0;value[7:0]="a";value[(KEY_BYTES-1)*8+:8]=8'hfe;configure(0,value,1,1,9001,1);query(8'h61,1,0);check_proto(9001);end
        value=0;configure(0,value,KEY_BYTES+1,1,9002,1);query(value,KEY_BYTES+1,1);check_proto(9002);
        configure(0,0,0,1,0,1);query(0,0,0);check_proto(0);
        // Reset reprograms prompt/text defaults and disables every other row.
        @(negedge clk);rst=1;repeat(3)@(negedge clk);rst=0;wait(idle);defaults();
        query(48'h74706d6f7270,6,1);query(32'h74786574,4,0);check_proto(1);check_proto(9002);
        $display("SCHEMA_SCENARIO_PASS entries=%0d bytes=%0d queries=%0d writes=%0d result_stalls=%0d",ENTRIES,KEY_BYTES,queries,writes,stalls);done=1;
    end
endmodule
module tb_schema_stream;
    logic clk=0;always #2 clk=~clk;
    wire full_done,odd_done,single_done;
    schema_stream_scenario full(clk,full_done);
    schema_stream_scenario #(.ENTRIES(3),.KEY_BYTES(7)) odd(clk,odd_done);
    schema_stream_scenario #(.ENTRIES(1),.KEY_BYTES(1)) single(clk,single_done);
    initial begin wait(full_done&&odd_done&&single_done);$display("PASS: BRAM streaming schemas, byte write isolation, exact length/padding, captured configuration, result leases, defaults and reset; 16x32, 3x7 and 1x1 dimensions");$finish;end
    initial begin #10000000;$fatal(1,"Streaming schema timeout");end
endmodule
