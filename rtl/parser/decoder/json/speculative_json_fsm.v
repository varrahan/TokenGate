`timescale 1ns/1ps
`default_nettype none
// Correctness grammar engine for a JSON packet. All JSON values are validated;
// selected object string fields are normalized to UTF-8 and concatenated in
// document order. EOF is a keep=0,last=1 input record. Output final status must
// be checked by the outer transactional decoder before releasing any text.
// The SIMD structural fast path remains a separate performance requirement.
module speculative_json_fsm #(
    parameter integer USER_WIDTH=16,
    parameter integer MAX_DEPTH=32,
    parameter integer KEY_BYTES=32,
    parameter integer KEY_LENGTH_WIDTH=$clog2(KEY_BYTES+2)
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output reg s_ready,
    input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire key_start_valid,input wire key_start_ready,
    output wire key_valid,input wire key_ready,output wire [7:0] key_data,output wire key_keep,key_last,
    input wire key_result_valid,output wire key_result_ready,input wire key_selected,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,
    output wire [7:0] packet_status,output wire idle
);
    localparam STRUCT=0,STRING=1,WAIT_STRING=2,NUMBER=3,LITERAL=4,DRAIN=5,FINISH=6,KEY_BEGIN=7,KEY_RESULT=8;
    localparam ROOT_VALUE=0,ROOT_DONE=1,OBJ_KEY_OR_END=2,OBJ_KEY=3,OBJ_COLON=4,
               OBJ_VALUE=5,OBJ_AFTER=6,ARR_VALUE_OR_END=7,ARR_VALUE=8,ARR_AFTER=9;
    localparam NMINUS=0,NZERO=1,NINT=2,NDOT=3,NFRAC=4,NEXP=5,NSIGN=6,NEXPDIG=7;
    localparam integer DW=$clog2(MAX_DEPTH+1);
    reg [3:0] state;
    reg [2:0] number_state;
    reg [3:0] phases[0:MAX_DEPTH];
    reg [DW-1:0] depth;
    reg [1:0] literal_kind;
    reg [2:0] literal_index;
    reg current_target,str_key,str_target,raw_escape,string_eof;
    reg [USER_WIDTH-1:0] context_id;
    reg packet_open;
    reg [7:0] status;
    wire [3:0] phase=phases[depth];
    function whitespace(input [7:0] b);
        begin whitespace=b==32 || b==9 || b==10 || b==13;end
    endfunction
    function [7:0] literal_char(input [1:0] kind,input [2:0] index);
        begin
            literal_char=0;
            case(kind)
                0:case(index)0:literal_char="t";1:literal_char="r";2:literal_char="u";3:literal_char="e";default:literal_char=0;endcase
                1:case(index)0:literal_char="f";1:literal_char="a";2:literal_char="l";3:literal_char="s";4:literal_char="e";default:literal_char=0;endcase
                2:case(index)0:literal_char="n";1:literal_char="u";2:literal_char="l";3:literal_char="l";default:literal_char=0;endcase
                default:literal_char=0;
            endcase
        end
    endfunction
    wire number_terminal=number_state==NZERO || number_state==NINT || number_state==NFRAC || number_state==NEXPDIG;
    wire delimiter=whitespace(s_data) || s_data==8'h2c || s_data==8'h5d || s_data==8'h7d;
    wire input_eof=!s_keep && s_last;
    wire raw_close=s_keep && s_data==8'h22 && !raw_escape;
    wire norm_ready,norm_valid,norm_keep,norm_last;
    wire [7:0] norm_byte,norm_status;
    wire norm_output_ready=str_key?key_ready:(!norm_keep || !str_target || m_ready);
    json_string_normalizer #(.USER_WIDTH(USER_WIDTH)) normalizer (
        .clk(clk),.rst(rst),.s_data(s_data),.s_keep(s_keep&&!raw_close),
        .s_valid(state==STRING && s_valid && (s_keep||s_last)),.s_ready(norm_ready),
        .s_last(raw_close||input_eof),.s_user(context_id),
        .m_data(norm_byte),.m_keep(norm_keep),.m_valid(norm_valid),.m_ready(norm_output_ready),
        .m_last(norm_last),.m_user(),.packet_status(norm_status));
    assign key_start_valid=state==KEY_BEGIN;
    assign key_valid=(state==STRING||state==WAIT_STRING)&&str_key&&norm_valid;
    assign key_data=norm_byte;assign key_keep=norm_keep;assign key_last=norm_last;
    // A malformed key still retires its matcher result while JSON drains.
    // Successful keys enter KEY_RESULT before a result can be published.
    assign key_result_ready=1'b1;
    assign m_valid=state==FINISH || ((state==STRING || state==WAIT_STRING) && norm_valid && norm_keep && str_target);
    assign m_keep=state!=FINISH;
    assign m_data=state==FINISH ? 8'd0 : norm_byte;
    assign m_last=state==FINISH;
    assign m_user=context_id;
    assign packet_status=status;
    assign idle=state==STRUCT && depth==0 && phases[0]==ROOT_VALUE && !packet_open;
    always @* begin
        s_ready=0;
        if(!rst)case(state)
            STRUCT,LITERAL,DRAIN:s_ready=1;
            STRING:s_ready=norm_ready;
            NUMBER:s_ready=!(s_valid && number_terminal && ((s_keep&&delimiter)||input_eof));
            default:s_ready=0;
        endcase
    end
    task fail;
        input [7:0] code;
        input at_end;
        begin status<=code;state<=at_end ? FINISH : DRAIN;end
    endtask
    task mark_value;
        begin
            if(depth==0)phases[depth]<=ROOT_DONE;
            else if(phase==OBJ_VALUE)phases[depth]<=OBJ_AFTER;
            else phases[depth]<=ARR_AFTER;
        end
    endtask
    task start_string;
        input is_key;
        input selected;
        begin
            state<=is_key?KEY_BEGIN:STRING;str_key<=is_key;str_target<=selected;
            raw_escape<=0;string_eof<=0;
        end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=STRUCT;number_state<=0;phases[0]<=ROOT_VALUE;depth<=0;
            literal_kind<=0;literal_index<=0;
            current_target<=0;str_key<=0;str_target<=0;raw_escape<=0;string_eof<=0;
            context_id<=0;packet_open<=0;status<=0;
        end else begin
            if(s_valid && s_ready && !packet_open && (s_keep||s_last))begin context_id<=s_user;packet_open<=1;end
            if((state==STRING || state==WAIT_STRING) && norm_valid && norm_output_ready)begin
                if(norm_last)begin
                    if(norm_status!=0)fail(8'd16+norm_status,string_eof);
                    else if(string_eof)fail(1,1);
                    else begin
                        state<=str_key?KEY_RESULT:STRUCT;
                    end
                end
            end
            case(state)
                KEY_BEGIN:if(key_start_ready)state<=STRING;
                KEY_RESULT:if(key_result_valid)begin phases[depth]<=OBJ_COLON;current_target<=key_selected;state<=STRUCT;end
                STRUCT:if(s_valid && s_ready)begin
                    if(input_eof)begin
                        if(depth!=0 || phases[0]!=ROOT_DONE)status<=1;
                        state<=FINISH;
                    end else if(s_keep && !whitespace(s_data))begin
                        if(phase==OBJ_KEY_OR_END || phase==OBJ_KEY)begin
                            if(s_data==8'h22)start_string(1,0);
                            else if(s_data==8'h7d && phase==OBJ_KEY_OR_END)depth<=depth-1'b1;
                            else fail(2,0);
                        end else if(phase==OBJ_COLON)begin
                            if(s_data==8'h3a)phases[depth]<=OBJ_VALUE;else fail(2,0);
                        end else if(phase==OBJ_AFTER)begin
                            if(s_data==8'h2c)phases[depth]<=OBJ_KEY;
                            else if(s_data==8'h7d)depth<=depth-1'b1;
                            else fail(2,0);
                        end else if(phase==ARR_AFTER)begin
                            if(s_data==8'h2c)phases[depth]<=ARR_VALUE;
                            else if(s_data==8'h5d)depth<=depth-1'b1;
                            else fail(2,0);
                        end else if(phase==ARR_VALUE_OR_END && s_data==8'h5d)depth<=depth-1'b1;
                        else if(phase==ROOT_DONE)fail(2,0);
                        else if(phase==ROOT_VALUE || phase==OBJ_VALUE || phase==ARR_VALUE || phase==ARR_VALUE_OR_END)begin
                            if(phase==OBJ_VALUE && current_target && s_data!=8'h22)fail(4,0);
                            else if(s_data==8'h22)begin mark_value();start_string(0,phase==OBJ_VALUE&&current_target);end
                            else if(s_data==8'h7b || s_data==8'h5b)begin
                                if(depth==MAX_DEPTH)fail(3,0);
                                else begin mark_value();depth<=depth+1'b1;phases[depth+1'b1]<=s_data==8'h7b ? OBJ_KEY_OR_END : ARR_VALUE_OR_END;end
                            end else if(s_data==8'h2d || (s_data>=48 && s_data<=57))begin
                                mark_value();state<=NUMBER;
                                number_state<=s_data==8'h2d ? NMINUS : s_data==48 ? NZERO : NINT;
                            end else if(s_data=="t" || s_data=="f" || s_data=="n")begin
                                mark_value();state<=LITERAL;literal_index<=1;
                                literal_kind<=s_data=="t" ? 0 : s_data=="f" ? 1 : 2;
                            end else fail(2,0);
                        end else fail(2,0);
                    end
                end
                STRING:if(s_valid && s_ready)begin
                    if(raw_close || input_eof)begin state<=WAIT_STRING;string_eof<=input_eof;end
                    else if(s_keep)raw_escape<=s_data==8'h5c ? !raw_escape : 0;
                end
                WAIT_STRING:begin end
                NUMBER:if(s_valid && (s_keep||s_last))begin
                    if(number_terminal && ((s_keep&&delimiter)||input_eof))state<=STRUCT;
                    else if(s_valid && s_ready)begin
                        if(input_eof)fail(1,1);
                        else case(number_state)
                            NMINUS:if(s_data>=48&&s_data<=57)number_state<=s_data==48 ? NZERO : NINT;else fail(2,0);
                            NZERO,NINT:if(s_data>=48&&s_data<=57 && number_state==NINT)number_state<=NINT;
                                       else if(s_data==8'h2e)number_state<=NDOT;
                                       else if(s_data=="e"||s_data=="E")number_state<=NEXP;
                                       else fail(2,0);
                            NDOT:if(s_data>=48&&s_data<=57)number_state<=NFRAC;else fail(2,0);
                            NFRAC:if(s_data>=48&&s_data<=57)number_state<=NFRAC;
                                  else if(s_data=="e"||s_data=="E")number_state<=NEXP;else fail(2,0);
                            NEXP:if(s_data==8'h2b||s_data==8'h2d)number_state<=NSIGN;
                                 else if(s_data>=48&&s_data<=57)number_state<=NEXPDIG;else fail(2,0);
                            NSIGN:if(s_data>=48&&s_data<=57)number_state<=NEXPDIG;else fail(2,0);
                            NEXPDIG:if(s_data>=48&&s_data<=57)number_state<=NEXPDIG;else fail(2,0);
                            default:fail(2,0);
                        endcase
                    end
                end
                LITERAL:if(s_valid && s_ready && (s_keep||s_last))begin
                    if(input_eof)fail(1,1);
                    else if(s_data!=literal_char(literal_kind,literal_index))fail(2,0);
                    else if(literal_index==(literal_kind==1 ? 4 : 3))state<=STRUCT;
                    else literal_index<=literal_index+1'b1;
                end
                DRAIN:if(s_valid && s_ready && input_eof)state<=FINISH;
                FINISH:if(m_ready)begin
                    state<=STRUCT;phases[0]<=ROOT_VALUE;depth<=0;status<=0;packet_open<=0;current_target<=0;
                end
                default:state<=STRUCT;
            endcase
        end
    end
endmodule
`default_nettype wire
