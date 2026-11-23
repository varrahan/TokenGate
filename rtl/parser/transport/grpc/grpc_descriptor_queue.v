`timescale 1ns/1ps
`default_nettype none
// External descriptor FIFO with one pending packet transaction. Append data
// never becomes visible until finish(commit) succeeds. Reset/config-clear is
// a queue-wide cancellation and must be coordinated with RPC ownership.
module grpc_descriptor_queue #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire cfg_valid,output wire cfg_ready,input wire cfg_clear,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_bytes,
    output wire cfg_result_valid,input wire cfg_result_ready,output reg [7:0] cfg_status,
    input wire begin_valid,output wire begin_ready,input wire [USER_WIDTH-1:0] begin_user,input wire [31:0] begin_tag,
    input wire s_valid,output wire s_ready,input wire [USER_WIDTH-1:0] s_user,s_application,input wire [30:0] s_stream,
    input wire s_protobuf,input wire [MEMORY_ADDR_WIDTH-1:0] s_base,input wire [31:0] s_bytes,s_ordinal,s_generation,
    input wire finish_valid,output wire finish_ready,input wire finish_commit,
    output wire finish_result_valid,input wire finish_result_ready,output reg finish_committed,
    output reg [7:0] finish_status,finish_detail,finish_memory_status,output wire [USER_WIDTH-1:0] finish_user,output wire [31:0] finish_tag,
    output wire m_valid,input wire m_ready,output wire [USER_WIDTH-1:0] m_user,m_application,output wire [30:0] m_stream,
    output wire m_protobuf,output wire [MEMORY_ADDR_WIDTH-1:0] m_base,output wire [31:0] m_bytes,m_ordinal,m_generation,m_packet_tag,
    output wire transaction_active,output reg transaction_failed,
    output reg recovery_required,output reg [7:0] recovery_detail,recovery_memory_status,
    output wire [31:0] queued_count,pending_count,output wire idle,
    output wire [1:0] mem_valid,input wire [1:0] mem_ready,output wire [1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [7:0] mem_bytes,output wire [143:0] mem_data,
    input wire [1:0] mem_rsp_valid,output wire [1:0] mem_rsp_ready,input wire [143:0] mem_rsp_data,input wire [15:0] mem_rsp_status
);
    localparam integer IW=MEMORY_ADDR_WIDTH-4;
    localparam W_IDLE=0,W_REQ=1,W_WAIT=2,W_RESULT=3;
    localparam R_IDLE=0,R_REQ=1,R_WAIT=2,R_CHECK=3,R_OUTPUT=4,R_FAULT=5;
    localparam [31:0] MAGIC=32'h47524d31;
    reg [1:0] wstate;reg [2:0] rstate;
    reg configured,active,config_response;
    reg [MEMORY_ADDR_WIDTH-1:0] pool_base;
    reg [MEMORY_ADDR_WIDTH:0] pool_bytes;
    reg [IW-1:0] slots,head,published_tail,reserve_tail,published_count,reserved_count,used_count;
    reg [255:0] write_buffer,read_buffer;
    reg [1:0] write_word,read_word;
    reg [USER_WIDTH-1:0] owner;reg [31:0] packet_tag;
    reg [7:0] transaction_status,transaction_detail,transaction_memory;
    wire pop=m_valid&&m_ready;
    wire space_available=used_count<slots||pop;
    wire [15:0] user16=s_user,application16=s_application;
    wire [63:0] requested_end={1'b0,cfg_base}+{1'b0,cfg_bytes};
    wire config_good=cfg_bytes>=32&&cfg_bytes[4:0]==0&&requested_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire [63:0] pool_end={1'b0,pool_base}+{1'b0,pool_bytes};
    wire [63:0] input_end={1'b0,s_base}+{32'd0,s_bytes};
    wire input_good=s_user==owner&&s_stream!=0&&input_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (s_bytes==0||input_end<=pool_base||{1'b0,s_base}>=pool_end);
    wire [63:0] output_end={32'd0,read_buffer[159:128]}+{32'd0,read_buffer[95:64]};
    wire output_good=read_buffer[223:192]==MAGIC&&read_buffer[62:32]!=0&&output_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (read_buffer[95:64]==0||output_end<=pool_base||{32'd0,read_buffer[159:128]}>=pool_end);
    wire wslot_ready,wslot_valid,wslot_idle,rslot_ready,rslot_valid,rslot_idle;
    wire [71:0] wslot_data,rslot_data;wire [7:0] wslot_status,rslot_status;
    wire [MEMORY_ADDR_WIDTH-1:0] write_address=pool_base+(reserve_tail<<5)+(write_word<<3);
    wire [MEMORY_ADDR_WIDTH-1:0] read_address=pool_base+(head<<5)+(read_word<<3);
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) writer(
        .clk(clk),.rst(rst),.req_valid(wstate==W_REQ),.req_ready(wslot_ready),.req_write(1'b1),.req_addr(write_address),.req_bytes(4'd8),.req_data({8'd0,write_buffer[write_word*64+:64]}),
        .result_valid(wslot_valid),.result_ready(wstate==W_WAIT),.result_data(wslot_data),.result_status(wslot_status),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(wslot_idle));
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) reader(
        .clk(clk),.rst(rst),.req_valid(rstate==R_REQ),.req_ready(rslot_ready),.req_write(1'b0),.req_addr(read_address),.req_bytes(4'd8),.req_data(72'd0),
        .result_valid(rslot_valid),.result_ready(rstate==R_WAIT),.result_data(rslot_data),.result_status(rslot_status),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),
        .mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),.idle(rslot_idle));
    wire read_fault_now=rstate==R_WAIT&&rslot_valid&&rslot_status!=0||rstate==R_CHECK&&!output_good;
    assign cfg_ready=!rst&&!active&&wstate==W_IDLE&&(rstate==R_IDLE||rstate==R_FAULT)&&wslot_idle&&rslot_idle&&!config_response&&(cfg_clear||used_count==0);
    wire configure=cfg_valid&&cfg_ready;
    assign cfg_result_valid=config_response;
    assign begin_ready=!rst&&configured&&!active&&wstate==W_IDLE&&!config_response&&!cfg_valid&&!recovery_required&&!read_fault_now;
    wire begin_accept=begin_valid&&begin_ready;
    assign s_ready=!rst&&active&&wstate==W_IDLE&&!finish_valid;
    wire append=s_valid&&s_ready;
    wire reserve=append&&!transaction_failed&&!recovery_required&&!read_fault_now&&input_good&&space_available;
    assign finish_ready=!rst&&active&&wstate==W_IDLE;
    wire finish=finish_valid&&finish_ready;
    wire commit=finish&&finish_commit&&!transaction_failed&&!recovery_required&&!read_fault_now;
    wire abort_packet=finish&&!commit;
    assign finish_result_valid=wstate==W_RESULT;
    assign finish_user=owner;assign finish_tag=packet_tag;
    assign transaction_active=active;
    assign m_valid=rstate==R_OUTPUT;
    assign m_user=read_buffer[0+:USER_WIDTH];assign m_application=read_buffer[16+:USER_WIDTH];assign m_stream=read_buffer[62:32];assign m_protobuf=read_buffer[63];
    assign m_bytes=read_buffer[95:64];assign m_ordinal=read_buffer[127:96];assign m_base=read_buffer[128+:MEMORY_ADDR_WIDTH];assign m_generation=read_buffer[191:160];assign m_packet_tag=read_buffer[255:224];
    assign queued_count=published_count;assign pending_count=reserved_count;
    assign idle=configured&&!active&&wstate==W_IDLE&&rstate==R_IDLE&&used_count==0&&wslot_idle&&rslot_idle&&!config_response&&!cfg_valid&&!begin_valid;
    initial begin if(USER_WIDTH>16||MEMORY_ADDR_WIDTH<6||MEMORY_ADDR_WIDTH>31)$error("Unsupported descriptor queue widths");end
    always @(posedge clk)begin
        if(rst)begin
            wstate<=W_IDLE;rstate<=R_IDLE;configured<=0;active<=0;config_response<=0;cfg_status<=0;
            pool_base<=0;pool_bytes<=0;slots<=0;head<=0;published_tail<=0;reserve_tail<=0;published_count<=0;reserved_count<=0;used_count<=0;
            write_buffer<=0;read_buffer<=0;write_word<=0;read_word<=0;owner<=0;packet_tag<=0;
            transaction_failed<=0;transaction_status<=0;transaction_detail<=0;transaction_memory<=0;
            recovery_required<=0;recovery_detail<=0;recovery_memory_status<=0;finish_committed<=0;finish_status<=0;finish_detail<=0;finish_memory_status<=0;
        end else begin
            if(config_response&&cfg_result_ready)config_response<=0;
            if(configure)begin
                config_response<=1;cfg_status<=config_good?8'd0:8'd13;
                if(config_good)begin
                    configured<=1;pool_base<=cfg_base;pool_bytes<=cfg_bytes;slots<=cfg_bytes>>5;
                    head<=0;published_tail<=0;reserve_tail<=0;published_count<=0;reserved_count<=0;used_count<=0;rstate<=R_IDLE;
                    recovery_required<=0;recovery_detail<=0;recovery_memory_status<=0;transaction_failed<=0;
                end
            end else begin
                case({reserve,pop})2'b10:used_count<=used_count+1'b1;2'b01:used_count<=used_count-1'b1;default:begin end endcase
                if(pop)begin published_count<=published_count-1'b1;head<=head+1'b1==slots?{IW{1'b0}}:head+1'b1;end
                if(reserve)reserved_count<=reserved_count+1'b1;
                if(finish)begin
                    active<=0;reserved_count<=0;finish_committed<=commit;finish_status<=transaction_status;finish_detail<=transaction_detail;finish_memory_status<=transaction_memory;
                    if(commit)begin published_tail<=reserve_tail;published_count<=used_count-(pop?1'b1:1'b0);end
                    else begin reserve_tail<=published_tail;used_count<=published_count-(pop?1'b1:1'b0);end
                    wstate<=W_RESULT;
                    if(recovery_required||read_fault_now)begin finish_status<=13;finish_detail<=8'h80;finish_memory_status<=read_fault_now&&rstate==R_WAIT?rslot_status:recovery_memory_status;end
                end else case(wstate)
                    W_IDLE:begin
                        if(begin_accept)begin
                            active<=1;owner<=begin_user;packet_tag<=begin_tag;transaction_failed<=0;transaction_status<=0;transaction_detail<=0;transaction_memory<=0;
                        end else if(append&&!transaction_failed)begin
                            if(recovery_required||read_fault_now)begin transaction_failed<=1;transaction_status<=13;transaction_detail<=8'h80;transaction_memory<=recovery_memory_status;end
                            else if(!input_good)begin transaction_failed<=1;transaction_status<=13;transaction_detail<=2;end
                            else if(!space_available)begin transaction_failed<=1;transaction_status<=8;transaction_detail<=3;end
                            else begin
                                write_buffer<={packet_tag,MAGIC,s_generation,{{(32-MEMORY_ADDR_WIDTH){1'b0}},s_base},s_ordinal,s_bytes,s_protobuf,s_stream,application16,user16};
                                write_word<=0;wstate<=W_REQ;
                            end
                        end
                    end
                    W_REQ:if(wslot_ready)wstate<=W_WAIT;
                    W_WAIT:if(wslot_valid)begin
                        if(wslot_status!=0)begin transaction_failed<=1;transaction_status<=13;transaction_detail<={6'd0,write_word};transaction_memory<=wslot_status;wstate<=W_IDLE;end
                        else if(write_word==3)begin reserve_tail<=reserve_tail+1'b1==slots?{IW{1'b0}}:reserve_tail+1'b1;wstate<=W_IDLE;end
                        else begin write_word<=write_word+1'b1;wstate<=W_REQ;end
                    end
                    W_RESULT:if(finish_result_ready)wstate<=W_IDLE;
                    default:begin end
                endcase
                case(rstate)
                    R_IDLE:if(configured&&published_count!=0&&!cfg_valid&&!recovery_required)begin read_word<=0;rstate<=R_REQ;end
                    R_REQ:if(rslot_ready)rstate<=R_WAIT;
                    R_WAIT:if(rslot_valid)begin
                        if(rslot_status!=0)rstate<=R_FAULT;
                        else begin read_buffer[read_word*64+:64]<=rslot_data[63:0];if(read_word==3)rstate<=R_CHECK;else begin read_word<=read_word+1'b1;rstate<=R_REQ;end end
                    end
                    R_CHECK:rstate<=output_good?R_OUTPUT:R_FAULT;
                    R_OUTPUT:if(pop)rstate<=R_IDLE;
                    default:begin end
                endcase
                if(read_fault_now)begin
                    recovery_required<=1;recovery_detail<=rstate==R_WAIT?{6'd0,read_word}:8'd4;recovery_memory_status<=rstate==R_WAIT?rslot_status:8'd0;
                    if(active)begin transaction_failed<=1;transaction_status<=13;transaction_detail<=8'h80;transaction_memory<=rstate==R_WAIT?rslot_status:8'd0;end
                end
            end
        end
    end
endmodule
`default_nettype wire
