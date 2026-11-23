`timescale 1ns/1ps
module tb_external_merge;
    logic clk=0,rst=1,cancel=0;always #2 clk=~clk;
    logic [22:0] work_base=0;logic [23:0] work_bytes=65536;
    logic [16:0] s_token=0;logic s_keep=0,s_valid=0,s_last=0,s_eos=0;logic [15:0] s_user=0;
    wire s_ready,m_valid,m_keep,m_last,m_eos,idle,error_valid;wire [16:0] m_token;wire [15:0] m_user,error_user;
    logic m_ready=0,error_ready=0,hold_output=0;wire [7:0] error_code,error_status;
    wire rank_req_valid,rank_req_ready,rank_rsp_valid,rank_rsp_ready,rank_found,rank_idle;
    wire [16:0] rank_left,rank_right,rank_merged,rank_rank;wire [7:0] rank_status;
    logic rank_gate=1,rank_response_gate=1,work_gate=1,work_response_gate=1;
    wire lookup_req_ready,lookup_rsp_valid;wire [22:0] hash_base=23'h200000;
    wire [1:0] cmd_valid,cmd_ready,cmd_write,rsp_valid,rsp_ready;wire [45:0] cmd_addr;wire [7:0] cmd_bytes;
    wire [143:0] cmd_data,rsp_data;wire [15:0] rsp_status;
    wire unit_mem_valid,unit_mem_ready,unit_mem_write,unit_rsp_ready;
    wire [22:0] unit_mem_addr;wire [3:0] unit_mem_bytes;wire [71:0] unit_mem_data;
    logic inject_bad_record=0;
    wire [71:0] unit_rsp_data=inject_bad_record&&!unit_mem_write?(rsp_data[71:0]&72'hff00000000ffffffff):rsp_data[71:0];
    logic inv=0;wire inv_ready,fabric_idle;
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [63:0] rdata,wdata;wire [1:0] rresp,bresp;
    logic read_fault=0,write_fault=0;logic [22:0] fault_line=0;
    integer expected[0:8191],source_ids[0:8191];integer expected_count=0,received=0,expected_user=0,expected_eos=0;
    integer phase=0,expected_error=0,expected_status=0,pieces=0,ids=0,packets=0,errors=0,cancelled=0;
    bit stalled=0,mem_stalled=0,rank_stalled=0,error_stalled=0;
    logic [35:0] held;logic [99:0] held_mem;logic [33:0] held_rank;logic [31:0] held_error;
    assign cmd_valid[0]=unit_mem_valid&&work_gate;assign unit_mem_ready=cmd_ready[0]&&work_gate;
    assign cmd_write[0]=unit_mem_write;assign cmd_addr[22:0]=unit_mem_addr;assign cmd_bytes[3:0]=unit_mem_bytes;assign cmd_data[71:0]=unit_mem_data;
    assign rsp_ready[0]=unit_rsp_ready&&work_response_gate;
    assign rank_req_ready=lookup_req_ready&&rank_gate;assign rank_rsp_valid=lookup_rsp_valid&&rank_response_gate;
    bpe_external_merge_unit dut(
        .clk(clk),.rst(rst),.cancel(cancel),.cfg_base(work_base),.cfg_bytes(work_bytes),
        .s_token(s_token),.s_keep(s_keep),.s_valid(s_valid),.s_ready(s_ready),.s_piece_last(s_last),.s_sequence_last(s_eos),.s_user(s_user),
        .m_token(m_token),.m_keep(m_keep),.m_valid(m_valid),.m_ready(m_ready),.m_piece_last(m_last),.m_sequence_last(m_eos),.m_user(m_user),
        .rank_req_valid(rank_req_valid),.rank_req_ready(rank_req_ready),.rank_req_left(rank_left),.rank_req_right(rank_right),
        .rank_rsp_valid(rank_rsp_valid),.rank_rsp_ready(rank_rsp_ready),.rank_rsp_found(rank_found),.rank_rsp_merged(rank_merged),.rank_rsp_rank(rank_rank),.rank_rsp_status(rank_status),
        .mem_valid(unit_mem_valid),.mem_ready(unit_mem_ready),.mem_write(unit_mem_write),.mem_addr(unit_mem_addr),.mem_bytes(unit_mem_bytes),.mem_data(unit_mem_data),
        .mem_rsp_valid(rsp_valid[0]&&work_response_gate),.mem_rsp_ready(unit_rsp_ready),.mem_rsp_data(unit_rsp_data),.mem_rsp_status(rsp_status[7:0]),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_status(error_status),.error_user(error_user),.idle(idle));
    bpe_rank_lookup lookup(
        .clk(clk),.rst(rst),.cfg_unlock(1'b0),.cfg_valid(1'b0),.cfg_ready(),.cfg_addr(18'd0),.cfg_data(72'd0),
        .req_valid(rank_req_valid&&rank_gate),.req_ready(lookup_req_ready),.req_left(rank_left),.req_right(rank_right),
        .rsp_valid(lookup_rsp_valid),.rsp_ready(rank_rsp_ready&&rank_response_gate),.rsp_found(rank_found),.rsp_merged(rank_merged),.rsp_rank(rank_rank),.rsp_status(rank_status),.idle(rank_idle),
        .hash_base(hash_base),.mem_rd_valid(cmd_valid[1]),.mem_rd_ready(cmd_ready[1]),.mem_rd_addr(cmd_addr[45:23]),.mem_rd_bytes(cmd_bytes[7:4]),
        .mem_rsp_valid(rsp_valid[1]),.mem_rsp_ready(rsp_ready[1]),.mem_rsp_data(rsp_data[143:72]),.mem_rsp_status(rsp_status[15:8]));
    assign cmd_write[1]=0;assign cmd_data[143:72]=0;
    external_memory_fabric #(.CLIENTS(2)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(inv),.invalidate_ready(inv_ready),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_data(rsp_data),.rsp_status(rsp_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(read_fault),.fault_line(fault_line),.write_fault(write_fault));
    always @(negedge clk)m_ready=!hold_output&&$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!m_valid||held!=={m_user,m_eos,m_last,m_keep,m_token}))$fatal(1,"External BPE output changed under stall");
        stalled=m_valid&&!m_ready;held={m_user,m_eos,m_last,m_keep,m_token};
        if(mem_stalled&&(!unit_mem_valid||held_mem!=={unit_mem_write,unit_mem_addr,unit_mem_bytes,unit_mem_data}))$fatal(1,"Workspace command changed under stall/cancel");
        mem_stalled=unit_mem_valid&&!unit_mem_ready;held_mem={unit_mem_write,unit_mem_addr,unit_mem_bytes,unit_mem_data};
        if(rank_stalled&&(!rank_req_valid||held_rank!=={rank_left,rank_right}))$fatal(1,"Rank command changed under stall/cancel");
        rank_stalled=rank_req_valid&&!rank_req_ready;held_rank={rank_left,rank_right};
        if(error_stalled&&(!error_valid||held_error!=={error_user,error_code,error_status}))$fatal(1,"BPE error changed under stall");
        error_stalled=error_valid&&!error_ready;held_error={error_user,error_code,error_status};
        if(error_valid&&phase!=1)$fatal(1,"Unexpected external BPE error %0d/%0d",error_code,error_status);
        if(error_valid&&error_ready)begin
            if(error_code!=expected_error||error_status!=expected_status||error_user!=expected_user)$fatal(1,"Wrong BPE error code/status/context");
            errors++;
        end
        if(m_valid&&m_ready)begin
            if(phase==0)begin
                if(m_user!=expected_user)$fatal(1,"External BPE context mismatch");
                if(m_keep)begin if(received>=expected_count||m_token!=expected[received])$fatal(1,"External BPE token mismatch piece=%0d index=%0d got=%0d expected=%0d",pieces,received,m_token,expected[received]);received++;ids++;end
                if(m_last)begin if(received!=expected_count||m_eos!=expected_eos)$fatal(1,"External BPE count/EOS mismatch");pieces++;end
            end else if(phase==1)$fatal(1,"Failed BPE piece emitted tokens");
            if(m_last)packets++;
        end
    end
    task automatic send(input integer id,input bit keep,input bit last,input bit eos);
        @(negedge clk);s_token=id;s_keep=keep;s_last=last;s_eos=eos;s_valid=1;
        do @(posedge clk);while(!s_ready);
        @(negedge clk);s_valid=0;
    endtask
    task automatic drain;
        wait(idle&&rank_idle&&fabric_idle);@(negedge clk);
    endtask
    task automatic invalidate;
        @(negedge clk);inv=1;do @(posedge clk);while(!inv_ready);@(negedge clk);inv=0;
    endtask
    task automatic accept_error;
        wait(error_valid);repeat(6)@(negedge clk);
        error_ready=1;@(posedge clk);@(negedge clk);error_ready=0;drain();
    endtask
    initial begin:driver
        integer fd,rc,n,k,eos,context_number,target,default_base,default_bytes,before_writes;
        integer cancel_states[0:5];
        fd=$fopen("config.txt","r");if(!fd)$fatal(1,"Missing merge config");rc=$fscanf(fd,"%d %d",default_base,default_bytes);$fclose(fd);if(rc!=2)$fatal(1,"Bad merge config");
        work_base=default_base;work_bytes=default_bytes;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("pieces.txt","r");if(!fd)$fatal(1,"Missing external merge vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d",n,k,eos,context_number);
            if(rc==4)begin
                if(n>8192||k>8192)$fatal(1,"Merge fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",source_ids[i]);if(rc!=1)$fatal(1,"Missing input ID");end
                for(integer i=0;i<k;i++)begin rc=$fscanf(fd,"%d",expected[i]);if(rc!=1)$fatal(1,"Missing expected ID");end
                expected_count=k;received=0;expected_user=context_number;expected_eos=eos;s_user=context_number;target=packets+1;
                work_base=default_base+((pieces%7)==0?3:0);work_bytes=default_bytes;
                if(n==0)send(0,0,1,eos!=0);else for(integer i=0;i<n;i++)begin
                    send(source_ids[i],1,i+1==n,(i+1==n)&&eos!=0);
                    if(i==0)begin work_base=23'h7fffff;work_bytes='1;end
                end
                wait(packets==target);drain();if(pieces%500==0)$display("PROGRESS: %0d external BPE reference pieces",pieces);
            end else if(!$feof(fd))$fatal(1,"Invalid external merge fixture");
        end
        $fclose(fd);
        // Explicit zero-keep EOF after real bytes must rewrite the last next
        // pointer; ignored empty nonfinal transfers must not start a piece.
        work_base=default_base;work_bytes=default_bytes;send(0,0,0,0);if(!idle)$fatal(1,"Empty nonfinal transfer started a piece");
        expected_user=16'hba5e;s_user=expected_user;expected_count=2;expected[0]=188;expected[1]=188;received=0;expected_eos=1;target=packets+1;
        send(188,1,0,0);send(188,1,0,0);send(0,0,1,1);wait(packets==target);drain();
        phase=1;expected_user=16'hcafe;s_user=expected_user;
        for(integer fault=0;fault<6;fault++)begin
            work_base=default_base;work_bytes=default_bytes;read_fault=0;write_fault=0;inject_bad_record=0;invalidate();before_writes=memory_model.writes;
            case(fault)
                0:begin work_bytes=0;expected_error=1;expected_status=0;end
                1:begin work_base=23'h7fffff;work_bytes=16;expected_error=6;expected_status=0;end
                2:begin write_fault=1;expected_error=2;expected_status=4;end
                3:begin read_fault=1;fault_line=default_base&~63;expected_error=2;expected_status=2;end
                4:begin read_fault=1;fault_line=23'h200000;expected_error=3;expected_status=8'h12;end
                5:begin inject_bad_record=1;expected_error=4;expected_status=0;end
            endcase
            if(fault<3)send(0,1,1,1);else begin send(0,1,0,0);send(0,1,1,1);end
            accept_error();if(fault<2&&memory_model.writes!=before_writes)$fatal(1,"Invalid workspace escaped to AXI");
        end
        read_fault=0;write_fault=0;inject_bad_record=0;work_base=default_base;work_bytes=default_bytes;
        expected_error=5;expected_status=0;send(0,1,0,0);wait(s_ready);s_user=16'hcaff;send(0,1,1,1);accept_error();s_user=expected_user;
        phase=2;
        cancel_states[0]=dut.STORE_REQ;cancel_states[1]=dut.STORE_WAIT;cancel_states[2]=dut.RANK_REQ;
        cancel_states[3]=dut.RANK_WAIT;cancel_states[4]=dut.EMIT;cancel_states[5]=dut.LOAD;
        for(integer trial=0;trial<6;trial++)begin
            work_gate=trial!=0;work_response_gate=trial!=1;rank_gate=trial!=2;rank_response_gate=trial!=3;hold_output=trial==4;
            if(trial==2||trial==3||trial==4)begin send(0,1,0,0);send(0,1,1,1);end
            else send(0,1,0,0);
            wait(dut.state==cancel_states[trial]);@(negedge clk);cancel=1;
            repeat(5)@(negedge clk);
            work_gate=1;work_response_gate=1;rank_gate=1;rank_response_gate=1;hold_output=0;
            drain();cancel=0;cancelled++;
        end
        phase=0;expected_count=1;expected[0]=0;received=0;expected_eos=1;target=packets+1;
        send(0,1,1,1);wait(packets==target);drain();
        if(pieces<1000||ids<5000||errors!=7||cancelled!=6)$fatal(1,"External merge coverage failure");
        $display("PASS: external linked-list BPE: %0d native-reference pieces/%0d exact IDs, >4096-byte piece, %0d errors, %0d cancellation phases; runtime bounds, snapshots, unaligned records, stalls and recovery",pieces,ids,errors,cancelled);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"External BPE timeout");end
endmodule
