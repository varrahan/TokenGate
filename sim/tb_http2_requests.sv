`timescale 1ns/1ps
module tb_http2_requests;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic admit_packets=1;logic [22:0] cfg_context_base=23'h7c0003;logic [23:0] cfg_context_bytes=16384;
    logic command_valid=0;wire command_ready;logic [1:0] command_op=0;logic [15:0] command_user=0;
    logic command_server_role=1,command_allow_push=0;logic [23:0] command_max_frame_bytes=16384;
    logic [22:0] command_buffer_base=0,command_table_base=0,command_scratch_base=0;
    logic [23:0] command_buffer_bytes=65536,command_table_bytes=4096,command_scratch_bytes=65536;
    logic [31:0] command_hpack_maximum=4096,command_hpack_allowed=4096,command_header_list_limit=262144,command_required_maximum=4096;
    logic command_required_update=0;
    logic [511:0] s_axis_rx_tdata=0;logic [63:0] s_axis_rx_tkeep=0;logic s_axis_rx_tvalid=0,s_axis_rx_tlast=0;
    logic [15:0] s_axis_rx_tuser=0;wire s_axis_rx_tready;
    wire event_valid;logic event_ready=0;wire [3:0] event_kind;wire [7:0] event_data,event_type,event_flags;
    wire [31:0] event_arg0,event_arg1;wire [23:0] event_length;wire [30:0] event_stream;wire [15:0] event_user;
    wire header_valid,header_ready;wire [22:0] header_name_base,header_value_base;
    wire [31:0] header_name_bytes,header_value_bytes;wire [1:0] header_representation;wire [15:0] header_user;
    wire block_valid,block_ready;wire [30:0] block_stream,block_promised_stream;wire [7:0] block_type,block_flags;
    wire [31:0] block_headers,block_list_bytes;wire [15:0] block_user;
    wire block_start_valid,block_start_ready;wire [30:0] block_start_stream,block_start_promised_stream;
    wire [7:0] block_start_type,block_start_flags;wire [15:0] block_start_user;
    wire rsp_valid,rsp_is_command,idle,recovery_required;logic rsp_ready=0;wire [1:0] rsp_command_op;
    wire [7:0] rsp_status,rsp_detail,rsp_memory_status;wire [31:0] rsp_http2_error;wire [15:0] rsp_user;wire [22:0] recovery_address;
    wire [3:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;
    wire [91:0] mem_addr;wire [15:0] mem_bytes;wire [287:0] mem_data,mem_rsp_data;wire [31:0] mem_rsp_status;
    http2_hpack_ingress #(.BLOCK_START_PORT(1)) ingress(.*);

    reg signed [63:0] fields[0:18];integer raw[0:65535],names[0:1023],values[0:1023],kinds[0:1023],offsets[0:1023],expected[0:262143];
    integer total=0,received=0,leased=0,header_total=0,byte_total=0,reads=0,faults=0,counts[0:4];
    bit checker_active=0,finish_sent=0,injected=0;
    wire finish_valid=block_valid||(rsp_valid&&!rsp_is_command&&rsp_status!=0&&checker_active&&!finish_sent);
    wire finish_ready,field_valid;logic field_ready=0;
    wire [22:0] field_name_base,field_value_base;wire [31:0] field_name_bytes,field_value_bytes;
    wire [1:0] field_representation;wire [3:0] field_kind;wire [15:0] field_user;
    wire result_valid;logic result_ready=0;wire [2:0] result_status;wire [7:0] result_detail,result_memory_status;
    wire [9:0] result_http_status;wire [1:0] result_format;wire result_identity_encoding,result_content_length_valid,result_timeout_valid;
    wire [63:0] result_content_length;wire [26:0] result_timeout_value;wire [2:0] result_timeout_unit;
    wire [31:0] result_headers;wire [15:0] result_user;wire [30:0] result_stream;wire result_trailers,result_end_stream,checker_idle;
    wire check_mem_valid,check_mem_ready,check_mem_write,check_rsp_valid,check_rsp_ready;
    wire [22:0] check_mem_addr;wire [3:0] check_mem_bytes;wire [71:0] check_mem_data,check_rsp_data;wire [7:0] check_rsp_status;
    wire [22:0] checked_name_base=(fields[4]==2&&leased==0)?23'h7ffffe:header_name_base;
    wire [22:0] checked_value_base=(fields[4]==5&&leased==0)?23'h7ffffe:header_value_base;
    wire [31:0] checked_name_bytes=(fields[4]==6&&leased==0)?32'hffffffff:header_name_bytes;
    wire [15:0] checked_user=(fields[4]==3&&leased==0)?header_user^16'd1:header_user;
    assign block_ready=finish_ready;
    http2_request_headers validator(
        .clk(clk),.rst(rst),.start_valid(block_start_valid),.start_ready(block_start_ready),.start_user(block_start_user),
        .start_stream(block_start_stream),.start_trailers(fields[2]!=0),.start_end_stream(block_start_flags[0]),
        .cfg_scratch_base(block_start_valid?23'(24'h500000+block_start_user*65536):23'h7fffff),.cfg_scratch_bytes(block_start_valid&&fields[4]!=4?24'd65536:24'd0),
        .header_valid(header_valid),.header_ready(header_ready),.header_name_base(checked_name_base),.header_value_base(checked_value_base),
        .header_name_bytes(checked_name_bytes),.header_value_bytes(header_value_bytes),.header_representation(header_representation),.header_user(checked_user),
        .field_valid(field_valid),.field_ready(field_ready),.field_name_base(field_name_base),.field_value_base(field_value_base),
        .field_name_bytes(field_name_bytes),.field_value_bytes(field_value_bytes),.field_representation(field_representation),.field_kind(field_kind),.field_user(field_user),
        .finish_valid(finish_valid),.finish_ready(finish_ready),.finish_failed(!block_valid),
        .result_valid(result_valid),.result_ready(result_ready),.result_status(result_status),.result_detail(result_detail),.result_memory_status(result_memory_status),
        .result_http_status(result_http_status),.result_format(result_format),.result_identity_encoding(result_identity_encoding),
        .result_content_length_valid(result_content_length_valid),.result_content_length(result_content_length),.result_timeout_valid(result_timeout_valid),
        .result_timeout_value(result_timeout_value),.result_timeout_unit(result_timeout_unit),.result_headers(result_headers),.result_user(result_user),
        .result_stream(result_stream),.result_trailers(result_trailers),.result_end_stream(result_end_stream),
        .mem_valid(check_mem_valid),.mem_ready(check_mem_ready),.mem_write(check_mem_write),.mem_addr(check_mem_addr),.mem_bytes(check_mem_bytes),.mem_data(check_mem_data),
        .mem_rsp_valid(check_rsp_valid),.mem_rsp_ready(check_rsp_ready),.mem_rsp_data(check_rsp_data),.mem_rsp_status(check_rsp_status),.idle(checker_idle));
    wire [5:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [137:0] cmd_addr;wire [23:0] cmd_bytes;
    wire [431:0] cmd_data,response_data;wire [47:0] response_status;
    logic helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;
    assign cmd_valid={helper_valid,check_mem_valid,mem_valid};assign cmd_write={1'b0,check_mem_write,mem_write};
    assign cmd_addr={helper_addr,check_mem_addr,mem_addr};assign cmd_bytes={helper_bytes,check_mem_bytes,mem_bytes};assign cmd_data={72'd0,check_mem_data,mem_data};
    assign mem_ready=cmd_ready[3:0];assign mem_rsp_valid=response_valid[3:0];assign mem_rsp_data=response_data[287:0];assign mem_rsp_status=response_status[31:0];
    assign check_mem_ready=cmd_ready[4];assign check_rsp_valid=response_valid[4];assign check_rsp_data=response_data[288+:72];
    assign check_rsp_status=fields[4]==1&&!injected&&reads==fields[5]?8'h52:response_status[32+:8];
    assign response_ready={helper_rsp_ready,check_rsp_ready,mem_rsp_ready};
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(6)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    bit field_stalled=0,result_stalled=0;bit [5:0] mem_stalled=0;
    logic [131:0] held_field;logic [209:0] held_result;logic [99:0] held_mem[0:5];
    wire [131:0] field_bundle={field_user,field_kind,field_representation,field_name_base,field_value_base,field_name_bytes,field_value_bytes};
    wire [209:0] result_bundle={result_status,result_detail,result_memory_status,result_http_status,result_format,result_identity_encoding,result_content_length_valid,result_content_length,
        result_timeout_valid,result_timeout_value,result_timeout_unit,result_headers,result_user,result_stream,result_trailers,result_end_stream};
    always @(negedge clk)event_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(block_start_valid&&block_start_ready)begin
            if(checker_active||block_start_type!=1||block_start_user!=fields[0]||block_start_stream!=fields[1])$fatal(1,"Bad request BEGIN");
            checker_active<=1;finish_sent<=0;
        end
        if(finish_valid&&finish_ready)begin if(finish_sent)$fatal(1,"Duplicate header finish");finish_sent<=1;end
        if(result_valid&&result_ready)checker_active<=0;
        if(header_valid&&header_ready)leased++;
        if(check_rsp_valid&&check_rsp_ready)begin
            if(check_rsp_status==8'h52)injected<=1;
            reads<=reads+1;
        end
        if(field_stalled&&(!field_valid||field_bundle!==held_field))$fatal(1,"Request field lease unstable");
        field_stalled=field_valid&&!field_ready;held_field=field_bundle;
        if(result_stalled&&(!result_valid||result_bundle!==held_result))$fatal(1,"Request result unstable");
        result_stalled=result_valid&&!result_ready;held_result=result_bundle;
        if((^{header_ready,field_valid,result_valid,block_start_ready,finish_ready})===1'bx)$fatal(1,"Unknown request handshake");
        if(field_valid&&((^field_bundle)===1'bx)||result_valid&&((^result_bundle)===1'bx))$fatal(1,"Unknown request metadata");
        if(field_valid&&(!header_valid||header_ready&&!field_ready||check_mem_valid||!checker_active))$fatal(1,"Scratch lease ownership violation");
        for(integer c=0;c<6;c++)begin
            if(mem_stalled[c]&&(!cmd_valid[c]||held_mem[c]!=={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]}))$fatal(1,"Request memory command unstable");
            mem_stalled[c]=cmd_valid[c]&&!cmd_ready[c];held_mem[c]={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]};
        end
        if(check_mem_valid&&(check_mem_write||check_mem_bytes==0||check_mem_bytes>9||check_mem_addr<24'h500000+fields[0]*65536||check_mem_addr+check_mem_bytes>24'h510000+fields[0]*65536))$fatal(1,"Checker escaped scratch");
    end
    task helper(input integer address,input integer size,output reg [71:0] result);
        begin
            @(negedge clk);helper_valid=1;helper_addr=23'(address);helper_bytes=4'(size);
            do @(posedge clk);while(!cmd_ready[5]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[5]);if(response_status[40+:8]!=0)$fatal(1,"Consumer read failed");result=response_data[360+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    task receive_fields;
        integer n,base,offset,chunk;reg [71:0] data;
        begin
            while(!result_valid)begin
                @(negedge clk);
                if(field_valid)begin
                    if(received>=fields[16]||field_name_bytes!=names[received]||field_value_bytes!=values[received]||field_kind!=kinds[received]||field_user!=fields[0])$fatal(1,"Request descriptor mismatch packet=%0d field=%0d kind=%0d/%0d",total,received,field_kind,kinds[received]);
                    for(integer part=0;part<2;part++)begin
                        n=part==0?field_name_bytes:field_value_bytes;base=part==0?field_name_base:field_value_base;offset=offsets[received]+(part==0?0:names[received]);
                        for(integer i=0;i<n;i+=9)begin
                            chunk=n-i;if(chunk>9)chunk=9;helper(base+i,chunk,data);
                            for(integer lane=0;lane<chunk;lane++)begin if(data[lane*8+:8]!==8'(expected[offset+i+lane]))$fatal(1,"Request byte mismatch");byte_total++;end
                        end
                    end
                    repeat($urandom_range(3,25))@(negedge clk);field_ready=1;@(posedge clk);@(negedge clk);field_ready=0;received++;header_total++;
                end
            end
        end
    endtask
    task acknowledge_packet;
        begin @(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;wait(idle&&fabric_idle);end
    endtask
    task open_connection(input integer ctx);
        begin
            @(negedge clk);command_user=16'(ctx);command_buffer_base=23'(24'h600000+ctx*65536);
            command_table_base=23'(24'h400000+ctx*4096);command_scratch_base=23'(24'h500000+ctx*65536);command_valid=1;
            do @(posedge clk);while(!command_ready);@(negedge clk);command_valid=0;
            wait(rsp_valid);if(!rsp_is_command||rsp_status!=0)$fatal(1,"Request connection OPEN failed");acknowledge_packet();
        end
    endtask
    initial begin:driver
        integer fd,rc,scanned,offset,position;reg [511:0] data;reg [63:0] keep;
        for(integer i=0;i<5;i++)counts[i]=0;
        repeat(5)@(negedge clk);rst=0;for(integer ctx=0;ctx<3;ctx++)open_connection(ctx);
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing request fixtures");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<19;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad request fixture");end
                for(integer i=0;i<fields[18];i++)begin rc=$fscanf(fd,"%h",raw[i]);if(rc!=1)$fatal(1,"Bad request wire");end
                offset=0;
                for(integer h=0;h<fields[17];h++)begin
                    rc=$fscanf(fd,"%d %d %d",names[h],values[h],kinds[h]);if(rc!=3)$fatal(1,"Bad request reference");offsets[h]=offset;
                    for(integer i=0;i<names[h]+values[h];i++)begin rc=$fscanf(fd,"%h",scanned);expected[offset]=scanned;offset++;if(rc!=1)$fatal(1,"Bad field byte");end
                end
                received=0;leased=0;reads=0;injected=0;
                fork
                    begin
                        position=0;
                        while(position<fields[18])begin
                            data=0;keep=0;
                            for(integer lane=0;lane<64;lane++)if(position<fields[18]&&$urandom_range(0,3)!=0)begin data[lane*8+:8]=8'(raw[position]);keep[lane]=1;position++;end
                            @(negedge clk);s_axis_rx_tdata=data;s_axis_rx_tkeep=keep;s_axis_rx_tlast=position==fields[18];s_axis_rx_tuser=16'(fields[0]);s_axis_rx_tvalid=1;
                            do @(posedge clk);while(!s_axis_rx_tready);@(negedge clk);s_axis_rx_tvalid=0;
                        end
                    end
                    receive_fields();
                join
                wait(result_valid);repeat(40)@(negedge clk);
                if(result_status!=fields[7]||result_user!=fields[0]||result_stream!=fields[1]||result_trailers!=fields[2]||result_end_stream!=fields[3]||result_headers!=fields[17]||received!=fields[16])
                    $fatal(1,"Request result packet=%0d status=%0d/%0d detail=%0d headers=%0d/%0d forwarded=%0d/%0d",total,result_status,fields[7],result_detail,result_headers,fields[17],received,fields[16]);
                if(result_status==0&&(result_format!=fields[9]||result_identity_encoding!=fields[10]||result_content_length_valid!=fields[11]||
                    result_content_length!=64'(fields[12])||result_timeout_valid!=fields[13]||result_timeout_value!=fields[14]||result_timeout_unit!=fields[15]))$fatal(1,"Request accepted-summary mismatch packet=%0d",total);
                if(result_status==2&&result_http_status!=fields[8])$fatal(1,"Wrong HTTP rejection packet=%0d http=%0d/%0d",total,result_http_status,fields[8]);
                if(fields[4]==1&&(!injected||result_memory_status!=8'h52))$fatal(1,"Request read fault missing");
                if(fields[4]>=2&&reads!=0)$fatal(1,"Invalid descriptor performed memory reads");
                if(fields[4])faults++;
                // A candidate can be observed before the enclosing packet
                // commits. Deliberately hold it until that packet's decision.
                wait(rsp_valid);
                if(rsp_is_command||rsp_user!=fields[0]||(rsp_status!=0)!=(fields[6]!=0)||recovery_required)$fatal(1,"Unexpected transport result packet=%0d status=%0d detail=%0d",total,rsp_status,rsp_detail);
                if(fields[6]&&rsp_http2_error!=9)$fatal(1,"Compression failure lost connection scope");
                @(negedge clk);result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;acknowledge_packet();wait(checker_idle);
                counts[result_status]++;total++;if(total%50==0)$display("PROGRESS: %0d raw request-field packets",total);
            end else if(!$feof(fd))$fatal(1,"Malformed request fixture");
        end
        $fclose(fd);
        if(total<300||header_total<2000||byte_total<50000||faults!=10||counts[0]<170||counts[1]<60||counts[2]<10||counts[3]!=10||counts[4]!=2)$fatal(1,"Insufficient request coverage total=%0d fields=%0d bytes=%0d statuses=%0d/%0d/%0d/%0d/%0d",total,header_total,byte_total,counts[0],counts[1],counts[2],counts[3],counts[4]);
        $display("PASS: raw HTTP/2 -> HPACK -> request fields: %0d packets/%0d exact leased fields/%0d exact bytes; status counts %0d/%0d/%0d/%0d/%0d, ten local fault/corruption cases, persistent connection dictionaries, tentative result/field stalls",total,header_total,byte_total,counts[0],counts[1],counts[2],counts[3],counts[4]);$finish;
    end
    initial begin #(64'd20000000000);$fatal(1,"Request timeout packet=%0d check=%0d HPACK=%0d",total,validator.state,ingress.dispatcher.state);end
endmodule
