`timescale 1ns/1ps
module tb_http2_prefill;
    localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
    logic  clk=0;
    logic  rst=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
    logic  queue_cfg_valid=0;
    wire  queue_cfg_ready;
    logic  queue_cfg_clear=0;
    logic  maintenance_grant=0;
    logic [MEMORY_ADDR_WIDTH-1:0] queue_cfg_base=0;
    logic [MEMORY_ADDR_WIDTH:0] queue_cfg_bytes=0;
    wire  queue_cfg_result_valid;
    logic  queue_cfg_result_ready=0;
    wire [7:0] queue_cfg_status;
    logic  control_valid=0;
    wire  control_ready;
    logic [2:0] control_op=0;
    logic [USER_WIDTH-1:0] control_user=0;
    logic [USER_WIDTH-1:0] control_application=0;
    logic [30:0] control_stream=0;
    logic [31:0] control_generation=0;
    logic [MEMORY_ADDR_WIDTH-1:0] control_address=0;
    logic [MEMORY_ADDR_WIDTH-1:0] control_buffer_base=0;
    logic [MEMORY_ADDR_WIDTH:0] control_buffer_bytes=0;
    logic [31:0] control_message_limit=0;
    logic  control_protobuf=0;
    logic  control_unsupported_encoding=0;
    logic  control_maintenance=0;
    wire  control_result_valid;
    logic  control_result_ready=0;
    wire [7:0] control_status;
    wire [7:0] control_detail;
    wire [7:0] control_memory_status;
    wire [2:0] control_result_op;
    wire [MEMORY_ADDR_WIDTH-1:0] control_result_address;
    wire [MEMORY_ADDR_WIDTH-1:0] control_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes;
    wire [USER_WIDTH-1:0] control_result_user;
    wire [USER_WIDTH-1:0] control_result_application;
    wire [30:0] control_result_stream;
    wire [31:0] control_result_generation;
    wire [31:0] control_result_message_limit;
    wire  control_result_protobuf;
    wire  control_result_unsupported_encoding;
    wire [255:0] control_result_state;
    wire  packet_result_valid;
    logic  packet_result_ready=0;
    wire  packet_committed;
    wire [7:0] packet_status;
    wire [7:0] packet_detail;
    wire [7:0] packet_memory_status;
    wire [USER_WIDTH-1:0] packet_user;
    wire [31:0] packet_tag;
    wire  rpc_error_valid;
    logic  rpc_error_ready=0;
    wire [7:0] rpc_error_status;
    wire [7:0] rpc_error_detail;
    wire [7:0] rpc_error_memory_status;
    wire [USER_WIDTH-1:0] rpc_error_user;
    wire [USER_WIDTH-1:0] rpc_error_application;
    wire [30:0] rpc_error_stream;
    wire [31:0] rpc_error_generation;
    wire [31:0] rpc_error_packet_tag;
    wire  stream_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address;
    wire  queue_recovery_required;
    wire [7:0] queue_recovery_detail;
    wire [7:0] queue_recovery_memory_status;
    wire  retirement_pending;
    wire [31:0] queued_count;
    wire [31:0] pending_count;
    logic  admit_messages=0;
    logic  stream_cfg_valid=0;
    wire  stream_cfg_ready;
    wire  stream_cfg_result_valid;
    logic  stream_cfg_result_ready=0;
    wire [7:0] stream_cfg_status;
    logic  cfg_unlock=0;
    logic  cfg_schema_valid=0;
    wire  cfg_schema_ready;
    wire  cfg_quiescent;
    logic [3:0] cfg_schema_index=0;
    logic [255:0] cfg_schema_key=0;
    logic [5:0] cfg_schema_key_length=0;
    logic  cfg_schema_json_enable=0;
    logic [28:0] cfg_schema_field=0;
    logic  cfg_schema_proto_enable=0;
    wire  completion_valid;
    logic  completion_ready=0;
    wire [7:0] completion_status;
    wire [7:0] completion_detail;
    wire [7:0] completion_memory_status;
    wire [USER_WIDTH-1:0] completion_user;
    wire [USER_WIDTH-1:0] completion_application;
    wire [30:0] completion_stream;
    wire [31:0] completion_generation;
    wire [31:0] completion_ordinal;
    wire [31:0] completion_packet_tag;
    wire  payload_lease_active;
    logic [1:0] cfg_token_profile=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_class_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_hash_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_node_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_edge_base=0;
    logic [31:0] cfg_token_node_count=0;
    logic [31:0] cfg_token_edge_count=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_work_floor=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_scalar_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_merge_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_token_commit_base=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_token_scalar_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_token_merge_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_token_commit_bytes=0;
    wire [511:0] m_axis_tokens_tdata;
    wire [63:0] m_axis_tokens_tkeep;
    wire  m_axis_tokens_tvalid;
    logic  m_axis_tokens_tready=0;
    wire  m_axis_tokens_tlast;
    wire [USER_WIDTH-1:0] m_axis_tokens_tuser;
    wire [USER_WIDTH-1:0] dma_connection;
    wire [30:0] dma_stream;
    wire [31:0] dma_generation;
    wire [31:0] dma_ordinal;
    wire [31:0] dma_packet_tag;
    wire [31:0] completion_count;
    wire [7:0] completion_token_stage;
    wire [7:0] completion_token_detail;
    wire [7:0] completion_token_status;
    logic [127:0] s_return_tdata=0;
    logic [15:0] s_return_tkeep=0;
    logic  s_return_tvalid=0;
    wire  s_return_tready;
    logic  s_return_tlast=0;
    logic [USER_WIDTH-1:0] s_return_tuser=0;
    wire [127:0] m_return_tdata;
    wire [15:0] m_return_tkeep;
    wire  m_return_tvalid;
    logic  m_return_tready=0;
    wire  m_return_tlast;
    wire [USER_WIDTH-1:0] m_return_tuser;
    logic  admit_packets=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
    logic  command_valid=0;
    wire  command_ready;
    logic [1:0] command_op=0;
    logic [USER_WIDTH-1:0] command_user=0;
    logic  command_server_role=0;
    logic  command_allow_push=0;
    logic [23:0] command_max_frame_bytes=0;
    logic [MEMORY_ADDR_WIDTH-1:0] command_buffer_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] command_table_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] command_scratch_base=0;
    logic [MEMORY_ADDR_WIDTH:0] command_buffer_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] command_table_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] command_scratch_bytes=0;
    logic [31:0] command_hpack_maximum=0;
    logic [31:0] command_hpack_allowed=0;
    logic [31:0] command_header_list_limit=0;
    logic [31:0] command_required_maximum=0;
    logic  command_required_update=0;
    logic [511:0] s_axis_rx_tdata=0;
    logic [63:0] s_axis_rx_tkeep=0;
    logic  s_axis_rx_tvalid=0;
    wire  s_axis_rx_tready;
    logic  s_axis_rx_tlast=0;
    logic [USER_WIDTH-1:0] s_axis_rx_tuser=0;
    wire  rsp_valid;
    logic  rsp_ready=0;
    wire  rsp_is_command;
    wire [1:0] rsp_command_op;
    wire [7:0] rsp_status;
    wire [7:0] rsp_detail;
    wire [7:0] rsp_memory_status;
    wire [31:0] rsp_http2_error;
    wire [USER_WIDTH-1:0] rsp_user;
    logic [31:0] s_axis_rx_tag=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_route_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_route_strings_base=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_route_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_route_strings_bytes=0;
    logic [31:0] cfg_routes=0;
    logic [31:0] cfg_model_epoch=0;
    logic [31:0] cfg_schema_epoch=0;
    wire  header_valid;
    logic  header_ready=0;
    wire [3:0] header_status;
    wire [7:0] header_detail;
    wire [7:0] header_memory_status;
    wire [7:0] header_control_status;
    wire [7:0] header_cleanup_status;
    wire  header_connection_error;
    wire [31:0] header_http2_error;
    wire [9:0] header_http_status;
    wire [7:0] header_grpc_status;
    wire [USER_WIDTH-1:0] header_user;
    wire [30:0] header_stream;
    wire [31:0] header_generation;
    wire [MEMORY_ADDR_WIDTH-1:0] header_address;
    wire [15:0] header_application;
    wire [31:0] header_model_epoch;
    wire [31:0] header_schema_epoch;
    wire  header_trailers;
    wire  header_end_stream;
    wire  admission_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] admission_recovery_address;
    wire [USER_WIDTH-1:0] admission_recovery_user;
    wire  transport_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] transport_recovery_address;
    wire  control_event_valid;
    logic  control_event_ready=0;
    wire [3:0] control_event_kind;
    wire [31:0] control_event_arg0;
    wire [31:0] control_event_arg1;
    wire [30:0] control_event_stream;
    wire [USER_WIDTH-1:0] control_event_user;
    wire [7:0] transport_packet_status;
    wire [7:0] transport_packet_detail;
    wire [7:0] transport_packet_memory_status;
    wire [31:0] transport_packet_http2_error;
    wire  idle;
    wire [19:0] mem_valid;
    wire [19:0] mem_ready;
    wire [19:0] mem_write;
    wire [20*MEMORY_ADDR_WIDTH-1:0] mem_addr;
    wire [79:0] mem_bytes;
    wire [1439:0] mem_data;
    wire [19:0] mem_rsp_valid;
    wire [19:0] mem_rsp_ready;
    wire [1439:0] mem_rsp_data;
    wire [159:0] mem_rsp_status;
    always #2 clk=~clk;
    http2_grpc_prefill #(.MAX_TEXT_BYTES(16384),.MAX_FIELD_BYTES(16384)) dut(.*);
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(20)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("memory.mem")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    integer layout[0:45],raw[0:65535],expected[0:65535],bindings[0:2][0:127],handles[0:2][0:127];
    integer expected_user=0,expected_stream=0,expected_app=0,expected_count=0,received=0;
    integer packets=0,headers=0,rejected=0,messages=0,ids=0,dma_stalls=0,packet_aborts=0,opened=0;
    wire [159:0] response_status;
    reg [159:0] injected_status;
    integer fault_client=-1,fault_target=-1,response_index=0,memory_faults=0;
    bit fault_injected=0;
    always @*begin
        injected_status=response_status;
        if(fault_client>=0&&!fault_injected&&response_index==fault_target)injected_status[fault_client*8+:8]=8'h75;
    end
    assign mem_rsp_status=injected_status;
    bit draining=0,saw_last=0,dma_stalled=0;reg [511:0] held_data;reg [63:0] held_keep;
    reg held_last;reg [31:0] held_generation,held_ordinal,held_tag;reg [15:0] held_user,held_conn;reg [30:0] held_stream;
    reg [63:0] golden_model[0:1048575];
    function automatic in_region(input integer address,input integer size,input integer base,input integer capacity);
        in_region=address>=base&&address+size<=base+capacity;
    endfunction
    function automatic permitted_write(input integer client,input integer address,input integer size);
        integer region_index;bit header_region;
        begin
            header_region=0;
            for(integer u=0;u<3;u++)for(integer r=0;r<3;r++)begin
                region_index=28+6*u+2*r;
                if(in_region(address,size,layout[region_index],layout[region_index+1]))header_region=1;
            end
            case(client)
                0:permitted_write=in_region(address,size,layout[13],layout[14])&&((address-layout[13])%128)<64&&((address-layout[13])%128)+size<=64;
                1:permitted_write=in_region(address,size,layout[17],3*layout[18]);
                2:permitted_write=in_region(address,size,layout[15],layout[16]);
                6:permitted_write=in_region(address,size,layout[7],layout[8]);
                11:permitted_write=in_region(address,size,layout[9],layout[10]);
                12:permitted_write=in_region(address,size,layout[11],layout[12]);
                13:permitted_write=in_region(address,size,layout[19],layout[20])&&((address-layout[19])%256)+size<=160;
                14,15,16:permitted_write=header_region;
                19:permitted_write=in_region(address,size,layout[19],layout[20])&&((address-layout[19])%256)>=160&&((address-layout[19])%256)+size<=168||
                    in_region(address,size,layout[13],layout[14])&&((address-layout[13])%128)>=64&&((address-layout[13])%128)+size<=128;
                default:permitted_write=0;
            endcase
        end
    endfunction
    always @(negedge clk)if(!rst)begin
        m_axis_tokens_tready=draining&&$urandom_range(0,3)!=0;
        header_ready=$urandom_range(0,3)!=0;
        control_event_ready=$urandom_range(0,3)!=0;
    end
    always @(posedge clk)if(!rst)begin
        if(fault_client>=0&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin
            if(!fault_injected&&response_index==fault_target)begin fault_injected=1;memory_faults++;end
            response_index++;
        end
        for(integer c=0;c<20;c++)if(mem_valid[c]&&mem_ready[c]&&mem_write[c])begin
            if(mem_addr[c*23+:23]<layout[6]||!permitted_write(c,mem_addr[c*23+:23],mem_bytes[c*4+:4]))
                $fatal(1,"Raw forward memory ownership client=%0d addr=%h size=%0d",c,mem_addr[c*23+:23],mem_bytes[c*4+:4]);
        end
        if(header_valid&&header_ready)begin
            headers++;
            if(header_status==0)begin
                if(header_generation==0||header_user>2||header_stream>127||header_model_epoch!=23||header_schema_epoch!=9)$fatal(1,"Invalid admitted wire identity/epoch");
                if(header_trailers&&bindings[header_user][header_stream]!=header_generation)$fatal(1,"Trailer rebound generation");
                bindings[header_user][header_stream]=header_generation;
                handles[header_user][header_stream]=header_address;
            end else begin
                rejected++;
                if(header_status!=3&&!(fault_client==19&&header_status==5&&header_memory_status==8'h75&&header_cleanup_status==0))
                    $fatal(1,"Unexpected raw header error status=%0d detail=%0d",header_status,header_detail);
            end
        end
        if(rpc_error_valid&&rpc_error_ready)$fatal(1,"Unexpected raw RPC error status=%0d detail=%0d",rpc_error_status,rpc_error_detail);
        if(dma_stalled&&(!m_axis_tokens_tvalid||m_axis_tokens_tdata!==held_data||m_axis_tokens_tkeep!==held_keep||m_axis_tokens_tlast!==held_last||
            dma_generation!==held_generation||dma_ordinal!==held_ordinal||dma_packet_tag!==held_tag||m_axis_tokens_tuser!==held_user||dma_connection!==held_conn||dma_stream!==held_stream))$fatal(1,"Raw DMA changed under backpressure");
        dma_stalled=m_axis_tokens_tvalid&&!m_axis_tokens_tready;
        if(dma_stalled)begin
            dma_stalls++;held_data=m_axis_tokens_tdata;held_keep=m_axis_tokens_tkeep;held_last=m_axis_tokens_tlast;
            held_generation=dma_generation;held_ordinal=dma_ordinal;held_tag=dma_packet_tag;held_user=m_axis_tokens_tuser;held_conn=dma_connection;held_stream=dma_stream;
        end
        if(m_axis_tokens_tvalid&&m_axis_tokens_tready)begin
            if(!draining||saw_last||dma_connection!=expected_user||dma_stream!=expected_stream||m_axis_tokens_tuser!=expected_app||dma_generation!=bindings[expected_user][expected_stream]||dma_ordinal!=0)$fatal(1,"Raw DMA identity or lifetime mismatch");
            for(integer lane=0;lane<16;lane++)begin
                if(m_axis_tokens_tkeep[lane*4+:4]==15)begin
                    if(received>=expected_count||m_axis_tokens_tdata[lane*32+:32]!=expected[received])$fatal(1,"Raw token mismatch index=%0d got=%0d wanted=%0d",received,m_axis_tokens_tdata[lane*32+:32],expected[received]);
                    received++;ids++;
                end else if(m_axis_tokens_tkeep[lane*4+:4]!=0||m_axis_tokens_tdata[lane*32+:32]!=0)$fatal(1,"Raw token keep/padding");
            end
            if(m_axis_tokens_tlast)begin if(received!=expected_count)$fatal(1,"Raw DMA premature TLAST");saw_last=1;end
        end
    end
    task configure;
        begin
            cfg_token_class_base=23'(layout[0]);cfg_token_hash_base=23'(layout[1]);cfg_token_node_base=23'(layout[2]);cfg_token_edge_base=23'(layout[3]);
            cfg_token_node_count=32'(layout[4]);cfg_token_edge_count=32'(layout[5]);cfg_token_work_floor=23'(layout[6]);
            cfg_token_scalar_base=23'(layout[7]);cfg_token_scalar_bytes=24'(layout[8]);cfg_token_merge_base=23'(layout[9]);cfg_token_merge_bytes=24'(layout[10]);
            cfg_token_commit_base=23'(layout[11]);cfg_token_commit_bytes=24'(layout[12]);
            cfg_stream_base=23'(layout[13]);cfg_stream_bytes=24'(layout[14]);queue_cfg_base=23'(layout[15]);queue_cfg_bytes=24'(layout[16]);
            cfg_payload_base=23'(layout[17]);cfg_payload_slot_bytes=24'(layout[18]);cfg_payload_bytes=24'(3*layout[18]);
            cfg_context_base=23'(layout[19]);cfg_context_bytes=24'(layout[20]);cfg_route_base=23'(layout[21]);cfg_route_bytes=24'(layout[22]);
            cfg_route_strings_base=23'(layout[23]);cfg_route_strings_bytes=24'(layout[24]);cfg_routes=32'(layout[25]);cfg_model_epoch=32'(layout[26]);cfg_schema_epoch=32'(layout[27]);cfg_work_floor=23'(layout[6]);
        end
    endtask
    task directory_command(input integer op,input integer user_id,input integer sid);
        begin
            @(negedge clk);control_valid=1;control_op=3'(op);control_user=16'(user_id);control_stream=31'(sid);control_maintenance=op==4;
            control_address=op==3?23'(handles[user_id][sid]):23'd0;control_generation=op==3?32'(bindings[user_id][sid]):32'd0;
            do @(posedge clk);while(!control_ready);@(negedge clk);control_valid=0;
            wait(control_result_valid);if(control_status!=0)$fatal(1,"Directory maintenance op=%0d status=%0d",op,control_status);
            repeat(3)@(negedge clk);control_result_ready=1;@(posedge clk);@(negedge clk);control_result_ready=0;
        end
    endtask
    task connection_open(input integer user_id);
        integer offset;
        begin
            configure();offset=28+6*user_id;@(negedge clk);command_op=0;command_user=16'(user_id);command_server_role=1;command_allow_push=0;
            command_max_frame_bytes=16384;command_buffer_base=23'(layout[offset]);command_buffer_bytes=24'(layout[offset+1]);
            command_table_base=23'(layout[offset+2]);command_table_bytes=24'(layout[offset+3]);command_scratch_base=23'(layout[offset+4]);command_scratch_bytes=24'(layout[offset+5]);
            command_hpack_maximum=4096;command_hpack_allowed=4096;command_header_list_limit=32768;command_required_maximum=4096;command_required_update=0;command_valid=1;
            do @(posedge clk);while(!command_ready);@(negedge clk);command_valid=0;
            // Every command parameter is a captured transaction, including
            // connection allocation and maintenance grant after handshaking.
            command_user='1;command_buffer_base='1;command_buffer_bytes=0;command_scratch_base='1;command_scratch_bytes=0;maintenance_grant=0;
            wait(rsp_valid);if(!rsp_is_command||rsp_status!=0||rsp_user!=user_id||admission_recovery_required)$fatal(1,"Raw connection OPEN status=%0d detail=%0d",rsp_status,rsp_detail);
            repeat(4)@(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;maintenance_grant=1;opened++;
        end
    endtask
    task wire_packet(input integer user_id,input integer tag,input integer length,input integer commit);
        integer offset,lane;
        begin
            configure();offset=0;
            while(offset<length)begin
                @(negedge clk);s_axis_rx_tdata=0;s_axis_rx_tkeep=0;s_axis_rx_tuser=16'(user_id);s_axis_rx_tag=32'(tag);
                for(lane=0;lane<64&&offset<length;lane++)if($urandom_range(0,4)!=0||lane==63)begin
                    s_axis_rx_tdata[lane*8+:8]=8'(raw[offset]);s_axis_rx_tkeep[lane]=1;offset++;
                end
                s_axis_rx_tlast=offset==length;s_axis_rx_tvalid=1;
                do @(posedge clk);while(!s_axis_rx_tready);
                @(negedge clk);s_axis_rx_tvalid=0;s_axis_rx_tag=32'hdeadbeef;
                cfg_context_base='1;cfg_context_bytes=0;cfg_payload_base='1;cfg_payload_bytes=0;cfg_payload_slot_bytes=0;
                cfg_route_base='1;cfg_route_bytes=0;cfg_route_strings_base='1;cfg_route_strings_bytes=0;cfg_routes=0;cfg_model_epoch='1;cfg_schema_epoch='1;cfg_work_floor='1;
            end
            wait(packet_result_valid);
            if(packet_committed!=commit||packet_user!=user_id||packet_tag!=32'(tag))$fatal(1,"Raw packet decision commit=%0d/%0d status=%0d detail=%0d transport=%0d",packet_committed,commit,packet_status,packet_detail,transport_packet_status);
            if(!commit)begin packet_aborts++;if(queued_count!=0||pending_count!=0||m_axis_tokens_tvalid)$fatal(1,"Tentative raw packet escaped");end
            if(fault_client>=0)begin
                if(!fault_injected||commit)$fatal(1,"Joined memory fault was not exercised");
                if(fault_client==19&&!admission_recovery_required)$fatal(1,"Uncertain admission write was not quarantined");
                fault_client=-1;
            end
            repeat(6)@(negedge clk);packet_result_ready=1;@(posedge clk);@(negedge clk);packet_result_ready=0;packets++;
        end
    endtask
    task drain;
        begin
            received=0;saw_last=0;draining=1;
            wait(completion_valid);
            if(completion_status!=0||completion_detail!=0||completion_memory_status!=0||completion_token_stage!=0||completion_count!=expected_count||
                completion_user!=expected_user||completion_stream!=expected_stream||completion_application!=expected_app||completion_generation!=bindings[expected_user][expected_stream]||
                completion_ordinal!=0||!payload_lease_active||!saw_last||received!=expected_count)$fatal(1,"Raw-to-token completion mismatch status=%0d stage=%0d count=%0d/%0d stream=%0d/%0d",completion_status,completion_token_stage,completion_count,expected_count,completion_stream,expected_stream);
            // Present a real LOAD while the joined payload lease blocks
            // directory controls, then a competing connection UPDATE. The
            // issued LOAD must stay asserted until it can actually handshake.
            if(messages==0)begin
                @(negedge clk);control_op=1;control_user=16'(expected_user);control_stream=31'(expected_stream);control_valid=1;
                repeat(3)@(negedge clk);
                if(!dut.p_control_valid||control_ready)$fatal(1,"Expected joined-lease control backpressure");
                configure();command_valid=1;command_op=2;command_user=16'(expected_user);command_max_frame_bytes=16384;
                repeat(3)@(negedge clk);
                if(!dut.p_control_valid||command_ready)$fatal(1,"Competing command withdrew stalled control");
            end
            repeat(20)@(negedge clk);
            if(!completion_valid||!payload_lease_active)$fatal(1,"Raw joined lease released before completion ACK");
            completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;draining=0;
            if(messages==0)begin
                do @(posedge clk);while(!control_ready);@(negedge clk);control_valid=0;
                wait(control_result_valid);if(control_status!=0||control_result_generation!=bindings[expected_user][expected_stream])$fatal(1,"Contended LOAD changed identity");
                control_result_ready=1;@(posedge clk);@(negedge clk);control_result_ready=0;
                do @(posedge clk);while(!command_ready);@(negedge clk);command_valid=0;
                wait(rsp_valid);if(rsp_status!=0)$fatal(1,"Contended connection UPDATE failed");
                rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
            end
            messages++;
        end
    endtask
    initial begin:driver
        integer fd,rc,op,user_id,sid,tag,length,commit,scanned;
        rst=1;$readmemh("memory.mem",golden_model);
        fd=$fopen("layout.txt","r");if(!fd)$fatal(1,"No raw full-model layout");
        for(integer i=0;i<46;i++)begin rc=$fscanf(fd,"%d",scanned);layout[i]=scanned;if(rc!=1)$fatal(1,"Bad raw layout");end $fclose(fd);configure();
        repeat(5)@(negedge clk);rst=0;maintenance_grant=1;admit_packets=1;admit_messages=1;rpc_error_ready=1;
        queue_cfg_valid=1;queue_cfg_clear=1;do @(posedge clk);while(!queue_cfg_ready);@(negedge clk);queue_cfg_valid=0;
        wait(queue_cfg_result_valid);if(queue_cfg_status!=0)$fatal(1,"Raw queue configuration");queue_cfg_result_ready=1;@(posedge clk);@(negedge clk);queue_cfg_result_ready=0;
        stream_cfg_valid=1;do @(posedge clk);while(!stream_cfg_ready);@(negedge clk);stream_cfg_valid=0;
        wait(stream_cfg_result_valid);if(stream_cfg_status!=0)$fatal(1,"Raw stream pool");stream_cfg_result_ready=1;@(posedge clk);@(negedge clk);stream_cfg_result_ready=0;
        directory_command(4,0,0);
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No raw HTTP/2 vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",op);
            if(rc==1)case(op)
                0:begin rc=$fscanf(fd,"%d",user_id);if(rc!=1)$fatal;connection_open(user_id);end
                1:begin
                    rc=$fscanf(fd,"%d %d %d %d",user_id,tag,length,commit);if(rc!=4||length<1||length>65536)$fatal;
                    for(integer i=0;i<length;i++)begin rc=$fscanf(fd,"%d",raw[i]);if(rc!=1)$fatal;end
                    wire_packet(user_id,tag,length,commit);
                end
                2:begin
                    rc=$fscanf(fd,"%d %d %d %d",expected_user,expected_stream,expected_app,expected_count);if(rc!=4)$fatal;
                    for(integer i=0;i<expected_count;i++)begin rc=$fscanf(fd,"%d",expected[i]);if(rc!=1)$fatal;end drain();
                end
                3:begin rc=$fscanf(fd,"%d %d",user_id,sid);if(rc!=2)$fatal;directory_command(3,user_id,sid);end
                4:begin rc=$fscanf(fd,"%d %d",fault_client,fault_target);if(rc!=2)$fatal;fault_injected=0;response_index=0;end
                default:$fatal(1,"Unknown raw opcode");
            endcase
        end
        $fclose(fd);wait(idle&&fabric_idle);
        for(integer i=0;i<layout[6]/8;i++)if(memory_model.memory[i]!==golden_model[i])$fatal(1,"Raw path modified full vocabulary at %0d",i);
        for(integer i=layout[21]/8;i<(layout[23]+layout[24]+7)/8;i++)if(memory_model.memory[i]!==golden_model[i])$fatal(1,"Raw path modified route policy at %0d",i);
        if(messages!=16||packet_aborts!=4||rejected!=3||headers!=21||ids!=2828||dma_stalls==0||opened!=7||memory_faults!=2||packets!=38)$fatal(1,"Insufficient raw-to-token coverage messages=%0d headers=%0d ids=%0d",messages,headers,ids);
        $display("PASS: raw HTTP/2 full-model prefill %0d packets/%0d headers/%0d exact messages/%0d DMA IDs/%0d aborts/%0d memory faults; HPACK, live route admission, Parser, BoW, complete BPE, interleaving, fragmentation, trailers, shared twenty-client memory and model/policy immutability",packets,headers,messages,ids,packet_aborts,memory_faults);$finish;
    end
    initial begin #(64'd1000000000);$fatal(1,"Raw prefill timeout state=%0d admission=%0d router=%0d parser=%0d token=%0d packets=%0d messages=%0d",dut.state,dut.admission.state,dut.router.validator.state,dut.prefill.parser.state,dut.prefill.tokenizer.state,packets,messages);end

endmodule
