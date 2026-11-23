// Included after the independent 8 MiB HyperBus model and AXI host tasks.
byte unsigned prompt[0:16383],expected_bow[0:1023],expected_packet[0:2047];
integer expected_ids[0:16383];
integer prompt_bytes,expected_count,case_user,case_application,case_format,case_chunks;
integer dma_received=0,dma_last_count=0,bow_received=0,tx_received=0,tx_last_count=0;
integer raw_bytes=0,packet_bytes=0,current_epoch=0,current_case=0;
integer total_forward=0,total_inverse=0,app_cycle=0,app_reads=0,app_writes=0;
integer dma_holds=0,tx_holds=0,maintenance_busy_holds=0;
bit dma_stalled=0,tx_stalled=0,pending_text_accepted=0;
logic [592:0] saved_dma,saved_tx;
wire [592:0] dma_snapshot={m_axis_tokens_tuser,m_axis_tokens_tlast,m_axis_tokens_tkeep,m_axis_tokens_tdata};
wire [592:0] tx_snapshot={test_tx_user,test_tx_last,test_tx_keep,test_tx_data};
always @(negedge app_clk)begin
    m_axis_tokens_tready=app_cycle%13>=4;
    test_tx_ready=app_cycle%19>=7;
end
always @(posedge app_clk)begin
    app_cycle++;
    if(application_reset)begin dma_stalled=0;tx_stalled=0;end
    else begin
        assert(!link_f_bpe_error_valid)else $fatal(1,"Actual BPE error stage=%0d detail=%0d status=%0d",link_f_bpe_error_stage,link_f_bpe_error_detail,link_f_bpe_error_status);
        if(dma_stalled)assert(m_axis_tokens_tvalid&&saved_dma==dma_snapshot)else $fatal(1,"Held actual DMA changed");
        if(tx_stalled)assert(test_tx_valid&&saved_tx==tx_snapshot)else $fatal(1,"Held actual serializer output changed");
        dma_stalled=m_axis_tokens_tvalid&&!m_axis_tokens_tready;saved_dma=dma_snapshot;
        tx_stalled=test_tx_valid&&!test_tx_ready;saved_tx=tx_snapshot;
        if(dma_stalled)dma_holds++;
        if(tx_stalled)tx_holds++;
    end
    if(link_f_bpe_s_axis_text_tvalid&&link_f_bpe_s_axis_text_tready)pending_text_accepted=1;
    if(!image_active)begin
        assert(!link_f_bpe_s_axis_text_tready&&!link_r_s_axis_tokens_tready&&!m_axis_tokens_tvalid&&!link_s_start_valid)else $fatal(1,"Inactive image admitted application traffic");
    end
    if(m_axis_tokens_tvalid&&m_axis_tokens_tready)begin
        assert(image_active&&m_axis_tokens_tuser==case_user)else $fatal(1,"DMA image/context binding");
        for(integer lane=0;lane<16;lane++)begin
            assert(m_axis_tokens_tkeep[lane*4+:4]==0||m_axis_tokens_tkeep[lane*4+:4]==15)else $fatal(1,"Partial token keep");
            if(m_axis_tokens_tkeep[lane*4+:4]==15)begin
                assert(dma_received<expected_count&&m_axis_tokens_tdata[lane*32+:32]==expected_ids[dma_received])else $fatal(1,"Actual BPE token mismatch epoch=%0d case=%0d index=%0d got=%0d expected=%0d",current_epoch,current_case,dma_received,m_axis_tokens_tdata[lane*32+:32],expected_ids[dma_received]);
                dma_received++;
            end
        end
        if(m_axis_tokens_tlast)begin assert(dma_received==expected_count)else $fatal(1,"DMA final count");dma_last_count++;end
    end
    if(link_s_s_axis_text_tvalid&&link_s_s_axis_text_tready)begin
        assert(!link_s_s_axis_text_abort&&link_s_s_axis_text_tuser==case_application)else $fatal(1,"Actual inverse BoW metadata");
        for(integer lane=0;lane<16;lane++)if(link_s_s_axis_text_tkeep[lane])begin
            assert(bow_received<raw_bytes&&link_s_s_axis_text_tdata[lane*8+:8]==expected_bow[bow_received])else $fatal(1,"Inverse vocabulary byte mismatch");bow_received++;
        end
    end
    if(test_tx_valid&&test_tx_ready)begin
        assert(test_tx_user==case_application)else $fatal(1,"Serialized application context");
        for(integer lane=0;lane<64;lane++)if(test_tx_keep[lane])begin
            assert(tx_received<packet_bytes&&test_tx_data[lane*8+:8]==expected_packet[tx_received])else $fatal(1,"Actual JSON/SSE/Protobuf byte mismatch epoch=%0d case=%0d byte=%0d",current_epoch,current_case,tx_received);tx_received++;
        end
        if(test_tx_last)begin assert(tx_received==packet_bytes)else $fatal(1,"Serialized packet final length");tx_last_count++;end
    end
    if(dut.application.m_axi_arvalid&&dut.application.m_axi_arready)begin assert(image_active)else $fatal(1,"Application AR during loader ownership");app_reads++;end
    if(dut.application.m_axi_awvalid&&dut.application.m_axi_awready)begin assert(image_active)else $fatal(1,"Application AW during loader ownership");app_writes++;end
end

task automatic scan_value(input integer file,output integer value);
    assert($fscanf(file,"%d",value)==1)else $fatal(1,"Truncated native vector");
endtask

task automatic load_case(input integer file);
    integer value;
    scan_value(file,prompt_bytes);scan_value(file,expected_count);scan_value(file,case_user);
    scan_value(file,case_application);scan_value(file,case_format);scan_value(file,case_chunks);
    assert(prompt_bytes<=16384&&expected_count<=16384&&case_chunks>=1)else $fatal(1,"Invalid case geometry");
    for(integer i=0;i<prompt_bytes;i++)begin scan_value(file,value);prompt[i]=8'(value);end
    for(integer i=0;i<expected_count;i++)scan_value(file,expected_ids[i]);
    dma_received=0;dma_last_count=0;pending_text_accepted=0;
endtask

task automatic prepare_text_beat(input integer offset);
    link_f_bpe_s_axis_text_tdata=0;link_f_bpe_s_axis_text_tkeep=0;
    for(integer lane=0;lane<16;lane++)if(offset+lane<prompt_bytes)begin
        link_f_bpe_s_axis_text_tdata[lane*8+:8]=prompt[offset+lane];link_f_bpe_s_axis_text_tkeep[lane]=1;
    end
    link_f_bpe_s_axis_text_tlast=offset+16>=prompt_bytes;
    link_f_bpe_s_axis_text_tuser=16'(case_user);link_f_bpe_s_axis_text_tvalid=1;
endtask

task automatic complete_forward(input bit first_pending);
    integer offset,guard;
    offset=0;guard=0;
    if(!first_pending)begin @(negedge app_clk);prepare_text_beat(0);end
    while(offset<prompt_bytes||offset==0)begin
        if(offset!=0)begin @(negedge app_clk);prepare_text_beat(offset);end
        pending_text_accepted=0;
        do begin @(posedge app_clk);guard++;assert(guard<10000000)else $fatal(1,"Actual Tokenizer ingress timeout");end while(!link_f_bpe_s_axis_text_tready);
        @(negedge app_clk);link_f_bpe_s_axis_text_tvalid=0;
        offset+=16;
    end
    guard=0;
    while(!link_f_bpe_completion_valid||dma_last_count==0)begin
        @(negedge app_clk);guard++;
        if(guard%1000000==0)$display("TOKENIZER_ENCODING_PROGRESS epoch=%0d case=%0d cycles=%0d state=%0d frontend=%0d merge=%0d live=%0d rank_state=%0d probes=%0d staged=%0d released=%0d dma=%0d app_reads=%0d app_writes=%0d wire_transactions=%0d",
            current_epoch,current_case,guard,dut.application.application.tokenizer.state,
            dut.application.application.tokenizer.frontend.state,dut.application.application.tokenizer.merger.state,
            dut.application.application.tokenizer.merger.live_count,dut.application.application.tokenizer.ranks.state,
            dut.application.application.tokenizer.ranks.probes,dut.application.application.tokenizer.token_count,
            dut.application.application.tokenizer.release_index,dma_received,app_reads,app_writes,transaction_count);
        assert(guard<200000000)else $fatal(1,"Actual BPE/DMA completion timeout epoch=%0d case=%0d staged=%0d released=%0d reads=%0d writes=%0d",current_epoch,current_case,dut.application.application.tokenizer.token_count,dut.application.application.tokenizer.release_index,app_reads,app_writes);
    end
    assert(!link_f_bpe_completion_failed&&link_f_bpe_completion_count==expected_count&&link_f_bpe_completion_user==case_user&&dma_last_count==1)else $fatal(1,"Actual BPE completion metadata");
    external_image_grant=1;maintenance_begin_valid=1;
    repeat(23)begin @(negedge app_clk);assert(link_f_bpe_completion_valid&&!maintenance_begin_ready&&image_active)else $fatal(1,"Maintenance bypassed held BPE completion");maintenance_busy_holds++;end
    maintenance_begin_valid=0;external_image_grant=0;
    link_f_bpe_completion_ready=1;@(posedge app_clk);@(negedge app_clk);link_f_bpe_completion_ready=0;
    wait(local_quiescent);total_forward++;
endtask

task automatic run_inverse(input integer file);
    integer token,keep,eos,decoded,carry,carry_count,value,guard;
    link_r_cfg_format=2'(case_format);link_r_lease_valid=1;link_r_lease_user=16'(case_user);
    link_r_lease_application=16'(case_application);link_r_lease_stream=31'(2*current_case+1);
    link_r_lease_generation=32'(current_epoch+1);link_r_lease_model_epoch=32'(23+current_epoch);link_r_lease_schema_epoch=9;
    link_r_carry_in=0;link_r_carry_in_count=0;
    for(integer chunk=0;chunk<case_chunks;chunk++)begin
        scan_value(file,token);scan_value(file,keep);scan_value(file,eos);scan_value(file,raw_bytes);
        scan_value(file,packet_bytes);scan_value(file,decoded);scan_value(file,carry);scan_value(file,carry_count);
        assert(raw_bytes<=1024&&packet_bytes<=2048)else $fatal(1,"Inverse fixture geometry");
        for(integer i=0;i<raw_bytes;i++)begin scan_value(file,value);expected_bow[i]=8'(value);end
        for(integer i=0;i<packet_bytes;i++)begin scan_value(file,value);expected_packet[i]=8'(value);end
        bow_received=0;tx_received=0;tx_last_count=0;guard=0;
        @(negedge app_clk);link_r_s_axis_tokens_tdata=32'(token);link_r_s_axis_tokens_tkeep=4'(keep);
        link_r_s_axis_tokens_tuser=16'(case_user);link_r_s_axis_tokens_tlast=1'(eos);link_r_s_axis_tokens_tvalid=1;
        do begin @(posedge app_clk);guard++;assert(guard<1000000)else $fatal(1,"Inverse admission timeout");end while(!link_r_s_axis_tokens_tready);
        @(negedge app_clk);link_r_s_axis_tokens_tvalid=0;
        while(!link_r_result_valid)begin @(negedge app_clk);guard++;assert(guard<1000000)else $fatal(1,"Inverse completion timeout");end
        assert(link_r_result_stage==0&&link_r_result_status==0&&link_r_result_memory_status==0)else $fatal(1,"Inverse failure stage=%0d status=%0d memory=%0d",link_r_result_stage,link_r_result_status,link_r_result_memory_status);
        assert(bow_received==raw_bytes&&tx_received==packet_bytes&&tx_last_count==1)else $fatal(1,"Inverse packet/BoW completion");
        assert(link_r_result_bytes==decoded&&link_r_carry_out==carry&&link_r_carry_out_count==carry_count)else $fatal(1,"Inverse UTF8 carry/result metadata");
        repeat(5)begin @(negedge app_clk);assert(link_r_result_valid)else $fatal(1,"Held inverse completion lost");end
        link_r_carry_in=24'(carry);link_r_carry_in_count=2'(carry_count);
        link_r_result_ready=1;@(posedge app_clk);@(negedge app_clk);link_r_result_ready=0;
        wait(local_quiescent);total_inverse++;
    end
    link_r_lease_valid=0;
endtask

task automatic activate_image(input bit revoke);
    integer guard;
    @(negedge app_clk);external_image_grant=1;reload_ack_valid=1;guard=0;
    do begin @(posedge app_clk);guard++;assert(guard<100000)else $fatal(1,"Image acknowledgement timeout");end while(!reload_ack_ready);
    @(negedge app_clk);reload_ack_valid=0;if(revoke)external_image_grant=0;
    while(!reload_done_valid)begin @(negedge app_clk);guard++;assert(guard<100000)else $fatal(1,"Image activation timeout");end
    repeat(31)begin @(negedge app_clk);assert(reload_done_valid&&!image_active&&!link_f_bpe_s_axis_text_tready)else $fatal(1,"Image activation fence/held completion");end
    reload_done_ready=1;@(posedge app_clk);@(negedge app_clk);reload_done_ready=0;
    if(revoke)assert(!image_active&&reload_rejected&&application_reset)else $fatal(1,"Revoked image grant activated model");
    else assert(image_active&&!reload_rejected&&!application_reset&&!contents_lost_app)else $fatal(1,"Validated image did not activate");
    external_image_grant=0;
endtask

initial begin : integrated_test
    integer image_file,vector_file,cases,loaded;
    string image_name,vector_name;
    `include "tokenizer_config.svh"
    link_f_bpe_admit_sequences=1;link_f_bpe_error_ready=1;
    link_r_cfg_strip_special=1;link_r_cfg_replace_invalid=1;link_r_cfg_protobuf_field=17;
    rst=1;power_good_mem=0;phy_ready_mem=0;
    for(integer epoch=0;epoch<2;epoch++)begin
        current_epoch=epoch;link_r_cfg_active_model_epoch=32'(23+epoch);
        vector_name=epoch==0?"epoch0.vectors":"epoch1.vectors";
        vector_file=$fopen(vector_name,"r");assert(vector_file!=0)else $fatal(1,"Missing complete corpus");
        scan_value(vector_file,cases);assert(cases==16)else $fatal(1,"Reduced corpus");
        current_case=0;load_case(vector_file);
        if(epoch==0)begin
            prepare_text_beat(0);
            #150000;power_good_mem=1;phy_ready_mem=1;rst=0;
            wait(!app_reset);read_burst(0,1,0,0,23);
        end else begin
            wait(local_quiescent);@(negedge app_clk);external_image_grant=0;maintenance_begin_valid=1;
            repeat(13)begin @(negedge app_clk);assert(!maintenance_begin_ready&&image_active)else $fatal(1,"Local idle granted global image mutation");end
            external_image_grant=1;prepare_text_beat(0);
            do begin @(posedge app_clk);assert(!link_f_bpe_s_axis_text_tready)else $fatal(1,"Maintenance/new-sequence priority");end while(!maintenance_begin_ready);
            @(negedge app_clk);maintenance_begin_valid=0;external_image_grant=0;
            assert(application_reset&&!image_active)else $fatal(1,"Maintenance did not reset actual application/cache");
        end
        image_name=epoch==0?"image0.bin":"image1.bin";
        image_file=$fopen(image_name,"rb");assert(image_file!=0)else $fatal(1,"Missing complete vocabulary image");
        loaded=$fread(image,image_file);$fclose(image_file);assert(loaded==8388608)else $fatal(1,"Vocabulary image reduced");
        full_wire_writes=0;full_wire_reads=0;full_phase=1;
        for(integer addr=0;addr<8388608;addr+=64)begin
            write_burst(addr);
            if((addr+64)%1048576==0)$display("TOKENIZER_IMAGE_WRITE epoch=%0d bytes=%0d",epoch,addr+64);
        end
        full_phase=0;assert(full_wire_writes==131072)else $fatal(1,"Incomplete integrated write sweep");
        for(integer i=0;i<8388608;i++)assert(device_memory[i]==image[i])else $fatal(1,"Integrated full device image mismatch");
        full_phase=2;
        for(integer addr=0;addr<8388608;addr+=64)begin
            read_burst(addr);
            if((addr+64)%1048576==0)$display("TOKENIZER_IMAGE_READ epoch=%0d bytes=%0d",epoch,addr+64);
        end
        full_phase=0;assert(full_wire_reads==131072)else $fatal(1,"Incomplete integrated read sweep");
        if(epoch==0)activate_image(1);
        activate_image(0);
        for(integer index=0;index<cases;index++)begin
            current_case=index;if(index!=0)load_case(vector_file);
            complete_forward(index==0);run_inverse(vector_file);
            $display("TOKENIZER_CORPUS_CASE epoch=%0d case=%0d tokens=%0d inverse_chunks=%0d",epoch,index,expected_count,case_chunks);
        end
        $fclose(vector_file);
    end
    assert(total_forward==32&&total_inverse==EXPECTED_INVERSE_CHUNKS&&app_reads>1000&&app_writes>1000&&dma_holds>100&&tx_holds>100)else $fatal(1,"Integrated coverage counts forward=%0d inverse=%0d reads=%0d writes=%0d dma_holds=%0d tx_holds=%0d",total_forward,total_inverse,app_reads,app_writes,dma_holds,tx_holds);
    // A real Tokenizer cache miss is interrupted. Reset aborts the whole local
    // transaction owner, exposes application_reset and invalidates the model.
    @(negedge app_clk);dma_received=0;dma_last_count=0;prepare_text_beat(0);
    do @(posedge app_clk);while(!link_f_bpe_s_axis_text_tready);
    @(negedge app_clk);link_f_bpe_s_axis_text_tvalid=0;
    wait(active&&!register_mode&&!write_mode&&read_words>=4);
    @(negedge mem_clk);power_good_mem=0;
    wait(app_reset&&application_reset);#150000;@(negedge mem_clk);power_good_mem=1;
    wait(!app_reset);wait(memory_ready_app);
    assert(!image_active&&application_reset&&contents_lost_app&&dma_received==0&&reset_epochs==2)else $fatal(1,"Actual Tokenizer reset/cache/image fencing");
    read_burst(0,8,0,0,19);
    repeat(37)begin @(negedge app_clk);assert(!image_active&&!m_axis_tokens_tvalid&&!reload_done_valid)else $fatal(1,"Tokenizer replayed invalid image");end
    $display("TOKENIZER_HYPERRAM_PASS image_epochs=2 image_bytes_each=8388608 full_writes=262144 full_reads=262144 sequences=%0d inverse_chunks=%0d app_reads=%0d app_writes=%0d dma_holds=%0d tx_holds=%0d reset_epochs=%0d grant_rejections=1 maintenance_switches=1",total_forward,total_inverse,app_reads,app_writes,dma_holds,tx_holds,reset_epochs);
    $finish;
end
initial begin #(64'd2000000000000);$fatal(1,"Actual Tokenizer/HyperRAM integration timeout");end
