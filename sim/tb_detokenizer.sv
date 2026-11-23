`timescale 1ns/1ps
module tb_detokenizer;
    logic clk=0,rst=1,cfg_unlock=1,cfg_valid=0,cfg_pool=0,strip_special=1;
    always #2 clk=~clk;
    logic [31:0] cfg_addr=0;
    logic [63:0] cfg_data=0;
    wire cfg_ready,cfg_error;
    logic [31:0] token=0;
    logic token_valid=0,token_last=0;
    logic [15:0] token_user=16'hcafe;
    wire token_ready;
    wire [127:0] text_data;
    wire [15:0] text_keep,text_user;
    wire text_valid,text_last;
    logic text_ready=0;
    wire error_valid,idle;
    wire [7:0] error_code;
    wire [15:0] error_user;
    logic [7:0] expected [0:511];
    integer expected_len=0,read_idx=0,packets=0,errors=0;
    logic [160:0] held;
    logic was_stalled=0;
    detokenizer_engine #(.VOCAB_ADDR_WIDTH(9),.POOL_ADDR_WIDTH(14),.EXTERNAL_MEMORY(0)) dut (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(cfg_valid),
        .cfg_ready(cfg_ready),.cfg_pool(cfg_pool),.cfg_addr(cfg_addr),.cfg_data(cfg_data),
        .cfg_error(cfg_error),.strip_special_tokens(strip_special),
        .s_axis_tokens_tdata(token),.s_axis_tokens_tvalid(token_valid),
        .s_axis_tokens_tready(token_ready),.s_axis_tokens_tlast(token_last),
        .s_axis_tokens_tuser(token_user),.m_axis_text_tdata(text_data),
        .m_axis_text_tkeep(text_keep),.m_axis_text_tvalid(text_valid),
        .m_axis_text_tready(text_ready),.m_axis_text_tlast(text_last),
        .m_axis_text_tuser(text_user),.error_valid(error_valid),.error_ready(1'b1),
        .error_code(error_code),.error_user(error_user),.idle(idle));
    task automatic write_word(input bit pool,input int address,input logic[63:0] value);
        @(negedge clk); cfg_pool=pool; cfg_addr=address; cfg_data=value; cfg_valid=1;
        do @(posedge clk); while(!cfg_ready);
        if(cfg_error) $fatal(1,"Unexpected config error");
        @(negedge clk); cfg_valid=0;
    endtask
    task automatic entry(input int id,input int offset,input int length,input bit special);
        write_word(0,id,{16'(length),32'(offset),14'd0,1'b1,special});
    endtask
    task automatic send_token(input int id,input bit last);
        @(negedge clk); token=id; token_last=last; token_valid=1;
        do @(posedge clk); while(!token_ready);
        @(negedge clk); token_valid=0;
    endtask
    task automatic await_packet(input int target);
        wait(packets==target); @(negedge clk);
        if(read_idx!=expected_len) $fatal(1,"Length mismatch: %0d vs %0d",read_idx,expected_len);
        if(!idle) begin repeat(3) @(negedge clk); if(!idle) $fatal(1,"Not idle after packet"); end
        expected_len=0;read_idx=0;
    endtask
    always @(negedge clk) text_ready=($urandom_range(0,3)!=0);
    always @(posedge clk) begin
        if(!rst) begin
            if(was_stalled && (!text_valid || held!=={text_user,text_last,text_keep,text_data}))
                $fatal(1,"Output changed under stall");
            was_stalled=text_valid&&!text_ready;
            held={text_user,text_last,text_keep,text_data};
            if(error_valid) begin
                errors++;
                if(error_code!=1 && error_code!=2 && error_code!=3) $fatal(1,"Unexpected error");
                if(error_user!=16'hcafe) $fatal(1,"Error context mismatch");
            end
            if(text_valid && text_ready) begin
                if(text_user!=16'hcafe) $fatal(1,"Context mismatch");
                for(integer i=0;i<16;i++) if(text_keep[i]) begin
                    if(read_idx>=expected_len || text_data[i*8+:8]!==expected[read_idx])
                        $fatal(1,"Byte mismatch idx=%0d actual=%h expected=%h",read_idx,text_data[i*8+:8],expected[read_idx]);
                    read_idx++;
                end
                if(text_last) packets++;
            end
        end
    end
    initial begin
        repeat(4) @(negedge clk); rst=0;
        // Explicitly invalidate unused directory entries: RAM is runtime-loaded.
        for(integer i=0;i<12;i++) write_word(0,i,0);
        entry(0,3,6,0); entry(1,17,5,0); entry(2,31,2,0); entry(3,70001,2,0);
        entry(4,91,7,1); entry(5,112,40,0); entry(6,0,0,0);
        entry(7,131070,4,0);
        write_word(1,0,64'h6f6c6c6548000000);
        write_word(1,1,64'h20);
        write_word(1,2,64'h0000646c726f7700);
        write_word(1,3,64'hf000000000000000);
        write_word(1,4,64'h9f);
        write_word(1,8750,64'h0000000000809800);
        write_word(1,11,64'h746f657c3c000000);
        write_word(1,12,64'h3e7c);
        for(integer w=0;w<5;w++) begin
            for(integer b=0;b<8;b++) cfg_data[b*8+:8]=8'(w*8+b);
            write_word(1,14+w,cfg_data);
        end
        @(negedge clk);cfg_unlock=0;
        expected[0]="H";expected[1]="e";expected[2]="l";expected[3]="l";expected[4]="o";expected[5]=" ";
        expected[6]="w";expected[7]="o";expected[8]="r";expected[9]="l";expected[10]="d";
        expected[11]=8'hf0;expected[12]=8'h9f;expected[13]=8'h98;expected[14]=8'h80;
        expected_len=15;
        send_token(0,0);send_token(1,0);send_token(2,0);send_token(3,0);send_token(4,1);
        await_packet(1);
        expected_len=40;
        for(integer j=0;j<40;j++) expected[j]=8'(j);
        send_token(5,1);await_packet(2);
        send_token(6,1);await_packet(3);
        send_token(512,1);await_packet(4);
        send_token(10,1);await_packet(5);
        send_token(7,1);await_packet(6);
        if(errors!=3) $fatal(1,"Expected 3 invalid token errors");
        // Runtime reload changes a token without recompiling RTL.
        @(negedge clk);cfg_unlock=1;
        entry(0,17,5,0);
        @(negedge clk);cfg_unlock=0;
        expected[0]="w";expected[1]="o";expected[2]="r";expected[3]="l";expected[4]="d";
        expected_len=5;send_token(0,1);await_packet(7);
        strip_special=0;
        expected[0]="<";expected[1]="|";expected[2]="e";expected[3]="o";
        expected[4]="t";expected[5]="|";expected[6]=">";
        expected_len=7;send_token(4,1);await_packet(8);
        $display("PASS: URAM detokenizer, dynamic reload, 32-bit offsets, UTF-8 split, long tokens, special filtering, bounds errors, stalls");
        $finish;
    end
    initial begin #200000; $fatal(1,"Timeout"); end
endmodule
