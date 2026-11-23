`timescale 1ns/1ps
`default_nettype none
// Generated fixed RFC7541 Appendix A protocol data; not a model vocabulary.
// Byte-pool SHA256: 4c950f0e5daad1630b91bea51ef4ccccbb6ccca3c06e8c3b9f6db64bbf5b1ea5
module hpack_static_table #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire [6:0] req_index,input wire [USER_WIDTH-1:0] req_user,
    output reg rsp_valid,input wire rsp_ready,output reg rsp_invalid,
    output reg [9:0] rsp_name_offset,rsp_value_offset,output reg [4:0] rsp_name_bytes,rsp_value_bytes,
    output reg [USER_WIDTH-1:0] rsp_user,
    input wire read_valid,output wire read_ready,input wire [9:0] read_offset,
    output reg byte_valid,input wire byte_ready,output wire [7:0] byte_data,output reg byte_invalid
);
    localparam integer TEXT_BYTES=623;
    (* rom_style="block" *) reg [7:0] bytes_rom[0:1023];
    reg [7:0] read_data;
    integer i;
    initial begin
        for(i=0;i<1024;i=i+1)bytes_rom[i]=0;
        bytes_rom[0]=8'h3a;
        bytes_rom[1]=8'h61;
        bytes_rom[2]=8'h75;
        bytes_rom[3]=8'h74;
        bytes_rom[4]=8'h68;
        bytes_rom[5]=8'h6f;
        bytes_rom[6]=8'h72;
        bytes_rom[7]=8'h69;
        bytes_rom[8]=8'h74;
        bytes_rom[9]=8'h79;
        bytes_rom[10]=8'h3a;
        bytes_rom[11]=8'h6d;
        bytes_rom[12]=8'h65;
        bytes_rom[13]=8'h74;
        bytes_rom[14]=8'h68;
        bytes_rom[15]=8'h6f;
        bytes_rom[16]=8'h64;
        bytes_rom[17]=8'h47;
        bytes_rom[18]=8'h45;
        bytes_rom[19]=8'h54;
        bytes_rom[20]=8'h50;
        bytes_rom[21]=8'h4f;
        bytes_rom[22]=8'h53;
        bytes_rom[23]=8'h54;
        bytes_rom[24]=8'h3a;
        bytes_rom[25]=8'h70;
        bytes_rom[26]=8'h61;
        bytes_rom[27]=8'h74;
        bytes_rom[28]=8'h68;
        bytes_rom[29]=8'h2f;
        bytes_rom[30]=8'h2f;
        bytes_rom[31]=8'h69;
        bytes_rom[32]=8'h6e;
        bytes_rom[33]=8'h64;
        bytes_rom[34]=8'h65;
        bytes_rom[35]=8'h78;
        bytes_rom[36]=8'h2e;
        bytes_rom[37]=8'h68;
        bytes_rom[38]=8'h74;
        bytes_rom[39]=8'h6d;
        bytes_rom[40]=8'h6c;
        bytes_rom[41]=8'h3a;
        bytes_rom[42]=8'h73;
        bytes_rom[43]=8'h63;
        bytes_rom[44]=8'h68;
        bytes_rom[45]=8'h65;
        bytes_rom[46]=8'h6d;
        bytes_rom[47]=8'h65;
        bytes_rom[48]=8'h68;
        bytes_rom[49]=8'h74;
        bytes_rom[50]=8'h74;
        bytes_rom[51]=8'h70;
        bytes_rom[52]=8'h68;
        bytes_rom[53]=8'h74;
        bytes_rom[54]=8'h74;
        bytes_rom[55]=8'h70;
        bytes_rom[56]=8'h73;
        bytes_rom[57]=8'h3a;
        bytes_rom[58]=8'h73;
        bytes_rom[59]=8'h74;
        bytes_rom[60]=8'h61;
        bytes_rom[61]=8'h74;
        bytes_rom[62]=8'h75;
        bytes_rom[63]=8'h73;
        bytes_rom[64]=8'h32;
        bytes_rom[65]=8'h30;
        bytes_rom[66]=8'h30;
        bytes_rom[67]=8'h32;
        bytes_rom[68]=8'h30;
        bytes_rom[69]=8'h34;
        bytes_rom[70]=8'h32;
        bytes_rom[71]=8'h30;
        bytes_rom[72]=8'h36;
        bytes_rom[73]=8'h33;
        bytes_rom[74]=8'h30;
        bytes_rom[75]=8'h34;
        bytes_rom[76]=8'h34;
        bytes_rom[77]=8'h30;
        bytes_rom[78]=8'h30;
        bytes_rom[79]=8'h34;
        bytes_rom[80]=8'h30;
        bytes_rom[81]=8'h34;
        bytes_rom[82]=8'h35;
        bytes_rom[83]=8'h30;
        bytes_rom[84]=8'h30;
        bytes_rom[85]=8'h61;
        bytes_rom[86]=8'h63;
        bytes_rom[87]=8'h63;
        bytes_rom[88]=8'h65;
        bytes_rom[89]=8'h70;
        bytes_rom[90]=8'h74;
        bytes_rom[91]=8'h2d;
        bytes_rom[92]=8'h63;
        bytes_rom[93]=8'h68;
        bytes_rom[94]=8'h61;
        bytes_rom[95]=8'h72;
        bytes_rom[96]=8'h73;
        bytes_rom[97]=8'h65;
        bytes_rom[98]=8'h74;
        bytes_rom[99]=8'h61;
        bytes_rom[100]=8'h63;
        bytes_rom[101]=8'h63;
        bytes_rom[102]=8'h65;
        bytes_rom[103]=8'h70;
        bytes_rom[104]=8'h74;
        bytes_rom[105]=8'h2d;
        bytes_rom[106]=8'h65;
        bytes_rom[107]=8'h6e;
        bytes_rom[108]=8'h63;
        bytes_rom[109]=8'h6f;
        bytes_rom[110]=8'h64;
        bytes_rom[111]=8'h69;
        bytes_rom[112]=8'h6e;
        bytes_rom[113]=8'h67;
        bytes_rom[114]=8'h67;
        bytes_rom[115]=8'h7a;
        bytes_rom[116]=8'h69;
        bytes_rom[117]=8'h70;
        bytes_rom[118]=8'h2c;
        bytes_rom[119]=8'h20;
        bytes_rom[120]=8'h64;
        bytes_rom[121]=8'h65;
        bytes_rom[122]=8'h66;
        bytes_rom[123]=8'h6c;
        bytes_rom[124]=8'h61;
        bytes_rom[125]=8'h74;
        bytes_rom[126]=8'h65;
        bytes_rom[127]=8'h61;
        bytes_rom[128]=8'h63;
        bytes_rom[129]=8'h63;
        bytes_rom[130]=8'h65;
        bytes_rom[131]=8'h70;
        bytes_rom[132]=8'h74;
        bytes_rom[133]=8'h2d;
        bytes_rom[134]=8'h6c;
        bytes_rom[135]=8'h61;
        bytes_rom[136]=8'h6e;
        bytes_rom[137]=8'h67;
        bytes_rom[138]=8'h75;
        bytes_rom[139]=8'h61;
        bytes_rom[140]=8'h67;
        bytes_rom[141]=8'h65;
        bytes_rom[142]=8'h61;
        bytes_rom[143]=8'h63;
        bytes_rom[144]=8'h63;
        bytes_rom[145]=8'h65;
        bytes_rom[146]=8'h70;
        bytes_rom[147]=8'h74;
        bytes_rom[148]=8'h2d;
        bytes_rom[149]=8'h72;
        bytes_rom[150]=8'h61;
        bytes_rom[151]=8'h6e;
        bytes_rom[152]=8'h67;
        bytes_rom[153]=8'h65;
        bytes_rom[154]=8'h73;
        bytes_rom[155]=8'h61;
        bytes_rom[156]=8'h63;
        bytes_rom[157]=8'h63;
        bytes_rom[158]=8'h65;
        bytes_rom[159]=8'h70;
        bytes_rom[160]=8'h74;
        bytes_rom[161]=8'h61;
        bytes_rom[162]=8'h63;
        bytes_rom[163]=8'h63;
        bytes_rom[164]=8'h65;
        bytes_rom[165]=8'h73;
        bytes_rom[166]=8'h73;
        bytes_rom[167]=8'h2d;
        bytes_rom[168]=8'h63;
        bytes_rom[169]=8'h6f;
        bytes_rom[170]=8'h6e;
        bytes_rom[171]=8'h74;
        bytes_rom[172]=8'h72;
        bytes_rom[173]=8'h6f;
        bytes_rom[174]=8'h6c;
        bytes_rom[175]=8'h2d;
        bytes_rom[176]=8'h61;
        bytes_rom[177]=8'h6c;
        bytes_rom[178]=8'h6c;
        bytes_rom[179]=8'h6f;
        bytes_rom[180]=8'h77;
        bytes_rom[181]=8'h2d;
        bytes_rom[182]=8'h6f;
        bytes_rom[183]=8'h72;
        bytes_rom[184]=8'h69;
        bytes_rom[185]=8'h67;
        bytes_rom[186]=8'h69;
        bytes_rom[187]=8'h6e;
        bytes_rom[188]=8'h61;
        bytes_rom[189]=8'h67;
        bytes_rom[190]=8'h65;
        bytes_rom[191]=8'h61;
        bytes_rom[192]=8'h6c;
        bytes_rom[193]=8'h6c;
        bytes_rom[194]=8'h6f;
        bytes_rom[195]=8'h77;
        bytes_rom[196]=8'h61;
        bytes_rom[197]=8'h75;
        bytes_rom[198]=8'h74;
        bytes_rom[199]=8'h68;
        bytes_rom[200]=8'h6f;
        bytes_rom[201]=8'h72;
        bytes_rom[202]=8'h69;
        bytes_rom[203]=8'h7a;
        bytes_rom[204]=8'h61;
        bytes_rom[205]=8'h74;
        bytes_rom[206]=8'h69;
        bytes_rom[207]=8'h6f;
        bytes_rom[208]=8'h6e;
        bytes_rom[209]=8'h63;
        bytes_rom[210]=8'h61;
        bytes_rom[211]=8'h63;
        bytes_rom[212]=8'h68;
        bytes_rom[213]=8'h65;
        bytes_rom[214]=8'h2d;
        bytes_rom[215]=8'h63;
        bytes_rom[216]=8'h6f;
        bytes_rom[217]=8'h6e;
        bytes_rom[218]=8'h74;
        bytes_rom[219]=8'h72;
        bytes_rom[220]=8'h6f;
        bytes_rom[221]=8'h6c;
        bytes_rom[222]=8'h63;
        bytes_rom[223]=8'h6f;
        bytes_rom[224]=8'h6e;
        bytes_rom[225]=8'h74;
        bytes_rom[226]=8'h65;
        bytes_rom[227]=8'h6e;
        bytes_rom[228]=8'h74;
        bytes_rom[229]=8'h2d;
        bytes_rom[230]=8'h64;
        bytes_rom[231]=8'h69;
        bytes_rom[232]=8'h73;
        bytes_rom[233]=8'h70;
        bytes_rom[234]=8'h6f;
        bytes_rom[235]=8'h73;
        bytes_rom[236]=8'h69;
        bytes_rom[237]=8'h74;
        bytes_rom[238]=8'h69;
        bytes_rom[239]=8'h6f;
        bytes_rom[240]=8'h6e;
        bytes_rom[241]=8'h63;
        bytes_rom[242]=8'h6f;
        bytes_rom[243]=8'h6e;
        bytes_rom[244]=8'h74;
        bytes_rom[245]=8'h65;
        bytes_rom[246]=8'h6e;
        bytes_rom[247]=8'h74;
        bytes_rom[248]=8'h2d;
        bytes_rom[249]=8'h65;
        bytes_rom[250]=8'h6e;
        bytes_rom[251]=8'h63;
        bytes_rom[252]=8'h6f;
        bytes_rom[253]=8'h64;
        bytes_rom[254]=8'h69;
        bytes_rom[255]=8'h6e;
        bytes_rom[256]=8'h67;
        bytes_rom[257]=8'h63;
        bytes_rom[258]=8'h6f;
        bytes_rom[259]=8'h6e;
        bytes_rom[260]=8'h74;
        bytes_rom[261]=8'h65;
        bytes_rom[262]=8'h6e;
        bytes_rom[263]=8'h74;
        bytes_rom[264]=8'h2d;
        bytes_rom[265]=8'h6c;
        bytes_rom[266]=8'h61;
        bytes_rom[267]=8'h6e;
        bytes_rom[268]=8'h67;
        bytes_rom[269]=8'h75;
        bytes_rom[270]=8'h61;
        bytes_rom[271]=8'h67;
        bytes_rom[272]=8'h65;
        bytes_rom[273]=8'h63;
        bytes_rom[274]=8'h6f;
        bytes_rom[275]=8'h6e;
        bytes_rom[276]=8'h74;
        bytes_rom[277]=8'h65;
        bytes_rom[278]=8'h6e;
        bytes_rom[279]=8'h74;
        bytes_rom[280]=8'h2d;
        bytes_rom[281]=8'h6c;
        bytes_rom[282]=8'h65;
        bytes_rom[283]=8'h6e;
        bytes_rom[284]=8'h67;
        bytes_rom[285]=8'h74;
        bytes_rom[286]=8'h68;
        bytes_rom[287]=8'h63;
        bytes_rom[288]=8'h6f;
        bytes_rom[289]=8'h6e;
        bytes_rom[290]=8'h74;
        bytes_rom[291]=8'h65;
        bytes_rom[292]=8'h6e;
        bytes_rom[293]=8'h74;
        bytes_rom[294]=8'h2d;
        bytes_rom[295]=8'h6c;
        bytes_rom[296]=8'h6f;
        bytes_rom[297]=8'h63;
        bytes_rom[298]=8'h61;
        bytes_rom[299]=8'h74;
        bytes_rom[300]=8'h69;
        bytes_rom[301]=8'h6f;
        bytes_rom[302]=8'h6e;
        bytes_rom[303]=8'h63;
        bytes_rom[304]=8'h6f;
        bytes_rom[305]=8'h6e;
        bytes_rom[306]=8'h74;
        bytes_rom[307]=8'h65;
        bytes_rom[308]=8'h6e;
        bytes_rom[309]=8'h74;
        bytes_rom[310]=8'h2d;
        bytes_rom[311]=8'h72;
        bytes_rom[312]=8'h61;
        bytes_rom[313]=8'h6e;
        bytes_rom[314]=8'h67;
        bytes_rom[315]=8'h65;
        bytes_rom[316]=8'h63;
        bytes_rom[317]=8'h6f;
        bytes_rom[318]=8'h6e;
        bytes_rom[319]=8'h74;
        bytes_rom[320]=8'h65;
        bytes_rom[321]=8'h6e;
        bytes_rom[322]=8'h74;
        bytes_rom[323]=8'h2d;
        bytes_rom[324]=8'h74;
        bytes_rom[325]=8'h79;
        bytes_rom[326]=8'h70;
        bytes_rom[327]=8'h65;
        bytes_rom[328]=8'h63;
        bytes_rom[329]=8'h6f;
        bytes_rom[330]=8'h6f;
        bytes_rom[331]=8'h6b;
        bytes_rom[332]=8'h69;
        bytes_rom[333]=8'h65;
        bytes_rom[334]=8'h64;
        bytes_rom[335]=8'h61;
        bytes_rom[336]=8'h74;
        bytes_rom[337]=8'h65;
        bytes_rom[338]=8'h65;
        bytes_rom[339]=8'h74;
        bytes_rom[340]=8'h61;
        bytes_rom[341]=8'h67;
        bytes_rom[342]=8'h65;
        bytes_rom[343]=8'h78;
        bytes_rom[344]=8'h70;
        bytes_rom[345]=8'h65;
        bytes_rom[346]=8'h63;
        bytes_rom[347]=8'h74;
        bytes_rom[348]=8'h65;
        bytes_rom[349]=8'h78;
        bytes_rom[350]=8'h70;
        bytes_rom[351]=8'h69;
        bytes_rom[352]=8'h72;
        bytes_rom[353]=8'h65;
        bytes_rom[354]=8'h73;
        bytes_rom[355]=8'h66;
        bytes_rom[356]=8'h72;
        bytes_rom[357]=8'h6f;
        bytes_rom[358]=8'h6d;
        bytes_rom[359]=8'h68;
        bytes_rom[360]=8'h6f;
        bytes_rom[361]=8'h73;
        bytes_rom[362]=8'h74;
        bytes_rom[363]=8'h69;
        bytes_rom[364]=8'h66;
        bytes_rom[365]=8'h2d;
        bytes_rom[366]=8'h6d;
        bytes_rom[367]=8'h61;
        bytes_rom[368]=8'h74;
        bytes_rom[369]=8'h63;
        bytes_rom[370]=8'h68;
        bytes_rom[371]=8'h69;
        bytes_rom[372]=8'h66;
        bytes_rom[373]=8'h2d;
        bytes_rom[374]=8'h6d;
        bytes_rom[375]=8'h6f;
        bytes_rom[376]=8'h64;
        bytes_rom[377]=8'h69;
        bytes_rom[378]=8'h66;
        bytes_rom[379]=8'h69;
        bytes_rom[380]=8'h65;
        bytes_rom[381]=8'h64;
        bytes_rom[382]=8'h2d;
        bytes_rom[383]=8'h73;
        bytes_rom[384]=8'h69;
        bytes_rom[385]=8'h6e;
        bytes_rom[386]=8'h63;
        bytes_rom[387]=8'h65;
        bytes_rom[388]=8'h69;
        bytes_rom[389]=8'h66;
        bytes_rom[390]=8'h2d;
        bytes_rom[391]=8'h6e;
        bytes_rom[392]=8'h6f;
        bytes_rom[393]=8'h6e;
        bytes_rom[394]=8'h65;
        bytes_rom[395]=8'h2d;
        bytes_rom[396]=8'h6d;
        bytes_rom[397]=8'h61;
        bytes_rom[398]=8'h74;
        bytes_rom[399]=8'h63;
        bytes_rom[400]=8'h68;
        bytes_rom[401]=8'h69;
        bytes_rom[402]=8'h66;
        bytes_rom[403]=8'h2d;
        bytes_rom[404]=8'h72;
        bytes_rom[405]=8'h61;
        bytes_rom[406]=8'h6e;
        bytes_rom[407]=8'h67;
        bytes_rom[408]=8'h65;
        bytes_rom[409]=8'h69;
        bytes_rom[410]=8'h66;
        bytes_rom[411]=8'h2d;
        bytes_rom[412]=8'h75;
        bytes_rom[413]=8'h6e;
        bytes_rom[414]=8'h6d;
        bytes_rom[415]=8'h6f;
        bytes_rom[416]=8'h64;
        bytes_rom[417]=8'h69;
        bytes_rom[418]=8'h66;
        bytes_rom[419]=8'h69;
        bytes_rom[420]=8'h65;
        bytes_rom[421]=8'h64;
        bytes_rom[422]=8'h2d;
        bytes_rom[423]=8'h73;
        bytes_rom[424]=8'h69;
        bytes_rom[425]=8'h6e;
        bytes_rom[426]=8'h63;
        bytes_rom[427]=8'h65;
        bytes_rom[428]=8'h6c;
        bytes_rom[429]=8'h61;
        bytes_rom[430]=8'h73;
        bytes_rom[431]=8'h74;
        bytes_rom[432]=8'h2d;
        bytes_rom[433]=8'h6d;
        bytes_rom[434]=8'h6f;
        bytes_rom[435]=8'h64;
        bytes_rom[436]=8'h69;
        bytes_rom[437]=8'h66;
        bytes_rom[438]=8'h69;
        bytes_rom[439]=8'h65;
        bytes_rom[440]=8'h64;
        bytes_rom[441]=8'h6c;
        bytes_rom[442]=8'h69;
        bytes_rom[443]=8'h6e;
        bytes_rom[444]=8'h6b;
        bytes_rom[445]=8'h6c;
        bytes_rom[446]=8'h6f;
        bytes_rom[447]=8'h63;
        bytes_rom[448]=8'h61;
        bytes_rom[449]=8'h74;
        bytes_rom[450]=8'h69;
        bytes_rom[451]=8'h6f;
        bytes_rom[452]=8'h6e;
        bytes_rom[453]=8'h6d;
        bytes_rom[454]=8'h61;
        bytes_rom[455]=8'h78;
        bytes_rom[456]=8'h2d;
        bytes_rom[457]=8'h66;
        bytes_rom[458]=8'h6f;
        bytes_rom[459]=8'h72;
        bytes_rom[460]=8'h77;
        bytes_rom[461]=8'h61;
        bytes_rom[462]=8'h72;
        bytes_rom[463]=8'h64;
        bytes_rom[464]=8'h73;
        bytes_rom[465]=8'h70;
        bytes_rom[466]=8'h72;
        bytes_rom[467]=8'h6f;
        bytes_rom[468]=8'h78;
        bytes_rom[469]=8'h79;
        bytes_rom[470]=8'h2d;
        bytes_rom[471]=8'h61;
        bytes_rom[472]=8'h75;
        bytes_rom[473]=8'h74;
        bytes_rom[474]=8'h68;
        bytes_rom[475]=8'h65;
        bytes_rom[476]=8'h6e;
        bytes_rom[477]=8'h74;
        bytes_rom[478]=8'h69;
        bytes_rom[479]=8'h63;
        bytes_rom[480]=8'h61;
        bytes_rom[481]=8'h74;
        bytes_rom[482]=8'h65;
        bytes_rom[483]=8'h70;
        bytes_rom[484]=8'h72;
        bytes_rom[485]=8'h6f;
        bytes_rom[486]=8'h78;
        bytes_rom[487]=8'h79;
        bytes_rom[488]=8'h2d;
        bytes_rom[489]=8'h61;
        bytes_rom[490]=8'h75;
        bytes_rom[491]=8'h74;
        bytes_rom[492]=8'h68;
        bytes_rom[493]=8'h6f;
        bytes_rom[494]=8'h72;
        bytes_rom[495]=8'h69;
        bytes_rom[496]=8'h7a;
        bytes_rom[497]=8'h61;
        bytes_rom[498]=8'h74;
        bytes_rom[499]=8'h69;
        bytes_rom[500]=8'h6f;
        bytes_rom[501]=8'h6e;
        bytes_rom[502]=8'h72;
        bytes_rom[503]=8'h61;
        bytes_rom[504]=8'h6e;
        bytes_rom[505]=8'h67;
        bytes_rom[506]=8'h65;
        bytes_rom[507]=8'h72;
        bytes_rom[508]=8'h65;
        bytes_rom[509]=8'h66;
        bytes_rom[510]=8'h65;
        bytes_rom[511]=8'h72;
        bytes_rom[512]=8'h65;
        bytes_rom[513]=8'h72;
        bytes_rom[514]=8'h72;
        bytes_rom[515]=8'h65;
        bytes_rom[516]=8'h66;
        bytes_rom[517]=8'h72;
        bytes_rom[518]=8'h65;
        bytes_rom[519]=8'h73;
        bytes_rom[520]=8'h68;
        bytes_rom[521]=8'h72;
        bytes_rom[522]=8'h65;
        bytes_rom[523]=8'h74;
        bytes_rom[524]=8'h72;
        bytes_rom[525]=8'h79;
        bytes_rom[526]=8'h2d;
        bytes_rom[527]=8'h61;
        bytes_rom[528]=8'h66;
        bytes_rom[529]=8'h74;
        bytes_rom[530]=8'h65;
        bytes_rom[531]=8'h72;
        bytes_rom[532]=8'h73;
        bytes_rom[533]=8'h65;
        bytes_rom[534]=8'h72;
        bytes_rom[535]=8'h76;
        bytes_rom[536]=8'h65;
        bytes_rom[537]=8'h72;
        bytes_rom[538]=8'h73;
        bytes_rom[539]=8'h65;
        bytes_rom[540]=8'h74;
        bytes_rom[541]=8'h2d;
        bytes_rom[542]=8'h63;
        bytes_rom[543]=8'h6f;
        bytes_rom[544]=8'h6f;
        bytes_rom[545]=8'h6b;
        bytes_rom[546]=8'h69;
        bytes_rom[547]=8'h65;
        bytes_rom[548]=8'h73;
        bytes_rom[549]=8'h74;
        bytes_rom[550]=8'h72;
        bytes_rom[551]=8'h69;
        bytes_rom[552]=8'h63;
        bytes_rom[553]=8'h74;
        bytes_rom[554]=8'h2d;
        bytes_rom[555]=8'h74;
        bytes_rom[556]=8'h72;
        bytes_rom[557]=8'h61;
        bytes_rom[558]=8'h6e;
        bytes_rom[559]=8'h73;
        bytes_rom[560]=8'h70;
        bytes_rom[561]=8'h6f;
        bytes_rom[562]=8'h72;
        bytes_rom[563]=8'h74;
        bytes_rom[564]=8'h2d;
        bytes_rom[565]=8'h73;
        bytes_rom[566]=8'h65;
        bytes_rom[567]=8'h63;
        bytes_rom[568]=8'h75;
        bytes_rom[569]=8'h72;
        bytes_rom[570]=8'h69;
        bytes_rom[571]=8'h74;
        bytes_rom[572]=8'h79;
        bytes_rom[573]=8'h74;
        bytes_rom[574]=8'h72;
        bytes_rom[575]=8'h61;
        bytes_rom[576]=8'h6e;
        bytes_rom[577]=8'h73;
        bytes_rom[578]=8'h66;
        bytes_rom[579]=8'h65;
        bytes_rom[580]=8'h72;
        bytes_rom[581]=8'h2d;
        bytes_rom[582]=8'h65;
        bytes_rom[583]=8'h6e;
        bytes_rom[584]=8'h63;
        bytes_rom[585]=8'h6f;
        bytes_rom[586]=8'h64;
        bytes_rom[587]=8'h69;
        bytes_rom[588]=8'h6e;
        bytes_rom[589]=8'h67;
        bytes_rom[590]=8'h75;
        bytes_rom[591]=8'h73;
        bytes_rom[592]=8'h65;
        bytes_rom[593]=8'h72;
        bytes_rom[594]=8'h2d;
        bytes_rom[595]=8'h61;
        bytes_rom[596]=8'h67;
        bytes_rom[597]=8'h65;
        bytes_rom[598]=8'h6e;
        bytes_rom[599]=8'h74;
        bytes_rom[600]=8'h76;
        bytes_rom[601]=8'h61;
        bytes_rom[602]=8'h72;
        bytes_rom[603]=8'h79;
        bytes_rom[604]=8'h76;
        bytes_rom[605]=8'h69;
        bytes_rom[606]=8'h61;
        bytes_rom[607]=8'h77;
        bytes_rom[608]=8'h77;
        bytes_rom[609]=8'h77;
        bytes_rom[610]=8'h2d;
        bytes_rom[611]=8'h61;
        bytes_rom[612]=8'h75;
        bytes_rom[613]=8'h74;
        bytes_rom[614]=8'h68;
        bytes_rom[615]=8'h65;
        bytes_rom[616]=8'h6e;
        bytes_rom[617]=8'h74;
        bytes_rom[618]=8'h69;
        bytes_rom[619]=8'h63;
        bytes_rom[620]=8'h61;
        bytes_rom[621]=8'h74;
        bytes_rom[622]=8'h65;
    end
    assign req_ready=!rst&&(!rsp_valid||rsp_ready);
    assign read_ready=!rst&&(!byte_valid||byte_ready);
    assign byte_data=byte_invalid?8'd0:read_data;
    // ROM storage/data have no reset. Only the valid/error pipeline resets.
    always @(posedge clk)if(read_ready&&read_valid)read_data<=bytes_rom[read_offset];
    always @(posedge clk)begin
        if(rst)begin
            rsp_valid<=0;rsp_invalid<=0;rsp_name_offset<=0;rsp_value_offset<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;rsp_user<=0;
            byte_valid<=0;byte_invalid<=0;
        end else begin
            if(read_ready)begin byte_valid<=read_valid;if(read_valid)byte_invalid<=read_offset>=TEXT_BYTES;end
            if(req_ready)begin
                rsp_valid<=req_valid;
                if(req_valid)begin
                    rsp_user<=req_user;rsp_invalid<=req_index==0||req_index>61;
                    case(req_index)
                7'd1:begin rsp_name_offset<=10'd0;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd10;rsp_value_bytes<=5'd0;end
                7'd2:begin rsp_name_offset<=10'd10;rsp_value_offset<=10'd17;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd3:begin rsp_name_offset<=10'd10;rsp_value_offset<=10'd20;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd4;end
                7'd4:begin rsp_name_offset<=10'd24;rsp_value_offset<=10'd29;rsp_name_bytes<=5'd5;rsp_value_bytes<=5'd1;end
                7'd5:begin rsp_name_offset<=10'd24;rsp_value_offset<=10'd30;rsp_name_bytes<=5'd5;rsp_value_bytes<=5'd11;end
                7'd6:begin rsp_name_offset<=10'd41;rsp_value_offset<=10'd48;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd4;end
                7'd7:begin rsp_name_offset<=10'd41;rsp_value_offset<=10'd52;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd5;end
                7'd8:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd64;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd9:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd67;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd10:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd70;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd11:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd73;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd12:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd76;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd13:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd79;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd14:begin rsp_name_offset<=10'd57;rsp_value_offset<=10'd82;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd3;end
                7'd15:begin rsp_name_offset<=10'd85;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd14;rsp_value_bytes<=5'd0;end
                7'd16:begin rsp_name_offset<=10'd99;rsp_value_offset<=10'd114;rsp_name_bytes<=5'd15;rsp_value_bytes<=5'd13;end
                7'd17:begin rsp_name_offset<=10'd127;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd15;rsp_value_bytes<=5'd0;end
                7'd18:begin rsp_name_offset<=10'd142;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd19:begin rsp_name_offset<=10'd155;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd6;rsp_value_bytes<=5'd0;end
                7'd20:begin rsp_name_offset<=10'd161;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd27;rsp_value_bytes<=5'd0;end
                7'd21:begin rsp_name_offset<=10'd188;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd3;rsp_value_bytes<=5'd0;end
                7'd22:begin rsp_name_offset<=10'd191;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd5;rsp_value_bytes<=5'd0;end
                7'd23:begin rsp_name_offset<=10'd196;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd24:begin rsp_name_offset<=10'd209;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd25:begin rsp_name_offset<=10'd222;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd19;rsp_value_bytes<=5'd0;end
                7'd26:begin rsp_name_offset<=10'd241;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd16;rsp_value_bytes<=5'd0;end
                7'd27:begin rsp_name_offset<=10'd257;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd16;rsp_value_bytes<=5'd0;end
                7'd28:begin rsp_name_offset<=10'd273;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd14;rsp_value_bytes<=5'd0;end
                7'd29:begin rsp_name_offset<=10'd287;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd16;rsp_value_bytes<=5'd0;end
                7'd30:begin rsp_name_offset<=10'd303;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd31:begin rsp_name_offset<=10'd316;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd12;rsp_value_bytes<=5'd0;end
                7'd32:begin rsp_name_offset<=10'd328;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd6;rsp_value_bytes<=5'd0;end
                7'd33:begin rsp_name_offset<=10'd334;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd34:begin rsp_name_offset<=10'd338;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd35:begin rsp_name_offset<=10'd342;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd6;rsp_value_bytes<=5'd0;end
                7'd36:begin rsp_name_offset<=10'd348;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd0;end
                7'd37:begin rsp_name_offset<=10'd355;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd38:begin rsp_name_offset<=10'd359;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd39:begin rsp_name_offset<=10'd363;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd8;rsp_value_bytes<=5'd0;end
                7'd40:begin rsp_name_offset<=10'd371;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd17;rsp_value_bytes<=5'd0;end
                7'd41:begin rsp_name_offset<=10'd388;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd42:begin rsp_name_offset<=10'd401;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd8;rsp_value_bytes<=5'd0;end
                7'd43:begin rsp_name_offset<=10'd409;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd19;rsp_value_bytes<=5'd0;end
                7'd44:begin rsp_name_offset<=10'd428;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd13;rsp_value_bytes<=5'd0;end
                7'd45:begin rsp_name_offset<=10'd441;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd46:begin rsp_name_offset<=10'd445;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd8;rsp_value_bytes<=5'd0;end
                7'd47:begin rsp_name_offset<=10'd453;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd12;rsp_value_bytes<=5'd0;end
                7'd48:begin rsp_name_offset<=10'd465;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd18;rsp_value_bytes<=5'd0;end
                7'd49:begin rsp_name_offset<=10'd483;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd19;rsp_value_bytes<=5'd0;end
                7'd50:begin rsp_name_offset<=10'd502;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd5;rsp_value_bytes<=5'd0;end
                7'd51:begin rsp_name_offset<=10'd507;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd0;end
                7'd52:begin rsp_name_offset<=10'd514;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd7;rsp_value_bytes<=5'd0;end
                7'd53:begin rsp_name_offset<=10'd521;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd11;rsp_value_bytes<=5'd0;end
                7'd54:begin rsp_name_offset<=10'd532;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd6;rsp_value_bytes<=5'd0;end
                7'd55:begin rsp_name_offset<=10'd538;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd10;rsp_value_bytes<=5'd0;end
                7'd56:begin rsp_name_offset<=10'd548;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd25;rsp_value_bytes<=5'd0;end
                7'd57:begin rsp_name_offset<=10'd573;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd17;rsp_value_bytes<=5'd0;end
                7'd58:begin rsp_name_offset<=10'd590;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd10;rsp_value_bytes<=5'd0;end
                7'd59:begin rsp_name_offset<=10'd600;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd4;rsp_value_bytes<=5'd0;end
                7'd60:begin rsp_name_offset<=10'd604;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd3;rsp_value_bytes<=5'd0;end
                7'd61:begin rsp_name_offset<=10'd607;rsp_value_offset<=10'd0;rsp_name_bytes<=5'd16;rsp_value_bytes<=5'd0;end
                        default:begin rsp_name_offset<=0;rsp_value_offset<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;end
                    endcase
                end
            end
        end
    end
endmodule
`default_nettype wire
