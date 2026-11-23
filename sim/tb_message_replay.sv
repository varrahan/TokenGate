`timescale 1ns/1ps
module tb_message_replay;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0;wire start_ready;logic [22:0] start_base=0;logic [31:0] start_bytes=0;logic [15:0] start_user=0;
    wire [511:0] m_axis_tdata;wire [63:0] m_axis_tkeep;wire m_axis_tvalid,m_axis_tlast,m_axis_abort;wire [15:0] m_axis_tuser;logic m_axis_tready=0;
    wire result_valid;logic result_ready=0;wire [7:0] result_status,result_memory_status;
    wire mem_valid,mem_write,mem_rsp_ready,idle;logic mem_ready=0,mem_rsp_valid=0;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data;logic [71:0] mem_rsp_data=0;logic [7:0] mem_rsp_status=0;
    transport_message_replay dut(.*);
    integer length=0,fault=-1,expected_status=0,expected_bytes=0,observed=0,requests=0,wait_cycles=0,cases=0,stalls=0,faults=0;bit end_seen=0,pending=0;
    reg [22:0] base;reg [15:0] user_id;
    function automatic [7:0] payload(input integer position);
        payload=8'(position*37+(position>>5)*19+7);
    endfunction
    bit axis_stalled=0,result_stalled=0,command_stalled=0;logic [593:0] held_axis;logic [15:0] held_result;logic [99:0] held_command;
    wire [593:0] axis_bundle={m_axis_tdata,m_axis_tkeep,m_axis_tlast,m_axis_tuser,m_axis_abort};
    always @(negedge clk)begin
        m_axis_tready=$urandom_range(0,4)==0;
        mem_ready=!pending&&!mem_rsp_valid&&$urandom_range(0,3)!=0;
    end
    always @(posedge clk)if(!rst)begin
        if(axis_stalled&&(!m_axis_tvalid||held_axis!==axis_bundle))$fatal(1,"Replay beat/abort changed under forced backpressure");axis_stalled=m_axis_tvalid&&!m_axis_tready;held_axis=axis_bundle;if(axis_stalled)stalls++;
        if(result_stalled&&(!result_valid||held_result!=={result_status,result_memory_status}))$fatal(1,"Replay result changed under stall");result_stalled=result_valid&&!result_ready;held_result={result_status,result_memory_status};
        if(command_stalled&&(!mem_valid||held_command!=={mem_write,mem_addr,mem_bytes,mem_data}))$fatal(1,"Replay read command changed under stall");command_stalled=mem_valid&&!mem_ready;held_command={mem_write,mem_addr,mem_bytes,mem_data};
        if((^{start_ready,m_axis_tvalid,result_valid,mem_valid,mem_rsp_ready})===1'bx||m_axis_tvalid&&((^axis_bundle)===1'bx)||result_valid&&((^held_result)===1'bx)||mem_valid&&((^held_command)===1'bx))$fatal(1,"Unknown replay interface");
        if(mem_valid&&mem_ready)begin
            if(mem_write||mem_addr!=base+requests*8||mem_bytes!=(length-requests*8>=8?8:length-requests*8))$fatal(1,"Replay read address/count mismatch case=%0d",cases);
            mem_rsp_data=0;
            for(integer i=0;i<8;i++)if(i<mem_bytes)mem_rsp_data[i*8+:8]=payload(mem_addr-base+i);
            mem_rsp_status=requests==fault?8'h62:0;requests++;pending=1;wait_cycles=$urandom_range(1,8);
        end
        if(pending)begin
            if(wait_cycles==0)begin mem_rsp_valid<=1;pending=0;end else wait_cycles--;
        end
        if(mem_rsp_valid&&mem_rsp_ready)mem_rsp_valid<=0;
        if(m_axis_tvalid&&m_axis_tready)begin
            if(end_seen||m_axis_tuser!=user_id||m_axis_abort!=(expected_status!=0&&m_axis_tlast))$fatal(1,"Replay terminal/context mismatch case=%0d",cases);
            if(!m_axis_tlast&&m_axis_tkeep!==64'hffffffffffffffff||m_axis_tlast&&m_axis_tkeep!==(expected_status!=0?64'd0:expected_bytes-observed>=64?64'hffffffffffffffff:(64'd1<<(expected_bytes-observed))-1'b1))$fatal(1,"Replay keep mismatch case=%0d",cases);
            for(integer lane=0;lane<64;lane++)if(m_axis_tkeep[lane])begin
                if(observed>=expected_bytes||m_axis_tdata[lane*8+:8]!==payload(observed))$fatal(1,"Replay byte mismatch case=%0d byte=%0d",cases,observed);
                observed++;
            end
            if(m_axis_tlast)begin if(observed!=expected_bytes)$fatal(1,"Replay length mismatch case=%0d",cases);end_seen=1;end
        end
    end
    task run(input integer bytes,input integer fault_index,input [22:0] address);
        begin
            @(negedge clk);length=bytes;fault=fault_index;base=address;user_id=16'(cases*43+7);requests=0;observed=0;end_seen=0;
            expected_status={1'b0,address}+64'(bytes)>(64'd1<<23)?1:fault_index>=0?2:0;
            expected_bytes=expected_status==1?0:fault_index>=0?(fault_index/8)*64:bytes;
            start_base=address;start_bytes=32'(bytes);start_user=user_id;start_valid=1;
            do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;start_base='1;start_bytes='1;start_user='1;
            wait(result_valid);
            if(!end_seen||result_status!=expected_status||result_memory_status!=(fault_index>=0?98:0))$fatal(1,"Replay completion mismatch case=%0d",cases);
            repeat($urandom_range(2,10))@(negedge clk);result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;wait(idle);
            if(fault_index>=0)faults++;cases++;
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);rst=0;
        for(integer n=0;n<=130;n++)run(n,-1,23'h200003);
        for(integer n=0;n<40;n++)run($urandom_range(131,4097),-1,23'h200003);
        for(integer n=0;n<16;n++)run(128,n,23'h200003);
        run(2,-1,23'h7fffff);run(0,-1,23'h7fffff);run(32'h7fffffff,-1,23'h200003);
        if(stalls<100||faults!=16)$fatal(1,"Insufficient replay backpressure coverage");
        $display("PASS: 512-bit message replay: %0d cases/%0d stalled beat cycles/%0d read faults; exact bytes/keeps/context, empty/partial packets, bounds, stable abort/result and snapshots",cases,stalls,faults);$finish;
    end
    initial begin #(64'd20000000);$fatal(1,"Replay unit timeout case=%0d",cases);end
endmodule
