`timescale 1ns/1ps
module tb_grpc_application;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0;wire start_ready;logic [15:0] context_id=0,application_id=0;logic [30:0] stream_id=0;
    logic input_valid=0,input_eos=0,finish_valid=0,def_result_ready=0;logic [7:0] input_data=0;wire input_ready,def_result_valid,def_idle;
    wire [255:0] def_state;wire [7:0] def_status,def_detail,def_memory;
    wire message_valid,message_ready;wire [22:0] message_base;wire [31:0] message_bytes,message_ordinal;wire [15:0] message_user,message_application;wire [30:0] message_stream;
    logic manual=0,manual_valid=0;wire application_ready;assign message_ready=!manual&&application_ready;
    logic message_protobuf=0;wire [127:0] text_data;wire [15:0] text_keep,text_user;wire text_valid,text_last;logic text_ready=0;
    wire completion_valid;logic completion_ready=0;wire [7:0] completion_status,completion_detail,completion_memory_status;wire [15:0] completion_user,completion_application;wire [30:0] completion_stream;wire [31:0] completion_ordinal;wire app_idle;
    wire [1:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [45:0] mem_addr;wire [7:0] mem_bytes;wire [143:0] mem_data,mem_rsp_data;logic [15:0] mem_rsp_status;wire [15:0] response_status;
    integer fields[0:6],raw[0:131071],golden[0:1023][0:4],expected[0:262143],offsets[0:1023];
    integer cases=0,completed=0,received=0,text_index=0,text_packets=0,successes=0,errors=0,read_faults=0,read_responses=0,replay_stalls=0;bit injected=0;
    grpc_message_deframer deframer(
        .clk(clk),.rst(rst),.start_valid(start_valid),.start_ready(start_ready),.start_user(context_id),.start_stream(stream_id),.start_application(application_id),
        .cfg_buffer_base(23'h300003),.cfg_buffer_bytes(24'd131072),.cfg_message_limit(32'd65536),.cfg_unsupported_encoding(1'b0),.cfg_state(256'd0),
        .s_valid(input_valid),.s_ready(input_ready),.s_kind(input_eos?2'd1:2'd0),.s_data(input_data),.s_user(context_id),.s_stream(stream_id),
        .message_valid(message_valid),.message_ready(message_ready),.message_base(message_base),.message_bytes(message_bytes),.message_ordinal(message_ordinal),.message_user(message_user),.message_application(message_application),.message_stream(message_stream),
        .finish_valid(finish_valid),.result_valid(def_result_valid),.result_ready(def_result_ready),.result_state(def_state),.result_status(def_status),.result_detail(def_detail),.result_memory_status(def_memory),.result_user(),.result_stream(),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:23]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),.mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(def_idle));
    grpc_application_decoder #(.MAX_TEXT_BYTES(1024),.MAX_FIELD_BYTES(4096)) application(
        .clk(clk),.rst(rst),.message_valid(manual?manual_valid:message_valid),.message_ready(application_ready),.message_base(manual?23'h7fffff:message_base),.message_bytes(manual?32'd2:message_bytes),.message_ordinal(manual?32'd0:message_ordinal),.message_user(manual?context_id:message_user),.message_application(manual?application_id:message_application),.message_stream(manual?stream_id:message_stream),.message_protobuf(message_protobuf),
        .cfg_unlock(1'b0),.cfg_schema_valid(1'b0),.cfg_schema_ready(),.cfg_schema_index(4'd0),.cfg_schema_key(256'd0),.cfg_schema_key_length(6'd0),.cfg_schema_json_enable(1'b0),.cfg_schema_field(29'd0),.cfg_schema_proto_enable(1'b0),
        .m_axis_text_tdata(text_data),.m_axis_text_tkeep(text_keep),.m_axis_text_tvalid(text_valid),.m_axis_text_tready(text_ready),.m_axis_text_tlast(text_last),.m_axis_text_tuser(text_user),
        .completion_valid(completion_valid),.completion_ready(completion_ready),.completion_status(completion_status),.completion_detail(completion_detail),.completion_memory_status(completion_memory_status),.completion_user(completion_user),.completion_application(completion_application),.completion_stream(completion_stream),.completion_ordinal(completion_ordinal),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[23+:23]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),.mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),.idle(app_idle));
    always @*begin mem_rsp_status=response_status;if(!injected&&read_responses==fields[2])mem_rsp_status[8+:8]=8'h62;end
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(2)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    bit text_stalled=0,completion_stalled=0;logic [160:0] held_text;logic [118:0] held_completion;logic [1:0] mem_stalled=0;logic [99:0] held_mem[0:1];
    bit replay_stalled=0;logic [593:0] held_replay;
    wire [593:0] replay_bundle={application.replay_data,application.replay_keep,application.replay_last,application.replay_user,application.replay_abort};
    wire [118:0] completion_bundle={completion_status,completion_detail,completion_memory_status,completion_user,completion_application,completion_stream,completion_ordinal};
    always @(negedge clk)begin text_ready=$urandom_range(0,3)!=0;completion_ready=$urandom_range(0,3)!=0;end
    always @(posedge clk)if(!rst)begin
        if(replay_stalled&&(!application.replay_valid||held_replay!==replay_bundle))$fatal(1,"512-bit replay changed under Parser backpressure");
        replay_stalled=application.replay_valid&&!application.replay_ready;held_replay=replay_bundle;
        if(replay_stalled)replay_stalls++;
        if((^{application.replay_valid,application.replay_ready})===1'bx||application.replay_valid&&((^replay_bundle)===1'bx))$fatal(1,"Unknown replay packet/abort metadata");
        if(text_stalled&&(!text_valid||held_text!=={text_user,text_last,text_keep,text_data}))$fatal(1,"gRPC application text unstable");text_stalled=text_valid&&!text_ready;held_text={text_user,text_last,text_keep,text_data};
        if(completion_stalled&&(!completion_valid||held_completion!==completion_bundle))$fatal(1,"gRPC application completion unstable");completion_stalled=completion_valid&&!completion_ready;held_completion=completion_bundle;
        if((^{message_ready,text_valid,completion_valid,input_ready,mem_valid,mem_rsp_ready})===1'bx)$fatal(1,"Unknown gRPC application handshake");
        if(text_valid&&((^{text_data,text_keep,text_last,text_user})===1'bx)||completion_valid&&((^completion_bundle)===1'bx))$fatal(1,"Unknown gRPC application metadata");
        for(integer c=0;c<2;c++)begin
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"gRPC application memory unstable");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&((^held_mem[c])===1'bx))$fatal(1,"Unknown gRPC application memory command");
        end
        if(mem_rsp_valid[1]&&mem_rsp_ready[1])begin if(read_responses==fields[2])injected<=1;read_responses<=read_responses+1;end
        if(text_valid)begin if(received>=fields[3]||golden[received][1]!=0)$fatal(1,"Text leaked from aborted/invalid application message case=%0d",cases);end
        if(text_valid&&text_ready)begin
            if(text_user!=fields[6])$fatal(1,"gRPC application context changed");
            for(integer lane=0;lane<16;lane++)if(text_keep[lane])begin
                if(text_index>=golden[received][4]||text_data[lane*8+:8]!==8'(expected[offsets[received]+text_index]))$fatal(1,"gRPC application text mismatch case=%0d message=%0d byte=%0d",cases,received,text_index);
                text_index++;
            end
            if(text_last)begin if(text_index!=golden[received][4])$fatal(1,"gRPC application text length");text_packets++;end
        end
        if(completion_valid&&completion_ready)begin
            if(received>=fields[3]||completion_ordinal!=golden[received][0]||completion_status!=golden[received][1]||
                (golden[received][2]==255?completion_detail==0:completion_detail!=golden[received][2])||completion_memory_status!=golden[received][3]||completion_user!=fields[4]||completion_stream!=fields[5]||completion_application!=fields[6]||
                (completion_status==0?(text_packets!=1||text_index!=golden[received][4]):text_packets!=0))$fatal(1,"gRPC application completion mismatch case=%0d message=%0d status=%0d/%0d detail=%0d/%0d text_packets=%0d",cases,received,completion_status,golden[received][1],completion_detail,golden[received][2],text_packets);
            if(completion_status==0)successes++;else errors++;
            received++;completed++;text_packets=0;text_index=0;
        end
    end
    task byte_event(input [7:0] data,input bit eos);
        begin
            repeat($urandom_range(0,2))@(negedge clk);input_data=data;input_eos=eos;input_valid=1;
            do @(posedge clk);while(!input_ready);@(negedge clk);input_valid=0;
        end
    endtask
    initial begin:driver
        integer fd,rc,scanned,offset;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No gRPC application fixture");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<7;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad gRPC application fixture");end
                for(integer i=0;i<fields[1];i++)begin rc=$fscanf(fd,"%h",raw[i]);if(rc!=1)$fatal(1,"Bad gRPC application wire");end
                offset=0;
                for(integer m=0;m<fields[3];m++)begin
                    for(integer j=0;j<5;j++)begin rc=$fscanf(fd,"%d",scanned);golden[m][j]=scanned;if(rc!=1)$fatal(1,"Bad gRPC application golden");end
                    offsets[m]=offset;
                    for(integer i=0;i<golden[m][4];i++)begin rc=$fscanf(fd,"%h",expected[offset]);if(rc!=1)$fatal(1,"Bad gRPC application text golden");offset++;end
                end
                @(negedge clk);message_protobuf=fields[0]!=0;context_id=16'(fields[4]);stream_id=31'(fields[5]);application_id=16'(fields[6]);start_valid=1;received=0;text_index=0;text_packets=0;read_responses=0;injected=0;
                do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;
                for(integer i=0;i<fields[1];i++)byte_event(8'(raw[i]),0);
                byte_event(0,1);finish_valid=1;
                wait(def_result_valid&&received==fields[3]&&app_idle&&fabric_idle);
                if(def_status!=0||def_detail!=0||def_memory!=0||injected!=(fields[2]>=0))$fatal(1,"gRPC deframer/application ownership failure");
                if(injected)read_faults++;
                @(negedge clk);def_result_ready=1;@(posedge clk);@(negedge clk);def_result_ready=0;finish_valid=0;wait(def_idle);cases++;
                if(cases%25==0)$display("PROGRESS: %0d gRPC/application sequences",cases);
            end else if(!$feof(fd))$fatal(1,"Malformed gRPC application fixture");
        end
        $fclose(fd);
        // Invalid descriptor bounds must terminate an aborted packet without
        // issuing a wrapped physical read, then allow the pipeline to drain.
        @(negedge clk);manual=1;message_protobuf=0;fields[2]=-1;fields[3]=1;fields[4]=68;fields[5]=17;fields[6]=273;
        context_id=68;stream_id=17;application_id=273;received=0;text_index=0;text_packets=0;read_responses=0;injected=0;
        golden[0][0]=0;golden[0][1]=1;golden[0][2]=129;golden[0][3]=0;golden[0][4]=0;offsets[0]=0;manual_valid=1;
        do @(posedge clk);while(!application_ready);@(negedge clk);manual_valid=0;
        wait(received==1&&app_idle&&fabric_idle);
        if(read_responses!=0)$fatal(1,"Invalid message descriptor wrapped into physical RAM");cases++;
        if(cases<90||completed<150||successes<100||errors<40||read_faults!=32)$fatal(1,"Insufficient gRPC application coverage");
        $display("PASS: gRPC wire -> external messages -> actual JSON/Protobuf Parser: %0d sequences/%0d messages/%0d committed/%0d rejected/%0d read faults/%0d replay stall cycles; real memory replay, append leases, 512-bit abort propagation, valid-prefix suppression and recovery",cases,completed,successes,errors,read_faults,replay_stalls);$finish;
    end
    initial begin #(64'd100000000);$fatal(1,"gRPC application timeout case=%0d def=%0d app=%0d parser=%0d",cases,deframer.state,application.state,application.parser.state);end
endmodule
