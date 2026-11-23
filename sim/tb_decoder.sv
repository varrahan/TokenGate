`timescale 1ns/1ps
module tb_decoder;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic mode=0,cfg_unlock=0,cfg_valid=0,cfg_json=0,cfg_proto=0;
    logic [3:0] cfg_index=0;
    logic [255:0] cfg_key=0;
    logic [5:0] cfg_len=0;
    logic [28:0] cfg_field=0;
    wire cfg_ready,idle;
    logic [511:0] sd=0;
    logic [63:0] sk=0;
    logic sv=0,sl=0;
    logic [15:0] su=0;
    wire sr;
    wire [127:0] md;
    wire [15:0] mk,mu;
    wire mv,ml,error_valid;
    logic mr=0,error_ready=0;
    wire [7:0] error_code;
    wire [15:0] error_user;
    byte unsigned raw_bytes[0:262143],expected_bytes[0:262143];
    integer raw_start[0:511],raw_len[0:511],out_start[0:511],out_len[0:511];
    integer format_id[0:511],profile_id[0:511],expected_code[0:511];
    integer packet_count=0,response_idx=0,output_index=0,errors=0,successes=0,rx_stalls=0;
    logic held_valid=0,error_held_valid=0;
    logic [160:0] held;
    logic [23:0] error_held;
    proto_json_decoder #(.FIFO_DEPTH(16),.MAX_TEXT_BYTES(128),.MAX_FIELD_BYTES(256),.MAX_JSON_DEPTH(8),.MAX_PROTO_GROUP_DEPTH(4)) dut (
        .clk(clk),.rst(rst),.cfg_protobuf(mode),.cfg_unlock(cfg_unlock),
        .cfg_schema_valid(cfg_valid),.cfg_schema_ready(cfg_ready),.cfg_schema_index(cfg_index),
        .cfg_schema_key(cfg_key),.cfg_schema_key_length(cfg_len),.cfg_schema_json_enable(cfg_json),
        .cfg_schema_field(cfg_field),.cfg_schema_proto_enable(cfg_proto),
        .s_axis_rx_tdata(sd),.s_axis_rx_tkeep(sk),.s_axis_rx_tvalid(sv),.s_axis_rx_tready(sr),
        .s_axis_rx_tlast(sl),.s_axis_rx_tuser(su),.s_axis_rx_abort(1'b0),
        .m_axis_text_tdata(md),.m_axis_text_tkeep(mk),.m_axis_text_tvalid(mv),
        .m_axis_text_tready(mr),.m_axis_text_tlast(ml),.m_axis_text_tuser(mu),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),
        .error_user(error_user),.idle(idle));
    always @(negedge clk)begin mr=$urandom_range(0,3)!=0;error_ready=$urandom_range(0,3)!=0;end
    always @(posedge clk)if(!rst)begin
        if(sv&&!sr)rx_stalls++;
        if(held_valid && (!mv || held!=={mu,ml,mk,md}))$fatal(1,"Decoder text changed under stall");
        if(error_held_valid && (!error_valid || error_held!=={error_user,error_code}))$fatal(1,"Decoder error changed under stall");
        held_valid=mv&&!mr;held={mu,ml,mk,md};
        error_held_valid=error_valid&&!error_ready;error_held={error_user,error_code};
        if(mv)begin
            if(expected_code[response_idx]!=0)$fatal(1,"Tentative text leaked from invalid packet %0d",response_idx);
        end
        if(mv&&mr)begin
            if(mu!=16'h5000+response_idx)$fatal(1,"Decoder output context mismatch packet=%0d",response_idx);
            if(mk!=0 && (({1'b0,mk}+1)&{1'b0,mk})!=0)$fatal(1,"Uncompacted decoder keep");
            for(integer lane=0;lane<16;lane++)if(mk[lane])begin
                if(output_index>=out_len[response_idx] || md[lane*8+:8]!==expected_bytes[out_start[response_idx]+output_index])
                    $fatal(1,"Decoder text mismatch packet=%0d byte=%0d got=%h expected=%h",response_idx,output_index,md[lane*8+:8],expected_bytes[out_start[response_idx]+output_index]);
                output_index++;
            end
            if(ml)begin
                if(output_index!=out_len[response_idx])$fatal(1,"Decoder text length mismatch");
                output_index=0;response_idx++;successes++;
            end
        end
        if(error_valid&&error_ready)begin
            if(expected_code[response_idx]==0 || error_user!=16'h5000+response_idx || error_code==0)
                $fatal(1,"Unexpected decoder error packet=%0d code=%h",response_idx,error_code);
            if(expected_code[response_idx]!=255 && error_code!=expected_code[response_idx])
                $fatal(1,"Decoder error code mismatch packet=%0d actual=%h expected=%h",response_idx,error_code,expected_code[response_idx]);
            if(output_index!=0)$fatal(1,"Partial text committed before error");
            response_idx++;errors++;
        end
    end
    task automatic write_schema(input integer entry,input logic[255:0] key,input integer length,input bit enabled,input integer field_id,input bit proto);
        @(negedge clk);cfg_valid=1;cfg_index=4'(entry);cfg_key=key;cfg_len=6'(length);
        cfg_json=enabled;cfg_field=29'(field_id);cfg_proto=proto;
        do @(posedge clk);while(!cfg_ready);
        @(negedge clk);cfg_valid=0;
    endtask
    task automatic send_beat;
        @(negedge clk);sv=1;
        do @(posedge clk);while(!sr);
        // Only the packet's first beat defines format/context. Subsequent
        // config changes must not affect packets already queued in BRAM.
        @(negedge clk);sv=0;mode=!mode;su=16'hdead;
    endtask
    initial begin: driver
        integer fd,result,unused,raw_total,out_total,current_profile,offset,available,take,value;
        fd=$fopen("decoder_vectors.mem","r");if(!fd)$fatal(1,"Missing decoder vectors");
        unused=$fscanf(fd,"%d",packet_count);raw_total=0;out_total=0;
        for(integer p=0;p<packet_count;p++)begin
            result=$fscanf(fd,"%d %d %d %d %d",format_id[p],profile_id[p],raw_len[p],out_len[p],expected_code[p]);
            if(result!=5)$fatal(1,"Truncated decoder fixture");
            raw_start[p]=raw_total;out_start[p]=out_total;
            for(integer i=0;i<raw_len[p];i++)begin unused=$fscanf(fd,"%d",value);raw_bytes[raw_total]=8'(value);raw_total++;end
            for(integer i=0;i<out_len[p];i++)begin unused=$fscanf(fd,"%d",value);expected_bytes[out_total]=8'(value);out_total++;end
        end
        $fclose(fd);
        repeat(5)@(negedge clk);rst=0;
        @(negedge clk);cfg_unlock=1;
        write_schema(2,0,0,0,17,1);
        @(negedge clk);cfg_unlock=0;current_profile=0;
        for(integer p=0;p<packet_count;p++)begin
            if(profile_id[p]!=current_profile)begin
                while(response_idx<p || !idle)@(negedge clk);
                cfg_unlock=1;
                write_schema(0,256'h746e65746e6f63,7,1,1,1);
                write_schema(1,{32{8'h78}},32,1,0,0);
                @(negedge clk);cfg_unlock=0;current_profile=profile_id[p];
            end
            @(negedge clk);mode=format_id[p]!=0;su=16'h5000+p;offset=0;
            if(p==0)begin
                // A write may wait without permission while a packet uses
                // the old schema. It must not block key parsing/quiescence.
                cfg_valid=1;cfg_unlock=0;cfg_index=2;cfg_key=0;cfg_len=0;cfg_json=0;cfg_field=17;cfg_proto=1;
            end
            if(p%13==0)begin sk=0;sd=512'hbad;sl=0;send_beat();end
            if(raw_len[p]==0)begin sd=0;sk=0;sl=1;send_beat();end
            else while(offset<raw_len[p])begin
                sd=0;sk=0;take=0;
                for(integer lane=0;lane<64;lane++)begin
                    if(offset+take<raw_len[p] && (lane==63 || $urandom_range(0,2)!=0))begin
                        sd[lane*8+:8]=raw_bytes[raw_start[p]+offset+take];sk[lane]=1;take++;
                    end else sd[lane*8+:8]=8'hff;
                end
                offset+=take;sl=offset==raw_len[p];send_beat();
            end
            if(p==0)begin
                while(response_idx<1||!idle)begin @(negedge clk);if(cfg_ready)$fatal(1,"Ungrantable schema write was accepted");end
                cfg_unlock=1;do @(posedge clk);while(!cfg_ready);@(negedge clk);cfg_valid=0;cfg_unlock=0;
            end
        end
        while(response_idx<packet_count || !idle)@(negedge clk);
        if(successes<150 || errors<50 || rx_stalls<100)$fatal(1,"Insufficient decoder coverage");
        $display("PASS: transactional 512-to-128 decoder: %0d queued packets, %0d committed, %0d discarded, %0d RX stall cycles; schema reload and packet config snapshots",packet_count,successes,errors,rx_stalls);
        $finish;
    end
    initial begin #20000000;$fatal(1,"Timeout");end
endmodule
