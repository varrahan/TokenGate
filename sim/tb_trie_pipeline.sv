`timescale 1ns/1ps
module tb_trie_pipeline;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic cfg_unlock=0,valid=0,ready_out=0,last=0;logic [17:0] parent=0;logic [7:0] label=0;logic [15:0] user_id=0;
    logic [22:0] node_base=0,edge_base=0;logic [31:0] node_count=0,edge_count=0;
    wire ready,output_valid,found,terminal,output_last,idle;wire [17:0] child;wire [16:0] token;wire [15:0] output_user;wire [7:0] status;
    wire [2:0] rv,rr,rrv,rrr;wire [68:0] ra;wire [11:0] rn;wire [215:0] rd;wire [23:0] rs;
    logic inv=0;wire inv_ready,fabric_idle;
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [63:0] rdata,wdata;wire [1:0] rresp,bresp;
    logic read_fault=0;logic [22:0] fault_line=0;
    integer configured_nodes,configured_edges,configured_node_base,configured_edge_base,zero_child,leaf_parent,leaf_label,leaf_child;
    integer head=0,tail=0,requests=0,checked=0,max_occupied=0;
    integer expected_found[0:7],expected_terminal[0:7],expected_child[0:7],expected_token[0:7],expected_last[0:7],expected_user[0:7],expected_status[0:7];
    integer stage_reads[0:2];bit stalled=0,rd_stalled[0:2];logic [61:0] held;logic [26:0] held_read[0:2];
    trie_search_pipeline dut(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_node_base(node_base),.cfg_edge_base(edge_base),.cfg_node_count(node_count),.cfg_edge_count(edge_count),
        .req_valid(valid),.req_ready(ready),.req_node(parent),.req_byte(label),.req_last(last),.req_user(user_id),
        .rsp_valid(output_valid),.rsp_ready(ready_out),.rsp_match(found),.rsp_terminal(terminal),.rsp_next_node(child),.rsp_token(token),.rsp_last(output_last),.rsp_user(output_user),.rsp_status(status),
        .mem_rd_valid(rv),.mem_rd_ready(rr),.mem_rd_addr(ra),.mem_rd_bytes(rn),.mem_rsp_valid(rrv),.mem_rsp_ready(rrr),.mem_rsp_data(rd),.mem_rsp_status(rs),.idle(idle));
    external_memory_fabric #(.CLIENTS(3)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(inv),.invalidate_ready(inv_ready),.s_valid(rv),.s_ready(rr),.s_write(3'd0),.s_addr(ra),.s_bytes(rn),.s_data(216'd0),
        .rsp_valid(rrv),.rsp_ready(rrr),.rsp_data(rd),.rsp_status(rs),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
        .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),
        .rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),
        .wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),.bresp(bresp),.bvalid(bvalid),.bready(bready),
        .read_fault(read_fault),.fault_line(fault_line),.write_fault(1'b0));
    always @(negedge clk)ready_out=(tail>=4||head>0)&&$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin:monitor
        integer slot,occupied;
        if(stalled&&(!output_valid||held!=={output_user,output_last,status,found,terminal,child,token}))$fatal(1,"Trie result changed under backpressure");
        stalled=output_valid&&!ready_out;held={output_user,output_last,status,found,terminal,child,token};
        for(integer i=0;i<3;i++)begin
            if(rd_stalled[i]&&(!rv[i]||held_read[i]!=={ra[i*23+:23],rn[i*4+:4]}))$fatal(1,"Trie memory command changed under backpressure");
            rd_stalled[i]=rv[i]&&!rr[i];held_read[i]={ra[i*23+:23],rn[i*4+:4]};
            if(rv[i]&&rr[i])stage_reads[i]++;
        end
        occupied=int'(dut.valid0)+int'(dut.state1!=0)+int'(dut.state2!=0)+int'(dut.state3!=0);
        if(occupied>max_occupied)max_occupied=occupied;
        if(valid&&ready)begin requests++;if(idle)$fatal(1,"Trie idle on admission");end
        if(awvalid||wvalid)$fatal(1,"Read-only trie issued external write");
        if(output_valid&&ready_out)begin
            slot=head%8;
            if(head>=tail||found!=expected_found[slot]||terminal!=expected_terminal[slot]||child!=expected_child[slot]||token!=expected_token[slot]||
               output_last!=expected_last[slot]||output_user!=expected_user[slot]||status!=expected_status[slot])
                $fatal(1,"Trie mismatch query=%0d status=%0d/%0d match=%0d/%0d child=%0d/%0d token=%0d/%0d",head,status,expected_status[slot],found,expected_found[slot],child,expected_child[slot],token,expected_token[slot]);
            head++;checked++;
        end
    end
    task automatic query(input integer n,input integer byte_value,input integer match_value,input integer terminal_value,input integer child_value,input integer token_value,
                         input integer last_value,input integer user_value,input integer status_value,input integer bad_config=0);
        integer slot;
        @(negedge clk);
        if(tail-head>=8)$fatal(1,"Trie scoreboard queue overflow");
        slot=tail%8;expected_found[slot]=match_value;expected_terminal[slot]=terminal_value;expected_child[slot]=child_value;expected_token[slot]=token_value;
        expected_last[slot]=last_value;expected_user[slot]=user_value;expected_status[slot]=status_value;
        node_base=bad_config==1?23'h7fffff:configured_node_base;edge_base=configured_edge_base;
        node_count=bad_config==2?0:configured_nodes;edge_count=configured_edges;
        parent=n;label=byte_value;last=last_value;user_id=user_value;valid=1;
        do @(posedge clk);while(!ready);
        tail++;@(negedge clk);valid=0;
        node_base=23'h7fffff;edge_base=23'h7fffff;node_count=0;edge_count=0;
    endtask
    task automatic drain;
        wait(head==tail);@(negedge clk);if(!idle||!fabric_idle)$fatal(1,"Trie did not drain all stages");
    endtask
    task automatic invalidate;
        @(negedge clk);inv=1;
        do @(posedge clk);while(!inv_ready);
        @(negedge clk);inv=0;
    endtask
    function automatic [47:0] peek_node(input integer address);
        begin for(integer i=0;i<6;i++)peek_node[i*8+:8]=memory_model.memory[(address+i)/8][((address+i)%8)*8+:8];end
    endfunction
    task automatic poke_node(input integer address,input logic[47:0] value);
        for(integer i=0;i<6;i++)memory_model.memory[(address+i)/8][((address+i)%8)*8+:8]=value[i*8+:8];
    endtask
    initial begin:driver
        integer fd,rc,n,b,f,t,c,id,l,u,before_reads;
        logic [47:0] original_node;logic [63:0] original_edge;
        for(integer i=0;i<3;i++)begin stage_reads[i]=0;rd_stalled[i]=0;end
        fd=$fopen("config.txt","r");if(!fd)$fatal(1,"Missing trie config");
        rc=$fscanf(fd,"%d %d %d %d %d %d %d %d",configured_node_base,configured_edge_base,configured_nodes,configured_edges,zero_child,leaf_parent,leaf_label,leaf_child);
        if(rc!=8)$fatal(1,"Invalid trie config");$fclose(fd);
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("queries.txt","r");if(!fd)$fatal(1,"Missing trie queries");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d %d %d %d",n,b,f,t,c,id,l,u);
            if(rc==8)query(n,b,f,t,c,id,l,u,0);else if(!$feof(fd))$fatal(1,"Invalid trie query");
        end
        $fclose(fd);drain();
        before_reads=stage_reads[0]+stage_reads[1]+stage_reads[2];
        query(configured_nodes,0,0,0,0,0,1,16'hcafe,1);drain();
        query(0,0,0,0,0,0,1,16'hcafe,1,1);drain();
        query(0,0,0,0,0,0,1,16'hcafe,1,2);drain();
        if(before_reads!=stage_reads[0]+stage_reads[1]+stage_reads[2])$fatal(1,"Invalid trie query reached memory");
        // Actual external-memory corruption and bus failures at each stage.
        original_node=peek_node(configured_node_base);poke_node(configured_node_base,original_node|(48'd1<<45));
        invalidate();query(0,0,0,0,0,0,1,1,2);drain();poke_node(configured_node_base,original_node);
        original_edge=memory_model.memory[configured_edge_base/8];
        memory_model.memory[configured_edge_base/8][31:0]=0;
        invalidate();query(0,0,0,0,0,0,1,2,3);drain();memory_model.memory[configured_edge_base/8]=original_edge;
        original_node=peek_node(configured_node_base+leaf_child*6);poke_node(configured_node_base+leaf_child*6,original_node&~(48'd1<<44));
        invalidate();query(leaf_parent,leaf_label,0,0,0,0,1,3,2);drain();poke_node(configured_node_base+leaf_child*6,original_node);
        for(integer stage=0;stage<3;stage++)begin
            invalidate();read_fault=1;
            case(stage)
                0:fault_line=configured_node_base&~63;
                1:fault_line=configured_edge_base&~63;
                2:fault_line=(configured_node_base+zero_child*6)&~63;
            endcase
            if(stage==2&&fault_line==(configured_node_base&~63))$fatal(1,"Child fault fixture aliases parent line");
            query(0,0,0,0,0,0,1,stage+10,(stage+1)*16+2);drain();read_fault=0;
        end
        if(checked<400000||max_occupied!=4||stage_reads[0]==0||stage_reads[1]==0||stage_reads[2]==0)$fatal(1,"Incomplete trie coverage");
        $display("PASS: four-stage trie pipeline: %0d transitions/misses, all %0d nodes/%0d edges, four occupied stages, %0d/%0d/%0d reads; snapshots, bounds, corruption, bus errors and stalls",checked,configured_nodes,configured_edges,stage_reads[0],stage_reads[1],stage_reads[2]);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"Trie pipeline timeout");end
endmodule
