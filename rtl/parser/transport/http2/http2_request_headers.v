`timescale 1ns/1ps
`default_nettype none
// Request-field checker between HPACK scratch leases and RPC admission.
// All forwarded fields and the result are tentative until the packet commits.
// A rejected request still drains every HPACK lease; it must not reset HPACK.
module http2_request_headers #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire [30:0] start_stream,input wire start_trailers,input wire start_end_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_scratch_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_scratch_bytes,
    input wire header_valid,output wire header_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] header_name_base,header_value_base,
    input wire [31:0] header_name_bytes,header_value_bytes,input wire [1:0] header_representation,
    input wire [USER_WIDTH-1:0] header_user,
    output wire field_valid,input wire field_ready,
    output reg [MEMORY_ADDR_WIDTH-1:0] field_name_base,field_value_base,
    output reg [31:0] field_name_bytes,field_value_bytes,output reg [1:0] field_representation,
    output reg [3:0] field_kind,output wire [USER_WIDTH-1:0] field_user,
    input wire finish_valid,output wire finish_ready,input wire finish_failed,
    output wire result_valid,input wire result_ready,
    output reg [2:0] result_status,output reg [7:0] result_detail,result_memory_status,
    output reg [9:0] result_http_status,output reg [1:0] result_format,
    output reg result_identity_encoding,result_content_length_valid,
    output reg [63:0] result_content_length,output reg result_timeout_valid,
    output reg [26:0] result_timeout_value,output reg [2:0] result_timeout_unit,
    output reg [31:0] result_headers,output reg [USER_WIDTH-1:0] result_user,
    output reg [30:0] result_stream,output reg result_trailers,result_end_stream,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,ACTIVE=1,CHECK=2,FETCH=3,WAIT_READ=4,BYTE=5,NAME_DONE=6,VALUE_DONE=7,FORWARD=8,DROP=9,FINALIZE=10,RESULT=11,NAME_START=12;
    localparam OTHER=0,METHOD=1,SCHEME=2,PATH=3,AUTHORITY=4,CONTENT_TYPE=5,TE=6,CONTENT_LENGTH=7,ENCODING=8,TIMEOUT=9,HOST=10;
    reg [3:0] state;
    reg [MEMORY_ADDR_WIDTH-1:0] scratch_base;
    reg [MEMORY_ADDR_WIDTH:0] scratch_bytes;
    reg name_part,name_pseudo,ordinary_seen,local_failed;
    reg [3:0] pseudo_seen;
    reg method_post,method_connect,method_options,scheme_web,path_star,path_slash,authority_userinfo,authority_empty;
    reg content_type_seen,te_seen,encoding_seen,timeout_seen;
    reg [31:0] position,part_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] part_base;
    reg [71:0] read_buffer;
    reg [3:0] read_count,read_lane;
    wire [7:0] octet=read_buffer[read_lane*8+:8];
    wire [7:0] lower_octet=(octet>=65&&octet<=90)?octet+8'd32:octet;
    reg match_post,match_connect,match_options,match_http,match_https,match_identity;
    reg match_ct,match_proto,match_json;
    reg [1:0] ct_delimiter,proto_delimiter,json_delimiter;
    reg [3:0] te_position;
    reg [63:0] number,list_number;
    reg number_bad,list_seen;reg [1:0] number_state;
    reg [3:0] timeout_digits;reg timeout_bad,timeout_unit_seen;reg [2:0] timeout_unit;
    wire slot_ready,slot_valid,slot_idle;
    wire [71:0] slot_data;wire [7:0] slot_status;
    wire [31:0] remaining=part_bytes-position;
    wire [3:0] request_bytes=remaining>9?4'd9:remaining[3:0];
    wire [32:0] scratch_end={1'b0,scratch_base}+{1'b0,scratch_bytes};
    wire [32:0] name_end={1'b0,field_name_base}+{1'b0,field_name_bytes};
    wire [32:0] value_end={1'b0,field_value_base}+{1'b0,field_value_bytes};
    wire name_bounds=field_name_bytes==0?field_name_base==0:
        field_name_base>=scratch_base&&name_end<=scratch_end;
    wire value_bounds=field_value_bytes==0?field_value_base==0:
        field_value_base>=scratch_base&&value_end<=scratch_end;
    wire scratch_ok=scratch_bytes!=0&&scratch_end<=(33'd1<<MEMORY_ADDR_WIDTH);
    wire [63:0] decimal_digit={60'd0,octet[3:0]};
    wire name_start_ready,name_byte_ready,name_result_valid,name_idle;
    wire [3:0] name_code;
    wire [3:0] name_kind=field_name_bytes==0||name_code>HOST?OTHER:name_code;
    http2_name_classifier names(
        .clk(clk),.rst(rst),.cancel(state==DROP),.start_valid(state==NAME_START),.start_ready(name_start_ready),
        .s_valid(state==BYTE&&name_part),.s_ready(name_byte_ready),.s_data(octet),.s_keep(1'b1),.s_last(position+1==part_bytes),
        .result_valid(name_result_valid),.result_ready(state==NAME_DONE),.result_code(name_code),.idle(name_idle));
    assign start_ready=!rst&&state==IDLE;
    assign header_ready=!rst&&(state==DROP||(state==FORWARD&&field_ready));
    assign field_valid=!rst&&state==FORWARD;
    assign field_user=result_user;
    assign finish_ready=!rst&&state==ACTIVE&&!header_valid;
    assign result_valid=!rst&&state==RESULT;
    assign idle=state==IDLE&&slot_idle&&name_idle;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) reader(
        .clk(clk),.rst(rst),.req_valid(state==FETCH),.req_ready(slot_ready),.req_write(1'b0),
        .req_addr(part_base+position[MEMORY_ADDR_WIDTH-1:0]),.req_bytes(request_bytes),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==WAIT_READ),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    function token_char;
        input [7:0] c;
        begin token_char=(c>=48&&c<=57)||(c>=65&&c<=90)||(c>=97&&c<=122)||
            c==33||c==35||c==36||c==37||c==38||c==39||c==42||c==43||c==45||c==46||c==94||c==95||c==96||c==124||c==126;end
    endfunction
    function [7:0] string_byte;
        input [255:0] text;input integer length;input [31:0] index;
        begin if(index>=length)string_byte=0;else string_byte=text>>((length-1-index)*8);end
    endfunction
    function [2:0] time_unit;
        input [7:0] c;
        begin case(c)"H":time_unit=0;"M":time_unit=1;"S":time_unit=2;"m":time_unit=3;"u":time_unit=4;"n":time_unit=5;default:time_unit=7;endcase end
    endfunction
    task malformed;
        input [7:0] detail;
        begin if(result_status==0||result_status==2)begin result_status<=1;result_detail<=detail;result_http_status<=0;end end
    endtask
    task unsupported;
        input [7:0] detail;input [9:0] http_status;
        begin if(result_status==0)begin result_status<=2;result_detail<=detail;result_http_status<=http_status;end end
    endtask
    task local_error;
        input [7:0] detail;input [7:0] memory_status;
        begin result_status<=3;result_detail<=detail;result_memory_status<=memory_status;result_http_status<=0;local_failed<=1;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;scratch_base<=0;scratch_bytes<=0;result_status<=0;result_detail<=0;result_memory_status<=0;result_http_status<=0;
            result_format<=0;result_identity_encoding<=1;result_content_length_valid<=0;result_content_length<=0;
            result_timeout_valid<=0;result_timeout_value<=0;result_timeout_unit<=0;result_headers<=0;result_user<=0;result_stream<=0;result_trailers<=0;result_end_stream<=0;
            field_name_base<=0;field_value_base<=0;field_name_bytes<=0;field_value_bytes<=0;field_representation<=0;field_kind<=0;
            name_part<=0;name_pseudo<=0;ordinary_seen<=0;local_failed<=0;pseudo_seen<=0;
            method_post<=0;method_connect<=0;method_options<=0;scheme_web<=0;path_star<=0;path_slash<=0;authority_userinfo<=0;authority_empty<=1;
            content_type_seen<=0;te_seen<=0;encoding_seen<=0;timeout_seen<=0;position<=0;part_bytes<=0;part_base<=0;
            read_buffer<=0;read_count<=0;read_lane<=0;
            match_post<=0;match_connect<=0;match_options<=0;match_http<=0;match_https<=0;match_identity<=0;
            match_ct<=0;match_proto<=0;match_json<=0;ct_delimiter<=0;proto_delimiter<=0;json_delimiter<=0;te_position<=0;
            number<=0;list_number<=0;number_bad<=0;list_seen<=0;number_state<=0;timeout_digits<=0;timeout_bad<=0;timeout_unit_seen<=0;timeout_unit<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin
                result_status<=0;result_detail<=0;result_memory_status<=0;result_http_status<=0;result_format<=0;result_identity_encoding<=1;
                result_content_length_valid<=0;result_content_length<=0;result_timeout_valid<=0;result_timeout_value<=0;result_timeout_unit<=0;
                result_headers<=0;result_user<=start_user;result_stream<=start_stream;result_trailers<=start_trailers;result_end_stream<=start_end_stream;
                scratch_base<=cfg_scratch_base;scratch_bytes<=cfg_scratch_bytes;ordinary_seen<=0;local_failed<=0;pseudo_seen<=0;
                method_post<=0;method_connect<=0;method_options<=0;scheme_web<=0;path_star<=0;path_slash<=0;authority_userinfo<=0;authority_empty<=1;
                content_type_seen<=0;te_seen<=0;encoding_seen<=0;timeout_seen<=0;state<=ACTIVE;
                if(start_stream==0)begin result_status<=1;result_detail<=1;end
                if(start_trailers&&!start_end_stream)begin result_status<=1;result_detail<=2;end
            end
            ACTIVE:if(header_valid)begin
                field_name_base<=header_name_base;field_value_base<=header_value_base;field_name_bytes<=header_name_bytes;field_value_bytes<=header_value_bytes;
                field_representation<=header_representation;field_kind<=OTHER;name_pseudo<=0;position<=0;name_part<=1;
                part_base<=header_name_base;part_bytes<=header_name_bytes;result_headers<=result_headers+1'b1;state<=CHECK;
                if(header_user!=result_user) local_error(8'd1,0);
                if(result_headers==32'hffffffff)local_error(8'd2,0);
            end else if(finish_valid&&finish_ready)begin
                state<=FINALIZE;
                if(finish_failed)begin result_status<=4;result_detail<=0;result_memory_status<=0;result_http_status<=0;end
            end
            CHECK:begin
                if(local_failed)state<=DROP;
                else if(!scratch_ok||!name_bounds||!value_bounds)begin local_error(8'd3,0);state<=DROP;end
                else if(field_name_bytes==0)begin malformed(8'd3);state<=NAME_DONE;end
                else state<=NAME_START;
            end
            NAME_START:if(name_start_ready)state<=FETCH;
            FETCH:if(slot_ready)begin read_count<=request_bytes;state<=WAIT_READ;end
            WAIT_READ:if(slot_valid)begin
                if(slot_status!=0)begin local_error(name_part?8'd4:8'd5,slot_status);state<=DROP;end
                else begin read_buffer<=slot_data;read_lane<=0;state<=BYTE;end
            end
            BYTE:if(!name_part||name_byte_ready)begin
                if(name_part)begin
                    if(position==0)name_pseudo<=octet==58;
                    if(!(position==0&&octet==58)&&(!token_char(octet)||(octet>=65&&octet<=90)))malformed(8'd4);
                end else begin
                    case(field_kind)
                        METHOD:begin
                            if(!token_char(octet))malformed(8'd9);
                            if(octet!=string_byte("POST",4,position))match_post<=0;
                            if(octet!=string_byte("CONNECT",7,position))match_connect<=0;
                            if(octet!=string_byte("OPTIONS",7,position))match_options<=0;
                        end
                        SCHEME:begin
                            if(!((octet>=65&&octet<=90)||(octet>=97&&octet<=122)||position!=0&&((octet>=48&&octet<=57)||octet==43||octet==45||octet==46)))malformed(8'd10);
                            if(lower_octet!=string_byte("http",4,position))match_http<=0;
                            if(lower_octet!=string_byte("https",5,position))match_https<=0;
                        end
                        PATH:begin
                            if(position==0)begin path_star<=octet==42;path_slash<=octet==47;end
                            if(octet<=32||octet==127||octet==35)malformed(8'd11);
                        end
                        AUTHORITY:begin if(octet==64)authority_userinfo<=1;if(octet<=32||octet==127)malformed(8'd12);end
                        CONTENT_TYPE:begin
                            if(position<16&&lower_octet!=string_byte("application/grpc",16,position))match_ct<=0;
                            if(position>=16&&position<22&&lower_octet!=string_byte("+proto",6,position-16))match_proto<=0;
                            if(position>=16&&position<21&&lower_octet!=string_byte("+json",5,position-16))match_json<=0;
                            // Media-type parameters permit OWS before ';'.
                            // 0 not reached, 1 OWS, 2 parameters, 3 not a delimiter.
                            if(position==16||position>16&&ct_delimiter==1)
                                ct_delimiter<=octet==59?2:(octet==32||octet==9)?1:3;
                            if(position==22||position>22&&proto_delimiter==1)
                                proto_delimiter<=octet==59?2:(octet==32||octet==9)?1:3;
                            if(position==21||position>21&&json_delimiter==1)
                                json_delimiter<=octet==59?2:(octet==32||octet==9)?1:3;
                        end
                        TE:begin
                            if(octet==32||octet==9)begin if(te_position!=0&&te_position!=8)malformed(8'd13);end
                            else if(octet==44)begin if(te_position!=8)malformed(8'd13);te_position<=0;end
                            else if(te_position>=8||lower_octet!=string_byte("trailers",8,te_position))malformed(8'd13);
                            else te_position<=te_position+1'b1;
                        end
                        CONTENT_LENGTH:begin
                            if(octet>=48&&octet<=57)begin
                                if(number_state==2||number>64'd1844674407370955161||number==64'd1844674407370955161&&octet>53)number_bad<=1;
                                number<=number*10+decimal_digit;number_state<=1;
                            end else if(octet==32||octet==9)begin if(number_state==1)number_state<=2;end
                            else if(octet==44)begin
                                if(number_state==0||list_seen&&number!=list_number)number_bad<=1;
                                list_number<=number;list_seen<=1;number<=0;number_state<=0;
                            end else number_bad<=1;
                        end
                        ENCODING:begin
                            if(!token_char(octet))unsupported(8'd9,10'd400);
                            if(octet!=string_byte("identity",8,position))match_identity<=0;
                        end
                        TIMEOUT:begin
                            if(octet>=48&&octet<=57&&!timeout_unit_seen)begin
                                if(timeout_digits==8)timeout_bad<=1;
                                timeout_digits<=timeout_digits+1'b1;number<=number*10+decimal_digit;
                            end else begin
                                if(timeout_unit_seen||timeout_digits==0||time_unit(octet)==7)timeout_bad<=1;
                                timeout_unit_seen<=1;timeout_unit<=time_unit(octet);
                            end
                        end
                        default:begin end
                    endcase
                    if(octet==0||octet==10||octet==13||(octet<32&&octet!=9)||octet==127||
                        ((position==0||position+1==part_bytes)&&(octet==32||octet==9)))malformed(8'd8);
                end
                position<=position+1'b1;read_lane<=read_lane+1'b1;
                if(position+1==part_bytes)state<=name_part?NAME_DONE:VALUE_DONE;
                else if(read_lane+1==read_count)state<=FETCH;
            end
            NAME_DONE:if(field_name_bytes==0||name_result_valid)begin
                field_kind<=name_kind;
                if(name_pseudo)begin
                    if(result_trailers||ordinary_seen)malformed(8'd5);
                    if(name_kind<METHOD||name_kind>AUTHORITY)malformed(8'd6);
                    else begin
                        if(pseudo_seen[name_kind-1])malformed(8'd7);
                        pseudo_seen[name_kind-1]<=1;
                    end
                end else ordinary_seen<=1;
                if(field_name_bytes!=0&&name_code==11)malformed(8'd14);
                position<=0;part_base<=field_value_base;part_bytes<=field_value_bytes;name_part<=0;
                match_post<=1;match_connect<=1;match_options<=1;match_http<=1;match_https<=1;match_identity<=1;
                match_ct<=1;match_proto<=1;match_json<=1;ct_delimiter<=0;proto_delimiter<=0;json_delimiter<=0;te_position<=0;
                number<=0;list_number<=0;number_bad<=0;list_seen<=0;number_state<=0;timeout_digits<=0;timeout_bad<=0;timeout_unit_seen<=0;timeout_unit<=0;
                state<=field_value_bytes==0?VALUE_DONE:FETCH;
            end
            VALUE_DONE:begin
                case(field_kind)
                    METHOD:begin
                        method_post<=match_post&&field_value_bytes==4;method_connect<=match_connect&&field_value_bytes==7;method_options<=match_options&&field_value_bytes==7;
                        if(field_value_bytes==0)malformed(8'd9);
                    end
                    SCHEME:begin scheme_web<=match_http&&field_value_bytes==4||match_https&&field_value_bytes==5;if(field_value_bytes==0)malformed(8'd10);end
                    PATH:begin path_star<=path_star&&field_value_bytes==1;if(field_value_bytes==0)malformed(8'd11);end
                    AUTHORITY:authority_empty<=field_value_bytes==0;
                    CONTENT_TYPE:begin
                        if(content_type_seen)unsupported(8'd1,10'd400);content_type_seen<=1;
                        if(match_ct&&(field_value_bytes==16||ct_delimiter==2||match_proto&&(field_value_bytes==22||proto_delimiter==2)))result_format<=0;
                        else if(match_ct&&match_json&&(field_value_bytes==21||json_delimiter==2))result_format<=1;
                        else begin result_format<=2;unsupported(8'd2,10'd415);end
                    end
                    TE:begin te_seen<=1;if(te_position!=8)malformed(8'd13);end
                    CONTENT_LENGTH:begin
                        if(number_bad||number_state==0||list_seen&&number!=list_number||result_content_length_valid&&number!=result_content_length)malformed(8'd15);
                        result_content_length_valid<=1;result_content_length<=number;
                    end
                    ENCODING:begin
                        if(encoding_seen||field_value_bytes==0)unsupported(8'd9,10'd400);encoding_seen<=1;
                        result_identity_encoding<=match_identity&&field_value_bytes==8;
                    end
                    TIMEOUT:begin
                        if(timeout_seen||timeout_bad||!timeout_unit_seen||number==0)unsupported(8'd10,10'd400);
                        timeout_seen<=1;result_timeout_valid<=1;result_timeout_value<=number[26:0];result_timeout_unit<=timeout_unit;
                    end
                    default:begin end
                endcase
                state<=FORWARD;
            end
            FORWARD:if(field_ready)state<=ACTIVE;
            DROP:state<=ACTIVE;
            FINALIZE:begin
                state<=RESULT;
                if(result_status==0||result_status==2)begin
                    if(!result_trailers)begin
                        if(!pseudo_seen[0]||(method_connect?(!pseudo_seen[3]||authority_empty||pseudo_seen[1]||pseudo_seen[2]):(!pseudo_seen[1]||!pseudo_seen[2])))malformed(8'd16);
                        else if((scheme_web||method_connect)&&authority_userinfo||scheme_web&&!path_slash&&!(path_star&&method_options))malformed(8'd17);
                        else if(!method_post)unsupported(8'd3,10'd405);
                        else if(!scheme_web)unsupported(8'd4,10'd400);
                        else if(!content_type_seen)unsupported(8'd5,10'd415);
                        else if(!te_seen)unsupported(8'd6,10'd400);
                    end
                end
            end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
