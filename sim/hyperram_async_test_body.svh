// Independent device model: only emitted HyperBus words/control are observed.
byte unsigned device_memory[0:8388607],image[0:8388607];
integer reset_epochs=0,mem_cycle=0,release_cycle=0,transaction_count=0;
integer ca_count=0,word_clocks=0,cs_cycles=0,read_words=0,write_words=0,data_clock=0;
integer full_phase=0,full_wire_writes=0,full_wire_reads=0,transaction_phase=0;
integer drop_after_next=-1,drop_after=-1,fault_after_next=-1,fault_after=-1;
integer last_write_words=0,last_read_words=0;
bit active=0,was_reset=0,write_mode=0,register_mode=0,first_cs=0;
logic [47:0] command_address=0;
integer address=0;
logic [15:0] cr0=16'h8f2f,cr1=16'hffc2;
integer axi_writes=0,axi_reads=0;
initial forever #2000 app_clk=~app_clk;
initial begin #700;forever #2500 mem_clk=~mem_clk;end
initial begin : startup_diagnostic
    #1000;
    $display("ASYNC_STARTUP_TRACE t=%0t request=%b app_reset=%b mem_reset=%b fifo_errors=%b src_reset=%b src_async=%b wr_busy=%b rd_busy=%b",
        $time,dut.reset_request,app_reset,mem_reset,fifo_errors,
        dut.clock_bridge.commands.s_fifo_reset,dut.clock_bridge.commands.s_reset_async,
        dut.clock_bridge.commands.wr_busy,dut.clock_bridge.commands.rd_busy);
    #124000;
    $display("ASYNC_STARTUP_TRACE t=%0t request=%b app_reset=%b mem_reset=%b fifo_errors=%b src_reset=%b src_async=%b wr_busy=%b rd_busy=%b",
        $time,dut.reset_request,app_reset,mem_reset,fifo_errors,
        dut.clock_bridge.commands.s_fifo_reset,dut.clock_bridge.commands.s_reset_async,
        dut.clock_bridge.commands.wr_busy,dut.clock_bridge.commands.rd_busy);
    assert(app_reset===1'b1&&mem_reset===1'b1)else $fatal(1,"Domain reset unknown before release");
    #875000;
    $display("ASYNC_STARTUP_TRACE t=%0t request=%b app_reset=%b mem_reset=%b fifo_errors=%b src_reset=%b src_async=%b wr_busy=%b rd_busy=%b",
        $time,dut.reset_request,app_reset,mem_reset,fifo_errors,
        dut.clock_bridge.commands.s_fifo_reset,dut.clock_bridge.commands.s_reset_async,
        dut.clock_bridge.commands.wr_busy,dut.clock_bridge.commands.rd_busy);
    assert(app_reset===1'b0&&mem_reset===1'b0&&fifo_errors===4'b0000)else $fatal(1,"Domain reset/flags failed to settle");
    if($test$plusargs("STARTUP_DIAGNOSTIC"))begin $display("ASYNC_STARTUP_DIAGNOSTIC_PASS");$finish;end
end

function automatic integer latency_cycles(input logic [3:0] code);
    case(code)14:return 3;15:return 4;0:return 5;1:return 6;2:return 7;
        default:$fatal(1,"Unsupported device latency code");endcase
endfunction
function automatic byte unsigned fault_byte(input integer offset);
    return 8'h5a^8'(offset);
endfunction

always @(negedge mem_clk)begin
    phy_latency_extra=active;phy_rx_valid=0;phy_rx_word=0;phy_fault=0;
    if(active&&ca_count==3)begin
        if(write_mode&&!register_mode&&fault_after>=0&&write_words>=fault_after)phy_fault=1;
        if(!write_mode&&word_clocks>=data_clock&&phy_rx_enable&&(drop_after<0||read_words<drop_after))begin
            phy_rx_valid=1;
            if(register_mode)case(address)
                0:phy_rx_word=16'h0c81;2:phy_rx_word=16'h0001;
                4096:phy_rx_word=cr0;4098:phy_rx_word=cr1;
                default:$fatal(1,"Invalid device register address");
            endcase
            else phy_rx_word={device_memory[address+read_words*2],device_memory[address+read_words*2+1]};
        end
    end
end

always @(posedge mem_clk)begin : device
    mem_cycle++;
    if(!phy_reset_n)begin
        assert(phy_cs_n&&!phy_clock_enable)else $fatal(1,"Clock/CS active during hardware reset");
        if(!was_reset)begin
            reset_epochs++;
            for(integer i=0;i<8388608;i++)device_memory[i]=8'ha0+8'(reset_epochs);
        end
        was_reset=1;active=0;cr0=16'h8f2f;cr1=16'hffc2;first_cs=0;
    end else begin
        if(was_reset)begin was_reset=0;release_cycle=mem_cycle;end
        if(phy_cs_n)begin
            assert(!phy_clock_enable&&!phy_dq_oe&&!phy_rwds_oe)else $fatal(1,"Driven idle device bus");
            if(active)begin
                if(transaction_phase==1)assert(write_words==32)else $fatal(1,"Incomplete image write");
                if(transaction_phase==2)assert(read_words==32)else $fatal(1,"Incomplete image read");
                last_write_words=write_words;last_read_words=read_words;transaction_count++;active=0;
            end
        end else begin
            if(!active)begin
                if(!first_cs)begin
                    assert(mem_cycle-release_cycle>=30000)else $fatal(1,"Early power-up access");first_cs=1;
                end
                active=1;ca_count=0;word_clocks=0;cs_cycles=0;read_words=0;write_words=0;
                command_address=0;transaction_phase=0;drop_after=drop_after_next;drop_after_next=-1;
                fault_after=fault_after_next;fault_after_next=-1;
            end
            cs_cycles++;
            assert(cs_cycles<=180)else $fatal(1,"Exceeded CS-low budget");
            if(phy_clock_enable)begin
                if(ca_count<3)begin
                    assert(phy_dq_oe&&!phy_rwds_oe)else $fatal(1,"Invalid command/address bus ownership");
                    command_address=(command_address<<16)|48'(phy_tx_word);ca_count++;
                    if(ca_count==3)begin
                        assert(command_address[45]&&command_address[44:35]==0&&command_address[15:3]==0)
                            else $fatal(1,"Invalid linear/reserved CA fields");
                        write_mode=!command_address[47];register_mode=command_address[46];
                        address=(integer'(command_address[34:16])<<4)|(integer'(command_address[2:0])<<1);
                        assert(address>=0&&address<8388608)else $fatal(1,"Device address overflow");
                        data_clock=write_mode&&register_mode?3:2+latency_cycles(cr0[7:4])*2;
                        if(!register_mode&&full_phase!=0)begin
                            transaction_phase=full_phase;
                            if(full_phase==1)begin
                                assert(write_mode&&address==full_wire_writes*64)else $fatal(1,"Image write address order");
                                full_wire_writes++;
                            end else begin
                                assert(!write_mode&&address==full_wire_reads*64)else $fatal(1,"Image read address order");
                                full_wire_reads++;
                            end
                        end
                    end
                end else if(write_mode)begin
                    if(word_clocks<data_clock)begin
                        assert(!phy_dq_oe&&phy_rwds_oe==(!register_mode&&word_clocks==data_clock-1))
                            else $fatal(1,"Invalid write latency/preamble");
                    end else begin
                        assert(phy_dq_oe&&phy_rwds_oe==!register_mode)else $fatal(1,"Invalid write ownership");
                        if(register_mode)begin
                            assert(write_words==0)else $fatal(1,"Register burst write");
                            case(address)4096:cr0=phy_tx_word;4098:cr1=phy_tx_word;
                                default:$fatal(1,"Invalid register write");endcase
                        end else begin
                            if(!phy_tx_mask[1])device_memory[address+write_words*2]=phy_tx_word[15:8];
                            if(!phy_tx_mask[0])device_memory[address+write_words*2+1]=phy_tx_word[7:0];
                            if(transaction_phase==1)begin
                                assert(phy_tx_mask==0&&phy_tx_word=={image[address+write_words*2],image[address+write_words*2+1]})
                                    else $fatal(1,"Image wire word/mask mismatch");
                            end
                        end
                        write_words++;
                    end
                end else begin
                    assert(!phy_dq_oe&&!phy_rwds_oe)else $fatal(1,"Host drives read bus");
                    assert(phy_rx_enable==(word_clocks>=data_clock))else $fatal(1,"Invalid read initial latency");
                    if(phy_rx_valid)read_words++;
                end
                word_clocks++;
            end
        end
    end
end

always @(posedge app_clk)if(!app_reset)begin
    assert(fifo_errors==0)else $fatal(1,"Clock FIFO error");
end

task automatic receive_read(input integer addr,input integer beats,input integer response,input integer mode,input integer hold_cycles=0);
    integer received,guard;
    logic [63:0] saved;
    received=0;guard=0;s_axi_rready=0;
    while(!s_axi_rvalid)begin @(negedge app_clk);guard++;assert(guard<100000)else $fatal(1,"Read response timeout");end
    saved=s_axi_rdata;
    repeat(hold_cycles)begin
        @(negedge app_clk);assert(s_axi_rvalid&&s_axi_rdata==saved&&s_axi_rresp==response)else $fatal(1,"Held read changed");
    end
    s_axi_rready=1;
    while(received<beats)begin
        @(posedge app_clk);
        if(s_axi_rvalid)begin
            assert(s_axi_rresp==response&&s_axi_rlast==(received==beats-1))else $fatal(1,"AXI read metadata");
            for(integer lane=0;lane<8;lane++)begin
                if(response!=0)assert(s_axi_rdata[lane*8+:8]==0)else $fatal(1,"Error read leaked bytes");
                else if(mode==1)assert(s_axi_rdata[lane*8+:8]==image[addr+received*8+lane])else $fatal(1,"Image AXI read mismatch at %0d",addr+received*8+lane);
                else assert(s_axi_rdata[lane*8+:8]==8'ha0+8'(reset_epochs))else $fatal(1,"Stale image after reset");
            end
            received++;
        end
        @(negedge app_clk);guard++;assert(guard<100000)else $fatal(1,"Incomplete AXI read");
    end
    s_axi_rready=0;axi_reads++;
endtask

task automatic send_read_address(input integer addr,input integer beats);
    integer guard;
    @(negedge app_clk);s_axi_araddr=23'(addr);s_axi_arlen=8'(beats-1);s_axi_arsize=3;s_axi_arburst=1;s_axi_arvalid=1;
    guard=0;
    do begin @(posedge app_clk);guard++;assert(guard<100000)else $fatal(1,"AR timeout");end while(!s_axi_arready);
    @(negedge app_clk);s_axi_arvalid=0;
endtask

task automatic read_burst(input integer addr,input integer beats=8,input integer response=0,input integer mode=1,input integer hold_cycles=0);
    send_read_address(addr,beats);receive_read(addr,beats,response,mode,hold_cycles);
endtask

task automatic write_burst(input integer addr,input bit use_image=1,input integer response=0,input integer hold_cycles=0);
    integer guard;
    @(negedge app_clk);s_axi_awaddr=23'(addr);s_axi_awlen=7;s_axi_awsize=3;s_axi_awburst=1;s_axi_awvalid=1;s_axi_bready=0;
    guard=0;
    do begin @(posedge app_clk);guard++;assert(guard<100000)else $fatal(1,"AW timeout");end while(!s_axi_awready);
    @(negedge app_clk);s_axi_awvalid=0;
    for(integer beat=0;beat<8;beat++)begin
        for(integer lane=0;lane<8;lane++)s_axi_wdata[lane*8+:8]=use_image?image[addr+beat*8+lane]:fault_byte(beat*8+lane);
        s_axi_wstrb=255;s_axi_wlast=beat==7;s_axi_wvalid=1;
        do begin @(posedge app_clk);guard++;assert(guard<100000)else $fatal(1,"W timeout");end while(!s_axi_wready);
        @(negedge app_clk);s_axi_wvalid=0;
    end
    while(!s_axi_bvalid)begin @(negedge app_clk);guard++;assert(guard<100000)else $fatal(1,"B timeout");end
    repeat(hold_cycles)begin @(negedge app_clk);assert(s_axi_bvalid&&s_axi_bresp==response)else $fatal(1,"Held write changed");end
    assert(s_axi_bresp==response)else $fatal(1,"AXI write result");
    s_axi_bready=1;@(posedge app_clk);@(negedge app_clk);s_axi_bready=0;axi_writes++;
endtask

initial begin : test
    integer file,loaded;
    string image_path;
    assert($value$plusargs("IMAGE=%s",image_path))else $fatal(1,"Missing complete image path");
    file=$fopen(image_path,"rb");assert(file!=0)else $fatal(1,"Cannot open full image");
    loaded=$fread(image,file);$fclose(file);assert(loaded==8388608)else $fatal(1,"Image size reduced");
    rst=1;power_good_mem=0;phy_ready_mem=0;
    #150000;power_good_mem=1;phy_ready_mem=1;rst=0;
    wait(!app_reset);assert(!memory_ready_app)else $fatal(1,"Startup was bypassed");
    // Queue a real AXI read while the memory is still initializing.
    read_burst(0,1,0,0,23);
    assert(memory_ready_app&&contents_lost_app&&reset_epochs==1)else $fatal(1,"Startup/loss status");
    assert(device_id0_mem==16'h0c81&&device_id1_mem==1&&config_readback_mem==16'h8f2f)else $fatal(1,"Device identification/configuration");
    full_phase=1;
    for(integer addr=0;addr<8388608;addr+=64)begin
        write_burst(addr);
        if((addr+64)%1048576==0)$display("ASYNC_WRITE_PROGRESS bytes=%0d",addr+64);
    end
    full_phase=0;
    assert(full_wire_writes==131072)else $fatal(1,"Incomplete wire write sweep");
    for(integer i=0;i<8388608;i++)assert(device_memory[i]==image[i])else $fatal(1,"Device image byte mismatch");
    $display("ASYNC_IMAGE_WRITTEN bytes=8388608 transactions=131072");
    full_phase=2;
    for(integer addr=0;addr<8388608;addr+=64)begin
        read_burst(addr);
        if((addr+64)%1048576==0)$display("ASYNC_READ_PROGRESS bytes=%0d",addr+64);
    end
    full_phase=0;
    assert(full_wire_reads==131072&&contents_lost_app)else $fatal(1,"Incomplete read sweep/loss acknowledgement");
    $display("ASYNC_IMAGE_READ_BACK bytes=8388608 transactions=131072");
    wait(idle_app);@(negedge app_clk);
    reload_ack_valid=1;s_axi_araddr=0;s_axi_arlen=0;s_axi_arsize=3;s_axi_arburst=1;s_axi_arvalid=1;
    @(posedge app_clk);assert(reload_ack_ready&&!s_axi_arready)else $fatal(1,"Reload/new-address priority");
    @(negedge app_clk);reload_ack_valid=0;
    while(!reload_done_valid)begin @(negedge app_clk);assert(!s_axi_arready)else $fatal(1,"Address admitted during reload fence");end
    repeat(31)begin @(negedge app_clk);assert(reload_done_valid&&!contents_lost_app&&!s_axi_arready)else $fatal(1,"Held reload completion/fence");end
    reload_done_ready=1;@(posedge app_clk);@(negedge app_clk);reload_done_ready=0;
    do @(posedge app_clk);while(!s_axi_arready);
    @(negedge app_clk);s_axi_arvalid=0;receive_read(0,1,0,1,11);
    drop_after_next=3;read_burst(0,8,2,1,17);
    assert(memory_detail_app==2&&last_read_words==3)else $fatal(1,"Timeout detail lost across CDC");
    read_burst(0,8,0,1,19);
    fault_after_next=3;write_burst(23'h700000,0,2,29);
    assert(memory_detail_app==3&&last_write_words==4)else $fatal(1,"Partial write detail lost across CDC");
    for(integer i=0;i<8;i++)image[23'h700000+i]=fault_byte(i);
    read_burst(23'h700000,8,0,1,7);
    send_read_address(0,8);
    wait(active&&!register_mode&&!write_mode&&read_words>=4);
    rst=1;s_axi_arvalid=0;s_axi_awvalid=0;s_axi_wvalid=0;s_axi_rready=0;s_axi_bready=0;
    #150000;rst=0;
    wait(!app_reset);
    while(!memory_ready_app)begin @(negedge app_clk);assert(!s_axi_rvalid&&!s_axi_bvalid)else $fatal(1,"Stale response after shared reset");end
    assert(contents_lost_app&&reset_epochs==2)else $fatal(1,"Reset retained a valid-image claim");
    read_burst(0,8,0,0,13);
    assert(contents_lost_app&&!reload_done_valid)else $fatal(1,"Unexpected reload acknowledgement");
    $display("ASYNC_HYPERRAM_PASS image_bytes=8388608 full_writes=%0d full_reads=%0d axi_writes=%0d axi_reads=%0d reset_epochs=%0d timeout_status=2 partial_write_words=4",
        full_wire_writes,full_wire_reads,axi_writes,axi_reads,reset_epochs);
    $finish;
end
initial begin #(64'd500000000000);$fatal(1,"Async memory integration timeout writes=%0d reads=%0d",axi_writes,axi_reads);end
