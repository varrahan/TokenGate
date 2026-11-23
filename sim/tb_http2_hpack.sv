`timescale 1ns/1ps
module tb_http2_hpack;
    localparam [191:0] CLIENT_MAGIC=192'h505249202a20485454502f322e300d0a0d0a534d0d0a0d0a;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic admit_packets=1;logic [22:0] cfg_context_base=23'h7c0003;logic [23:0] cfg_context_bytes=16384;
    logic command_valid=0;wire command_ready;logic [1:0] command_op=0;logic [15:0] command_user=0;logic command_server_role=1,command_allow_push=0;logic [23:0] command_max_frame_bytes=16384;
    logic [22:0] command_buffer_base=0,command_table_base=0,command_scratch_base=0;logic [23:0] command_buffer_bytes=65536,command_table_bytes=4096,command_scratch_bytes=65536;
    logic [31:0] command_hpack_maximum=4096,command_hpack_allowed=4096,command_header_list_limit=262144,command_required_maximum=4096;logic command_required_update=0;
    logic [511:0] s_axis_rx_tdata=0;logic [63:0] s_axis_rx_tkeep=0;logic s_axis_rx_tvalid=0,s_axis_rx_tlast=0;logic [15:0] s_axis_rx_tuser=0;wire s_axis_rx_tready;
    wire event_valid;logic event_ready=0;wire [3:0] event_kind;wire [7:0] event_data,event_type,event_flags;wire [31:0] event_arg0,event_arg1;wire [23:0] event_length;wire [30:0] event_stream;wire [15:0] event_user;
    wire header_valid;logic header_ready=0;wire [22:0] header_name_base,header_value_base;wire [31:0] header_name_bytes,header_value_bytes;wire [1:0] header_representation;wire [15:0] header_user;
    wire block_valid;logic block_ready=0;wire [30:0] block_stream,block_promised_stream;wire [7:0] block_type,block_flags;wire [31:0] block_headers,block_list_bytes;wire [15:0] block_user;
    wire block_start_valid;logic block_start_ready=0;wire [30:0] block_start_stream,block_start_promised_stream;wire [7:0] block_start_type,block_start_flags;wire [15:0] block_start_user;
    wire rsp_valid,rsp_is_command,idle,recovery_required;logic rsp_ready=0;wire [1:0] rsp_command_op;wire [7:0] rsp_status,rsp_detail,rsp_memory_status;wire [31:0] rsp_http2_error;wire [15:0] rsp_user;wire [22:0] recovery_address;
    wire [3:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [91:0] mem_addr;wire [15:0] mem_bytes;wire [287:0] mem_data,mem_rsp_data;logic [31:0] mem_rsp_status;
    http2_hpack_ingress #(.BLOCK_START_PORT(1)) dut(.*);
    wire [4:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [114:0] cmd_addr;wire [19:0] cmd_bytes;wire [359:0] cmd_data,response_data;wire [39:0] response_status;
    logic helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;
    integer fault_target=-1,fault_client=0,response_index=0;bit injected=0;
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={1'b0,mem_write};assign cmd_addr={helper_addr,mem_addr};assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={72'd0,mem_data};
    assign mem_ready=cmd_ready[3:0];assign mem_rsp_valid=response_valid[3:0];assign response_ready={helper_rsp_ready,mem_rsp_ready};assign mem_rsp_data=response_data[287:0];
    always @*begin mem_rsp_status=response_status[31:0];if(!injected&&response_index==fault_target)mem_rsp_status[fault_client*8+:8]=8'h52;end
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(5)) fabric(
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
    integer fields[0:13],raw[0:65535],golden[0:65535][0:9],names[0:1023],values[0:1023],kinds[0:1023],offsets[0:1023],expected[0:262143],blocks[0:1023][0:5];
    integer received=0,received_headers=0,received_blocks=0,total=0,event_total=0,header_total=0,block_total=0,errors=0,controls=0,faults=0;
    reg [7:0] prior_record[0:159];
    bit event_stalled=0,header_stalled=0,block_stalled=0,result_stalled=0;bit [3:0] mem_stalled=0;
    logic [162:0] held_event;logic [127:0] held_header;logic [157:0] held_block;logic [74:0] held_result;logic [99:0] held_mem[0:3];
    wire [162:0] event_bundle={event_kind,event_data,event_arg0,event_arg1,event_length,event_type,event_flags,event_stream,event_user};
    wire [127:0] header_bundle={header_user,header_representation,header_name_base,header_value_base,header_name_bytes,header_value_bytes};
    wire [157:0] block_bundle={block_user,block_stream,block_promised_stream,block_type,block_flags,block_headers,block_list_bytes};
    wire [74:0] result_bundle={rsp_is_command,rsp_command_op,rsp_status,rsp_detail,rsp_memory_status,rsp_http2_error,rsp_user};
    integer start_total=0,start_stalls=0,start_cycle=0;bit begin_active=0,begin_stalled=0;logic [93:0] held_begin,active_begin;
    wire [93:0] begin_bundle={block_start_user,block_start_stream,block_start_promised_stream,block_start_type,block_start_flags};
    always @(negedge clk)begin event_ready=$urandom_range(0,3)!=0;block_ready=$urandom_range(0,3)!=0;start_cycle++;block_start_ready=start_cycle%17>=10;end
    always @(posedge clk)if(!rst)begin
        if(begin_stalled&&(!block_start_valid||held_begin!==begin_bundle))$fatal(1,"Header block BEGIN changed under admission backpressure");
        begin_stalled=block_start_valid&&!block_start_ready;held_begin=begin_bundle;if(begin_stalled)start_stalls++;
        if(block_start_valid&&((^begin_bundle)===1'bx))$fatal(1,"Unknown header block BEGIN metadata");
        if(block_start_valid&&block_start_ready)begin
            if(begin_active||block_start_user!=fields[0]||block_start_stream==0||(block_start_type!=1&&block_start_type!=5))$fatal(1,"Duplicate or malformed block BEGIN");
            begin_active=1;active_begin=begin_bundle;start_total++;
        end
        if(header_valid&&!begin_active)$fatal(1,"HPACK field escaped before admission BEGIN acknowledgement");
        if(event_stalled&&(!event_valid||held_event!==event_bundle))$fatal(1,"Header ingress semantic event unstable");event_stalled=event_valid&&!event_ready;held_event=event_bundle;
        if(header_stalled&&(!header_valid||held_header!==header_bundle))$fatal(1,"Decoded header lease unstable");header_stalled=header_valid&&!header_ready;held_header=header_bundle;
        if(block_stalled&&(!block_valid||held_block!==block_bundle))$fatal(1,"Block completion unstable");block_stalled=block_valid&&!block_ready;held_block=block_bundle;
        if(result_stalled&&(!rsp_valid||held_result!==result_bundle))$fatal(1,"Header ingress result unstable");result_stalled=rsp_valid&&!rsp_ready;held_result=result_bundle;
        if((^{event_valid,header_valid,block_valid,rsp_valid,s_axis_rx_tready,command_ready,recovery_required})===1'bx)$fatal(1,"Unknown ingress handshake");
        if(event_valid&&((^event_bundle)===1'bx)||header_valid&&((^header_bundle)===1'bx)||block_valid&&((^block_bundle)===1'bx)||rsp_valid&&((^result_bundle)===1'bx))$fatal(1,"Unknown ingress metadata");
        for(integer c=0;c<4;c++)begin
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"Header ingress memory command unstable");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&((^held_mem[c])===1'bx))$fatal(1,"Unknown HPACK ingress memory command");
        end
        if(mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
        if(event_valid&&event_ready)begin
            if(received>=fields[7]||event_kind!=golden[received][0]||event_data!=golden[received][1]||event_arg0!=golden[received][2]||event_arg1!=golden[received][3]||event_length!=golden[received][4]||event_type!=golden[received][5]||event_flags!=golden[received][6]||event_stream!=golden[received][7]||event_user!=fields[0])$fatal(1,"HPACK ingress passthrough mismatch packet=%0d event=%0d kind=%0d/%0d",total,received,event_kind,golden[received][0]);
            received++;event_total++;
        end
        if(block_valid&&block_ready)begin
            if(!begin_active||active_begin!=={block_user,block_stream,block_promised_stream,block_type,block_flags})$fatal(1,"Block completion lost BEGIN identity");
            begin_active=0;
            if(received_blocks>=fields[13]||block_stream!=blocks[received_blocks][0]||block_promised_stream!=blocks[received_blocks][1]||block_type!=blocks[received_blocks][2]||block_flags!=blocks[received_blocks][3]||block_headers!=blocks[received_blocks][4]||block_list_bytes!=blocks[received_blocks][5]||block_user!=fields[0])$fatal(1,"Decoded block mismatch packet=%0d block=%0d",total,received_blocks);
            received_blocks++;block_total++;
        end
    end
    task helper(input integer address,input integer size,output reg [71:0] result);
        begin
            @(negedge clk);helper_valid=1;helper_addr=23'(address);helper_bytes=4'(size);
            do @(posedge clk);while(!cmd_ready[4]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[4]);if(response_status[32+:8]!=0)$fatal(1,"Header lease read failed");result=response_data[288+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    task receive_headers;
        integer n,base,chunk,offset;reg [71:0] result;
        begin
            while(!rsp_valid)begin
                @(negedge clk);
                if(header_valid)begin
                    if(received_headers>=fields[12]||header_name_bytes!=names[received_headers]||header_value_bytes!=values[received_headers]||header_representation!=kinds[received_headers]||header_user!=fields[0])$fatal(1,"Header descriptor mismatch packet=%0d field=%0d",total,received_headers);
                    for(integer part=0;part<2;part++)begin
                        n=part==0?header_name_bytes:header_value_bytes;base=part==0?header_name_base:header_value_base;offset=offsets[received_headers]+(part==0?0:names[received_headers]);
                        if(n!=0&&(base<24'h500000+fields[0]*65536||base+n>24'h510000+fields[0]*65536))$fatal(1,"Header scratch bounds");
                        for(integer i=0;i<n;i+=8)begin
                            chunk=n-i;if(chunk>8)chunk=8;helper(base+i,chunk,result);
                            for(integer lane=0;lane<chunk;lane++)if(result[lane*8+:8]!==8'(expected[offset+i+lane]))$fatal(1,"Header bytes mismatch packet=%0d field=%0d byte=%0d",total,received_headers,i+lane);
                        end
                    end
                    repeat($urandom_range(1,8))@(negedge clk);header_ready=1;@(posedge clk);@(negedge clk);header_ready=0;received_headers++;header_total++;
                end
            end
        end
    endtask
    task acknowledge;
        begin repeat($urandom_range(2,10))@(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;wait(idle&&fabric_idle);begin_active=0;end
    endtask
    task control(input integer op,input integer context_number,input integer maximum,input bit role,input bit push,input integer status,input integer detail);
        begin
            @(negedge clk);command_op=2'(op);command_user=16'(context_number);command_max_frame_bytes=24'(maximum);command_server_role=role;command_allow_push=push;
            command_buffer_base=23'(24'h600000+context_number*65536);command_table_base=23'(24'h400000+context_number*4096);command_scratch_base=23'(24'h500000+context_number*65536);command_valid=1;
            do @(posedge clk);while(!command_ready);@(negedge clk);command_valid=0;command_user='1;command_buffer_base=0;command_table_base=0;command_scratch_base=0;command_max_frame_bytes=0;
            wait(rsp_valid);if(!rsp_is_command||rsp_status!=status||rsp_detail!=detail||rsp_user!=context_number)$fatal(1,"Header control mismatch op=%0d status=%0d/%0d detail=%0d/%0d",op,rsp_status,status,rsp_detail,detail);
            acknowledge;controls++;
        end
    endtask
    task beat(input [511:0] data,input [63:0] keep,input last,input integer context_number);
        begin
            repeat($urandom_range(0,3))@(negedge clk);s_axis_rx_tdata=data;s_axis_rx_tkeep=keep;s_axis_rx_tlast=last;s_axis_rx_tuser=16'(context_number);s_axis_rx_tvalid=1;
            do @(posedge clk);while(!s_axis_rx_tready);@(negedge clk);s_axis_rx_tvalid=0;
        end
    endtask
    task fault_setup(input integer client,input integer target);
        begin @(negedge clk);fault_client=client;fault_target=target;response_index=0;injected=0;end
    endtask
    function automatic [31:0] physical_word(input integer address);
        reg [31:0] value;
        begin for(integer i=0;i<4;i++)value[i*8+:8]=memory_model.memory[(address+i)>>3][((address+i)&7)*8+:8];physical_word=value;end
    endfunction
    initial begin:driver
        integer fd,rc,scanned,position,offset;reg [511:0] data;reg [63:0] keep;bit sent_last;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No raw HPACK ingress vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<14;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad HPACK ingress fixture");end
                for(integer i=0;i<fields[6];i++)begin rc=$fscanf(fd,"%h",raw[i]);if(rc!=1)$fatal(1,"Bad packet byte");end
                for(integer i=0;i<fields[7];i++)for(integer j=0;j<10;j++)begin rc=$fscanf(fd,"%d",scanned);golden[i][j]=scanned;if(rc!=1)$fatal(1,"Bad semantic golden");end
                offset=0;
                for(integer h=0;h<fields[12];h++)begin
                    rc=$fscanf(fd,"%d %d %d",names[h],values[h],kinds[h]);if(rc!=3)$fatal(1,"Bad header golden");offsets[h]=offset;
                    for(integer i=0;i<names[h]+values[h];i++)begin rc=$fscanf(fd,"%h",expected[offset]);if(rc!=1)$fatal(1,"Bad header byte");offset++;end
                end
                for(integer b=0;b<fields[13];b++)for(integer j=0;j<6;j++)begin rc=$fscanf(fd,"%d",scanned);blocks[b][j]=scanned;if(rc!=1)$fatal(1,"Bad block golden");end
                if(fields[1])control(0,fields[0],fields[4],fields[2]!=0,fields[3]!=0,0,0);
                received=0;received_headers=0;received_blocks=0;
                fork
                    begin
                        position=0;sent_last=0;
                        while(position<fields[6])begin
                            data=0;keep=0;
                            for(integer lane=0;lane<64;lane++)if(position<fields[6]&&$urandom_range(0,3)!=0)begin data[lane*8+:8]=8'(raw[position]);keep[lane]=1;position++;end
                            sent_last=position==fields[6];beat(data,keep,sent_last,fields[0]);
                        end
                        if(!sent_last)beat(0,0,1,fields[0]);
                    end
                    receive_headers();
                join
                wait(rsp_valid);
                if(rsp_is_command||rsp_status!=(fields[8]?4:0)||rsp_http2_error!=fields[9]||rsp_detail!=fields[10]||rsp_user!=fields[0]||received!=fields[7]||received_headers!=fields[12]||received_blocks!=fields[13])$fatal(1,"Raw HPACK ingress mismatch packet=%0d status=%0d error=%0d/%0d detail=%0d/%0d headers=%0d/%0d blocks=%0d/%0d",total,rsp_status,rsp_http2_error,fields[9],rsp_detail,fields[10],received_headers,fields[12],received_blocks,fields[13]);
                if(fields[8])errors++;acknowledge;total++;if(total%100==0)$display("PROGRESS: %0d raw HTTP/2 HPACK packets",total);
            end else if(!$feof(fd))$fatal(1,"Bad raw HPACK fixture");
        end
        $fclose(fd);fields[0]=10;fields[7]=0;fields[12]=0;fields[13]=0;received=0;received_headers=0;received_blocks=0;
        for(integer i=0;i<160;i++)prior_record[i]=memory_model.memory[(24'h7c0003+i)>>3][((24'h7c0003+i)&7)*8+:8];
        if(physical_word(24'h7c0063)==0)$fatal(1,"Dictionary preservation case had no live entries");
        command_hpack_maximum=123;command_hpack_allowed=512;command_required_maximum=512;command_required_update=1;
        command_buffer_bytes=32768;command_table_bytes=8192;command_scratch_bytes=32768;
        control(2,0,65537,0,1,0,0);
        for(integer i=8;i<160;i++)if(!(i>=92&&i<96||i>=108&&i<116)&&memory_model.memory[(24'h7c0003+i)>>3][((24'h7c0003+i)&7)*8+:8]!==prior_record[i])$fatal(1,"Masked UPDATE changed live progress/dictionary/allocation byte=%0d",i);
        if(physical_word(24'h7c005f)!=512||physical_word(24'h7c006f)!=512||physical_word(24'h7c0073)!=1)$fatal(1,"Masked HPACK limit update failed");
        // Exercise the persisted reduction through the wire decoder. The
        // peer updates its dynamic-table maximum to 512, then indexes :method.
        fields[0]=0;fields[7]=0;fields[12]=1;fields[13]=1;
        received=0;received_headers=0;received_blocks=0;
        names[0]=7;values[0]=3;kinds[0]=0;offsets[0]=0;
        expected[0]=":";expected[1]="m";expected[2]="e";expected[3]="t";expected[4]="h";
        expected[5]="o";expected[6]="d";expected[7]="G";expected[8]="E";expected[9]="T";
        blocks[0][0]=43;blocks[0][1]=0;blocks[0][2]=1;blocks[0][3]=4;blocks[0][4]=1;blocks[0][5]=42;
        data=0;data[2*8+:8]=4;data[3*8+:8]=1;data[4*8+:8]=4;data[8*8+:8]=43;
        data[9*8+:8]=8'h3f;data[10*8+:8]=8'he1;data[11*8+:8]=3;data[12*8+:8]=8'h82;
        fork beat(data,64'h1fff,1,0);receive_headers();join
        wait(rsp_valid);
        if(rsp_is_command||rsp_status!=0||rsp_http2_error!=0||received!=0||received_headers!=1||received_blocks!=1||physical_word(24'h7c005b)!=512||physical_word(24'h7c0073)!=0)$fatal(1,"Persisted HPACK size reduction did not complete through raw HEADERS");
        acknowledge;total++;
        fields[0]=10;fields[7]=0;fields[12]=0;fields[13]=0;received=0;received_headers=0;received_blocks=0;
        command_hpack_maximum=4096;command_hpack_allowed=4096;command_required_maximum=4096;command_required_update=0;
        command_buffer_bytes=65536;command_table_bytes=4096;command_scratch_bytes=65536;
        control(0,10,16384,1,0,0,0);
        for(integer target=0;target<41;target++)begin
            fault_setup(0,target);beat(0,0,1,10);wait(rsp_valid);
            if(rsp_status!=(target<20?2:5)||rsp_detail!=(target<20?target:target-20)||!injected||!recovery_required)$fatal(1,"Combined record fault target=%0d status=%0d detail=%0d",target,rsp_status,rsp_detail);
            acknowledge;faults++;fault_setup(0,-1);control(0,11,16384,1,0,6,0);control(1,10,16384,1,0,0,0);control(0,10,16384,1,0,0,0);
        end
        for(integer target=0;target<21;target++)begin fault_setup(0,target);control(0,10,16384,1,0,5,target);if(!injected||!recovery_required)$fatal(1,"Header OPEN fault");faults++;fault_setup(0,-1);control(0,10,16384,1,0,0,0);end
        for(integer target=0;target<41;target++)begin fault_setup(0,target);control(2,10,65537,1,0,target<20?2:5,target<20?target:target-20);if(!injected||!recovery_required)$fatal(1,"Header UPDATE fault");faults++;fault_setup(0,-1);control(0,10,16384,1,0,0,0);end
        fault_setup(0,0);control(1,10,16384,1,0,5,0);faults++;fault_setup(0,-1);control(0,10,16384,1,0,0,0);
        // Fault each header-data client after real bytes have entered the
        // pipeline; packet failure must invalidate the otherwise active record.
        for(integer test_number=0;test_number<4;test_number++)begin
            control(0,10,16384,1,0,0,0);received=0;received_headers=0;received_blocks=0;fields[7]=2;
            for(integer e=0;e<2;e++)for(integer j=0;j<10;j++)golden[e][j]=0;
            golden[0][0]=0;golden[1][0]=3;golden[0][5]=4;golden[1][5]=4;
            data=0;
            // Client magic followed by empty SETTINGS and a one-byte indexed
            // header, or an incremental literal for the dictionary writer.
            for(integer i=0;i<24;i++)data[i*8+:8]=CLIENT_MAGIC[(23-i)*8+:8];
            data[27*8+:8]=4;data[35*8+:8]=test_number==3?5:1;data[36*8+:8]=1;data[37*8+:8]=4;data[41*8+:8]=1;
            data[42*8+:8]=test_number==3?8'h40:8'h82;
            if(test_number==3)begin data[43*8+:8]=1;data[44*8+:8]="x";data[45*8+:8]=1;data[46*8+:8]="y";end
            fault_setup(test_number<2?1:test_number==2?2:3,test_number==1?1:0);
            beat(data,test_number==3?64'h00007fffffffffff:64'h000007ffffffffff,1,10);
            wait(rsp_valid);
            if(rsp_status!=4||rsp_http2_error!=2||rsp_detail!=(test_number==0?10:test_number==1?11:test_number==2?135:140)||!injected||recovery_required||received!=2||header_valid||block_valid)$fatal(1,"Header data fault not retired case=%0d status=%0d error=%0d detail=%0d",test_number,rsp_status,rsp_http2_error,rsp_detail);
            for(integer i=0;i<8;i++)if(memory_model.memory[(24'h7c0a03+i)>>3][((24'h7c0a03+i)&7)*8+:8]!==8'd0)$fatal(1,"Header data fault retained active marker");
            acknowledge;faults++;fault_setup(0,-1);
        end
        for(integer c=0;c<16;c++)for(integer i=160;i<256;i++)begin
            scanned=24'h7c0003+c*256+i;
            if(memory_model.memory[scanned>>3][(scanned&7)*8+:8]!==8'(scanned*37+(scanned>>5)*19+7))$fatal(1,"Reserved metadata overwritten");
        end
        if(total<2000||header_total<100||block_total<20||faults!=108||start_total<block_total||start_stalls==0)$fatal(1,"Insufficient raw HPACK coverage");
        $display("BLOCK_BEGIN: %0d acknowledged header blocks/%0d admission stall cycles; no field before BEGIN and exact completion identity",start_total,start_stalls);
        $display("PASS: raw 512-bit HTTP/2 -> external assembly -> HPACK: %0d packets/%0d semantic events/%0d exact header fields/%0d blocks/%0d protocol failures/%0d controls/%0d memory fault cases; no host boundaries/state, persistent dictionaries, padding/priority/CONTINUATION, leased fields and atomic packet commit",total,event_total,header_total,block_total,errors,controls,faults);$finish;
    end
    initial begin #(64'd20000000000);$fatal(1,"Raw header ingress timeout packet=%0d state=%0d",total,dut.dispatcher.state);end
endmodule
