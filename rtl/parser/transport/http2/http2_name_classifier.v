`timescale 1ns/1ps
`default_nettype none
// Fixed protocol-name trie; this is not a configurable service route table.
// Every byte is consumed, including unknown/long names. Only exact terminal
// names classify; a prefix, suffix or case change never authorizes a field.
module http2_name_classifier(
    input wire clk,input wire rst,input wire cancel,
    input wire start_valid,output wire start_ready,
    input wire s_valid,output wire s_ready,input wire [7:0] s_data,input wire s_keep,s_last,
    output wire result_valid,input wire result_ready,output reg [3:0] result_code,output wire idle
);
    localparam IDLE=0,NODE_REQ=1,NODE_WAIT=2,RUN=3,PICK=4,EDGE_REQ=5,EDGE_WAIT=6,RESULT=7;
    reg [2:0] state;
    reg known,last_pending,held_last;
    reg [7:0] octet;
    reg [6:0] node,first_edge,low,high,probe;
    reg [3:0] edge_count,terminal;
    wire [7:0] middle_sum={1'b0,low}+{1'b0,high};
    wire rom_en=state==NODE_REQ||state==EDGE_REQ;
    wire [7:0] rom_address=state==NODE_REQ?{1'b0,node}:{1'b1,probe};
    reg [15:0] rom_data;
    (* rom_style="block" *) reg [15:0] words[0:255];
    integer row;
    initial begin
        for(row=0;row<256;row=row+1)words[row]=16'd0;
        // BEGIN_NAME_ROM
        // 127 nodes/126 sorted edges; image SHA256 eebd30bfce0b2b8ed697f579e0aa9ab176cbb39caf6447bc6e41d9bff4eb9891
        words[8'd0]=16'h0400;
        words[8'd1]=16'h0208;
        words[8'd2]=16'h008c;
        words[8'd3]=16'h008d;
        words[8'd4]=16'h008e;
        words[8'd5]=16'h008f;
        words[8'd6]=16'h0090;
        words[8'd7]=16'h0091;
        words[8'd8]=16'h0092;
        words[8'd9]=16'h0093;
        words[8'd10]=16'h2014;
        words[8'd11]=16'h0094;
        words[8'd12]=16'h0095;
        words[8'd13]=16'h0096;
        words[8'd14]=16'h0097;
        words[8'd15]=16'h0098;
        words[8'd16]=16'h0819;
        words[8'd17]=16'h0099;
        words[8'd18]=16'h009a;
        words[8'd19]=16'h009b;
        words[8'd20]=16'h181c;
        words[8'd21]=16'h009c;
        words[8'd22]=16'h009d;
        words[8'd23]=16'h009e;
        words[8'd24]=16'h009f;
        words[8'd25]=16'h00a0;
        words[8'd26]=16'h1021;
        words[8'd27]=16'h00a1;
        words[8'd28]=16'h00a2;
        words[8'd29]=16'h0123;
        words[8'd30]=16'h00a5;
        words[8'd31]=16'h00a6;
        words[8'd32]=16'h00a7;
        words[8'd33]=16'h00a8;
        words[8'd34]=16'h00a9;
        words[8'd35]=16'h00aa;
        words[8'd36]=16'h582b;
        words[8'd37]=16'h00ab;
        words[8'd38]=16'h00ac;
        words[8'd39]=16'h00ad;
        words[8'd40]=16'h00ae;
        words[8'd41]=16'h012f;
        words[8'd42]=16'h00b1;
        words[8'd43]=16'h00b2;
        words[8'd44]=16'h00b3;
        words[8'd45]=16'h00b4;
        words[8'd46]=16'h00b5;
        words[8'd47]=16'h3836;
        words[8'd48]=16'h00b6;
        words[8'd49]=16'h00b7;
        words[8'd50]=16'h00b8;
        words[8'd51]=16'h2839;
        words[8'd52]=16'h00b9;
        words[8'd53]=16'h00ba;
        words[8'd54]=16'h00bb;
        words[8'd55]=16'h00bc;
        words[8'd56]=16'h013d;
        words[8'd57]=16'h00bf;
        words[8'd58]=16'h00c0;
        words[8'd59]=16'h00c1;
        words[8'd60]=16'h00c2;
        words[8'd61]=16'h00c3;
        words[8'd62]=16'h00c4;
        words[8'd63]=16'h00c5;
        words[8'd64]=16'h4046;
        words[8'd65]=16'h00c6;
        words[8'd66]=16'h00c7;
        words[8'd67]=16'h00c8;
        words[8'd68]=16'h00c9;
        words[8'd69]=16'h00ca;
        words[8'd70]=16'h00cb;
        words[8'd71]=16'h484c;
        words[8'd72]=16'h00cc;
        words[8'd73]=16'h00cd;
        words[8'd74]=16'h00ce;
        words[8'd75]=16'h504f;
        words[8'd76]=16'h00cf;
        words[8'd77]=16'h00d0;
        words[8'd78]=16'h00d1;
        words[8'd79]=16'h00d2;
        words[8'd80]=16'h00d3;
        words[8'd81]=16'h00d4;
        words[8'd82]=16'h00d5;
        words[8'd83]=16'h00d6;
        words[8'd84]=16'h00d7;
        words[8'd85]=16'h5858;
        words[8'd86]=16'h00d8;
        words[8'd87]=16'h00d9;
        words[8'd88]=16'h00da;
        words[8'd89]=16'h00db;
        words[8'd90]=16'h00dc;
        words[8'd91]=16'h00dd;
        words[8'd92]=16'h00de;
        words[8'd93]=16'h00df;
        words[8'd94]=16'h00e0;
        words[8'd95]=16'h00e1;
        words[8'd96]=16'h00e2;
        words[8'd97]=16'h00e3;
        words[8'd98]=16'h00e4;
        words[8'd99]=16'h00e5;
        words[8'd100]=16'h00e6;
        words[8'd101]=16'h5867;
        words[8'd102]=16'h0167;
        words[8'd103]=16'h3069;
        words[8'd104]=16'h00e9;
        words[8'd105]=16'h00ea;
        words[8'd106]=16'h00eb;
        words[8'd107]=16'h00ec;
        words[8'd108]=16'h00ed;
        words[8'd109]=16'h00ee;
        words[8'd110]=16'h00ef;
        words[8'd111]=16'h00f0;
        words[8'd112]=16'h00f1;
        words[8'd113]=16'h00f2;
        words[8'd114]=16'h00f3;
        words[8'd115]=16'h00f4;
        words[8'd116]=16'h00f5;
        words[8'd117]=16'h00f6;
        words[8'd118]=16'h00f7;
        words[8'd119]=16'h5878;
        words[8'd120]=16'h00f8;
        words[8'd121]=16'h00f9;
        words[8'd122]=16'h00fa;
        words[8'd123]=16'h00fb;
        words[8'd124]=16'h00fc;
        words[8'd125]=16'h00fd;
        words[8'd126]=16'h587e;
        words[8'd128]=16'h013a;
        words[8'd129]=16'h1b63;
        words[8'd130]=16'h3467;
        words[8'd131]=16'h4868;
        words[8'd132]=16'h4c6b;
        words[8'd133]=16'h5670;
        words[8'd134]=16'h6674;
        words[8'd135]=16'h7875;
        words[8'd136]=16'h0261;
        words[8'd137]=16'h0b6d;
        words[8'd138]=16'h1170;
        words[8'd139]=16'h1573;
        words[8'd140]=16'h0375;
        words[8'd141]=16'h0474;
        words[8'd142]=16'h0568;
        words[8'd143]=16'h066f;
        words[8'd144]=16'h0772;
        words[8'd145]=16'h0869;
        words[8'd146]=16'h0974;
        words[8'd147]=16'h0a79;
        words[8'd148]=16'h0c65;
        words[8'd149]=16'h0d74;
        words[8'd150]=16'h0e68;
        words[8'd151]=16'h0f6f;
        words[8'd152]=16'h1064;
        words[8'd153]=16'h1261;
        words[8'd154]=16'h1374;
        words[8'd155]=16'h1468;
        words[8'd156]=16'h1663;
        words[8'd157]=16'h1768;
        words[8'd158]=16'h1865;
        words[8'd159]=16'h196d;
        words[8'd160]=16'h1a65;
        words[8'd161]=16'h1c6f;
        words[8'd162]=16'h1d6e;
        words[8'd163]=16'h1e6e;
        words[8'd164]=16'h2574;
        words[8'd165]=16'h1f65;
        words[8'd166]=16'h2063;
        words[8'd167]=16'h2174;
        words[8'd168]=16'h2269;
        words[8'd169]=16'h236f;
        words[8'd170]=16'h246e;
        words[8'd171]=16'h2665;
        words[8'd172]=16'h276e;
        words[8'd173]=16'h2874;
        words[8'd174]=16'h292d;
        words[8'd175]=16'h2a6c;
        words[8'd176]=16'h3074;
        words[8'd177]=16'h2b65;
        words[8'd178]=16'h2c6e;
        words[8'd179]=16'h2d67;
        words[8'd180]=16'h2e74;
        words[8'd181]=16'h2f68;
        words[8'd182]=16'h3179;
        words[8'd183]=16'h3270;
        words[8'd184]=16'h3365;
        words[8'd185]=16'h3572;
        words[8'd186]=16'h3670;
        words[8'd187]=16'h3763;
        words[8'd188]=16'h382d;
        words[8'd189]=16'h3965;
        words[8'd190]=16'h4174;
        words[8'd191]=16'h3a6e;
        words[8'd192]=16'h3b63;
        words[8'd193]=16'h3c6f;
        words[8'd194]=16'h3d64;
        words[8'd195]=16'h3e69;
        words[8'd196]=16'h3f6e;
        words[8'd197]=16'h4067;
        words[8'd198]=16'h4269;
        words[8'd199]=16'h436d;
        words[8'd200]=16'h4465;
        words[8'd201]=16'h456f;
        words[8'd202]=16'h4675;
        words[8'd203]=16'h4774;
        words[8'd204]=16'h496f;
        words[8'd205]=16'h4a73;
        words[8'd206]=16'h4b74;
        words[8'd207]=16'h4d65;
        words[8'd208]=16'h4e65;
        words[8'd209]=16'h4f70;
        words[8'd210]=16'h502d;
        words[8'd211]=16'h5161;
        words[8'd212]=16'h526c;
        words[8'd213]=16'h5369;
        words[8'd214]=16'h5476;
        words[8'd215]=16'h5565;
        words[8'd216]=16'h5772;
        words[8'd217]=16'h586f;
        words[8'd218]=16'h5978;
        words[8'd219]=16'h5a79;
        words[8'd220]=16'h5b2d;
        words[8'd221]=16'h5c63;
        words[8'd222]=16'h5d6f;
        words[8'd223]=16'h5e6e;
        words[8'd224]=16'h5f6e;
        words[8'd225]=16'h6065;
        words[8'd226]=16'h6163;
        words[8'd227]=16'h6274;
        words[8'd228]=16'h6369;
        words[8'd229]=16'h646f;
        words[8'd230]=16'h656e;
        words[8'd231]=16'h6765;
        words[8'd232]=16'h6872;
        words[8'd233]=16'h6961;
        words[8'd234]=16'h6a6e;
        words[8'd235]=16'h6b73;
        words[8'd236]=16'h6c66;
        words[8'd237]=16'h6d65;
        words[8'd238]=16'h6e72;
        words[8'd239]=16'h6f2d;
        words[8'd240]=16'h7065;
        words[8'd241]=16'h716e;
        words[8'd242]=16'h7263;
        words[8'd243]=16'h736f;
        words[8'd244]=16'h7464;
        words[8'd245]=16'h7569;
        words[8'd246]=16'h766e;
        words[8'd247]=16'h7767;
        words[8'd248]=16'h7970;
        words[8'd249]=16'h7a67;
        words[8'd250]=16'h7b72;
        words[8'd251]=16'h7c61;
        words[8'd252]=16'h7d64;
        words[8'd253]=16'h7e65;
        // END_NAME_ROM
    end
    always @(posedge clk)if(rom_en)rom_data<=words[rom_address];
    assign start_ready=!rst&&!cancel&&state==IDLE;
    assign s_ready=!rst&&!cancel&&state==RUN;
    assign result_valid=!rst&&!cancel&&state==RESULT;
    assign idle=!rst&&state==IDLE;
    task miss;
        begin known<=0;result_code<=0;state<=held_last?RESULT:RUN;end
    endtask
    always @(posedge clk)begin
        if(rst||cancel)begin
            state<=IDLE;known<=0;last_pending<=0;held_last<=0;octet<=0;node<=0;
            first_edge<=0;low<=0;high<=0;probe<=0;edge_count<=0;terminal<=0;result_code<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin known<=1;node<=0;last_pending<=0;result_code<=0;state<=NODE_REQ;end
            NODE_REQ:state<=NODE_WAIT;
            NODE_WAIT:begin
                first_edge<=rom_data[6:0];edge_count<=rom_data[10:7];terminal<=rom_data[14:11];
                if(last_pending)begin result_code<=rom_data[14:11];state<=RESULT;end else state<=RUN;
            end
            RUN:if(s_valid&&s_ready)begin
                if(!s_keep)begin if(s_last)begin result_code<=known?terminal:4'd0;state<=RESULT;end end
                else if(!known)begin if(s_last)begin result_code<=0;state<=RESULT;end end
                else begin
                    octet<=s_data;held_last<=s_last;low<=first_edge;high<=first_edge+edge_count;state<=PICK;
                end
            end
            PICK:if(low>=high)miss;else begin probe<=middle_sum[7:1];state<=EDGE_REQ;end
            EDGE_REQ:state<=EDGE_WAIT;
            EDGE_WAIT:if(rom_data[7:0]==octet)begin node<=rom_data[14:8];last_pending<=held_last;state<=NODE_REQ;end
                else begin if(octet<rom_data[7:0])high<=probe;else low<=probe+1'b1;state<=PICK;end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
