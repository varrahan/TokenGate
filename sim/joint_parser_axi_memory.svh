// External Parser memory BFM. The real production cache and arbiter precede it.
// Independent AR/AW ownership; deterministic stalls; R/B stable until accepted.
byte unsigned parser_bank[0:8388607];
integer parser_reads=0,parser_writes=0,parser_memory_cycle=0;
integer pr_address=0,pr_beats=0,pr_index=0,pw_address=0,pw_beats=0,pw_index=0;
bit pr_active=0,pw_active=0;
always @(posedge app_clk)begin : parser_axi_accept
    if(rst)begin
        pr_active=0;pw_active=0;pr_index=0;pw_index=0;
        p_axi_rvalid<=0;p_axi_bvalid<=0;
    end else begin
        if(p_axi_arvalid&&p_axi_arready)begin
            assert(!pr_active&&!p_axi_rvalid&&p_axi_arsize==3&&p_axi_arburst==1&&
                   p_axi_araddr+8*(integer'(p_axi_arlen)+1)<=8388608)
                else $fatal(1,"Invalid Parser AXI AR geometry");
            pr_active=1;pr_address=integer'(p_axi_araddr);pr_beats=integer'(p_axi_arlen)+1;pr_index=0;parser_reads++;
        end
        if(p_axi_rvalid&&p_axi_rready)begin
            p_axi_rvalid<=0;pr_index++;
            if(pr_index==pr_beats)pr_active=0;
        end
        if(p_axi_awvalid&&p_axi_awready)begin
            assert(!pw_active&&!p_axi_bvalid&&p_axi_awsize==3&&p_axi_awburst==1&&
                   p_axi_awaddr+8*(integer'(p_axi_awlen)+1)<=8388608)
                else $fatal(1,"Invalid Parser AXI AW geometry");
            pw_active=1;pw_address=integer'(p_axi_awaddr);pw_beats=integer'(p_axi_awlen)+1;pw_index=0;parser_writes++;
        end
        if(p_axi_wvalid&&p_axi_wready)begin
            assert(pw_active&&p_axi_wlast==(pw_index+1==pw_beats))else $fatal(1,"Parser WLAST/ownership");
            for(integer lane=0;lane<8;lane++)if(p_axi_wstrb[lane])begin
                assert(pw_address+pw_index*8+lane>=6903552)else $fatal(1,"Parser modified protected model");
                parser_bank[pw_address+pw_index*8+lane]=p_axi_wdata[lane*8+:8];
            end
            pw_index++;
            if(pw_index==pw_beats)begin pw_active=0;p_axi_bvalid<=1;p_axi_bresp<=0;end
        end
        // A newly generated B response is not visible to the DUT until NBA.
        // Clear responses at the negative edge using the sampled handshake.
    end
end
bit parser_b_accepted=0;
always @(posedge app_clk)parser_b_accepted<=!rst&&p_axi_bvalid&&p_axi_bready;
always @(negedge app_clk)begin : parser_axi_drive
    parser_memory_cycle++;
    if(parser_b_accepted)p_axi_bvalid=0;
    p_axi_arready=!rst&&!pr_active&&!p_axi_rvalid&&parser_memory_cycle%7>=2;
    p_axi_awready=!rst&&!pw_active&&!p_axi_bvalid&&parser_memory_cycle%11>=3;
    p_axi_wready=!rst&&pw_active&&parser_memory_cycle%5>=2;
    if(!rst&&pr_active&&!p_axi_rvalid&&parser_memory_cycle%9>=3)begin
        for(integer lane=0;lane<8;lane++)p_axi_rdata[lane*8+:8]=parser_bank[pr_address+pr_index*8+lane];
        p_axi_rresp=0;p_axi_rlast=pr_index+1==pr_beats;p_axi_rvalid=1;
    end
end
