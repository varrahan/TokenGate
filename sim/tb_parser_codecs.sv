`timescale 1ns/1ps
module tb_parser_codecs;
    logic clk=0,rst=1;
    always #2 clk=~clk;
    logic [7:0] js_data=0;
    logic js_keep=0,js_valid=0,js_last=0;
    wire js_ready;
    wire [7:0] jm_data;
    wire jm_keep,jm_valid,jm_last;
    logic jm_ready=0;
    wire [15:0] jm_user;
    logic [63:0] vs_data=0;
    logic [3:0] vs_count=0;
    logic vs_valid=0,vs_last=0;
    wire vs_ready;
    wire [3:0] consumed;
    wire [63:0] vm_value;
    wire vm_error,vm_valid;
    logic vm_ready=0;
    integer json_expected[0:4095],json_source[0:4095];
    integer json_length=0,json_index=0,json_packets=0;
    integer varint_results=0;
    logic [63:0] varint_expected=0;
    logic varint_error_expected=0;
    logic json_done=0,varint_done=0;
    logic json_stalled=0,varint_stalled=0;
    logic [25:0] json_held;
    logic [64:0] varint_held;
    json_escape_encoder json_i (.clk(clk),.rst(rst),.s_data(js_data),.s_keep(js_keep),
        .s_valid(js_valid),.s_ready(js_ready),.s_last(js_last),.s_user(16'h4321),
        .m_data(jm_data),.m_keep(jm_keep),.m_valid(jm_valid),.m_ready(jm_ready),
        .m_last(jm_last),.m_user(jm_user));
    protobuf_varint_decoder varint_i (.clk(clk),.rst(rst),.s_data(vs_data),.s_count(vs_count),
        .s_valid(vs_valid),.s_ready(vs_ready),.s_packet_last(vs_last),.consumed(consumed),
        .m_value(vm_value),.m_error(vm_error),.m_valid(vm_valid),.m_ready(vm_ready));
    always @(negedge clk)begin jm_ready=$urandom_range(0,3)!=0;vm_ready=$urandom_range(0,3)!=0;end
    always @(posedge clk)if(!rst)begin
        if(json_stalled && (!jm_valid || json_held!=={jm_user,jm_last,jm_keep,jm_data}))$fatal(1,"JSON changed while stalled");
        json_stalled=jm_valid&&!jm_ready;json_held={jm_user,jm_last,jm_keep,jm_data};
        if(varint_stalled && (!vm_valid || varint_held!=={vm_error,vm_value}))$fatal(1,"Varint changed while stalled");
        varint_stalled=vm_valid&&!vm_ready;varint_held={vm_error,vm_value};
        if(jm_valid&&jm_ready)begin
            if(jm_user!=16'h4321)$fatal(1,"JSON context mismatch");
            if(jm_keep)begin
                if(json_index>=json_length || jm_data!=json_expected[json_index])$fatal(1,"JSON reference mismatch idx=%0d got=%0d expected=%0d",json_index,jm_data,json_expected[json_index]);
                json_index++;
            end
            if(jm_last)begin
                if(json_index!=json_length)$fatal(1,"JSON length mismatch");
                json_packets++;
            end
        end
        if(vm_valid&&vm_ready)begin
            if(vm_error!=varint_error_expected || (!vm_error&&vm_value!==varint_expected))
                $fatal(1,"Varint mismatch got=%h err=%b expected=%h err=%b",vm_value,vm_error,varint_expected,varint_error_expected);
            varint_results++;
        end
    end
    initial begin repeat(5)@(negedge clk);rst=0;end
    task automatic send_json(input integer value,input bit keep,input bit last);
        @(negedge clk);js_data=8'(value);js_keep=keep;js_valid=1;js_last=last;
        do @(posedge clk);while(!js_ready);
        @(negedge clk);js_valid=0;
    endtask
    initial begin: json_driver
        integer fd,status,nraw,nescaped,unused,packet_target;
        wait(!rst);
        fd=$fopen("json_vectors.txt","r");if(!fd)$fatal(1,"Missing JSON reference vectors");
        status=$fscanf(fd,"%d %d",nraw,nescaped);
        while(status==2)begin
            for(integer i=0;i<nraw;i++)unused=$fscanf(fd,"%d",json_source[i]);
            for(integer i=0;i<nescaped;i++)unused=$fscanf(fd,"%d",json_expected[i]);
            json_length=nescaped;json_index=0;packet_target=json_packets+1;
            if(nraw==0)send_json(0,0,1);
            else for(integer i=0;i<nraw;i++)send_json(json_source[i],1,i+1==nraw);
            while(json_packets<packet_target)@(negedge clk);
            status=$fscanf(fd,"%d %d",nraw,nescaped);
        end
        $fclose(fd);if(json_packets!=5)$fatal(1,"Insufficient JSON coverage");json_done=1;
    end
    task automatic send_varint(input logic [63:0] value,input integer fragment);
        byte unsigned encoded[0:17];
        logic [63:0] remaining;
        integer n,offset,window_count,used,target;
        begin
            remaining=value;n=0;
            do begin
                encoded[n]=8'(remaining & 127);remaining=remaining>>7;
                if(remaining!=0)encoded[n]=encoded[n]|8'h80;
                n++;
            end while(remaining!=0);
            for(integer i=n;i<18;i++)encoded[i]=8'h55;
            varint_expected=value;varint_error_expected=0;offset=0;target=varint_results+1;
            while(offset<n)begin
                window_count=fragment;
                @(negedge clk);vs_data=0;
                for(integer i=0;i<window_count;i++)vs_data[i*8+:8]=encoded[offset+i];
                vs_count=4'(window_count);vs_last=offset+window_count>=n;vs_valid=1;
                do @(posedge clk);while(!vs_ready);
                used=consumed;
                if(used!=(n-offset<window_count ? n-offset : window_count))$fatal(1,"Varint consumed trailing bytes or made no progress");
                offset+=used;
                @(negedge clk);vs_valid=0;
            end
            while(varint_results<target)@(negedge clk);
        end
    endtask
    task automatic malformed(input logic [63:0] window,input integer count,input bit last);
        @(negedge clk);vs_data=window;vs_count=4'(count);vs_last=last;vs_valid=1;
        do @(posedge clk);while(!vs_ready);
        @(negedge clk);vs_valid=0;
    endtask
    initial begin: varint_driver
        integer target;
        wait(!rst);
        for(integer split=1;split<=8;split++)begin
            send_varint(0,split);send_varint(1,split);send_varint(127,split);
            send_varint(128,split);send_varint(300,split);send_varint(16384,split);
            send_varint(64'h8000000000000000,split);send_varint(64'hffffffffffffffff,split);
        end
        for(integer i=0;i<500;i++)send_varint({$urandom,$urandom},$urandom_range(1,8));
        varint_error_expected=1;target=varint_results+1;
        malformed(64'h80,1,1);while(varint_results<target)@(negedge clk);
        target=varint_results+1;
        malformed(64'hffffffffffffffff,8,0);malformed(64'h02ff,2,1);
        while(varint_results<target)@(negedge clk);
        target=varint_results+1;
        malformed(64'h8080808080808080,8,0);malformed(64'h8080,2,1);
        while(varint_results<target)@(negedge clk);
        varint_done=1;
    end
    initial begin
        wait(json_done&&varint_done);
        $display("PASS: Python JSON byte references and %0d varints: 1..8 lanes, 64-bit bounds, malformed/truncated values, stalls",varint_results);
        $finish;
    end
    initial begin #1000000;$fatal(1,"Timeout");end
endmodule
