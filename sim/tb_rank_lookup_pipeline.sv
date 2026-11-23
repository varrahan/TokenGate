`timescale 1ns/1ps
// Independent command/response memory model. This is a lookup unit test;
// the full Tokenizer/HyperBus regression exercises the physical-word contract.
module tb_rank_lookup_pipeline;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic cfg_unlock=0,cfg_valid=0,req_valid=0,rsp_ready=0;
    logic [16:0] req_left=0,req_right=0;
    logic [22:0] hash_base=0;
    wire req_ready,cfg_ready,rsp_valid,rsp_found,idle;
    wire [16:0] rsp_merged,rsp_rank;
    wire [7:0] rsp_status;
    wire mem_rd_valid,mem_rsp_ready;
    wire [22:0] mem_rd_addr;
    wire [3:0] mem_rd_bytes;
    logic mem_rsp_valid=0;
    logic [71:0] mem_rsp_data=0;
    logic [7:0] mem_rsp_status=0;
    integer cycle=0,mode=0,reads=0,total_reads=0,passed=0,aborts=0;
    integer pending_delay=0,expected_slot=0;
    logic pending=0;
    logic [22:0] expected_base=0;
    logic [16:0] expected_left=0,expected_right=0;
    bit stalled=0;
    logic [26:0] held_command;
    wire mem_rd_ready=!rst&&!pending&&!mem_rsp_valid&&cycle%7!=0&&cycle%7!=1;
    bpe_rank_lookup #(.ID_WIDTH(17),.RANK_WIDTH(17),.HASH_ADDR_WIDTH(18),
        .EXTERNAL_MEMORY(1),.MEMORY_ADDR_WIDTH(23)) dut(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),
        .cfg_addr(18'h3ffff),.cfg_data(72'hffffffffffffffffff),
        .req_valid(req_valid),.req_ready(req_ready),.req_left(req_left),.req_right(req_right),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_found(rsp_found),
        .rsp_merged(rsp_merged),.rsp_rank(rsp_rank),.rsp_status(rsp_status),.idle(idle),
        .hash_base(hash_base),.mem_rd_valid(mem_rd_valid),.mem_rd_ready(mem_rd_ready),
        .mem_rd_addr(mem_rd_addr),.mem_rd_bytes(mem_rd_bytes),.mem_rsp_valid(mem_rsp_valid),
        .mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status));
    function automatic [71:0] entry(input [16:0] left_id,input [16:0] right_id);
        reg [71:0] word_value;
        begin
            word_value=0;word_value[0+:17]=left_id;word_value[17+:17]=right_id;
            word_value[34+:17]=17'd321;word_value[51+:17]=17'd777;word_value[68]=1;
            entry=word_value;
        end
    endfunction
    always @(posedge clk)begin
        cycle<=cycle+1;
        if(rst)begin
            pending<=0;pending_delay<=0;mem_rsp_valid<=0;stalled=0;
        end else begin
            assert(!cfg_ready)else $fatal(1,"External lookup accepted native configuration");
            if(stalled)assert(mem_rd_valid&&held_command==={mem_rd_addr,mem_rd_bytes})
                else $fatal(1,"Lookup command changed under backpressure");
            stalled=mem_rd_valid&&!mem_rd_ready;held_command={mem_rd_addr,mem_rd_bytes};
            if(mem_rsp_valid&&mem_rsp_ready)mem_rsp_valid<=0;
            if(pending)begin
                if(pending_delay==0)begin mem_rsp_valid<=1;pending<=0;end
                else pending_delay<=pending_delay-1;
            end
            if(mem_rd_valid&&mem_rd_ready)begin
                assert(mem_rd_bytes==9&&mem_rd_addr==expected_base+9*((expected_slot+reads)&262143))
                    else $fatal(1,"Wrong slot address case=%0d probe=%0d got=%0d",mode,reads,mem_rd_addr);
                assert({1'b0,mem_rd_addr}+9<=8388608)else $fatal(1,"Out-of-range memory request");
                mem_rsp_data<=entry(expected_left,expected_right);mem_rsp_status<=0;
                case(mode)
                    1:if(reads<2)mem_rsp_data<=entry(17'd111,17'd222);
                    2:mem_rsp_data<=0;
                    3:mem_rsp_status<=2;
                    5,6:if(reads==0)mem_rsp_data<=entry(17'd111,17'd222);
                    7:mem_rsp_data<=entry(17'd111,17'd222);
                endcase
                pending<=1;pending_delay<=mode==10?30:cycle%4;
                reads=reads+1;total_reads=total_reads+1;
            end
        end
    end
    task automatic start_query(input integer new_mode,input [22:0] base,
        input [16:0] left_id,input [16:0] right_id,input integer slot);
        @(negedge clk);assert(idle)else $fatal(1,"Lookup not idle");
        mode=new_mode;expected_base=base;expected_slot=slot;expected_left=left_id;expected_right=right_id;reads=0;
        hash_base=base;req_left=left_id;req_right=right_id;cfg_unlock=0;cfg_valid=0;req_valid=1;rsp_ready=0;
        do @(posedge clk);while(!req_ready);
        @(negedge clk);req_valid=0;
        // Poison all live inputs immediately after admission. Only latched
        // query/configuration values may affect this transaction.
        hash_base=23'h7fffff;req_left=17'h1ffff;req_right=17'h1fffe;cfg_unlock=1;cfg_valid=1;
    endtask
    task automatic finish_query(input bit found,input [7:0] status,input integer read_count);
        reg [42:0] held_result;
        while(!rsp_valid)@(negedge clk);
        assert(rsp_found===found&&rsp_status===status&&reads==read_count)
            else $fatal(1,"Wrong result case=%0d found=%0d status=%0d reads=%0d",mode,rsp_found,rsp_status,reads);
        if(found)assert(rsp_merged==321&&rsp_rank==777)else $fatal(1,"Wrong merge/rank");
        else assert(rsp_merged==0&&rsp_rank==0)else $fatal(1,"Failed query leaked merge/rank");
        held_result={rsp_status,rsp_found,rsp_merged,rsp_rank};
        repeat(9)begin
            @(negedge clk);assert(rsp_valid&&held_result==={rsp_status,rsp_found,rsp_merged,rsp_rank}&&!req_ready&&!mem_rd_valid)
                else $fatal(1,"Lookup result changed while held");
        end
        rsp_ready=1;@(negedge clk);rsp_ready=0;cfg_unlock=0;cfg_valid=0;
        assert(idle)else $fatal(1,"Lookup did not return idle");
        passed++;$display("RANK_CASE_PASS case=%0d reads=%0d",mode,reads);
    endtask
    task automatic abort_query(input integer target_state);
        while(dut.state!=target_state)@(negedge clk);
        rst=1;repeat(3)@(negedge clk);rst=0;cfg_unlock=0;cfg_valid=0;
        repeat(40)begin @(negedge clk);assert(idle&&!rsp_valid&&!mem_rd_valid)
            else $fatal(1,"Reset left a stale transaction");end
        aborts++;
        start_query(0,23'd37,17'd123,17'd456,228916);finish_query(1,0,1);
    endtask
    initial begin
        repeat(30)@(negedge clk);rst=0;
        start_query(0,23'd37,17'd123,17'd456,228916);finish_query(1,0,1);
        start_query(1,23'd63,17'd123,17'd456,228916);finish_query(1,0,3);
        start_query(2,23'd12,17'd123,17'd456,228916);finish_query(0,0,1);
        start_query(3,23'd11,17'd123,17'd456,228916);finish_query(0,8'h12,1);
        start_query(4,23'd8388600,17'd0,17'd0,0);finish_query(0,1,0);
        start_query(5,23'd8388590,17'd0,17'd0,0);finish_query(1,0,2);
        start_query(6,23'd8388591,17'd0,17'd0,0);finish_query(0,1,1);
        // The complete 18-bit table is probed, including wrap to slot zero.
        start_query(7,23'd0,17'd123,17'd456,228916);finish_query(0,0,262144);
        start_query(8,23'd37,17'd123,17'd456,228916);abort_query(4);
        start_query(9,23'd37,17'd123,17'd456,228916);abort_query(5);
        start_query(10,23'd37,17'd123,17'd456,228916);abort_query(2);
        assert(passed==11&&aborts==3&&total_reads==262157)else $fatal(1,"Incomplete test coverage %0d/%0d/%0d",passed,aborts,total_reads);
        $display("RANK_PIPELINE_PASS completed_queries=%0d reset_aborts=%0d total_reads=%0d full_probe_reads=262144",passed,aborts,total_reads);$finish;
    end
    initial begin #(64'd100000000);$fatal(1,"Rank lookup watchdog");end
endmodule
