`timescale 1ns/1ps
module tb_grpc_parser;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [23-1:0] cfg_stream_base=0;
    logic [23:0] cfg_stream_bytes=0;
    logic  queue_cfg_valid=0;
    wire  queue_cfg_ready;
    logic  queue_cfg_clear=0;
    logic  maintenance_grant=0;
    logic [23-1:0] queue_cfg_base=0;
    logic [23:0] queue_cfg_bytes=0;
    wire  queue_cfg_result_valid;
    logic  queue_cfg_result_ready=0;
    wire [7:0] queue_cfg_status;
    logic  control_valid=0;
    wire  control_ready;
    logic [2:0] control_op=0;
    logic [16-1:0] control_user=0;
    logic [16-1:0] control_application=0;
    logic [30:0] control_stream=0;
    logic [31:0] control_generation=0;
    logic [23-1:0] control_address=0;
    logic [23-1:0] control_buffer_base=0;
    logic [23:0] control_buffer_bytes=0;
    logic [31:0] control_message_limit=0;
    logic  control_protobuf=0;
    logic  control_unsupported_encoding=0;
    logic  control_maintenance=0;
    wire  control_result_valid;
    logic  control_result_ready=0;
    wire [7:0] control_status;
    wire [7:0] control_detail;
    wire [7:0] control_memory_status;
    wire [2:0] control_result_op;
    wire [23-1:0] control_result_address;
    wire [23-1:0] control_result_buffer_base;
    wire [23:0] control_result_buffer_bytes;
    wire [16-1:0] control_result_user;
    wire [16-1:0] control_result_application;
    wire [30:0] control_result_stream;
    wire [31:0] control_result_generation;
    wire [31:0] control_result_message_limit;
    wire  control_result_protobuf;
    wire  control_result_unsupported_encoding;
    wire [255:0] control_result_state;
    logic  packet_start_valid=0;
    wire  packet_start_ready;
    logic [16-1:0] packet_start_user=0;
    logic [31:0] packet_start_tag=0;
    logic  s_valid=0;
    wire  s_ready;
    logic [1:0] s_kind=0;
    logic [7:0] s_data=0;
    logic [30:0] s_stream=0;
    logic  prepare_valid=0;
    wire  prepare_ready;
    wire  prepared_valid;
    logic  prepared_ready=0;
    wire  prepared_failed;
    wire [7:0] prepared_status;
    logic  decision_valid=0;
    wire  decision_ready;
    logic  decision_commit=0;
    wire  packet_result_valid;
    logic  packet_result_ready=0;
    wire  packet_committed;
    wire [7:0] packet_status;
    wire [7:0] packet_detail;
    wire [7:0] packet_memory_status;
    wire [16-1:0] packet_user;
    wire [31:0] packet_tag;
    wire  rpc_error_valid;
    logic  rpc_error_ready=0;
    wire [7:0] rpc_error_status;
    wire [7:0] rpc_error_detail;
    wire [7:0] rpc_error_memory_status;
    wire [16-1:0] rpc_error_user;
    wire [16-1:0] rpc_error_application;
    wire [30:0] rpc_error_stream;
    wire [31:0] rpc_error_generation;
    wire [31:0] rpc_error_packet_tag;
    wire  stream_recovery_required;
    wire [23-1:0] stream_recovery_address;
    wire  queue_recovery_required;
    wire [7:0] queue_recovery_detail;
    wire [7:0] queue_recovery_memory_status;
    wire  retirement_pending;
    wire [31:0] queued_count;
    wire [31:0] pending_count;
    wire  idle;
    wire [4:0] mem_valid;
    wire [4:0] mem_ready;
    wire [4:0] mem_write;
    wire [5*23-1:0] mem_addr;
    wire [19:0] mem_bytes;
    wire [359:0] mem_data;
    wire [4:0] mem_rsp_valid;
    wire [4:0] mem_rsp_ready;
    wire [359:0] mem_rsp_data;
    logic [39:0] mem_rsp_status=0;
    logic  admit_messages=0;
    logic  stream_cfg_valid=0;
    wire  stream_cfg_ready;
    wire  stream_cfg_result_valid;
    logic  stream_cfg_result_ready=0;
    wire [7:0] stream_cfg_status;
    logic  cfg_unlock=0;
    logic  cfg_schema_valid=0;
    wire  cfg_schema_ready;
    wire  cfg_quiescent;
    logic [3:0] cfg_schema_index=0;
    logic [255:0] cfg_schema_key=0;
    logic [5:0] cfg_schema_key_length=0;
    logic  cfg_schema_json_enable=0;
    logic [28:0] cfg_schema_field=0;
    logic  cfg_schema_proto_enable=0;
    wire [127:0] m_axis_text_tdata;
    wire [15:0] m_axis_text_tkeep;
    wire  m_axis_text_tvalid;
    logic  m_axis_text_tready=0;
    wire  m_axis_text_tlast;
    wire [16-1:0] m_axis_text_tuser;
    wire [16-1:0] text_connection;
    wire [30:0] text_stream;
    wire [31:0] text_generation;
    wire [31:0] text_ordinal;
    wire [31:0] text_packet_tag;
    wire  completion_valid;
    logic  completion_ready=0;
    wire [7:0] completion_status;
    wire [7:0] completion_detail;
    wire [7:0] completion_memory_status;
    wire [16-1:0] completion_user;
    wire [16-1:0] completion_application;
    wire [30:0] completion_stream;
    wire [31:0] completion_generation;
    wire [31:0] completion_ordinal;
    wire [31:0] completion_packet_tag;
    wire  payload_lease_active;
    grpc_ingress_parser #(.MAX_TEXT_BYTES(1024),.MAX_FIELD_BYTES(32768)) dut(.*);
    wire [39:0] response_status;logic [359:0] forward_data;
    integer fault_client=-1,fault_target=-1,response_index=0,write_index=0,corrupt_word=0;
    logic [63:0] corrupt_mask=0,corrupt_value=0;bit injected=0,corrupt_armed=0;
    always @*begin
        mem_rsp_status=response_status;
        if(fault_client>=0&&!injected&&response_index==fault_target)mem_rsp_status[fault_client*8+:8]=fault_client==0?8'h73:8'h74;
        forward_data=mem_data;
        if(corrupt_armed&&write_index==corrupt_word)forward_data[144+:64]=(mem_data[144+:64]&~corrupt_mask)|(corrupt_value&corrupt_mask);
    end
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(5)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(forward_data),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    integer definitions[0:127][0:8],events[0:131071][0:2],errors[0:31][0:3],golden[0:127][0:8],expected[0:262143],offsets[0:127];
    logic [22:0] handles[0:127];integer packets=0,controls=0,completed=0,successes=0,rejected=0,memory_faults=0,corruptions=0,probes=0;
    integer received=0,n_completions=0,n_errors=0,received_errors=0,text_index=0,text_packets=0,payload_reads=0,text_stalls=0,lease_cycles=0,probe_text_wait=0;
    bit draining=0,probe_active=0,text_stalled=0,result_stalled=0,control_stalled=0;logic [303:0] held_text;logic [182:0] held_result;logic [481:0] held_control;
    wire [303:0] text_bundle={text_connection,text_stream,text_generation,text_ordinal,text_packet_tag,m_axis_text_tuser,m_axis_text_tlast,m_axis_text_tkeep,m_axis_text_tdata};
    wire [182:0] result_bundle={completion_status,completion_detail,completion_memory_status,completion_user,completion_application,completion_stream,completion_generation,completion_ordinal,completion_packet_tag};
    wire [481:0] control_bundle={control_status,control_detail,control_memory_status,control_result_op,control_result_address,control_result_buffer_base,control_result_buffer_bytes,control_result_user,control_result_application,control_result_stream,control_result_generation,control_result_message_limit,control_result_protobuf,control_result_unsupported_encoding,control_result_state};
    logic [4:0] mem_stalled=0;logic [99:0] held_mem[0:4];
    always @(negedge clk)begin
        rpc_error_ready=$urandom_range(0,3)!=0;
        m_axis_text_tready=draining&&(!probe_active||probe_text_wait>40)&&$urandom_range(0,3)!=0;
    end
    always @(posedge clk)if(!rst)begin
        if(text_stalled&&(!m_axis_text_tvalid||held_text!==text_bundle))$fatal(1,"Admitted text/identity unstable");
        text_stalled=m_axis_text_tvalid&&!m_axis_text_tready;held_text=text_bundle;if(text_stalled)text_stalls++;
        if(result_stalled&&(!completion_valid||held_result!==result_bundle))$fatal(1,"Admission result unstable");
        result_stalled=completion_valid&&!completion_ready;held_result=result_bundle;
        if(control_stalled&&(!control_result_valid||held_control!==control_bundle))$fatal(1,"External control result unstable");
        control_stalled=control_result_valid&&!control_result_ready;held_control=control_bundle;
        if((^{packet_start_ready,control_ready,queue_cfg_ready,stream_cfg_ready,s_ready,prepare_ready,prepared_valid,decision_ready,packet_result_valid,rpc_error_valid,completion_valid,m_axis_text_tvalid,mem_valid,mem_rsp_ready,payload_lease_active})===1'bx)$fatal(1,"Unknown admitted ingress handshake");
        if(m_axis_text_tvalid&&((^text_bundle)===1'bx)||completion_valid&&((^result_bundle)===1'bx)||control_result_valid&&((^control_bundle)===1'bx))$fatal(1,"Unknown admitted ingress metadata");
        if(payload_lease_active)begin
            lease_cycles++;
            if(control_ready||packet_start_ready||queue_cfg_ready||stream_cfg_ready||cfg_schema_ready)$fatal(1,"Payload lease allowed a competing mutation");
            if(!dut.descriptor_valid)$fatal(1,"Descriptor was popped before application retirement");
        end
        for(integer c=0;c<5;c++)begin
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"Ingress Parser memory command changed");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&((^held_mem[c])===1'bx))$fatal(1,"Unknown ingress Parser memory command");
        end
        if(fault_client>=0&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
        if(corrupt_armed&&mem_valid[2]&&mem_ready[2]&&mem_write[2])begin
            if(write_index==corrupt_word)begin corrupt_armed<=0;corruptions++;end
            write_index<=write_index+1;
        end
        if(mem_valid[4]&&mem_ready[4])begin if(mem_write[4])$fatal(1,"Parser replay wrote payload");payload_reads++;end
        if(rpc_error_valid&&rpc_error_ready)begin
            integer id;id=errors[received_errors][0];
            if(received_errors>=n_errors||rpc_error_user!=definitions[id][0]||rpc_error_application!=definitions[id][2]||rpc_error_stream!=definitions[id][1]||rpc_error_generation!=definitions[id][3]||rpc_error_status!=errors[received_errors][1]||rpc_error_detail!=errors[received_errors][2]||rpc_error_memory_status!=errors[received_errors][3])$fatal(1,"Integrated RPC error mismatch");
            received_errors++;
        end
        if(m_axis_text_tvalid)begin
            integer id;id=golden[received][0];
            if(probe_active)probe_text_wait++;
            if(!draining||received>=n_completions||golden[received][3]!=0)$fatal(1,"Text escaped from a closed/stale/invalid message");
            if(text_connection!=definitions[id][0]||text_stream!=definitions[id][1]||text_generation!=32'(golden[received][8])||m_axis_text_tuser!=golden[received][7]||text_ordinal!=golden[received][2]||text_packet_tag!=32'(golden[received][1]))$fatal(1,"Text lost RPC metadata");
            if(m_axis_text_tready)begin
                for(integer lane=0;lane<16;lane++)if(m_axis_text_tkeep[lane])begin
                    if(text_index>=golden[received][6]||m_axis_text_tdata[lane*8+:8]!==8'(expected[offsets[received]+text_index]))$fatal(1,"Admitted Parser text mismatch completion=%0d byte=%0d",completed,text_index);
                    text_index++;
                end
                if(m_axis_text_tlast)begin if(text_index!=golden[received][6])$fatal(1,"Admitted text length");text_packets++;end
            end
        end
        if(completion_valid&&completion_ready)begin
            integer id;id=golden[received][0];
            if(!draining||received>=n_completions||completion_user!=definitions[id][0]||completion_application!=golden[received][7]||completion_stream!=definitions[id][1]||completion_generation!=32'(golden[received][8])||completion_ordinal!=golden[received][2]||completion_packet_tag!=32'(golden[received][1])||completion_status!=golden[received][3]||(golden[received][4]==255?completion_detail==0:completion_detail!=golden[received][4])||completion_memory_status!=golden[received][5]||
                (completion_status==0?(text_packets!=1||text_index!=golden[received][6]):text_packets!=0))$fatal(1,"Admission completion mismatch index=%0d status=%0d/%0d detail=%0d/%0d reads=%0d checks=%h base=%h bytes=%0d",completed,completion_status,golden[received][3],completion_detail,golden[received][4],payload_reads,dut.checks,dut.descriptor_base,dut.descriptor_bytes);
            if(completion_status>=4&&payload_reads!=0)$fatal(1,"Rejected descriptor read payload before admission");
            if(completion_status==0)successes++;else rejected++;
            received++;completed++;text_index=0;text_packets=0;payload_reads=0;
        end
    end
    task control_command(input integer op,input integer id,input integer wanted);
        begin
            @(negedge clk);control_op=3'(op);control_user=16'(definitions[id][0]);control_stream=31'(definitions[id][1]);control_application=16'(definitions[id][2]);control_generation=32'(definitions[id][3]);
            control_address=op==5?stream_recovery_address:handles[id];control_buffer_base=23'(definitions[id][4]);control_buffer_bytes=24'(definitions[id][5]);control_message_limit=32'(definitions[id][6]);control_protobuf=definitions[id][7]!=0;control_unsupported_encoding=definitions[id][8]!=0;control_maintenance=op==4||op==5;control_valid=1;
            do @(posedge clk);while(!control_ready);@(negedge clk);control_valid=0;control_op='1;control_user='1;control_stream='1;control_application='1;control_generation='1;control_address='1;control_buffer_base='1;control_buffer_bytes='1;control_message_limit='1;control_protobuf=!control_protobuf;control_unsupported_encoding=!control_unsupported_encoding;control_maintenance=0;
            wait(control_result_valid);
            if(control_status!=wanted||control_memory_status!=0||control_result_op!=op||control_result_user!=definitions[id][0]||control_result_stream!=definitions[id][1])$fatal(1,"Ingress Parser control mismatch op=%0d status=%0d/%0d",op,control_status,wanted);
            if(wanted==0&&op==0)handles[id]=control_result_address;
            if(wanted==0&&op<=1&&(control_result_application!=definitions[id][2]||control_result_generation!=definitions[id][3]||control_result_buffer_base!=definitions[id][4]))$fatal(1,"Admission configuration changed");
            repeat($urandom_range(2,7))@(negedge clk);control_result_ready=1;@(posedge clk);@(negedge clk);control_result_ready=0;controls++;
        end
    endtask
    task data_event(input integer kind,input integer stream,input integer data);
        begin
            repeat($urandom_range(0,2))@(negedge clk);s_kind=2'(kind);s_stream=31'(stream);s_data=8'(data);s_valid=1;
            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
        end
    endtask
    task packet(input integer user_id,input integer tag,input integer commit,input integer count);
        begin
            @(negedge clk);packet_start_user=16'(user_id);packet_start_tag=32'(tag);packet_start_valid=1;received_errors=0;
            do @(posedge clk);while(!packet_start_ready);@(negedge clk);packet_start_valid=0;packet_start_user='1;packet_start_tag='1;
            for(integer i=0;i<count;i++)data_event(events[i][0],events[i][1],events[i][2]);
            @(negedge clk);prepare_valid=1;do @(posedge clk);while(!prepare_ready);@(negedge clk);prepare_valid=0;
            wait(prepared_valid);if(prepared_failed)$fatal(1,"Unexpected integration PREPARE failure");
            repeat($urandom_range(2,9))@(negedge clk);prepared_ready=1;@(posedge clk);@(negedge clk);prepared_ready=0;
            decision_commit=commit!=0;decision_valid=1;do @(posedge clk);while(!decision_ready);@(negedge clk);decision_valid=0;decision_commit=0;
            wait(packet_result_valid);
            if(packet_status!=0||packet_committed!=(commit!=0)||packet_user!=user_id||packet_tag!=32'(tag)||received_errors!=n_errors)$fatal(1,"Integrated packet result mismatch");
            repeat($urandom_range(2,9))@(negedge clk);packet_result_ready=1;@(posedge clk);@(negedge clk);packet_result_ready=0;packets++;
        end
    endtask
    task drain(input integer client,input integer target,input integer probe);
        begin
            @(negedge clk);fault_client=client;fault_target=target;response_index=0;injected=0;received=0;payload_reads=0;text_index=0;text_packets=0;lease_cycles=0;probe_text_wait=0;draining=1;admit_messages=1;
            if(probe>=0)begin
                wait(payload_lease_active);@(negedge clk);probe_active=1;
                control_valid=1;control_op=3;control_user=16'(definitions[probe][0]);control_stream=31'(definitions[probe][1]);control_generation=32'(definitions[probe][3]);control_address=handles[probe];control_maintenance=0;
                packet_start_valid=1;packet_start_user=9;packet_start_tag='1;queue_cfg_valid=1;queue_cfg_clear=1;maintenance_grant=1;
                cfg_unlock=1;cfg_schema_valid=1;cfg_schema_json_enable=1;cfg_schema_proto_enable=1;cfg_schema_field=2;cfg_schema_key=32'h626164;cfg_schema_key_length=3;
                stream_cfg_valid=1;cfg_stream_base=23'h700003;cfg_stream_bytes=2048;
            end
            for(integer i=0;i<n_completions;i++)begin
                wait(completion_valid);repeat($urandom_range(8,21))@(negedge clk);completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;
            end
            if(received!=n_completions||injected!=(client>=0))$fatal(1,"Missing admitted completion or fault");
            if(injected)memory_faults++;
            admit_messages=0;draining=0;fault_client=-1;fault_target=-1;
            if(probe>=0)begin
                if(probe_text_wait<=40)$fatal(1,"Missing forced text stall during payload lease");
                probe_active=0;packet_start_valid=0;queue_cfg_valid=0;queue_cfg_clear=0;maintenance_grant=0;cfg_unlock=0;cfg_schema_valid=0;stream_cfg_valid=0;
                cfg_stream_base='1;cfg_stream_bytes='1;
                do @(posedge clk);while(!control_ready);@(negedge clk);control_valid=0;
                wait(control_result_valid);if(control_status!=0||control_result_op!=3)$fatal(1,"Deferred CLOSE failed");
                repeat(5)@(negedge clk);control_result_ready=1;@(posedge clk);@(negedge clk);control_result_ready=0;controls++;probes++;
            end
            if(client==0)begin
                if(!stream_recovery_required)$fatal(1,"Directory fault did not quarantine admission");
                cfg_stream_base=23'h700003;cfg_stream_bytes=2048;stream_cfg_valid=1;maintenance_grant=1;cfg_unlock=1;cfg_schema_valid=1;
                repeat(8)begin @(negedge clk);if(stream_cfg_ready||cfg_schema_ready||idle)$fatal(1,"Quarantine allowed pool/schema reconfiguration or healthy idle");end
                stream_cfg_valid=0;maintenance_grant=0;cfg_unlock=0;cfg_schema_valid=0;cfg_stream_base='1;cfg_stream_bytes='1;
            end
        end
    endtask
    initial begin:driver
        integer fd,rc,n_definitions,scanned,opcode,op,id,wanted,user_id,tag,commit,event_count,client,target,probe,offset;
        repeat(5)@(negedge clk);rst=0;
        queue_cfg_base=23'h7f0003;queue_cfg_bytes=512;queue_cfg_valid=1;
        do @(posedge clk);while(!queue_cfg_ready);@(negedge clk);queue_cfg_valid=0;
        wait(queue_cfg_result_valid);if(queue_cfg_status!=0)$fatal(1,"Parser integration queue configuration");queue_cfg_result_ready=1;@(posedge clk);@(negedge clk);queue_cfg_result_ready=0;
        for(integer valid_config=0;valid_config<2;valid_config++)begin
            cfg_stream_base=23'h780003;cfg_stream_bytes=valid_config?2048:129;stream_cfg_valid=1;
            do @(posedge clk);while(!stream_cfg_ready);@(negedge clk);stream_cfg_valid=0;
            wait(stream_cfg_result_valid);if(stream_cfg_status!=(valid_config?0:1))$fatal(1,"Directory pool validation");
            repeat(4)@(negedge clk);stream_cfg_result_ready=1;@(posedge clk);@(negedge clk);stream_cfg_result_ready=0;
        end
        cfg_stream_base='1;cfg_stream_bytes='1;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No ingress Parser fixtures");rc=$fscanf(fd,"%d",n_definitions);
        if(rc!=1||n_definitions>128)$fatal(1,"Bad Parser definition count");
        for(integer i=0;i<n_definitions;i++)for(integer j=0;j<9;j++)begin rc=$fscanf(fd,"%d",scanned);definitions[i][j]=scanned;if(rc!=1)$fatal(1,"Bad Parser definition");end
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",opcode);
            if(rc==1)begin
                if(opcode==0)begin rc=$fscanf(fd,"%d %d %d",op,id,wanted);if(rc!=3)$fatal(1,"Bad control command");control_command(op,id,wanted);end
                else if(opcode==1)begin
                    rc=$fscanf(fd,"%d %d %d %d %d",user_id,tag,commit,event_count,n_errors);if(rc!=5)$fatal(1,"Bad packet command");
                    for(integer i=0;i<event_count;i++)for(integer j=0;j<3;j++)begin rc=$fscanf(fd,"%d",scanned);events[i][j]=scanned;if(rc!=1)$fatal(1,"Bad packet event");end
                    for(integer i=0;i<n_errors;i++)for(integer j=0;j<4;j++)begin rc=$fscanf(fd,"%d",scanned);errors[i][j]=scanned;if(rc!=1)$fatal(1,"Bad RPC error");end
                    packet(user_id,tag,commit,event_count);
                end else if(opcode==2)begin
                    rc=$fscanf(fd,"%d %d %d %d",client,target,probe,n_completions);if(rc!=4)$fatal(1,"Bad drain command");offset=0;
                    for(integer i=0;i<n_completions;i++)begin
                        for(integer j=0;j<9;j++)begin rc=$fscanf(fd,"%d",scanned);golden[i][j]=scanned;if(rc!=1)$fatal(1,"Bad admitted completion");end
                        offsets[i]=offset;
                        for(integer j=0;j<golden[i][6];j++)begin rc=$fscanf(fd,"%h",expected[offset]);if(rc!=1)$fatal(1,"Bad admitted text");offset++;end
                    end
                    drain(client,target,probe);
                end else if(opcode==3)begin
                    if(corrupt_armed)$fatal(1,"Prior queue mutation unused");rc=$fscanf(fd,"%d %h %h",corrupt_word,corrupt_mask,corrupt_value);if(rc!=3)$fatal(1,"Bad queue mutation");
                    write_index=0;corrupt_armed=1;
                end else $fatal(1,"Unknown Parser fixture command");
            end else if(!$feof(fd))$fatal(1,"Malformed Parser fixture");
        end
        $fclose(fd);wait(idle&&fabric_idle);
        if(packets<150||successes<50||rejected<20||memory_faults!=11||corruptions!=7||probes!=1||text_stalls==0||corrupt_armed)$fatal(1,"Insufficient ingress Parser coverage packets=%0d successes=%0d rejects=%0d",packets,successes,rejected);
        $display("PASS: committed gRPC ingress to actual Parser: %0d packets/%0d controls/%0d exact text messages/%0d rejected descriptors or applications/%0d memory faults/%0d corrupted queue records; live generations, payload pinning, deferred mutations, metadata, replay aborts and recovery",packets,controls,successes,rejected,memory_faults,corruptions);$finish;
    end
    initial begin #100000000;$fatal(1,"Ingress Parser timeout state=%0d packet_busy=%0d controls=%0d packets=%0d completions=%0d",dut.state,dut.packet_busy,controls,packets,completed);end
endmodule

