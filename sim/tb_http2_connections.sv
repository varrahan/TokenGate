`timescale 1ns/1ps
module tb_http2_connections #(parameter integer SEMANTIC=0);
    logic clk=0,rst=1;always #2 clk=~clk;
    logic admit_packets=1;logic [22:0] cfg_context_base=23'h7c0003;logic [23:0] cfg_context_bytes=16384;
    logic command_valid=0;wire command_ready;logic [1:0] command_op=0;logic [15:0] command_user=0;logic command_server_role=1,command_allow_push=0;logic [23:0] command_max_frame_bytes=16384;
    logic [511:0] s_axis_rx_tdata=0;logic [63:0] s_axis_rx_tkeep=0;logic s_axis_rx_tvalid=0,s_axis_rx_tlast=0;logic [15:0] s_axis_rx_tuser=0;wire s_axis_rx_tready;
    wire event_valid;logic event_ready=0;wire [3:0] event_kind;wire [31:0] event_arg0,event_arg1;wire [7:0] event_data,event_type,event_flags;wire [23:0] event_length;wire [30:0] event_stream;
    wire event_payload_last;wire [31:0] event_error;wire [15:0] event_user;
    wire rsp_valid,rsp_is_command,idle,recovery_required;logic rsp_ready=0;wire [1:0] rsp_command_op;wire [7:0] rsp_status,rsp_detail,rsp_memory_status;wire [31:0] rsp_http2_error;wire [15:0] rsp_user;wire [22:0] recovery_address;
    wire mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data,mem_rsp_data;wire [7:0] mem_rsp_status;
    wire [71:0] response_data;wire [7:0] response_status;integer fault_target=-1,response_index=0;bit injected=0;
    assign mem_rsp_data=response_data;assign mem_rsp_status=!injected&&response_index==fault_target?8'h52:response_status;
    wire aux_start_valid,aux_server_role,aux_finish_valid,aux_result_ready;
    wire aux_start_ready=1'b0,aux_result_valid=1'b0,aux_failed=1'b0;
    wire [255:0] aux_restore;wire [255:0] aux_save=256'd0;wire [15:0] aux_user;wire [31:0] aux_error=0;wire [7:0] aux_detail=0;
    wire [255:0] command_aux_initial=256'd0;
    generate if(!SEMANTIC)begin:raw_path
        wire [1:0] raw_kind;
        http2_connection_ingress dut(.event_kind(raw_kind),.*);
        assign event_kind={2'd0,raw_kind};assign event_arg0=0;assign event_arg1=0;
    end else begin:semantic_path
        http2_transport_ingress dut(.*);
        assign event_payload_last=0;assign event_error=0;
    end endgenerate
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(1)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    integer fields[0:11],raw[0:65535],golden[0:65535][0:9],received=0,total=0,events_total=0,errors=0,controls=0,faults=0;
    bit event_stalled=0,result_stalled=0,mem_stalled=0;logic [195:0] held_event;logic [74:0] held_result;logic [99:0] held_mem;
    wire [195:0] event_bundle={event_kind,event_data,event_arg0,event_arg1,event_length,event_type,event_flags,event_stream,event_payload_last,event_error,event_user};
    wire [74:0] result_bundle={rsp_is_command,rsp_command_op,rsp_status,rsp_detail,rsp_memory_status,rsp_http2_error,rsp_user};
    always @(negedge clk)event_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(event_stalled&&(!event_valid||held_event!==event_bundle))$fatal(1,"Connection event unstable");event_stalled=event_valid&&!event_ready;held_event=event_bundle;
        if(result_stalled&&(!rsp_valid||held_result!==result_bundle))$fatal(1,"Connection result unstable");result_stalled=rsp_valid&&!rsp_ready;held_result=result_bundle;
        if(mem_stalled&&(!mem_valid||held_mem!=={mem_write,mem_addr,mem_bytes,mem_data}))$fatal(1,"Connection command unstable");mem_stalled=mem_valid&&!mem_ready;held_mem={mem_write,mem_addr,mem_bytes,mem_data};
        if((^{event_valid,rsp_valid,command_ready,s_axis_rx_tready,recovery_required})===1'bx)$fatal(1,"Unknown connection handshake");
        if(event_valid&&((^event_bundle)===1'bx)||rsp_valid&&((^result_bundle)===1'bx)||mem_valid&&((^held_mem)===1'bx))$fatal(1,"Unknown connection metadata");
        if(rsp_valid&&(command_ready||s_axis_rx_tready))$fatal(1,"Held result admitted work");
        if(mem_rsp_valid&&mem_rsp_ready)begin if(response_index==fault_target)injected<=1;response_index<=response_index+1;end
        if(event_valid&&event_ready)begin
            if(received>=fields[7]||event_kind!=golden[received][0]||event_data!=golden[received][1]||event_length!=golden[received][SEMANTIC?4:2]||event_type!=golden[received][SEMANTIC?5:3]||event_flags!=golden[received][SEMANTIC?6:4]||event_stream!=golden[received][SEMANTIC?7:5]||event_user!=fields[0]||
               (SEMANTIC?(event_arg0!=golden[received][2]||event_arg1!=golden[received][3]):(event_payload_last!=golden[received][6]||event_error!=golden[received][7])))$fatal(1,"Stored connection event mismatch packet=%0d event=%0d kind=%0d/%0d args=%0d/%0d vs %0d/%0d type=%0d/%0d",total,received,event_kind,golden[received][0],event_arg0,event_arg1,golden[received][2],golden[received][3],event_type,golden[received][5]);
            received++;events_total++;
        end
    end
    function automatic [7:0] physical_byte(input integer address);
        physical_byte=memory_model.memory[address>>3][(address&7)*8+:8];
    endfunction
    function automatic [159:0] physical_state(input integer context_number);
        reg [159:0] value;
        begin for(integer i=0;i<20;i++)value[i*8+:8]=physical_byte(24'h7c0003+context_number*256+8+i);physical_state=value;end
    endfunction
    function automatic [63:0] physical_header(input integer context_number);
        reg [63:0] value;
        begin for(integer i=0;i<8;i++)value[i*8+:8]=physical_byte(24'h7c0003+context_number*256+i);physical_header=value;end
    endfunction
    task acknowledge;
        begin repeat($urandom_range(2,10))@(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;wait(idle&&fabric_idle);end
    endtask
    task control(input integer op,input integer context_number,input integer maximum,input bit role,input bit push,input integer expected_status,input integer expected_detail);
        begin
            @(negedge clk);command_op=2'(op);command_user=16'(context_number);command_max_frame_bytes=24'(maximum);command_server_role=role;command_allow_push=push;command_valid=1;
            do @(posedge clk);while(!command_ready);@(negedge clk);command_valid=0;command_user='1;command_max_frame_bytes=0;command_server_role=!role;command_allow_push=!push;
            wait(rsp_valid);if(!rsp_is_command||rsp_command_op!=op||rsp_status!=expected_status||rsp_detail!=expected_detail||rsp_user!=context_number)$fatal(1,"Control mismatch op=%0d status=%0d/%0d detail=%0d/%0d",op,rsp_status,expected_status,rsp_detail,expected_detail);
            acknowledge;controls++;
        end
    endtask
    task beat(input [511:0] data,input [63:0] keep,input last,input [15:0] context_number);
        begin
            repeat($urandom_range(0,3))@(negedge clk);s_axis_rx_tdata=data;s_axis_rx_tkeep=keep;s_axis_rx_tlast=last;s_axis_rx_tuser=context_number;s_axis_rx_tvalid=1;
            do @(posedge clk);while(!s_axis_rx_tready);@(negedge clk);s_axis_rx_tvalid=0;
        end
    endtask
    task fault_setup(input integer target);
        begin @(negedge clk);fault_target=target;response_index=0;injected=0;end
    endtask
    initial begin:driver
        integer fd,rc,scanned,position;reg [511:0] data;reg [63:0] keep;bit sent_last;reg [159:0] prior_state;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"No connection wire vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<12;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad connection fixture");end
                for(integer i=0;i<fields[6];i++)begin rc=$fscanf(fd,"%h",raw[i]);if(rc!=1)$fatal(1,"Bad connection bytes");end
                for(integer i=0;i<fields[7];i++)for(integer j=0;j<(SEMANTIC?10:8);j++)begin rc=$fscanf(fd,"%d",scanned);golden[i][j]=scanned;if(rc!=1)$fatal(1,"Bad connection event");end
                if(fields[5]==0)begin
                if(fields[1])control(0,fields[0],fields[4],fields[2]!=0,fields[3]!=0,0,0);
                received=0;position=0;sent_last=0;
                while(position<fields[6])begin
                    data=0;keep=0;
                    for(integer lane=0;lane<64;lane++)if(position<fields[6]&&$urandom_range(0,3)!=0)begin data[lane*8+:8]=8'(raw[position]);keep[lane]=1;position++;end
                    sent_last=position==fields[6];beat(data,keep,sent_last,16'(fields[0]));
                end
                if(!sent_last)beat(0,0,1,16'(fields[0]));
                wait(rsp_valid);if(rsp_is_command||rsp_status!=(fields[8]?4:0)||rsp_http2_error!=fields[9]||rsp_detail!=fields[10]||rsp_user!=fields[0]||received!=fields[7])$fatal(1,"Stored fragment mismatch %0d status=%0d error=%0d/%0d detail=%0d/%0d events=%0d/%0d",total,rsp_status,rsp_http2_error,fields[9],rsp_detail,fields[10],received,fields[7]);
                if(fields[8])begin errors++;for(integer i=0;i<8;i++)if(physical_byte(24'h7c0003+fields[0]*256+i)!==8'd0)$fatal(1,"Protocol-failed record stayed active");end
                else begin
                    if(fields[11]&&physical_state(fields[0])!==((160'd1<<135)|160'd24))$fatal(1,"State was not durably stored");
                    if((physical_byte(24'h7c0003+fields[0]*256+4)&8'h08)!=0)$fatal(1,"Fresh flag survived packet commit");
                end
                acknowledge;total++;if(total%50==0)$display("PROGRESS: %0d externally scheduled HTTP/2 packets",total);
                end
            end else if(!$feof(fd))$fatal(1,"Bad connection fixture header");
        end
        $fclose(fd);fields[0]=10;fields[7]=0;received=0;
        prior_state=physical_state(6);control(2,6,65537,0,1,0,0);
        if(prior_state===160'd0||physical_state(6)!==prior_state||physical_header(6)!=={24'd65537,8'h07,32'h48324331})$fatal(1,"UPDATE lost an established connection state");
        // Every load/save phase, with explicit quarantine and exact-address recovery.
        control(0,10,16384,1,0,0,0);
        for(integer target=0;target<(SEMANTIC?17:9);target++)begin
            fault_setup(target);beat(0,0,1,10);wait(rsp_valid);
            if(rsp_status!=(target<(SEMANTIC?8:4)?2:5)||rsp_detail!=(target<(SEMANTIC?8:4)?target:target-(SEMANTIC?8:4))||rsp_memory_status!=8'h52||!injected||!recovery_required||recovery_address!=23'h7c0a03)$fatal(1,"Memory phase fault not contained target=%0d status=%0d detail=%0d mem=%0d injected=%0d recovery=%0d addr=%h responses=%0d",target,rsp_status,rsp_detail,rsp_memory_status,injected,recovery_required,recovery_address,response_index);
            acknowledge;faults++;fault_setup(-1);if(s_axis_rx_tready)$fatal(1,"Poisoned scheduler admitted packet");
            control(0,11,16384,1,0,6,0);control(1,10,16384,1,0,0,0);if(recovery_required)$fatal(1,"Close did not recover");control(0,10,16384,1,0,0,0);
        end
        for(integer target=0;target<(SEMANTIC?9:5);target++)begin
            fault_setup(target);control(0,10,16384,1,0,5,target);
            if(!recovery_required||!injected)$fatal(1,"Open fault not quarantined");faults++;fault_setup(-1);control(0,10,16384,1,0,0,0);if(recovery_required)$fatal(1,"Open did not recover");
        end
        prior_state=physical_state(10);control(2,10,65537,0,1,0,0);if(physical_state(10)!==prior_state||physical_header(10)!=={24'd65537,8'h0f,32'h48324331})$fatal(1,"UPDATE failed to preserve state/role while changing negotiated limits");
        for(integer target=0;target<2;target++)begin
            fault_setup(target);control(2,10,65537,0,0,target==0?2:5,target==0?0:(SEMANTIC?8:4));
            if(!injected||!recovery_required)$fatal(1,"Update fault not quarantined");faults++;fault_setup(-1);control(0,10,16384,1,0,0,0);
        end
        fault_setup(0);control(1,10,16384,1,0,5,0);if(!injected||!recovery_required)$fatal(1,"Close fault not quarantined");faults++;fault_setup(-1);control(0,10,16384,1,0,0,0);
        beat(0,0,1,10);cfg_context_base=0;cfg_context_bytes=0;wait(rsp_valid);if(rsp_status!=0)$fatal(1,"Accepted packet did not snapshot pool configuration");acknowledge;cfg_context_base=23'h7c0003;cfg_context_bytes=16384;
        control(1,10,16384,1,0,0,0);beat(0,0,1,10);wait(rsp_valid);if(rsp_status!=3)$fatal(1,"Closed connection admitted packet");acknowledge;
        control(0,10,16384,1,0,0,0);fault_setup(0);beat(1,1,0,10);beat(0,0,1,10);wait(rsp_valid);if(rsp_status!=2||!recovery_required)$fatal(1,"Read-fault multi-beat drain failed");acknowledge;faults++;fault_setup(-1);control(1,10,16384,1,0,0,0);
        control(0,100,16384,1,0,1,0);control(3,10,16384,1,0,7,0);control(0,10,100,1,0,1,1);
        for(integer c=0;c<16;c++)for(integer offset=SEMANTIC?64:32;offset<256;offset++)begin
            scanned=24'h7c0003+c*256+offset;
            if(physical_byte(scanned)!==8'(scanned*37+(scanned>>5)*19+7))$fatal(1,"Record update clobbered reserved transport metadata");
        end
        if(total<400||errors<70||faults!=(SEMANTIC?30:18))$fatal(1,"Insufficient connection coverage");
        $display("PASS: external HTTP/2 ingress semantic=%0d: %0d packets/%0d exact events/%0d protocol failures/%0d controls/%0d injected memory phases; automatic record load/save, interleaved connections, unaligned RAM, durable marker/state commits, update/close, poisoned-state admission block and fresh recovery",SEMANTIC,total,events_total,errors,controls,faults);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Connection timeout packet=%0d",total);end
endmodule
