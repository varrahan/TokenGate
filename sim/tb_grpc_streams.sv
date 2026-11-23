`timescale 1ns/1ps
module tb_grpc_streams;
    localparam [22:0] POOL=23'h7a0003;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic req_valid=0,rsp_ready=0;wire req_ready,rsp_valid,idle;logic [2:0] req_op=0;
    logic [22:0] cfg_pool_base=POOL;logic [23:0] cfg_pool_bytes=384;
    logic [15:0] req_user=0,req_application=0;logic [30:0] req_stream=0;logic [31:0] req_generation=0;
    logic [22:0] req_address=0,req_buffer_base=0;logic [23:0] req_buffer_bytes=0;logic [31:0] req_message_limit=0;
    logic req_protobuf=0,req_unsupported_encoding=0,req_maintenance=0;logic [255:0] req_state=0;
    wire [7:0] rsp_status,rsp_detail,rsp_memory_status;wire [2:0] rsp_op;wire [22:0] rsp_address,rsp_buffer_base;wire [23:0] rsp_buffer_bytes;
    wire [15:0] rsp_user,rsp_application;wire [30:0] rsp_stream;wire [31:0] rsp_generation,rsp_message_limit;wire rsp_protobuf,rsp_unsupported_encoding;wire [255:0] rsp_state;
    wire recovery_required;wire [22:0] recovery_address;
    wire mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data,mem_rsp_data;wire [7:0] mem_rsp_status;
    wire [1:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [45:0] cmd_addr;wire [7:0] cmd_bytes;wire [143:0] cmd_data,response_data;wire [15:0] response_status;
    logic helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [71:0] helper_data=0;
    integer fault_target=-1,response_index=0;bit injected=0;
    grpc_stream_store dut(.*);
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={1'b1,mem_write};assign cmd_addr={helper_addr,mem_addr};assign cmd_bytes={4'd8,mem_bytes};assign cmd_data={helper_data,mem_data};assign response_ready={helper_rsp_ready,mem_rsp_ready};
    assign mem_ready=cmd_ready[0];assign mem_rsp_valid=response_valid[0];assign mem_rsp_data=response_data[0+:72];
    assign mem_rsp_status=!injected&&response_index==fault_target?8'h53:response_status[0+:8];
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(2)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    bit active[0:2];integer identity[0:2];logic [255:0] progress[0:2];logic [22:0] handles[0:127];
    integer operations=0,successes=0,failures=0,faults=0,formats=0;reg [255:0] partial;
    bit result_stalled=0,command_stalled=0;logic [481:0] held_result;logic [99:0] held_command;
    wire [481:0] result_bundle={rsp_status,rsp_detail,rsp_memory_status,rsp_op,rsp_address,rsp_buffer_base,rsp_buffer_bytes,rsp_user,rsp_application,rsp_stream,rsp_generation,rsp_message_limit,rsp_protobuf,rsp_unsupported_encoding,rsp_state};
    always @(posedge clk)if(!rst)begin
        if(result_stalled&&(!rsp_valid||held_result!==result_bundle))$fatal(1,"Stream-store result changed under stall");result_stalled=rsp_valid&&!rsp_ready;held_result=result_bundle;
        if(command_stalled&&(!mem_valid||held_command!=={mem_write,mem_addr,mem_bytes,mem_data}))$fatal(1,"Stream-store memory request changed");command_stalled=mem_valid&&!mem_ready;held_command={mem_write,mem_addr,mem_bytes,mem_data};
        if((^{req_ready,rsp_valid,mem_valid,mem_rsp_ready,recovery_required})===1'bx||rsp_valid&&((^result_bundle)===1'bx)||mem_valid&&((^held_command)===1'bx))$fatal(1,"Unknown stream-store interface");
        if(mem_valid&&(mem_bytes!=8||mem_addr<POOL||{1'b0,mem_addr}+8>{1'b0,POOL}+384||mem_write&&((mem_addr-POOL)&127)>=64))$fatal(1,"Stream store escaped pool/owned record bytes");
        if(mem_rsp_valid&&mem_rsp_ready)begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
    end
    function automatic [15:0] user_for(input integer id);user_for=16'(5+((id/2)%2));endfunction
    function automatic [30:0] stream_for(input integer id);stream_for=31'(1+2*(id%2));endfunction
    function automatic [255:0] completed_state(input integer used,input integer ordinal,input bit ended);
        completed_state={64'd0,28'd0,ended,3'd0,32'(ordinal),32'd0,32'd0,32'(used),32'(used)};
    endfunction
    task operation(input integer op,input integer id,input [22:0] address,input [255:0] value,input integer status,
                   input integer detail=0,input integer memory_status=0,input bit maintenance=0,input integer override_mode=0);
        integer index,model_id;
        begin
            index=-1;
            if(status==0)begin
                if(op==0)begin for(integer i=2;i>=0;i--)if(!active[i])index=i;end
                else if(op==1||op==6)begin for(integer i=2;i>=0;i--)if(active[i]&&user_for(identity[i])==user_for(id)&&(op==6||stream_for(identity[i])==stream_for(id)))index=i;end
                else if(op==2||op==3||op==5)index=(address-POOL)/128;
            end
            @(negedge clk);req_op=3'(op);cfg_pool_base=POOL;cfg_pool_bytes=override_mode==1?127:384;
            req_user=user_for(id);req_application=16'(100+id);req_stream=op>=4?0:stream_for(id);req_generation=32'ha0000000+id;
            req_address=override_mode==2?POOL+1:address;req_buffer_base=override_mode==4?POOL:override_mode==5?23'h600004:23'(24'h600003+id*4096);
            req_buffer_bytes=256;req_message_limit=256;req_protobuf=id&1;req_unsupported_encoding=(id&2)!=0;req_state=value;req_maintenance=maintenance;
            if(override_mode==3)req_stream=0;
            if(override_mode==6)req_generation=req_generation^32'h80000000;
            if(override_mode==9)begin req_application=9999;req_buffer_base=23'h700003;req_buffer_bytes=128;req_message_limit=0;req_protobuf=!req_protobuf;req_unsupported_encoding=!req_unsupported_encoding;end
            req_valid=1;do @(posedge clk);while(!req_ready);@(negedge clk);req_valid=0;
            cfg_pool_base='1;cfg_pool_bytes='1;req_op='1;req_address='1;req_user='1;req_stream='1;req_application='1;req_generation='1;req_buffer_base='1;req_buffer_bytes='1;req_message_limit='1;req_state='1;req_maintenance=0;
            wait(rsp_valid);
            if(rsp_op!=op||rsp_status!=status||rsp_detail!=detail||rsp_memory_status!=memory_status||rsp_user!=user_for(id)||rsp_stream!=(op==6&&status==0?stream_for(identity[index]):op>=4?0:override_mode==3?0:stream_for(id)))$fatal(1,"Stream operation mismatch operation=%0d op=%0d status=%0d/%0d detail=%0d/%0d memory=%0d/%0d",operations,op,rsp_status,status,rsp_detail,detail,rsp_memory_status,memory_status);
            if(status==0)begin
                if(op==0)begin if(index<0)$fatal(1,"Reference stream pool full");active[index]=1;identity[index]=id;progress[index]=0;handles[id]=rsp_address;end
                if(op==2)progress[index]=value;
                if(op<=3||op==6)begin
                    model_id=identity[index];
                    if(rsp_address!=POOL+index*128||rsp_application!=100+model_id||rsp_buffer_base!=24'h600003+model_id*4096||rsp_buffer_bytes!=256||rsp_message_limit!=256||rsp_generation!=32'ha0000000+model_id||rsp_protobuf!=(model_id&1)||rsp_unsupported_encoding!=((model_id&2)!=0)||rsp_state!==progress[index])$fatal(1,"Stream identity/config/progress mismatch operation=%0d slot=%0d actual_state=%h expected=%h",operations,index,rsp_state,progress[index]);
                end
                if(op==3||op==5)active[index]=0;
                if(op==4)begin for(integer i=0;i<3;i++)active[i]=0;formats++;end
                successes++;
            end else begin
                if(rsp_application!=0||rsp_buffer_base!=0||rsp_buffer_bytes!=0||rsp_generation!=0||rsp_state!==256'd0)$fatal(1,"Failed stream operation exposed usable state");
                failures++;
            end
            repeat($urandom_range(2,10))@(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;wait(idle&&fabric_idle);operations++;
        end
    endtask
    task fault_setup(input integer target);
        begin @(negedge clk);fault_target=target;response_index=0;injected=0;end
    endtask
    task recover_fault;
        reg [22:0] failed_address;
        begin
            if(!recovery_required||!injected)$fatal(1,"Stream memory failure not quarantined");failed_address=recovery_address;
            operation(1,0,0,0,6);operation(5,0,failed_address==POOL?POOL+128:POOL,0,6,0,0,1);
            fault_setup(-1);operation(5,0,failed_address,0,0,0,0,1);
            if(recovery_required)$fatal(1,"Exact-slot recovery did not clear quarantine");faults++;
        end
    endtask
    task corrupt(input [22:0] address,input [63:0] value);
        begin
            @(negedge clk);helper_addr=address;helper_data={8'd0,value};helper_valid=1;
            do @(posedge clk);while(!cmd_ready[1]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[1]);if(response_status[8+:8]!=0)$fatal(1,"Stream corruption helper failed");
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    initial begin
        for(integer i=0;i<3;i++)begin active[i]=0;identity[i]=0;progress[i]=0;end
        repeat(5)@(negedge clk);rst=0;
        operation(4,0,0,0,7,2);operation(4,0,0,0,1,0,0,1,1);operation(4,0,0,0,0,0,0,1);
        operation(1,0,0,0,3);operation(5,0,POOL,0,7,1,0,1);
        for(integer id=0;id<3;id++)operation(0,id,0,0,0);
        operation(0,3,0,0,10);operation(0,4,0,0,4);operation(0,3,0,0,1,3,0,0,5);
        for(integer id=2;id>=0;id--)operation(1,id,0,0,0);
        operation(6,0,0,0,0);operation(6,2,0,0,0);
        partial=0;partial[162:160]=3;operation(2,0,handles[0],partial,0);
        operation(2,0,handles[0],256'd0,1,4);
        operation(2,0,handles[0],completed_state(16,1,0),0,0,0,0,9);
        operation(2,0,handles[0],completed_state(32,2,0),0);
        operation(2,0,handles[0],completed_state(16,1,0),1,4);
        partial=completed_state(32,2,0);partial[255]=1;operation(2,0,handles[0],partial,1,4);
        operation(2,0,handles[0],completed_state(32,2,1),0);operation(2,0,handles[0],completed_state(32,2,0),1,4);
        operation(2,0,handles[0],0,8,0,0,0,6);operation(3,0,handles[0],0,8,0,0,0,6);
        operation(3,0,handles[0],0,0);operation(0,4,0,0,0);operation(2,0,handles[0],0,8);
        operation(1,4,0,0,0);operation(1,1,0,0,0);operation(1,2,0,0,0);
        operation(2,4,handles[4],0,1,2,0,0,2);operation(1,4,0,0,1,1,0,0,3);operation(0,3,0,0,1,1,0,0,4);
        // Every LOAD response word on an active first record.
        for(integer target=0;target<8;target++)begin
            operation(4,0,0,0,0,0,0,1);operation(0,0,0,0,0);operation(0,1,0,0,0);
            fault_setup(target);operation(1,0,0,0,2,target,83);recover_fault();operation(1,1,0,0,0);
        end
        // SAVE reads eight words, invalidates, writes four state words and
        // commits. An uncertain applied commit still requires exact recovery.
        for(integer target=0;target<14;target++)begin
            operation(4,0,0,0,0,0,0,1);operation(0,0,0,0,0);
            fault_setup(target);operation(2,0,handles[0],completed_state(8,1,0),target<8?2:5,target<8?target:target==8?8:target==13?9:target-5,83);recover_fault();
        end
        // Three free-marker reads and all nine OPEN write acknowledgements.
        for(integer target=0;target<12;target++)begin
            operation(4,0,0,0,0,0,0,1);fault_setup(target);
            operation(0,0,0,0,target<3?2:5,target<3?0:target==3?8:target==11?9:target-3,83);recover_fault();
        end
        for(integer target=0;target<9;target++)begin
            operation(4,0,0,0,0,0,0,1);operation(0,0,0,0,0);fault_setup(target);
            operation(3,0,handles[0],0,target<8?2:5,target<8?target:8,83);recover_fault();
        end
        for(integer target=0;target<3;target++)begin
            operation(4,0,0,0,0,0,0,1);fault_setup(target);operation(4,0,0,0,5,8,83,1);
            if(!recovery_required||!injected)$fatal(1,"FORMAT fault lost quarantine");faults++;fault_setup(-1);operation(4,0,0,0,0,0,0,1);
        end
        operation(0,0,0,0,0);corrupt(handles[0],64'hdeadbeef);operation(1,0,0,0,9,10);
        operation(5,0,recovery_address,0,7,2);fault_setup(0);operation(5,0,recovery_address,0,5,8,83,1);recover_fault();
        operation(0,0,0,0,0);corrupt(handles[0]+56,64'h8000000000000000);operation(1,0,0,0,9,10);fault_setup(-1);operation(5,0,recovery_address,0,0,0,0,1);
        operation(0,0,0,0,0);operation(1,0,0,0,0);
        operation(3,0,handles[0],0,0);operation(6,0,0,0,3);operation(0,0,0,0,0);
        for(integer slot=0;slot<3;slot++)for(integer offset=64;offset<128;offset++)begin
            integer address;address=POOL+slot*128+offset;
            if(memory_model.memory[address>>3][(address&7)*8+:8]!==8'(address*37+(address>>5)*19+7))$fatal(1,"Stream store overwrote reserved record bytes");
        end
        if(faults!=47||operations<250||formats<40)$fatal(1,"Insufficient stream-store coverage faults=%0d operations=%0d formats=%0d",faults,operations,formats);
        $display("PASS: external gRPC stream registry: %0d operations/%0d successes/%0d rejected/%0d memory fault phases; runtime allocation, connection/stream keys, immutable config, progress/closed guards, stale generations, all commit phases, quarantine and exact recovery",operations,successes,failures,faults);$finish;
    end
    initial begin #(64'd300000000);$fatal(1,"Stream registry timeout operation=%0d state=%0d",operations,dut.state);end
endmodule
