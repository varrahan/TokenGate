// All original prompts, two complete models, actual DMA -> GPU return traffic.
// Host supplies explicit directory retirement and exclusive image maintenance.
// This does not implement a global RPC/image authority or any package PHY.
`define JOINT_WAIT(condition,limit) \
begin \
    integer wait_guard;wait_guard=0; \
    while(!(condition))begin \
        @(negedge app_clk);wait_guard++; \
        assert(wait_guard<(limit))else $fatal(1,"Joint wait timeout epoch=%0d case=%0d line=%0d",current_epoch,current_case,`__LINE__); \
    end \
end
`define JOINT_SEND(valid,ready) \
begin \
    integer send_guard;send_guard=0;@(negedge app_clk);valid=1; \
    do begin @(posedge app_clk);send_guard++; \
        assert(send_guard<2000000)else $fatal(1,"Joint admission timeout line=%0d",`__LINE__); \
    end while(!(ready)); \
    @(negedge app_clk);valid=0; \
end
`define JOINT_ACK(valid,ready,hold) \
begin \
    `JOINT_WAIT(valid,2000000) \
    repeat(hold)begin @(negedge app_clk);assert(valid)else $fatal(1,"Held result withdrawn");end \
    ready=1;@(posedge app_clk);@(negedge app_clk);ready=0; \
end

integer current_case=-1,case_stream=0,case_mode=0,case_application=0,case_tag=0;
integer raw_length=0,expected_count=0,dma_received=0,dma_last_count=0;
integer total_dma=0,total_gpu=0,total_calls=0,total_packets=0,total_wire_frames=0;
integer total_host_configuration_commands=0;
integer cycle=0,wire_file,dma_file,gpu_file;
integer expected_ids[0:16383],captured_ids[0:16383];
integer generations[0:127],handles[0:127];
byte unsigned raw_packet[0:32767];
bit draining=0,wire_enabled=0,dma_stalled=0,wire_stalled=0,completion_stalled=0,result_stalled=0;
reg [1023:0] saved_dma=0,saved_wire=0,saved_completion=0,saved_result=0;
wire [1023:0] dma_snapshot={tokenizer_m_axis_tokens_tdata,tokenizer_m_axis_tokens_tkeep,
    tokenizer_m_axis_tokens_tlast,tokenizer_m_axis_tokens_tuser,parser_dma_connection,
    parser_dma_stream,parser_dma_generation,parser_dma_ordinal,parser_dma_packet_tag};
wire [1023:0] wire_snapshot={parser_m_axis_tx_tdata,parser_m_axis_tx_tkeep,parser_m_axis_tx_tlast,parser_m_axis_tx_tuser};
wire [1023:0] completion_snapshot={parser_completion_status,parser_completion_detail,parser_completion_memory_status,
    parser_completion_token_stage,parser_completion_token_detail,parser_completion_token_status,
    parser_completion_count,parser_completion_user,parser_completion_stream,parser_completion_application,
    parser_completion_generation,parser_completion_ordinal,parser_completion_packet_tag,parser_payload_lease_active};
wire [1023:0] result_snapshot={parser_response_result_stage,parser_response_result_status,
    parser_response_result_memory_status,parser_response_result_cancelled,parser_response_result_user,
    parser_response_result_application,parser_response_result_stream,parser_response_result_generation,
    parser_response_result_model_epoch,parser_response_result_schema_epoch,parser_response_result_ordinal,
    parser_response_result_bytes,parser_response_result_eos,parser_response_result_tx_emitted};
always @(negedge app_clk)begin
    parser_header_ready=!rst&&cycle%7>=2;
    parser_control_event_ready=!rst&&cycle%11>=3;
    tokenizer_m_axis_tokens_tready=!rst&&draining&&cycle%13>=4;
    parser_m_axis_tx_tready=!rst&&wire_enabled&&cycle%19>=8;
end
always @(posedge app_clk)begin : actual_observers
    cycle++;
    if(rst)begin dma_stalled=0;wire_stalled=0;completion_stalled=0;result_stalled=0;end
    else begin
        if(host_cfg_valid&&host_cfg_ready)begin
            assert(parser_maintenance_grant&&parser_idle&&!parser_admit_packets&&!parser_admit_messages&&
                !parser_s_axis_rx_tvalid&&!parser_s_axis_generated_tvalid)
                else $fatal(1,"Host route configuration without the maintenance fence");
            total_host_configuration_commands++;
        end
        assert(!parser_rpc_error_valid&&!dut.link_f_bpe_error_valid)else
            $fatal(1,"Unexpected RPC/BPE error rpc=%0d/%0d/%0d bpe=%0d/%0d/%0d",parser_rpc_error_status,
                parser_rpc_error_detail,parser_rpc_error_memory_status,dut.link_f_bpe_error_stage,
                dut.link_f_bpe_error_detail,dut.link_f_bpe_error_status);
        assert(!parser_transport_close_valid&&!parser_receive_fault_valid&&!parser_response_recovery_required)
            else $fatal(1,"Unexpected transport/receive/reverse recovery");
        if(dma_stalled)assert(tokenizer_m_axis_tokens_tvalid&&saved_dma==dma_snapshot)else $fatal(1,"Held DMA changed");
        if(wire_stalled)assert(parser_m_axis_tx_tvalid&&saved_wire==wire_snapshot)else $fatal(1,"Held wire output changed");
        if(completion_stalled)assert(parser_completion_valid&&saved_completion==completion_snapshot)else $fatal(1,"Held completion changed");
        if(result_stalled)assert(parser_response_result_valid&&saved_result==result_snapshot)else $fatal(1,"Held reverse result changed");
        dma_stalled=tokenizer_m_axis_tokens_tvalid&&!tokenizer_m_axis_tokens_tready;saved_dma=dma_snapshot;
        wire_stalled=parser_m_axis_tx_tvalid&&!parser_m_axis_tx_tready;saved_wire=wire_snapshot;
        completion_stalled=parser_completion_valid&&!parser_completion_ready;saved_completion=completion_snapshot;
        result_stalled=parser_response_result_valid&&!parser_response_result_ready;saved_result=result_snapshot;
        if(parser_header_valid&&parser_header_ready)begin
            assert(parser_header_status==0&&parser_header_user==0&&parser_header_stream<128&&
                parser_header_generation!=0&&parser_header_model_epoch==23+current_epoch&&parser_header_schema_epoch==9)
                else $fatal(1,"Header binding rejected status=%0d detail=%0d memory=%0d",parser_header_status,parser_header_detail,parser_header_memory_status);
            generations[parser_header_stream]=integer'(parser_header_generation);
            handles[parser_header_stream]=integer'(parser_header_address);
        end
        if(tokenizer_m_axis_tokens_tvalid&&tokenizer_m_axis_tokens_tready)begin
            assert(draining&&tokenizer_image_active&&dma_last_count==0&&tokenizer_m_axis_tokens_tuser==case_application&&
                parser_dma_connection==0&&parser_dma_stream==case_stream&&parser_dma_generation==generations[case_stream]&&
                parser_dma_ordinal==0&&parser_dma_packet_tag==case_tag)else $fatal(1,"DMA identity mismatch");
            for(integer lane=0;lane<16;lane++)begin
                if(tokenizer_m_axis_tokens_tkeep[lane*4+:4]==15)begin
                    assert(dma_received<expected_count&&tokenizer_m_axis_tokens_tdata[lane*32+:32]==expected_ids[dma_received])
                        else $fatal(1,"Full-model DMA mismatch epoch=%0d case=%0d index=%0d got=%0d expected=%0d",current_epoch,current_case,dma_received,tokenizer_m_axis_tokens_tdata[lane*32+:32],expected_ids[dma_received]);
                    captured_ids[dma_received]=integer'(tokenizer_m_axis_tokens_tdata[lane*32+:32]);
                    $fwrite(dma_file,"%0d %0d %0d %0d\n",current_epoch,current_case,dma_received,captured_ids[dma_received]);
                    dma_received++;total_dma++;
                end else assert(tokenizer_m_axis_tokens_tkeep[lane*4+:4]==0&&tokenizer_m_axis_tokens_tdata[lane*32+:32]==0)
                    else $fatal(1,"Partial/nonzero DMA padding");
            end
            if(tokenizer_m_axis_tokens_tlast)begin assert(dma_received==expected_count)else $fatal(1,"DMA last count");dma_last_count++;end
        end
        if(parser_s_axis_generated_tvalid&&parser_s_axis_generated_tready)begin
            assert(parser_s_axis_generated_tdata==captured_ids[parser_generated_ordinal])else $fatal(1,"GPU input did not use captured DMA ID");
            $fwrite(gpu_file,"%0d %0d %0d %0d %0d\n",current_epoch,current_case,parser_generated_ordinal,parser_s_axis_generated_tdata,parser_s_axis_generated_tlast);
            total_gpu++;
        end
        if(parser_m_axis_tx_tvalid&&parser_m_axis_tx_tready)begin
            assert(parser_m_axis_tx_tuser==0)else $fatal(1,"Wire connection identity");
            $fwrite(wire_file,"%0d %0d %0d %016h %0128h\n",current_epoch,current_case,parser_m_axis_tx_tlast,parser_m_axis_tx_tkeep,parser_m_axis_tx_tdata);
            if(parser_m_axis_tx_tlast)total_wire_frames++;
        end
        if(cycle%1000000==0)$display("JOINT_PROGRESS epoch=%0d case=%0d cycles=%0d dma=%0d gpu=%0d wire=%0d parser_reads=%0d parser_writes=%0d hyperbus=%0d",current_epoch,current_case,cycle,total_dma,total_gpu,total_wire_frames,parser_reads,parser_writes,transaction_count);
    end
end

task automatic scan_value(input integer file,output integer value);
    assert($fscanf(file,"%d",value)==1)else $fatal(1,"Truncated complete native vector");
endtask
task automatic read_raw(input integer file,input integer length);
    integer value;
    assert(length>0&&length<=32768)else $fatal(1,"Raw request geometry");raw_length=length;
    for(integer i=0;i<length;i++)begin scan_value(file,value);assert(value>=0&&value<=255)else $fatal(1,"Raw byte range");raw_packet[i]=8'(value);end
endtask
task automatic packet(input integer tag);
    integer offset,beat;
    configure();offset=0;beat=0;case_tag=tag;
    while(offset<raw_length)begin
        @(negedge app_clk);parser_s_axis_rx_tdata=0;parser_s_axis_rx_tkeep=0;
        for(integer lane=0;lane<64;lane++)if(offset<raw_length&&((lane+beat)%5!=0||lane==63))begin
            parser_s_axis_rx_tdata[lane*8+:8]=raw_packet[offset];parser_s_axis_rx_tkeep[lane]=1;offset++;
        end
        parser_s_axis_rx_tuser=0;parser_s_axis_rx_tag=32'(tag);parser_s_axis_rx_tlast=offset==raw_length;
        `JOINT_SEND(parser_s_axis_rx_tvalid,parser_s_axis_rx_tready)
        parser_s_axis_rx_tag=32'hdeadbeef;parser_s_axis_rx_tdata='1;poison();beat++;
    end
    `JOINT_WAIT(parser_packet_result_valid,200000000)
    assert(parser_packet_committed&&parser_packet_user==0&&parser_packet_tag==tag)
        else $fatal(1,"Raw packet rejected tag=%0d status=%0d detail=%0d mem=%0d",tag,parser_packet_status,parser_packet_detail,parser_packet_memory_status);
    `JOINT_ACK(parser_packet_result_valid,parser_packet_result_ready,6)
    total_packets++;
endtask
task automatic directory(input integer operation,input integer stream=0);
    configure();parser_control_op=3'(operation);parser_control_user=0;parser_control_stream=31'(stream);
    parser_control_maintenance=operation==4;parser_control_address=operation==3?23'(handles[stream]):0;
    parser_control_generation=operation==3?32'(generations[stream]):0;
    `JOINT_SEND(parser_control_valid,parser_control_ready)
    `JOINT_WAIT(parser_control_result_valid,2000000)
    assert(parser_control_status==0)else $fatal(1,"Directory operation=%0d status=%0d mem=%0d",operation,parser_control_status,parser_control_memory_status);
    `JOINT_ACK(parser_control_result_valid,parser_control_result_ready,3)
endtask
task automatic configure_route_epochs;
    integer route;
    configure();parser_maintenance_grant=1;
    assert(!parser_admit_packets&&!parser_admit_messages)else $fatal(1,"Route update admitted application traffic");
    `JOINT_WAIT(parser_idle&&parser_fabric_idle,2000000)
    for(integer entry=0;entry<2;entry++)begin
        route=integer'(parser_cfg_route_base)+entry*32+20;
        @(negedge app_clk);host_cfg_addr=23'(route);host_cfg_data=32'(23+current_epoch);host_cfg_write=1;
        `JOINT_SEND(host_cfg_valid,host_cfg_ready)
        `JOINT_WAIT(host_cfg_rsp_valid,2000000)
        assert(host_cfg_rsp_status==0)else $fatal(1,"Host route epoch write failed");
        `JOINT_ACK(host_cfg_rsp_valid,host_cfg_rsp_ready,9)
        @(negedge app_clk);host_cfg_write=0;
        `JOINT_SEND(host_cfg_valid,host_cfg_ready)
        `JOINT_WAIT(host_cfg_rsp_valid,2000000)
        assert(host_cfg_rsp_status==0&&host_cfg_rsp_data[31:0]==23+current_epoch)else $fatal(1,"Host route epoch readback mismatch");
        `JOINT_ACK(host_cfg_rsp_valid,host_cfg_rsp_ready,9)
        $display("JOINT_ROUTE_EPOCH epoch=%0d entry=%0d model_epoch=%0d",current_epoch,entry,23+current_epoch);
    end
endtask
task automatic initialize_parser;
    configure();parser_maintenance_grant=1;parser_admit_packets=0;parser_admit_messages=0;
    parser_rpc_error_ready=1;parser_queue_cfg_clear=1;
    `JOINT_SEND(parser_queue_cfg_valid,parser_queue_cfg_ready)
    `JOINT_WAIT(parser_queue_cfg_result_valid,2000000)
    assert(parser_queue_cfg_status==0)else $fatal(1,"Queue configuration");
    `JOINT_ACK(parser_queue_cfg_result_valid,parser_queue_cfg_result_ready,0)
    `JOINT_SEND(parser_stream_cfg_valid,parser_stream_cfg_ready)
    `JOINT_WAIT(parser_stream_cfg_result_valid,2000000)
    assert(parser_stream_cfg_status==0)else $fatal(1,"Stream configuration");
    `JOINT_ACK(parser_stream_cfg_result_valid,parser_stream_cfg_result_ready,0)
    response_configuration();directory(4);
    // Descriptor idle is false until its explicit queue configuration. Keep
    // admission fenced, initialize the stores, then program route epochs.
    configure_route_epochs();
    // OPEN retires its actual server SETTINGS before publishing success.
    // Keep wire backpressure active, but allow that frame to complete.
    parser_admit_packets=1;parser_admit_messages=1;wire_enabled=1;setup_open();
    `JOINT_SEND(parser_command_valid,parser_command_ready)
    poison();parser_command_user=65535;parser_maintenance_grant=0;
    `JOINT_WAIT(parser_rsp_valid,2000000)
    assert(parser_rsp_status==0&&parser_rsp_detail==0&&parser_rsp_memory_status==0&&
        parser_command_window_status==0&&parser_command_control_status==0&&parser_peer_format_status==0)
        else $fatal(1,"OPEN failed status=%0d mem=%0d window=%0d control=%0d peer=%0d",parser_rsp_status,parser_rsp_memory_status,parser_command_window_status,parser_command_control_status,parser_peer_format_status);
    repeat(9)begin @(negedge app_clk);assert(parser_rsp_valid)else $fatal(1,"OPEN result withdrawn");end
    `JOINT_ACK(parser_rsp_valid,parser_rsp_ready,0)
endtask
task automatic complete_forward;
    draining=1;
    `JOINT_WAIT(parser_completion_valid,200000000)
    assert(dma_last_count==1&&dma_received==expected_count&&parser_completion_status==0&&parser_completion_detail==0&&
        parser_completion_memory_status==0&&parser_completion_token_stage==0&&parser_completion_token_status==0&&
        parser_completion_count==expected_count&&parser_completion_user==0&&parser_completion_stream==case_stream&&
        parser_completion_application==case_application&&parser_completion_generation==generations[case_stream]&&
        parser_completion_ordinal==0&&parser_completion_packet_tag==case_tag&&parser_payload_lease_active)
        else $fatal(1,"Actual forward completion failed/count mismatch count=%0d dma=%0d expected=%0d status=%0d/%0d/%0d token=%0d/%0d/%0d",parser_completion_count,dma_received,expected_count,parser_completion_status,parser_completion_detail,parser_completion_memory_status,parser_completion_token_stage,parser_completion_token_detail,parser_completion_token_status);
    if(current_case==0)begin
        configure();parser_control_op=1;parser_control_user=0;parser_control_stream=31'(case_stream);parser_control_maintenance=0;parser_control_valid=1;
        repeat(3)begin @(negedge app_clk);assert(!parser_control_ready)else $fatal(1,"Control bypassed held completion");end
        parser_command_op=2;parser_command_user=0;parser_command_max_frame_bytes=16384;parser_command_valid=1;
        repeat(3)begin @(negedge app_clk);assert(!parser_command_ready)else $fatal(1,"Command bypassed held completion");end
    end
    `JOINT_ACK(parser_completion_valid,parser_completion_ready,20)
    draining=0;
    if(current_case==0)begin
        do @(posedge app_clk);while(!parser_control_ready);
        @(negedge app_clk);parser_control_valid=0;
        `JOINT_WAIT(parser_control_result_valid,2000000)
        assert(parser_control_status==0&&parser_control_result_generation==generations[case_stream])else $fatal(1,"Held lookup failed");
        `JOINT_ACK(parser_control_result_valid,parser_control_result_ready,0)
        do @(posedge app_clk);while(!parser_command_ready);
        @(negedge app_clk);parser_command_valid=0;
        `JOINT_WAIT(parser_rsp_valid,2000000)
        assert(parser_rsp_status==0)else $fatal(1,"Held command failed");
        `JOINT_ACK(parser_rsp_valid,parser_rsp_ready,0)
    end
endtask
task automatic return_captured_ids;
    for(integer ordinal=0;ordinal<dma_received;ordinal++)begin
        response_configuration();parser_cfg_response_format=2'(case_mode);
        parser_s_axis_generated_tdata=32'(captured_ids[ordinal]);parser_s_axis_generated_tkeep=15;
        parser_s_axis_generated_tlast=ordinal+1==dma_received;parser_s_axis_generated_tuser=0;
        parser_generated_stream=31'(case_stream);parser_generated_generation=32'(generations[case_stream]);
        parser_generated_model_epoch=32'(23+current_epoch);parser_generated_schema_epoch=9;parser_generated_ordinal=32'(ordinal);
        `JOINT_SEND(parser_s_axis_generated_tvalid,parser_s_axis_generated_tready)
        parser_s_axis_generated_tdata='1;parser_generated_stream=0;parser_generated_generation=0;
        parser_cfg_response_progress_base=23'h7fffff;parser_cfg_response_progress_bytes=0;parser_cfg_response_format=3;
        `JOINT_WAIT(parser_response_result_valid,2000000)
        assert(parser_response_result_stage==0&&parser_response_result_status==0&&parser_response_result_memory_status==0&&
            !parser_response_result_cancelled&&parser_response_result_stream==case_stream&&
            parser_response_result_generation==generations[case_stream]&&parser_response_result_model_epoch==23+current_epoch&&
            parser_response_result_schema_epoch==9&&parser_response_result_ordinal==ordinal&&
            parser_response_result_eos==(ordinal+1==dma_received))
            else $fatal(1,"Actual return failed epoch=%0d case=%0d ordinal=%0d stage=%0d status=%0d mem=%0d",current_epoch,current_case,ordinal,parser_response_result_stage,parser_response_result_status,parser_response_result_memory_status);
        `JOINT_ACK(parser_response_result_valid,parser_response_result_ready,13)
        `JOINT_WAIT(!dut.parser.core.return_pending,2000000)
    end
endtask
task automatic activate_image;
    tokenizer_external_image_grant=1;
    `JOINT_SEND(tokenizer_reload_ack_valid,tokenizer_reload_ack_ready)
    `JOINT_WAIT(tokenizer_reload_done_valid,2000000)
    repeat(31)begin @(negedge app_clk);assert(tokenizer_reload_done_valid&&!tokenizer_image_active)else $fatal(1,"Image activation fence");end
    `JOINT_ACK(tokenizer_reload_done_valid,tokenizer_reload_done_ready,0)
    assert(tokenizer_image_active&&!tokenizer_reload_rejected&&!tokenizer_application_reset&&!tokenizer_contents_lost_app)
        else $fatal(1,"Complete image did not activate");
    tokenizer_external_image_grant=0;
endtask
task automatic dump_banks;
    integer file;
    string name;
    name=$sformatf("parser-final%0d.bin",current_epoch);file=$fopen(name,"wb");assert(file!=0)else $fatal(1,"Parser dump open");
    for(integer i=0;i<8388608;i++)$fwrite(file,"%c",parser_bank[i]);$fclose(file);
    name=$sformatf("tokenizer-final%0d.bin",current_epoch);file=$fopen(name,"wb");assert(file!=0)else $fatal(1,"Tokenizer dump open");
    for(integer i=0;i<8388608;i++)$fwrite(file,"%c",device_memory[i]);$fclose(file);
endtask
initial begin : complete_joint_test
    integer file,vectors,loaded,count,value,length,index;
    string name;
    wire_file=$fopen("wire.log","w");dma_file=$fopen("dma.log","w");gpu_file=$fopen("gpu.log","w");
    assert(wire_file!=0&&dma_file!=0&&gpu_file!=0)else $fatal(1,"Trace output open");
    file=$fopen("parser-image.bin","rb");assert(file!=0)else $fatal(1,"Missing Parser image");
    loaded=$fread(parser_bank,file);$fclose(file);assert(loaded==8388608)else $fatal(1,"Reduced Parser image");
    parser_admit_packets=0;parser_admit_messages=0;rst=1;tokenizer_power_good_mem=0;tokenizer_phy_ready_mem=0;
    #150000;tokenizer_power_good_mem=1;tokenizer_phy_ready_mem=1;
    #50000;rst=0;
    for(integer epoch=0;epoch<2;epoch++)begin
        current_epoch=epoch;current_case=-1;wire_enabled=0;
        `JOINT_WAIT(tokenizer_memory_ready_app&&!tokenizer_app_reset,2000000)
        name=$sformatf("image%0d.bin",epoch);file=$fopen(name,"rb");assert(file!=0)else $fatal(1,"Missing full vocabulary image");
        loaded=$fread(image,file);$fclose(file);assert(loaded==8388608)else $fatal(1,"Reduced model image");
        tokenizer_external_image_grant=1;full_wire_writes=0;full_wire_reads=0;full_phase=1;
        for(integer addr=0;addr<8388608;addr+=64)begin
            write_burst(addr);
            if((addr+64)%1048576==0)$display("JOINT_IMAGE_WRITE epoch=%0d bytes=%0d",epoch,addr+64);
        end
        full_phase=0;assert(full_wire_writes==131072)else $fatal(1,"Incomplete full image program");
        for(integer i=0;i<8388608;i++)assert(device_memory[i]==image[i])else $fatal(1,"Full image device mismatch");
        full_phase=2;
        for(integer addr=0;addr<8388608;addr+=64)begin
            read_burst(addr);
            if((addr+64)%1048576==0)$display("JOINT_IMAGE_READ epoch=%0d bytes=%0d",epoch,addr+64);
        end
        full_phase=0;assert(full_wire_reads==131072)else $fatal(1,"Incomplete full image readback");
        activate_image();initialize_parser();
        name=$sformatf("epoch%0d.vectors",epoch);vectors=$fopen(name,"r");assert(vectors!=0)else $fatal(1,"Missing complete HTTP/2 vectors");
        scan_value(vectors,length);read_raw(vectors,length);packet(1);
        `JOINT_WAIT(parser_idle&&parser_fabric_idle,2000000)
        repeat(50)@(negedge app_clk);
        scan_value(vectors,count);assert(count==16)else $fatal(1,"Reduced native corpus");
        for(integer c=0;c<16;c++)begin
            scan_value(vectors,index);assert(index==c)else $fatal(1,"Case order");current_case=c;
            scan_value(vectors,case_stream);scan_value(vectors,case_mode);scan_value(vectors,case_application);
            scan_value(vectors,length);scan_value(vectors,expected_count);read_raw(vectors,length);
            assert(expected_count>0&&expected_count<=16384)else $fatal(1,"Expected IDs geometry");
            for(integer i=0;i<expected_count;i++)scan_value(vectors,expected_ids[i]);
            dma_received=0;dma_last_count=0;packet(c+2);complete_forward();return_captured_ids();directory(3,case_stream);
            `JOINT_WAIT(parser_idle&&parser_fabric_idle&&tokenizer_local_quiescent,2000000)
            total_calls++;
            $display("JOINT_CORPUS_CASE epoch=%0d case=%0d tokens=%0d total_dma=%0d total_gpu=%0d",epoch,c,dma_received,total_dma,total_gpu);
            $fflush(wire_file);$fflush(dma_file);$fflush(gpu_file);
        end
        assert($fscanf(vectors,"%d",value)!=1)else $fatal(1,"Trailing corpus vectors");$fclose(vectors);
        dump_banks();
        if(epoch==0)begin
            @(negedge app_clk);parser_admit_packets=0;parser_admit_messages=0;wire_enabled=0;rst=1;
            #200000;@(negedge app_clk);rst=0;
        end
    end
    assert(total_calls==32&&total_dma==11091&&total_gpu==11091&&total_packets==34&&axi_writes==262144&&axi_reads==262144&&total_host_configuration_commands==8)
        else $fatal(1,"Joint workload coverage incomplete calls=%0d dma=%0d gpu=%0d packets=%0d loader_w=%0d loader_r=%0d",total_calls,total_dma,total_gpu,total_packets,axi_writes,axi_reads);
    $fclose(wire_file);$fclose(dma_file);$fclose(gpu_file);
    $display("JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS calls=%0d dma=%0d gpu=%0d wire_frames=%0d parser_reads=%0d parser_writes=%0d",total_calls,total_dma,total_gpu,total_wire_frames,parser_reads,parser_writes);
    $finish;
end
initial begin #(64'd2000000000000);$fatal(1,"Complete joint workload watchdog");end
`undef JOINT_WAIT
`undef JOINT_SEND
`undef JOINT_ACK
