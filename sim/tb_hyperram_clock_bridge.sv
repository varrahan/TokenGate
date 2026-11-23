`timescale 1ps/1ps
module tb_hyperram_clock_bridge;
    logic app_clk=0,mem_clk=0,reset_request=1;
    integer app_half=2000,mem_half=2500,mem_phase=700;
    wire app_reset,mem_reset;
    logic s_cmd_valid=0,s_cmd_write=0;
    wire s_cmd_ready;
    logic [22:0] s_cmd_address=0;
    logic [6:0] s_cmd_bytes=0;
    logic [511:0] s_cmd_data=0;
    logic [63:0] s_cmd_strobes=0;
    wire m_cmd_valid,m_cmd_write;
    logic m_cmd_ready=0;
    wire [22:0] m_cmd_address;
    wire [6:0] m_cmd_bytes;
    wire [511:0] m_cmd_data;
    wire [63:0] m_cmd_strobes;
    logic m_rsp_valid=0,m_rsp_error=0;
    wire m_rsp_ready;
    logic [7:0] m_rsp_detail=0;
    logic [511:0] m_rsp_data=0;
    wire s_rsp_valid,s_rsp_error;
    logic s_rsp_ready=0;
    wire [7:0] s_rsp_detail;
    wire [511:0] s_rsp_data;
    wire [3:0] fifo_errors;
    hyperram_clock_bridge dut(.*);
    typedef struct packed {
        logic write_mode;
        logic [22:0] address;
        logic [6:0] bytes_count;
        logic [511:0] data;
        logic [63:0] strobes;
    } command_t;
    command_t expected_commands[$];
    logic [520:0] expected_responses[$],pending_responses[$];
    integer sent=0,received=0,responses_sent=0,responses_received=0;
    integer source_holds=0,response_holds=0,epoch=0,limit=0;
    bit produce=0,hold_memory=1,hold_application=1;
    logic [31:0] source_random=32'h15a37c91,memory_random=32'h62b81f03;
    logic held_source=0,held_command=0,held_response=0,held_result=0;
    logic source_transfer=0,memory_transfer=0;
    logic [606:0] previous_source,previous_command;
    logic [520:0] previous_response,previous_result;
    logic [520:0] result_before_edge;
    function automatic [31:0] advance(input logic [31:0] x);
        return {x[30:0],x[31]^x[21]^x[1]^x[0]};
    endfunction
    function automatic [520:0] response_for(input command_t c);
        return {^c.data,c.address[7:0]^{1'b0,c.bytes_count},c.data^{8{c.strobes}}};
    endfunction
    initial begin
        void'($value$plusargs("APP_HALF=%d",app_half));
        forever #(app_half) app_clk=~app_clk;
    end
    initial begin
        void'($value$plusargs("MEM_HALF=%d",mem_half));
        void'($value$plusargs("MEM_PHASE=%d",mem_phase));
        #(mem_phase);
        forever #(mem_half) mem_clk=~mem_clk;
    end
    always @(negedge app_clk)begin
        source_random=advance(source_random);
        if(app_reset)begin s_cmd_valid=0;s_rsp_ready=0;end
        else begin
            s_rsp_ready=!hold_application&&source_random[1:0]!=0;
            if(!s_cmd_valid||source_transfer)begin
                s_cmd_valid=produce&&sent<limit&&(hold_memory||source_random[4:2]!=0);
                if(s_cmd_valid)begin
                    s_cmd_write=source_random[0];s_cmd_address=(source_random>>9)^sent;
                    s_cmd_bytes=source_random[14:8];s_cmd_strobes={source_random,32'(sent)};
                    for(integer i=0;i<16;i++)s_cmd_data[i*32+:32]=source_random^(32'h9e3779b9*i)^sent;
                    s_cmd_data[511:480]=32'hb0070000|epoch;
                end
            end
        end
        #1;result_before_edge={s_rsp_error,s_rsp_detail,s_rsp_data};
    end
    always @(negedge mem_clk)begin
        memory_random=advance(memory_random);
        if(mem_reset)begin m_cmd_ready=0;m_rsp_valid=0;end
        else begin
            m_cmd_ready=!hold_memory&&memory_random[1:0]!=0;
            if(!m_rsp_valid||memory_transfer)begin
                m_rsp_valid=pending_responses.size()!=0&&memory_random[4:2]!=0;
                if(m_rsp_valid){m_rsp_error,m_rsp_detail,m_rsp_data}=pending_responses[0];
            end
        end
    end
    always @(posedge app_clk)begin : application_check
        command_t actual;
        logic [520:0] result,expected;
        actual={s_cmd_write,s_cmd_address,s_cmd_bytes,s_cmd_data,s_cmd_strobes};
        result={s_rsp_error,s_rsp_detail,s_rsp_data};
        source_transfer=!app_reset&&s_cmd_valid&&s_cmd_ready;
        if(app_reset)begin
            held_source=0;held_result=0;
            assert(!s_cmd_ready&&!s_rsp_valid)else $fatal(1,"Application handshake during reset");
        end else begin
            if(held_source)assert(s_cmd_valid&&actual==previous_source)else $fatal(1,"Source command changed while held");
            if(held_result)assert(s_rsp_valid&&result==previous_result)else $fatal(1,"FIFO result changed while held");
            held_source=s_cmd_valid&&!s_cmd_ready;previous_source=actual;
            held_result=s_rsp_valid&&!s_rsp_ready;previous_result=result;
            if(held_source)source_holds++;
            if(s_cmd_valid&&s_cmd_ready)begin expected_commands.push_back(actual);sent++;end
            if(s_rsp_valid&&s_rsp_ready)begin
                assert(expected_responses.size()>0)else $fatal(1,"Phantom response after reset");
                expected=expected_responses.pop_front();
                if(epoch==3&&responses_received<3)$display("APP_RSP actual=%h before_edge=%h expected=%h",result[31:0],result_before_edge[31:0],expected[31:0]);
                assert(result==expected)else begin
                    $display("CDC_MISMATCH epoch=%0d sent=%0d received=%0d rsp_sent=%0d rsp_received=%0d actual=%h expected=%h",
                        epoch,sent,received,responses_sent,responses_received,result,expected);
                    $fatal(1,"CDC response mismatch");
                end
                responses_received++;
            end
            assert(fifo_errors==0)else $fatal(1,"FIFO overflow/underflow");
        end
    end
    always @(posedge mem_clk)begin : memory_check
        command_t actual,expected;
        logic [520:0] response,discard;
        integer pending_before;
        actual={m_cmd_write,m_cmd_address,m_cmd_bytes,m_cmd_data,m_cmd_strobes};
        response={m_rsp_error,m_rsp_detail,m_rsp_data};
        memory_transfer=!mem_reset&&m_rsp_valid&&m_rsp_ready;
        if(mem_reset)begin
            held_command=0;held_response=0;
            assert(!m_cmd_valid&&!m_rsp_ready)else $fatal(1,"Memory handshake during reset");
        end else begin
            if(held_command)assert(m_cmd_valid&&actual==previous_command)else $fatal(1,"FIFO command changed while held");
            if(held_response)assert(m_rsp_valid&&response==previous_response)else $fatal(1,"Memory result changed while held");
            held_command=m_cmd_valid&&!m_cmd_ready;previous_command=actual;
            held_response=m_rsp_valid&&!m_rsp_ready;previous_response=response;
            if(held_response)response_holds++;
            if(m_rsp_valid&&m_rsp_ready)begin
                if(epoch==3&&responses_received<3)$display("MEM_RSP count=%0d data=%h",responses_sent,response[31:0]);
                pending_before=pending_responses.size();
                assert(pending_before>0)else $fatal(1,"Responder queue empty");
                discard=pending_responses.pop_front();
                assert(discard==response&&pending_responses.size()==pending_before-1)else $fatal(1,"Responder pop/order mismatch");
                responses_sent++;
            end
            if(m_cmd_valid&&m_cmd_ready)begin
                assert(expected_commands.size()>0)else $fatal(1,"Phantom command after reset");
                expected=expected_commands.pop_front();
                if(epoch==3&&responses_received<3)$display("MEM_CMD count=%0d response=%h",received,actual.data[31:0]^actual.strobes[31:0]);
                assert(actual==expected)else $fatal(1,"CDC command mismatch");
                pending_responses.push_back(response_for(actual));expected_responses.push_back(response_for(expected));received++;
            end
            assert(fifo_errors==0)else $fatal(1,"FIFO overflow/underflow");
        end
    end
    task automatic reset_link;
        produce=0;reset_request=1;epoch++;
        #150000;
        expected_commands.delete();expected_responses.delete();pending_responses.delete();
        reset_request=0;
        wait(!app_reset&&!mem_reset);
        repeat(20)@(negedge app_clk);
        assert(!s_rsp_valid&&!m_cmd_valid)else $fatal(1,"Stale packet after reset");
    endtask
    task automatic drain_round(input integer count);
        integer target;
        target=responses_received+count;limit=sent+count;hold_memory=0;hold_application=0;produce=1;
        wait(responses_received==target);produce=0;
        repeat(20)@(negedge app_clk);
        assert(expected_commands.size()==0&&expected_responses.size()==0&&pending_responses.size()==0)
            else $fatal(1,"Packets missing after drain");
    endtask
    initial begin : test
        integer before_count;
        reset_link();
        // Fill and hold the command FIFO, then discard it through shared reset.
        limit=sent+64;produce=1;hold_memory=1;hold_application=1;
        repeat(250)@(negedge app_clk);
        assert(sent>=16&&source_holds>=50&&received==0)else $fatal(1,"Command FIFO did not fill");
        reset_link();
        // Fill the response FIFO with the application refusing every result.
        before_count=received;limit=sent+64;produce=1;hold_memory=0;hold_application=1;
        wait(received-before_count==64);
        repeat(250)@(negedge app_clk);
        assert(response_holds>=50&&responses_received==0)else $fatal(1,"Response FIFO did not fill");
        reset_link();drain_round(1000);
        // Reset during traffic, then require a new epoch to drain without ghosts.
        before_count=received;limit=sent+500;produce=1;hold_memory=0;hold_application=0;
        wait(received-before_count>=37);
        reset_link();drain_round(2000);
        $display("CDC_TEST_PASS app_half=%0d mem_half=%0d phase=%0d epochs=%0d commands=%0d received=%0d responses=%0d completed=%0d source_holds=%0d response_holds=%0d",
            app_half,mem_half,mem_phase,epoch,sent,received,responses_sent,responses_received,source_holds,response_holds);
        $finish;
    end
    initial begin #200000000;$fatal(1,"CDC test timeout");end
endmodule
