`timescale 1ns/1ps
`default_nettype none
// Runtime schema. Each BRAM row holds one byte from every JSON key.
// Normalized bytes compare one row at a time. Configuration commits only
// after all key bytes are durable; queries never overlap programming.
module schema_cam_lut #(
    parameter integer ENTRIES=16,parameter integer KEY_BYTES=32,
    parameter integer INDEX_WIDTH=(ENTRIES>1?$clog2(ENTRIES):1),
    parameter integer LENGTH_WIDTH=$clog2(KEY_BYTES+2)
)(
    input wire clk,input wire rst,
    input wire cfg_unlock,input wire cfg_valid,output wire cfg_ready,
    input wire [INDEX_WIDTH-1:0] cfg_index,
    input wire [KEY_BYTES*8-1:0] cfg_key,input wire [LENGTH_WIDTH-1:0] cfg_key_length,
    input wire cfg_json_enable,input wire [28:0] cfg_field,input wire cfg_proto_enable,
    input wire key_start_valid,output wire key_start_ready,
    input wire key_valid,output wire key_ready,input wire [7:0] key_data,input wire key_keep,key_last,
    output wire key_result_valid,input wire key_result_ready,output reg json_selected,
    input wire [28:0] proto_field,output reg proto_selected,
    output wire programming,output wire idle
);
    localparam C_IDLE=0,C_DEFAULTS=1,C_WRITE=2;
    localparam K_IDLE=0,K_RUN=1,K_READ=2,K_RESULT=3;
    localparam integer AW=(KEY_BYTES>1?$clog2(KEY_BYTES):1),RW=ENTRIES*8;
    reg [1:0] config_state,key_state;
    reg [AW-1:0] write_position;
    reg [LENGTH_WIDTH-1:0] position,pending_length;
    reg [INDEX_WIDTH-1:0] pending_index;
    reg [KEY_BYTES*8-1:0] pending_key;
    reg [28:0] pending_field;
    reg pending_json,pending_proto,padding_bad,overflow,held_last;
    reg [7:0] held_byte;
    reg [LENGTH_WIDTH-1:0] lengths[0:ENTRIES-1];
    reg [28:0] fields[0:ENTRIES-1];
    reg [ENTRIES-1:0] json_en,proto_en,match_mask;
    reg [ENTRIES-1:0] compared;
    reg selected_now,selected_after_read;
    wire write_en=!rst&&config_state!=C_IDLE;
    wire read_en=key_valid&&key_ready&&key_keep&&position<KEY_BYTES;
    wire [AW-1:0] memory_address=write_en?write_position:position[AW-1:0];
    reg [RW-1:0] write_data;
    reg [ENTRIES-1:0] byte_enable;
    wire [RW-1:0] read_data;
    integer lane,query_entry,entry;
    function [7:0] default_prompt;
        input integer n;
        begin case(n)0:default_prompt="p";1:default_prompt="r";2:default_prompt="o";3:default_prompt="m";4:default_prompt="p";5:default_prompt="t";default:default_prompt=0;endcase end
    endfunction
    function [7:0] default_text;
        input integer n;
        begin case(n)0:default_text="t";1:default_text="e";2:default_text="x";3:default_text="t";default:default_text=0;endcase end
    endfunction
    assign programming=config_state!=C_IDLE;
    assign idle=!rst&&config_state==C_IDLE&&key_state==K_IDLE;
    assign cfg_ready=!rst&&cfg_unlock&&config_state==C_IDLE&&key_state==K_IDLE;
    // An ungranted write may wait while an admitted packet drains. Blocking
    // its key lookup on cfg_valid would prevent the very quiescence needed
    // to grant that write. cfg_unlock alone arbitrates the two operations.
    assign key_start_ready=!rst&&!cfg_unlock&&config_state==C_IDLE&&key_state==K_IDLE;
    assign key_ready=!rst&&config_state==C_IDLE&&key_state==K_RUN;
    assign key_result_valid=!rst&&key_state==K_RESULT;
    always @*begin
        write_data=0;byte_enable=0;
        for(lane=0;lane<ENTRIES;lane=lane+1)begin
            if(config_state==C_DEFAULTS)begin
                byte_enable[lane]=lane<2;
                write_data[lane*8+:8]=lane==0?default_prompt(write_position):lane==1?default_text(write_position):8'd0;
            end else begin
                byte_enable[lane]=pending_index==lane;
                write_data[lane*8+:8]=pending_key[7:0];
            end
        end
    end
    always @*begin
        compared=0;selected_now=0;selected_after_read=0;proto_selected=0;
        for(query_entry=0;query_entry<ENTRIES;query_entry=query_entry+1)begin
            compared[query_entry]=match_mask[query_entry]&&(read_data[query_entry*8+:8]==held_byte);
            if(match_mask[query_entry]&&!overflow&&position==lengths[query_entry])selected_now=1;
            if(compared[query_entry]&&!overflow&&position==lengths[query_entry])selected_after_read=1;
            if(proto_en[query_entry]&&proto_field==fields[query_entry])proto_selected=1;
        end
    end
`ifdef PARSER_PORTABLE_SIM
`ifdef SYNTHESIS
    initial $error("PARSER_PORTABLE_SIM is not a synthesis configuration");
`endif
    reg [RW-1:0] portable_memory[0:2**AW-1];
    reg [RW-1:0] portable_read;
    integer byte_lane;
    assign read_data=portable_read;
    always @(posedge clk)begin
        if(write_en)for(byte_lane=0;byte_lane<ENTRIES;byte_lane=byte_lane+1)
            if(byte_enable[byte_lane])portable_memory[memory_address][byte_lane*8+:8]<=write_data[byte_lane*8+:8];
        if(rst)portable_read<=0;
        else if(read_en)portable_read<=portable_memory[memory_address];
    end
`else
    xpm_memory_spram #(
        .ADDR_WIDTH_A(AW),.AUTO_SLEEP_TIME(0),.BYTE_WRITE_WIDTH_A(8),.CASCADE_HEIGHT(1),.ECC_MODE("no_ecc"),
        .MEMORY_INIT_FILE("none"),.MEMORY_INIT_PARAM("0"),.MEMORY_OPTIMIZATION("true"),.MEMORY_PRIMITIVE("block"),
        .MEMORY_SIZE(RW*(2**AW)),.MESSAGE_CONTROL(0),.READ_DATA_WIDTH_A(RW),.READ_LATENCY_A(1),
        .READ_RESET_VALUE_A("0"),.RST_MODE_A("SYNC"),.SIM_ASSERT_CHK(1),.USE_MEM_INIT(0),.WAKEUP_TIME("disable_sleep"),
        .WRITE_DATA_WIDTH_A(RW),.WRITE_MODE_A("no_change")
    ) key_memory(
        .clka(clk),.rsta(rst),.ena(write_en||read_en),.regcea(1'b1),.wea(write_en?byte_enable:{ENTRIES{1'b0}}),
        .addra(memory_address),.dina(write_data),.douta(read_data),.sleep(1'b0),.injectsbiterra(1'b0),.injectdbiterra(1'b0),.sbiterra(),.dbiterra());
`endif
    initial begin if(ENTRIES<1||KEY_BYTES<1)$error("Invalid schema dimensions");end
    always @(posedge clk)begin
        if(rst)begin
            config_state<=C_DEFAULTS;key_state<=K_IDLE;write_position<=0;position<=0;
            pending_index<=0;pending_key<=0;pending_length<=0;pending_field<=0;pending_json<=0;pending_proto<=0;
            padding_bad<=0;overflow<=0;held_last<=0;held_byte<=0;json_en<=0;proto_en<=0;match_mask<=0;json_selected<=0;
            for(entry=0;entry<ENTRIES;entry=entry+1)begin lengths[entry]<=0;fields[entry]<=0;end
        end else begin
            case(config_state)
                C_DEFAULTS:if(write_position==KEY_BYTES-1)begin
                    write_position<=0;config_state<=C_IDLE;lengths[0]<=6;fields[0]<=1;json_en[0]<=1;proto_en[0]<=1;
                    if(ENTRIES>1)begin lengths[1]<=4;json_en[1]<=1;end
                end else write_position<=write_position+1'b1;
                C_IDLE:if(cfg_valid&&cfg_ready&&cfg_index<ENTRIES)begin
                    pending_index<=cfg_index;pending_key<=cfg_key;pending_length<=cfg_key_length;pending_field<=cfg_field;
                    pending_json<=cfg_json_enable;pending_proto<=cfg_proto_enable;padding_bad<=0;write_position<=0;config_state<=C_WRITE;
                end
                C_WRITE:begin
                    if(write_position>=pending_length&&pending_key[7:0]!=0)padding_bad<=1;
                    pending_key<=pending_key>>8;
                    if(write_position==KEY_BYTES-1)begin
                        lengths[pending_index]<=pending_length;fields[pending_index]<=pending_field;
                        json_en[pending_index]<=pending_json&&pending_length<=KEY_BYTES&&!padding_bad&&!(write_position>=pending_length&&pending_key[7:0]!=0);
                        proto_en[pending_index]<=pending_proto&&pending_field!=0;config_state<=C_IDLE;write_position<=0;
                    end else write_position<=write_position+1'b1;
                end
                default:config_state<=C_DEFAULTS;
            endcase
            case(key_state)
                K_IDLE:if(key_start_valid&&key_start_ready)begin match_mask<=json_en;position<=0;overflow<=0;json_selected<=0;key_state<=K_RUN;end
                K_RUN:if(key_valid&&key_ready)begin
                    if(key_keep)begin
                        if(position<KEY_BYTES)begin held_byte<=key_data;held_last<=key_last;position<=position+1'b1;key_state<=K_READ;end
                        else begin
                            overflow<=1;match_mask<=0;if(position<KEY_BYTES+1)position<=position+1'b1;
                            if(key_last)begin json_selected<=0;key_state<=K_RESULT;end
                        end
                    end else if(key_last)begin json_selected<=selected_now;key_state<=K_RESULT;end
                end
                K_READ:begin
                    match_mask<=compared;
                    if(held_last)begin json_selected<=selected_after_read;key_state<=K_RESULT;end else key_state<=K_RUN;
                end
                K_RESULT:if(key_result_ready)key_state<=K_IDLE;
                default:key_state<=K_IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
