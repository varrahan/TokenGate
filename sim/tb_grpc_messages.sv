`timescale 1ns/1ps
module tb_grpc_messages;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0;wire start_ready;
    logic [15:0] start_user=0,start_application=0;logic [30:0] start_stream=0;
    logic [22:0] cfg_buffer_base=0;logic [23:0] cfg_buffer_bytes=0;logic [31:0] cfg_message_limit=0;
    logic cfg_unsupported_encoding=0;logic [255:0] cfg_state=0;
    logic s_valid=0;wire s_ready;logic [1:0] s_kind=0;logic [7:0] s_data=0;logic [15:0] s_user=0;logic [30:0] s_stream=0;
    wire message_valid;logic message_ready=0;wire [22:0] message_base;wire [31:0] message_bytes,message_ordinal;
    wire [15:0] message_user,message_application;wire [30:0] message_stream;
    logic finish_valid=0,result_ready=0;wire result_valid;wire [255:0] result_state;wire [7:0] result_status,result_detail,result_memory_status;
    wire [15:0] result_user;wire [30:0] result_stream;wire idle;
    wire mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data,mem_rsp_data;wire [7:0] mem_rsp_status;
    wire [1:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [45:0] cmd_addr;wire [7:0] cmd_bytes;wire [143:0] cmd_data,response_data;wire [15:0] response_status;
    logic helper_valid=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;
    integer write_responses=0;bit injected=0;
    integer fields[0:14],events[0:131071][0:3],bases[0:1023],sizes[0:1023],ordinals[0:1023],offsets[0:1023],expected[0:262143];
    logic [255:0] saved_state[0:2],initial_state,expected_state;
    integer segments=0,messages=0,errors=0,faults=0,received=0,total_bytes=0;
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={1'b0,mem_write};assign cmd_addr={helper_addr,mem_addr};
    assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={72'd0,mem_data};assign response_ready={helper_rsp_ready,mem_rsp_ready};
    assign mem_ready=cmd_ready[0];assign mem_rsp_valid=response_valid[0];assign mem_rsp_data=response_data[0+:72];
    assign mem_rsp_status=!injected&&write_responses==fields[13]?8'h51:response_status[0+:8];
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    grpc_message_deframer dut(.*);
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
    bit message_stalled=0,result_stalled=0,mem_stalled=0;logic [149:0] held_message;logic [326:0] held_result;logic [99:0] held_mem;
    wire [149:0] message_bundle={message_base,message_bytes,message_ordinal,message_user,message_application,message_stream};
    wire [326:0] result_bundle={result_state,result_status,result_detail,result_memory_status,result_user,result_stream};
    always @(posedge clk)if(!rst)begin
        if(message_stalled&&(!message_valid||held_message!==message_bundle))$fatal(1,"gRPC message lease unstable");
        if(result_stalled&&(!result_valid||held_result!==result_bundle))$fatal(1,"gRPC result unstable");
        if(mem_stalled&&(!mem_valid||held_mem!=={mem_write,mem_addr,mem_bytes,mem_data}))$fatal(1,"gRPC write command unstable");
        message_stalled=message_valid&&!message_ready;held_message=message_bundle;
        result_stalled=result_valid&&!result_ready;held_result=result_bundle;
        mem_stalled=mem_valid&&!mem_ready;held_mem={mem_write,mem_addr,mem_bytes,mem_data};
        if((^{start_ready,s_ready,message_valid,result_valid,mem_valid,mem_rsp_ready})===1'bx)$fatal(1,"Unknown gRPC handshake");
        if(message_valid&&((^message_bundle)===1'bx)||result_valid&&((^result_bundle)===1'bx)||mem_valid&&((^held_mem)===1'bx))$fatal(1,"Unknown gRPC metadata");
        if(mem_valid&&(!mem_write||mem_bytes!=1||mem_addr<fields[5]||{1'b0,mem_addr}>={1'b0,fields[5]}+fields[6]))$fatal(1,"gRPC allocation escaped");
        if(mem_rsp_valid&&mem_rsp_ready)begin
            if(write_responses==fields[13])injected<=1;
            write_responses<=write_responses+1;
        end
    end
    task helper(input integer address,input integer size,output reg [71:0] result);
        begin
            @(negedge clk);helper_valid=1;helper_addr=23'(address);helper_bytes=4'(size);
            do @(posedge clk);while(!cmd_ready[1]);@(negedge clk);helper_valid=0;helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[1]);if(response_status[8+:8]!=0)$fatal(1,"gRPC staged payload read failed");result=response_data[72+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    task consume_messages;
        integer chunk;reg [71:0] value;
        begin
            while(!result_valid)begin
                @(negedge clk);
                if(message_valid)begin
                    if(received>=fields[14]||message_base!=bases[received]||message_bytes!=sizes[received]||message_ordinal!=ordinals[received]||message_user!=fields[2]||message_stream!=fields[3]||message_application!=fields[4])$fatal(1,"gRPC message mismatch segment=%0d message=%0d base=%h/%h size=%0d/%0d ordinal=%0d/%0d",segments,received,message_base,bases[received],message_bytes,sizes[received],message_ordinal,ordinals[received]);
                    for(integer i=0;i<sizes[received];i+=8)begin
                        chunk=sizes[received]-i;if(chunk>8)chunk=8;helper(bases[received]+i,chunk,value);
                        for(integer lane=0;lane<chunk;lane++)if(value[lane*8+:8]!==8'(expected[offsets[received]+i+lane]))$fatal(1,"gRPC payload mismatch segment=%0d byte=%0d",segments,i+lane);
                    end
                    repeat($urandom_range(1,9))@(negedge clk);message_ready=1;@(posedge clk);@(negedge clk);message_ready=0;
                    total_bytes+=sizes[received];received++;messages++;
                end
            end
        end
    endtask
    initial begin:driver
        integer fd,rc,offset,scanned;
        for(integer i=0;i<3;i++)saved_state[i]=0;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No gRPC message fixtures");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<15;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad gRPC fixture");end
                rc=$fscanf(fd,"%h %h",initial_state,expected_state);if(rc!=2)$fatal(1,"Bad gRPC state fixture");
                for(integer i=0;i<fields[9];i++)for(integer j=0;j<4;j++)begin rc=$fscanf(fd,"%d",scanned);events[i][j]=scanned;if(rc!=1)$fatal(1,"Bad gRPC input event");end
                offset=0;
                for(integer m=0;m<fields[14];m++)begin
                    rc=$fscanf(fd,"%d %d %d",bases[m],sizes[m],ordinals[m]);if(rc!=3)$fatal(1,"Bad gRPC message golden");offsets[m]=offset;
                    for(integer i=0;i<sizes[m];i++)begin rc=$fscanf(fd,"%h",expected[offset]);if(rc!=1)$fatal(1,"Bad gRPC payload golden");offset++;end
                end
                if(fields[1])saved_state[fields[0]]=initial_state;
                if(saved_state[fields[0]]!==initial_state)$fatal(1,"gRPC restored-state oracle mismatch segment=%0d actual=%h expected=%h",segments,saved_state[fields[0]],initial_state);
                @(negedge clk);start_user=16'(fields[2]);start_stream=31'(fields[3]);start_application=16'(fields[4]);cfg_buffer_base=23'(fields[5]);cfg_buffer_bytes=24'(fields[6]);cfg_message_limit=32'(fields[7]);
                cfg_unsupported_encoding=fields[8]!=0;cfg_state=saved_state[fields[0]];start_valid=1;write_responses=0;injected=0;received=0;
                do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;cfg_state='1;cfg_buffer_base='1;cfg_buffer_bytes='1;cfg_message_limit=0;cfg_unsupported_encoding=!cfg_unsupported_encoding;start_user='1;start_stream=0;start_application=0;
                fork
                    begin
                        for(integer i=0;i<fields[9];i++)begin
                            repeat($urandom_range(0,3))@(negedge clk);s_kind=2'(events[i][0]);s_data=8'(events[i][1]);s_user=16'(events[i][2]);s_stream=31'(events[i][3]);s_valid=1;
                            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
                        end
                        finish_valid=1;
                    end
                    consume_messages();
                join
                wait(result_valid);
                if(result_status!=fields[10]||result_detail!=fields[11]||result_memory_status!=fields[12]||result_state!==expected_state||result_user!=fields[2]||result_stream!=fields[3]||received!=fields[14]||injected!=(fields[13]>=0))$fatal(1,"gRPC result mismatch segment=%0d status=%0d/%0d detail=%0d/%0d state=%h/%h messages=%0d/%0d",segments,result_status,fields[10],result_detail,fields[11],result_state,expected_state,received,fields[14]);
                saved_state[fields[0]]=result_state;if(result_status!=0)errors++;if(injected)faults++;
                repeat($urandom_range(2,10))@(negedge clk);result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;finish_valid=0;wait(idle&&fabric_idle);
                segments++;if(segments%50==0)$display("PROGRESS: %0d gRPC stream segments",segments);
            end else if(!$feof(fd))$fatal(1,"Malformed gRPC fixture");
        end
        $fclose(fd);
        if(segments<100||messages<100||errors<20||faults!=12||total_bytes<65537)$fatal(1,"Insufficient gRPC message coverage");
        $display("PASS: gRPC message deframer: %0d stream segments/%0d exact message leases/%0d bytes/%0d failures/%0d write faults; prefix/payload resume, interleaved contexts, append allocation, compression/length/EOS errors, snapshots and leases",segments,messages,total_bytes,errors,faults);$finish;
    end
    initial begin #(64'd500000000);$fatal(1,"gRPC message timeout segment=%0d state=%0d",segments,dut.state);end
endmodule
