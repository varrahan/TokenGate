`timescale 1ns/1ps
module arbiter_stress_case #(parameter integer CLIENTS=4)(output bit done=0);
    logic clk=0,rst=1,pause=0;always #2 clk=~clk;
    logic [CLIENTS-1:0] valid=0,write_cmd=0,response_ready=0;
    wire [CLIENTS-1:0] ready,response_valid;
    logic [CLIENTS*12-1:0] addresses=0;logic [CLIENTS*4-1:0] lengths=0;logic [CLIENTS*72-1:0] payloads=0;
    wire [CLIENTS*72-1:0] response_data;wire [CLIENTS*8-1:0] response_status;
    wire rv,wv,rrr,wrr,idle,drained;logic rr=0,wr=0,rrv=0,wrv=0;
    wire [11:0] ra,wa;wire [3:0] rn,wn;wire [71:0] wd;
    logic [71:0] rd=0;logic [7:0] rs=0,ws=0;
    integer completed[0:CLIENTS-1],age[0:CLIENTS-1];
    bit waiting_service[0:CLIENTS-1],waiting_response[0:CLIENTS-1];
    logic [71:0] expected_data[0:CLIENTS-1];logic [7:0] expected_status[0:CLIENTS-1];
    bit stalled[0:CLIENTS-1];logic [79:0] held[0:CLIENTS-1];
    bit backend_busy=0,backend_write=0,backend_accepted=0;
    integer latency=0,cycles=0,services=0,held_progress=0,finished_clients=0;
    logic [71:0] pending_data;logic [7:0] pending_status;
    function automatic [71:0] value(input integer address,input integer bytes_count);
        begin value=0;for(integer lane=0;lane<9;lane++)if(lane<bytes_count)value[lane*8+:8]=8'((address+lane)*37+((address+lane)>>5));end
    endfunction
    external_memory_arbiter #(.CLIENTS(CLIENTS),.ADDR_WIDTH(12)) dut(
        .clk(clk),.rst(rst),.pause(pause),.s_valid(valid),.s_ready(ready),.s_write(write_cmd),.s_addr(addresses),.s_bytes(lengths),.s_data(payloads),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .rd_valid(rv),.rd_ready(rr),.rd_addr(ra),.rd_bytes(rn),.rd_rsp_valid(rrv),.rd_rsp_ready(rrr),.rd_rsp_data(rd),.rd_rsp_status(rs),
        .wr_valid(wv),.wr_ready(wr),.wr_addr(wa),.wr_bytes(wn),.wr_data(wd),.wr_rsp_valid(wrv),.wr_rsp_ready(wrr),.wr_rsp_status(ws),.idle(idle),.drained(drained));
    always @(negedge clk)begin:timing
        integer other_completions;
        cycles++;
        pause=!rst&&(cycles%37<3);
        other_completions=0;for(integer i=1;i<CLIENTS;i++)other_completions+=completed[i];
        for(integer i=0;i<CLIENTS;i++)response_ready[i]=!rst&&$urandom_range(0,3)!=0&&(i!=0||CLIENTS==1||other_completions>=32*(CLIENTS-1));
        rr=!rst&&!backend_busy&&$urandom_range(0,3)!=0;
        wr=!rst&&!backend_busy&&$urandom_range(0,3)!=0;
        if(backend_accepted)begin rrv=0;wrv=0;end
        if(backend_busy&&!rrv&&!wrv)begin
            if(latency>0)latency--;
            else if(backend_write)begin wrv=1;ws=pending_status;end
            else begin rrv=1;rd=pending_data;rs=pending_status;end
        end
    end
    always @(posedge clk)begin:scoreboard
        integer owner;
        backend_accepted=(rrv&&rrr)||(wrv&&wrr);
        if(rst)begin backend_busy=0;end
        else begin
            if(pause&&(|ready))$fatal(1,"Paused arbiter accepted input");
            for(integer i=0;i<CLIENTS;i++)begin
                if(stalled[i]&&(!response_valid[i]||held[i]!=={response_status[i*8+:8],response_data[i*72+:72]}))$fatal(1,"Client response changed under stall");
                stalled[i]=response_valid[i]&&!response_ready[i];held[i]={response_status[i*8+:8],response_data[i*72+:72]};
                if(valid[i]&&ready[i])begin
                    if(waiting_response[i])$fatal(1,"Client admitted two outstanding commands");
                    waiting_response[i]=1;waiting_service[i]=1;age[i]=0;
                    expected_data[i]=write_cmd[i]?72'd0:value(addresses[i*12+:12],lengths[i*4+:4]);
                    expected_status[i]=addresses[i*12+:3]==7?8'h55:0;
                    if(idle)$fatal(1,"Idle exposed on a newly admitted request");
                end
                if(response_valid[i]&&response_ready[i])begin
                    if(!waiting_response[i]||response_status[i*8+:8]!==expected_status[i]||response_data[i*72+:72]!==expected_data[i])$fatal(1,"Response routed to wrong client/status/data");
                    waiting_response[i]=0;completed[i]++;
                    if(i!=0&&response_valid[0]&&!response_ready[0])held_progress++;
                end
            end
            if(backend_accepted)backend_busy=0;
            if((rv&&rr)||(wv&&wr))begin
                if(rv&&wv)$fatal(1,"Read and write issued together");
                owner=(wv?wa:ra)>>10;
                if(owner>=CLIENTS||!waiting_service[owner])$fatal(1,"Duplicate/unowned backend command");
                waiting_service[owner]=0;services++;
                for(integer i=0;i<CLIENTS;i++)if(waiting_service[i])begin
                    age[i]++;if(age[i]>CLIENTS)$fatal(1,"Read/write arbitration starved a queued client");
                end
                backend_busy=1;backend_write=wv;latency=$urandom_range(0,12);
                pending_data=value(ra,rn);pending_status=(wv?wa[2:0]:ra[2:0])==7?8'h55:0;
            end
        end
    end
    generate for(genvar client=0;client<CLIENTS;client++)begin:drivers
        initial begin
            completed[client]=0;age[client]=0;waiting_service[client]=0;waiting_response[client]=0;stalled[client]=0;
            wait(!rst);
            for(integer transaction=0;transaction<250;transaction++)begin
                repeat($urandom_range(0,3))@(negedge clk);
                @(negedge clk);addresses[client*12+:12]=client*1024+$urandom_range(0,1000);
                lengths[client*4+:4]=$urandom_range(1,9);payloads[client*72+:72]={$urandom,$urandom,$urandom};
                write_cmd[client]=$urandom_range(0,1);valid[client]=1;
                do @(posedge clk);while(!ready[client]);
                @(negedge clk);valid[client]=0;
                wait(completed[client]==transaction+1);@(negedge clk);
            end
            finished_clients++;
        end
    end endgenerate
    initial begin
        repeat(5)@(negedge clk);rst=0;
        wait(finished_clients==CLIENTS);@(negedge clk);
        if(!idle||!drained||services!=250*CLIENTS||(CLIENTS>1&&held_progress<32))$fatal(1,"Arbiter coverage/drain failure");
        $display("PASS: arbiter %0d clients/%0d mixed read-write commands; fairness, response isolation, pause, faults and stalls",CLIENTS,services);
        done=1;
    end
endmodule
module tb_external_memory_arbiter;
    wire one_done,three_done,four_done;
    arbiter_stress_case #(.CLIENTS(1)) one(.done(one_done));
    arbiter_stress_case #(.CLIENTS(3)) three(.done(three_done));
    arbiter_stress_case #(.CLIENTS(4)) four(.done(four_done));
    initial begin wait(one_done&&three_done&&four_done);$display("PASS: all shared-memory arbiter configurations");$finish;end
    initial begin #10000000;$fatal(1,"Arbiter timeout");end
endmodule
