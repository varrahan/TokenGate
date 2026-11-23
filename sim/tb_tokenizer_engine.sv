`timescale 1ns/1ps
module tb_tokenizer_engine;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic admit=1;logic [1:0] profile=0;
    logic [22:0] class_base,hash_base,node_base,edge_base,work_floor,scalar_base,merge_base,commit_base;
    logic [23:0] scalar_bytes,merge_bytes,commit_bytes;
    logic [31:0] node_count,edge_count;
    integer cfg[0:12];
    logic [127:0] s_data=0;logic [15:0] s_keep=0,s_user=0;logic s_valid=0,s_last=0;
    wire s_ready;wire [31:0] t_data;wire [3:0] t_keep;wire [15:0] t_user;wire t_valid,t_ready,t_last;
    wire completion_valid,completion_failed;logic completion_ready=0;wire [31:0] completion_count;wire [15:0] completion_user;
    wire error_valid,engine_idle;logic error_ready=0;wire [7:0] error_stage,error_detail,error_status;wire [15:0] error_user;
    wire [7:0] cmd_valid,cmd_ready,cmd_write,rsp_valid,rsp_ready;
    wire [183:0] cmd_addr;wire [31:0] cmd_bytes;wire [575:0] cmd_data,rsp_data;
    wire [63:0] fabric_status;logic [63:0] dut_status;
    logic [7:0] previous_write=0;
    integer mode=0,inject_client=-1,inject_write=0,response_number=0,inject_number=0,inject_status=0;
    bit injected=0;
    wire injection_eligible=mode!=16||(dut.frontend.state==dut.frontend.EMIT_READ_WAIT&&dut.token_count!=0);
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [63:0] rdata,wdata;wire [1:0] rresp,bresp;wire fabric_idle;
    wire [511:0] dma_data;wire [63:0] dma_keep;wire [15:0] dma_user;wire dma_valid,dma_last,pack_idle;logic dma_ready=0;
    integer raw[0:19999],expected[0:19999],expected_count=0,received=0,expected_user=0,expected_stage=0,expected_detail=0,expected_status=0;
    integer sequence_total=0,ids_total=0,error_total=0,dma_packets=0,case_errors=0,case_packets=0,partial_failures=0;
    bit stalled32=0,stalled512=0,stalled_error=0,stalled_completion=0;
    logic [52:0] held32;logic [592:0] held512;logic [39:0] held_error;logic [48:0] held_completion;
    bit [7:0] mem_stalled=0;logic [99:0] held_mem[0:7];
    always @*begin
        dut_status=fabric_status;
        if(!injected&&injection_eligible&&inject_client>=0&&response_number==inject_number&&previous_write[inject_client]==inject_write)
            dut_status[inject_client*8+:8]=inject_status;
    end
    bpe_tokenizer_engine dut(
        .clk(clk),.rst(rst),.admit_sequences(admit),.cfg_profile(profile),.cfg_class_base(class_base),.cfg_hash_base(hash_base),.cfg_node_base(node_base),.cfg_edge_base(edge_base),
        .cfg_node_count(node_count),.cfg_edge_count(edge_count),.cfg_work_floor(work_floor),.cfg_scalar_base(scalar_base),.cfg_scalar_bytes(scalar_bytes),
        .cfg_merge_base(merge_base),.cfg_merge_bytes(merge_bytes),.cfg_commit_base(commit_base),.cfg_commit_bytes(commit_bytes),
        .s_axis_text_tdata(s_data),.s_axis_text_tkeep(s_keep),.s_axis_text_tvalid(s_valid),.s_axis_text_tready(s_ready),.s_axis_text_tlast(s_last),.s_axis_text_tuser(s_user),
        .m_axis_tokens_tdata(t_data),.m_axis_tokens_tkeep(t_keep),.m_axis_tokens_tvalid(t_valid),.m_axis_tokens_tready(t_ready),.m_axis_tokens_tlast(t_last),.m_axis_tokens_tuser(t_user),
        .completion_valid(completion_valid),.completion_ready(completion_ready&&pack_idle),.completion_failed(completion_failed),.completion_count(completion_count),.completion_user(completion_user),
        .error_valid(error_valid),.error_ready(error_ready),.error_stage(error_stage),.error_detail(error_detail),.error_status(error_status),.error_user(error_user),
        .mem_valid(cmd_valid),.mem_ready(cmd_ready),.mem_write(cmd_write),.mem_addr(cmd_addr),.mem_bytes(cmd_bytes),.mem_data(cmd_data),
        .mem_rsp_valid(rsp_valid),.mem_rsp_ready(rsp_ready),.mem_rsp_data(rsp_data),.mem_rsp_status(dut_status),.idle(engine_idle));
    token_packager packager(
        .clk(clk),.rst(rst),.s_token(t_data),.s_keep(t_keep==15),.s_valid(t_valid),.s_ready(t_ready),.s_sequence_last(t_last),.s_user(t_user),
        .m_axis_tokens_tdata(dma_data),.m_axis_tokens_tkeep(dma_keep),.m_axis_tokens_tvalid(dma_valid),.m_axis_tokens_tready(dma_ready),.m_axis_tokens_tlast(dma_last),.m_axis_tokens_tuser(dma_user),.idle(pack_idle));
    external_memory_fabric #(.CLIENTS(8)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_data(rsp_data),.rsp_status(fabric_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    always @(negedge clk)begin dma_ready=$urandom_range(0,3)!=0;error_ready=$urandom_range(0,3)==0;end
    always @(posedge clk)if(!rst)begin
        if(stalled32&&(!t_valid||held32!=={t_user,t_last,t_keep,t_data}))$fatal(1,"Engine token changed under stall");
        stalled32=t_valid&&!t_ready;held32={t_user,t_last,t_keep,t_data};
        if(stalled512&&(!dma_valid||held512!=={dma_user,dma_last,dma_keep,dma_data}))$fatal(1,"DMA changed under stall");
        stalled512=dma_valid&&!dma_ready;held512={dma_user,dma_last,dma_keep,dma_data};
        if(stalled_error&&(!error_valid||held_error!=={error_user,error_stage,error_detail,error_status}))$fatal(1,"Error changed under stall");
        stalled_error=error_valid&&!error_ready;held_error={error_user,error_stage,error_detail,error_status};
        if(stalled_completion&&(!completion_valid||held_completion!=={completion_user,completion_failed,completion_count}))$fatal(1,"Completion changed under stall");
        stalled_completion=completion_valid&&!(completion_ready&&pack_idle);held_completion={completion_user,completion_failed,completion_count};
        for(integer c=0;c<8;c++)begin
            if(mem_stalled[c]&&(!cmd_valid[c]||held_mem[c]!=={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]}))$fatal(1,"Client %0d command changed under stall",c);
            mem_stalled[c]=cmd_valid[c]&&!cmd_ready[c];held_mem[c]={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]};
            if(cmd_valid[c]&&cmd_ready[c])previous_write[c]=cmd_write[c];
            if(injection_eligible&&c==inject_client&&rsp_valid[c]&&rsp_ready[c]&&previous_write[c]==inject_write)begin
                if(response_number==inject_number)injected<=1;
                response_number<=response_number+1;
            end
        end
        if(error_valid&&error_ready)begin
            if(mode==0||error_stage!=expected_stage||error_detail!=expected_detail||error_status!=expected_status||error_user!=expected_user)
                $fatal(1,"Unexpected engine error mode=%0d got=%0d/%0d/%0d expected=%0d/%0d/%0d",mode,error_stage,error_detail,error_status,expected_stage,expected_detail,expected_status);
            error_total++;case_errors++;
        end
        if(t_valid&&t_ready&&t_keep!=0&&t_keep!=15)$fatal(1,"Partial token keep");
        if(dma_valid&&dma_ready)begin
            if(mode!=0&&mode!=13)$fatal(1,"Failed computation released a DMA prefix mode=%0d",mode);
            if(dma_user!=expected_user)$fatal(1,"DMA context mismatch");
            for(integer lane=0;lane<16;lane++)begin
                if(dma_keep[lane*4+:4]!=0&&dma_keep[lane*4+:4]!=15)$fatal(1,"Split token on DMA");
                if(dma_keep[lane*4+:4]==15)begin
                    if(received>=expected_count||dma_data[lane*32+:32]!=expected[received])$fatal(1,"Token mismatch sequence=%0d profile=%0d index=%0d got=%0d expected=%0d",sequence_total,profile,received,dma_data[lane*32+:32],expected[received]);
                    received++;ids_total++;
                end
            end
            if(dma_last)begin
                if(mode==0&&received!=expected_count)$fatal(1,"DMA token count mismatch");
                if(mode==13&&received!=17)$fatal(1,"Release fault did not terminate the exact tentative prefix");
                dma_packets++;case_packets++;
            end
        end
    end
    task automatic configure;
        class_base=cfg[0];hash_base=cfg[1];node_base=cfg[2];edge_base=cfg[3];node_count=cfg[4];edge_count=cfg[5];work_floor=cfg[6];
        scalar_base=cfg[7];scalar_bytes=cfg[8];merge_base=cfg[9];merge_bytes=cfg[10];commit_base=cfg[11];commit_bytes=cfg[12];
        admit=1;injected=0;response_number=0;inject_client=-1;inject_number=0;inject_write=0;inject_status=2;
        received=0;case_errors=0;case_packets=0;expected_detail=0;expected_status=0;
    endtask
    task automatic send_text(input integer n,input bit corrupt_context);
        integer position_in,beat,lane;
        position_in=0;beat=0;
        do begin
            @(negedge clk);s_data=0;s_keep=0;s_user=expected_user^(corrupt_context&&beat!=0?1:0);
            for(lane=0;lane<16;lane++)if(position_in<n&&(lane==15||$urandom_range(0,2)!=0))begin
                s_data[lane*8+:8]=raw[position_in];s_keep[lane]=1;position_in++;
            end
            s_last=position_in==n;s_valid=1;do @(posedge clk);while(!s_ready);
            @(negedge clk);s_valid=0;beat++;
            // The sequence owns its snapshots even with admission closed and
            // every live configuration pin subsequently invalid.
            admit=0;profile=3;class_base='1;hash_base='1;node_base='1;edge_base='1;node_count=0;edge_count=0;
            scalar_base='1;scalar_bytes='1;merge_base='1;merge_bytes='1;commit_base='1;commit_bytes='1;work_floor=0;
        end while(position_in<n);
    endtask
    task automatic finish_sequence;
        wait(completion_valid&&pack_idle);@(negedge clk);
        if(completion_user!=expected_user||completion_failed!=(mode!=0)||completion_count!=(mode==0?expected_count:0))$fatal(1,"Wrong completion mode=%0d count=%0d",mode,completion_count);
        if(case_errors!=(mode==0?0:1)||case_packets!=((mode==0||mode==13)?1:0))$fatal(1,"Error/packet ordering mismatch");
        if(inject_client>=0&&!injected)$fatal(1,"Requested response fault was not exercised");
        admit=1;s_valid=1;
        repeat(7)begin @(negedge clk);if(s_ready)$fatal(1,"Accepted next sequence before completion ACK");end
        s_valid=0;completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;
        wait(engine_idle&&fabric_idle&&pack_idle);@(negedge clk);sequence_total++;
    endtask
    initial begin:driver
        integer fd,rc,n,k,p,context_number;
        fd=$fopen("config.txt","r");if(!fd)$fatal(1,"No engine config");
        for(integer i=0;i<13;i++)begin rc=$fscanf(fd,"%d",cfg[i]);if(rc!=1)$fatal(1,"Bad engine config");end $fclose(fd);
        configure();repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No whole-text vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d",n,k,p,context_number);
            if(rc==4)begin
                if(n>20000||k>20000)$fatal(1,"Fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",raw[i]);if(rc!=1)$fatal(1,"Bad raw fixture");end
                for(integer i=0;i<k;i++)begin rc=$fscanf(fd,"%d",expected[i]);if(rc!=1)$fatal(1,"Bad token fixture");end
                configure();mode=0;profile=p;expected_user=context_number;expected_count=k;
                send_text(n,0);finish_sequence();
                if(sequence_total%50==0)$display("PROGRESS: %0d complete raw-text tokenizer sequences",sequence_total);
            end else if(!$feof(fd))$fatal(1,"Malformed whole-text fixture");
        end $fclose(fd);
        for(integer failure=1;failure<=16;failure++)begin
            configure();mode=failure;profile=0;expected_user=16'hc000+failure;expected_count=80;
            for(integer i=0;i<80;i++)begin raw[i]=0;expected[i]=188;end
            case(failure)
                1:begin merge_base=scalar_base+16;expected_stage=1;end
                2:begin scalar_bytes=8;expected_stage=2;expected_detail=3;end
                3:begin merge_bytes=8;expected_stage=4;expected_detail=1;end
                4:begin commit_bytes=4;expected_stage=5;end
                5:begin inject_client=0;expected_stage=2;expected_detail=5;expected_status=8'h12;end
                6:begin inject_client=1;inject_write=1;inject_status=4;expected_stage=2;expected_detail=6;expected_status=4;end
                7:begin inject_client=2;expected_stage=3;expected_status=8'h12;end
                8:begin inject_client=5;expected_stage=4;expected_detail=3;expected_status=8'h12;end
                9:begin inject_client=6;inject_write=1;inject_status=4;expected_stage=4;expected_detail=2;expected_status=4;end
                10:begin inject_client=7;inject_write=1;inject_number=3;inject_status=4;expected_stage=6;expected_status=4;end
                11:begin inject_client=7;expected_stage=7;expected_status=2;end
                12:begin raw[79]=255;expected_stage=2;expected_detail=4;expected_status=1;end
                13:begin inject_client=7;inject_number=17;expected_stage=7;expected_status=2;end
                14:begin expected_stage=9;end
                15:begin merge_base=23'h7fffff;merge_bytes=16;expected_stage=1;end
                16:begin
                    for(integer i=0;i<80;i++)raw[i]=i%2==0?97:32;
                    inject_client=1;expected_stage=2;expected_detail=9;expected_status=2;
                end
            endcase
            send_text(80,failure==14);finish_sequence();if(failure==13)partial_failures++;
        end
        configure();mode=0;profile=0;expected_user=16'hbeef;expected_count=1;raw[0]=0;expected[0]=188;
        send_text(1,0);finish_sequence();
        // Keep a first beat pending while live configuration changes every
        // cycle. Admission must wait for the matching validation result and
        // retain the configuration present at the eventual handshake.
        configure();mode=0;profile=0;expected_user=16'hd00d;expected_count=1;expected[0]=188;
        @(negedge clk);s_data=0;s_keep=1;s_last=1;s_user=expected_user;s_valid=1;node_count=cfg[4]-1;
        for(integer change=0;change<6;change++)begin
            @(posedge clk);if(s_ready)$fatal(1,"Accepted configuration before its matching validation");
            @(negedge clk);node_count=cfg[4]-(change%2);
        end
        node_count=cfg[4];do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
        finish_sequence();
        if(sequence_total!=291||ids_total<24000||error_total!=16||partial_failures!=1)$fatal(1,"Engine coverage failure sequences=%0d ids=%0d errors=%0d",sequence_total,ids_total,error_total);
        $display("PASS: whole-text tokenizer: %0d sequences/%0d reference IDs; three runtime profiles, full trie/hash, 4097-byte piece, 16 errors, no compute-error DMA prefix, explicit failed readback completion, sparse AXIS, snapshots, admission, eight-client stalls and recovery",sequence_total,ids_total);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Tokenizer engine timeout state=%0d frontend=%0d merge=%0d slot=%0d",dut.state,dut.frontend.state,dut.merger.state,dut.commit_slot.state);end
endmodule
