`timescale 1ns/1ps
module tb_grpc_engine;
    localparam [22:0] STREAM_POOL=23'h780003;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [22:0] cfg_stream_base=STREAM_POOL;logic [23:0] cfg_stream_bytes=2048;
    logic queue_cfg_valid=0,queue_cfg_clear=0,maintenance_grant=0,queue_cfg_result_ready=0;wire queue_cfg_ready,queue_cfg_result_valid;wire [7:0] queue_cfg_status;
    logic [22:0] queue_cfg_base=23'h7f0003;logic [23:0] queue_cfg_bytes=512;
    logic control_valid=0,control_result_ready=0;wire control_ready,control_result_valid;logic [2:0] control_op=0;
    logic [15:0] control_user=0,control_application=0;logic [30:0] control_stream=0;logic [31:0] control_generation=0;
    logic [22:0] control_address=0,control_buffer_base=0;logic [23:0] control_buffer_bytes=0;logic [31:0] control_message_limit=0;logic control_protobuf=0,control_unsupported_encoding=0,control_maintenance=0;
    wire [7:0] control_status,control_detail,control_memory_status;wire [2:0] control_result_op;wire [22:0] control_result_address,control_result_buffer_base;wire [23:0] control_result_buffer_bytes;
    wire [15:0] control_result_user,control_result_application;wire [30:0] control_result_stream;wire [31:0] control_result_generation,control_result_message_limit;wire control_result_protobuf,control_result_unsupported_encoding;wire [255:0] control_result_state;
    logic packet_start_valid=0;wire packet_start_ready;logic [15:0] packet_start_user=0;logic [31:0] packet_start_tag=0;
    logic s_valid=0;wire s_ready;logic [1:0] s_kind=0;logic [7:0] s_data=0;logic [30:0] s_stream=0;
    logic prepare_valid=0,prepared_ready=0,decision_valid=0,decision_commit=0,packet_result_ready=0;wire prepare_ready,prepared_valid,prepared_failed,decision_ready,packet_result_valid,packet_committed;wire [7:0] prepared_status,packet_status,packet_detail,packet_memory_status;wire [15:0] packet_user;wire [31:0] packet_tag;
    wire rpc_error_valid;logic rpc_error_ready=0;wire [7:0] rpc_error_status,rpc_error_detail,rpc_error_memory_status;wire [15:0] rpc_error_user,rpc_error_application;wire [30:0] rpc_error_stream;wire [31:0] rpc_error_generation,rpc_error_packet_tag;
    wire m_valid;logic m_ready=0;wire [15:0] m_user,m_application;wire [30:0] m_stream;wire m_protobuf;wire [22:0] m_base;wire [31:0] m_bytes,m_ordinal,m_generation,m_packet_tag;
    wire stream_recovery_required,queue_recovery_required,retirement_pending,idle;wire [22:0] stream_recovery_address;wire [7:0] queue_recovery_detail,queue_recovery_memory_status;wire [31:0] queued_count,pending_count;
    wire [3:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [91:0] mem_addr;wire [15:0] mem_bytes;wire [287:0] mem_data,mem_rsp_data;logic [31:0] mem_rsp_status;
    wire [4:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [114:0] cmd_addr;wire [19:0] cmd_bytes;wire [359:0] cmd_data,response_data;wire [39:0] response_status;
    logic helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;
    integer fault_client=-1,fault_target=-1,response_index=0;bit injected=0;
    grpc_ingress_engine dut(.*);
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={1'b0,mem_write};assign cmd_addr={helper_addr,mem_addr};assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={72'd0,mem_data};assign response_ready={helper_rsp_ready,mem_rsp_ready};
    assign mem_ready=cmd_ready[3:0];assign mem_rsp_valid=response_valid[3:0];assign mem_rsp_data=response_data[287:0];
    always @*begin
        mem_rsp_status=response_status[31:0];
        if(fault_client>=0&&!injected&&response_index==fault_target)mem_rsp_status[fault_client*8+:8]=fault_client==0?8'h53:fault_client==1?8'h51:fault_client==2?8'h52:8'h63;
    end
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(5)) fabric(
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
    integer definitions[0:127][0:8],fields[0:11],events[0:131071][0:2],descriptors[0:127][0:3],errors[0:31][0:3],expected[0:262143],offsets[0:127];
    logic [22:0] handles[0:127];integer packets=0,controls=0,messages=0,rpc_errors=0,faults=0,received=0,received_errors=0;bit in_packet=0,publish_allowed=0;
    bit desc_stalled=0,packet_stalled=0,prepared_stalled=0,error_stalled=0,control_stalled=0;logic [255:0] held_desc;logic [72:0] held_packet;logic [8:0] held_prepared;logic [150:0] held_error;logic [481:0] held_control;logic [3:0] mem_stalled=0;logic [99:0] held_mem[0:3];
    wire [255:0] descriptor_bundle={m_packet_tag,32'h47524d31,m_generation,9'd0,m_base,m_ordinal,m_bytes,m_protobuf,m_stream,m_application,m_user};
    wire [72:0] packet_bundle={packet_committed,packet_status,packet_detail,packet_memory_status,packet_user,packet_tag};
    wire [150:0] error_bundle={rpc_error_status,rpc_error_detail,rpc_error_memory_status,rpc_error_user,rpc_error_application,rpc_error_stream,rpc_error_generation,rpc_error_packet_tag};
    wire [481:0] control_bundle={control_status,control_detail,control_memory_status,control_result_op,control_result_address,control_result_buffer_base,control_result_buffer_bytes,control_result_user,control_result_application,control_result_stream,control_result_generation,control_result_message_limit,control_result_protobuf,control_result_unsupported_encoding,control_result_state};
    always @(negedge clk)rpc_error_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(desc_stalled&&(!m_valid||held_desc!==descriptor_bundle))$fatal(1,"Ingress descriptor unstable");desc_stalled=m_valid&&!m_ready;held_desc=descriptor_bundle;
        if(packet_stalled&&(!packet_result_valid||held_packet!==packet_bundle))$fatal(1,"Ingress packet result unstable");packet_stalled=packet_result_valid&&!packet_result_ready;held_packet=packet_bundle;
        if(prepared_stalled&&(!prepared_valid||held_prepared!=={prepared_failed,prepared_status}))$fatal(1,"Ingress PREPARE changed while stalled");prepared_stalled=prepared_valid&&!prepared_ready;held_prepared={prepared_failed,prepared_status};
        if(error_stalled&&(!rpc_error_valid||held_error!==error_bundle))$fatal(1,"Ingress RPC error unstable");error_stalled=rpc_error_valid&&!rpc_error_ready;held_error=error_bundle;
        if(control_stalled&&(!control_result_valid||held_control!==control_bundle))$fatal(1,"Ingress control result unstable");control_stalled=control_result_valid&&!control_result_ready;held_control=control_bundle;
        if((^{packet_start_ready,s_ready,prepare_ready,prepared_valid,decision_ready,packet_result_valid,rpc_error_valid,control_ready,control_result_valid,m_valid,mem_valid,mem_rsp_ready})===1'bx)$fatal(1,"Unknown ingress handshake");
        if(m_valid&&((^descriptor_bundle)===1'bx)||packet_result_valid&&((^packet_bundle)===1'bx)||rpc_error_valid&&((^error_bundle)===1'bx)||control_result_valid&&((^control_bundle)===1'bx))$fatal(1,"Unknown ingress metadata");
        if(m_valid&&!publish_allowed)$fatal(1,"Message escaped before transport COMMIT or after abort");
        for(integer c=0;c<4;c++)begin
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"Ingress memory command changed");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&((^held_mem[c])===1'bx))$fatal(1,"Unknown ingress memory command");
        end
        if(fault_client>=0&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
        if(rpc_error_valid&&rpc_error_ready)begin
            integer id;id=errors[received_errors][0];
            if(!in_packet||received_errors>=fields[11]||rpc_error_status!=errors[received_errors][1]||rpc_error_detail!=errors[received_errors][2]||rpc_error_memory_status!=errors[received_errors][3]||rpc_error_user!=definitions[id][0]||rpc_error_stream!=definitions[id][1]||rpc_error_application!=definitions[id][2]||rpc_error_generation!=definitions[id][3]||rpc_error_packet_tag!=32'(fields[1]))$fatal(1,"Ingress RPC error mismatch packet=%0d index=%0d stream=%0d status=%0d detail=%0d",packets,received_errors,rpc_error_stream,rpc_error_status,rpc_error_detail);
            received_errors++;rpc_errors++;
        end
    end
    task helper(input integer address,input integer size,output reg [71:0] value);
        begin
            @(negedge clk);helper_addr=23'(address);helper_bytes=4'(size);helper_valid=1;
            do @(posedge clk);while(!cmd_ready[4]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[4]);if(response_status[32+:8]!=0)$fatal(1,"Committed payload read failed");value=response_data[288+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    task consume;
        integer id,chunk;reg [71:0] value;
        begin
            while(!packet_result_valid||received<fields[10])begin
                @(negedge clk);
                if(m_valid)begin
                    id=descriptors[received][0];
                    if(received>=fields[10]||m_user!=definitions[id][0]||m_stream!=definitions[id][1]||m_application!=definitions[id][2]||m_generation!=definitions[id][3]||m_protobuf!=definitions[id][7]||m_base!=descriptors[received][1]||m_bytes!=descriptors[received][2]||m_ordinal!=descriptors[received][3]||m_packet_tag!=32'(fields[1]))$fatal(1,"Automatic ingress descriptor mismatch packet=%0d index=%0d stream=%0d base=%h size=%0d ordinal=%0d",packets,received,m_stream,m_base,m_bytes,m_ordinal);
                    for(integer i=0;i<m_bytes;i+=8)begin
                        chunk=m_bytes-i;if(chunk>8)chunk=8;helper(m_base+i,chunk,value);
                        for(integer lane=0;lane<chunk;lane++)if(value[lane*8+:8]!==8'(expected[offsets[received]+i+lane]))$fatal(1,"Automatic ingress payload mismatch packet=%0d index=%0d byte=%0d",packets,received,i+lane);
                    end
                    repeat($urandom_range(1,7))@(negedge clk);m_ready=1;@(posedge clk);@(negedge clk);m_ready=0;received++;messages++;
                end
            end
        end
    endtask
    task control_command(input integer op,input integer id,input integer expected_status,input integer expected_detail,input integer expected_slot,input [255:0] expected_state);
        begin
            @(negedge clk);
            if(!in_packet)begin cfg_stream_base=STREAM_POOL;cfg_stream_bytes=2048;end
            control_op=3'(op);control_user=16'(definitions[id][0]);control_stream=31'(definitions[id][1]);control_application=16'(definitions[id][2]);control_generation=32'(definitions[id][3]);
            control_address=op==5?stream_recovery_address:handles[id];control_buffer_base=23'(definitions[id][4]);control_buffer_bytes=24'(definitions[id][5]);control_message_limit=32'(definitions[id][6]);control_protobuf=definitions[id][7]!=0;control_unsupported_encoding=definitions[id][8]!=0;control_maintenance=op==4||op==5;control_valid=1;
            do @(posedge clk);while(!control_ready);@(negedge clk);control_valid=0;control_op='1;control_user='1;control_stream='1;control_application='1;control_generation='1;control_address='1;control_buffer_base='1;control_buffer_bytes='1;control_message_limit='1;control_protobuf=!control_protobuf;control_unsupported_encoding=!control_unsupported_encoding;control_maintenance=0;
            wait(control_result_valid);
            if(control_status!=expected_status||control_detail!=expected_detail||control_memory_status!=0||control_result_op!=op||control_result_user!=definitions[id][0]||control_result_stream!=definitions[id][1])$fatal(1,"Ingress control mismatch command=%0d op=%0d status=%0d/%0d detail=%0d/%0d",controls,op,control_status,expected_status,control_detail,expected_detail);
            if(expected_status==0&&op<=3)begin
                if(control_result_address!=STREAM_POOL+expected_slot*128||control_result_application!=definitions[id][2]||control_result_generation!=definitions[id][3]||control_result_buffer_base!=definitions[id][4]||control_result_buffer_bytes!=definitions[id][5]||control_result_message_limit!=definitions[id][6]||control_result_protobuf!=definitions[id][7]||control_result_unsupported_encoding!=definitions[id][8]||control_result_state!==expected_state)$fatal(1,"Autonomous persisted stream mismatch command=%0d op=%0d state=%h/%h",controls,op,control_result_state,expected_state);
                if(op==0)handles[id]=control_result_address;
            end else if(control_result_state!==256'd0)$fatal(1,"Failed/maintenance control exposed progress");
            repeat($urandom_range(2,8))@(negedge clk);control_result_ready=1;@(posedge clk);@(negedge clk);control_result_ready=0;controls++;
        end
    endtask
    task data_event(input integer kind,input integer stream,input integer data);
        begin
            repeat($urandom_range(0,2))@(negedge clk);s_kind=2'(kind);s_stream=31'(stream);s_data=8'(data);s_valid=1;
            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
        end
    endtask
    initial begin:driver
        integer fd,rc,opcode,n_definitions,scanned,op,id,expected_status,expected_detail,expected_slot,offset;logic [255:0] expected_state;
        repeat(5)@(negedge clk);rst=0;
        @(negedge clk);queue_cfg_valid=1;do @(posedge clk);while(!queue_cfg_ready);@(negedge clk);queue_cfg_valid=0;
        wait(queue_cfg_result_valid);if(queue_cfg_status!=0)$fatal(1,"Engine queue setup failed");queue_cfg_result_ready=1;@(posedge clk);@(negedge clk);queue_cfg_result_ready=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No automatic ingress fixtures");
        rc=$fscanf(fd,"%d",n_definitions);if(rc!=1)$fatal(1,"No ingress admission definitions");
        for(integer i=0;i<n_definitions;i++)for(integer j=0;j<9;j++)begin rc=$fscanf(fd,"%d",scanned);definitions[i][j]=scanned;if(rc!=1)$fatal(1,"Bad ingress definition");end
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",opcode);
            if(rc==1)begin
                if(opcode==0)begin
                    rc=$fscanf(fd,"%d %d %d %d %d %h",op,id,expected_status,expected_detail,expected_slot,expected_state);if(rc!=6)$fatal(1,"Bad ingress control fixture");
                    control_command(op,id,expected_status,expected_detail,expected_slot,expected_state);
                end else if(opcode==1)begin
                    for(integer i=0;i<12;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad ingress packet fixture");end
                    for(integer i=0;i<fields[9];i++)for(integer j=0;j<3;j++)begin rc=$fscanf(fd,"%d",scanned);events[i][j]=scanned;if(rc!=1)$fatal(1,"Bad ingress DATA event");end
                    offset=0;
                    for(integer d=0;d<fields[10];d++)begin
                        for(integer j=0;j<4;j++)begin rc=$fscanf(fd,"%d",scanned);descriptors[d][j]=scanned;if(rc!=1)$fatal(1,"Bad ingress message golden");end
                        offsets[d]=offset;
                        for(integer i=0;i<descriptors[d][2];i++)begin rc=$fscanf(fd,"%h",expected[offset]);if(rc!=1)$fatal(1,"Bad ingress payload golden");offset++;end
                    end
                    for(integer e=0;e<fields[11];e++)for(integer j=0;j<4;j++)begin rc=$fscanf(fd,"%d",scanned);errors[e][j]=scanned;if(rc!=1)$fatal(1,"Bad RPC error golden");end
                    @(negedge clk);packet_start_user=16'(fields[0]);packet_start_tag=32'(fields[1]);packet_start_valid=1;received=0;received_errors=0;publish_allowed=0;fault_client=fields[5];fault_target=fields[6];response_index=0;injected=0;in_packet=1;
                    do @(posedge clk);while(!packet_start_ready);@(negedge clk);packet_start_valid=0;packet_start_user='1;packet_start_tag='1;cfg_stream_base='1;cfg_stream_bytes='1;
                    fork
                        begin
                            for(integer i=0;i<fields[9];i++)begin
                                if(events[i][0]==2)control_command(0,events[i][1],0,0,events[i][2],256'd0);
                                else data_event(events[i][0],events[i][1],events[i][2]);
                            end
                            @(negedge clk);prepare_valid=1;do @(posedge clk);while(!prepare_ready);@(negedge clk);prepare_valid=0;
                            wait(prepared_valid);if(prepared_failed!=(fields[4]!=0))$fatal(1,"Ingress prepare failure mismatch packet=%0d failed=%0d/%0d",packets,prepared_failed,fields[4]);
                            repeat($urandom_range(2,12))@(negedge clk);prepared_ready=1;@(posedge clk);@(negedge clk);prepared_ready=0;
                            repeat($urandom_range(2,10))@(negedge clk);decision_commit=fields[2]!=0;decision_valid=1;
                            do @(posedge clk);while(!decision_ready);publish_allowed=fields[7]!=0;@(negedge clk);decision_valid=0;decision_commit=0;
                        end
                        consume();
                    join
                    wait(packet_result_valid);
                    if(packet_committed!=(fields[7]!=0)||packet_status!=fields[3]||packet_user!=fields[0]||packet_tag!=32'(fields[1])||retirement_pending!=(fields[8]!=0)||received!=fields[10]||received_errors!=fields[11]||injected!=(fields[5]>=0))$fatal(1,"Ingress packet mismatch packet=%0d status=%0d/%0d committed=%0d/%0d descriptors=%0d/%0d errors=%0d/%0d retiring=%0d/%0d",packets,packet_status,fields[3],packet_committed,fields[7],received,fields[10],received_errors,fields[11],retirement_pending,fields[8]);
                    if(injected)faults++;
                    repeat($urandom_range(2,10))@(negedge clk);packet_result_ready=1;@(posedge clk);@(negedge clk);packet_result_ready=0;fault_client=-1;fault_target=-1;in_packet=0;publish_allowed=0;cfg_stream_base=STREAM_POOL;cfg_stream_bytes=2048;packets++;
                end else $fatal(1,"Unknown ingress fixture opcode");
            end else if(!$feof(fd))$fatal(1,"Malformed ingress fixture");
        end
        $fclose(fd);wait(idle&&fabric_idle);
        if(packets<15||controls<35||messages<8||rpc_errors<3||faults!=5)$fatal(1,"Insufficient integrated ingress coverage packets=%0d controls=%0d messages=%0d errors=%0d faults=%0d",packets,controls,messages,rpc_errors,faults);
        $display("PASS: automatic gRPC ingress engine: %0d packets/%0d admissions and queries/%0d exact committed descriptors/%0d RPC errors/%0d integrated memory faults; real directory load/save, stream switches, PREPARE/COMMIT, inline admission, RPC-local failure, connection retirement and recovery",packets,controls,messages,rpc_errors,faults);$finish;
    end
    initial begin #(64'd500000000);$fatal(1,"Automatic ingress timeout packet=%0d controls=%0d engine=%0d action=%0d registry=%0d decoder=%0d queue=%0d",packets,controls,dut.state,dut.action,dut.registry.state,dut.decoder.state,dut.descriptors.wstate);end
endmodule
