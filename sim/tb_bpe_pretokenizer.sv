`timescale 1ns/1ps
module tb_bpe_pretokenizer;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic admit=1;logic [1:0] profile=0;
    logic [22:0] workspace_base=23'h484400,class_base=23'h440000;
    logic [23:0] workspace_bytes=24'h37bc00;wire [22:0] active_class_base;
    logic [127:0] source_data=0;logic [15:0] source_keep=0,source_user=0;
    logic source_valid=0,source_last=0;wire source_ready;
    wire [7:0] output_byte;wire output_keep,output_valid,output_piece_last,output_sequence_last;wire [15:0] output_user;
    logic output_ready=0,error_ready=0;wire error_valid,idle;wire [7:0] error_code,error_status;wire [15:0] error_user;
    wire class_req_valid,class_req_ready,class_rsp_valid,class_rsp_ready;wire [20:0] class_cp;wire [1:0] class_value;wire [7:0] class_status;
    wire [1:0] cmd_valid,cmd_ready,cmd_write,rsp_valid,rsp_ready;wire [45:0] cmd_addr;wire [7:0] cmd_bytes;
    wire [143:0] cmd_data,rsp_data;wire [15:0] rsp_status;
    logic inv=0;wire inv_ready,fabric_idle,class_idle;
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready;
    wire [63:0] rdata,wdata;wire [1:0] rresp,bresp;
    logic read_fault=0,write_fault=0;logic [22:0] fault_line=0;
    integer fault_mode=0,workspace_reads=0,workspace_writes=0;
    bit command_is_write=0;
    wire [7:0] injected_status=fault_mode==9&&workspace_reads==2&&!command_is_write?8'd2:rsp_status[15:8];
    wire [71:0] injected_data=fault_mode==10&&workspace_reads==2&&!command_is_write?(rsp_data[143:72]&~(72'd7<<55)):rsp_data[143:72];
    bpe_pretokenizer dut(
        .clk(clk),.rst(rst),.admit_sequences(admit),.cfg_profile(profile),.cfg_workspace_base(workspace_base),.cfg_workspace_bytes(workspace_bytes),.cfg_class_base(class_base),.active_class_base(active_class_base),
        .s_axis_text_tdata(source_data),.s_axis_text_tkeep(source_keep),.s_axis_text_tvalid(source_valid),.s_axis_text_tready(source_ready),.s_axis_text_tlast(source_last),.s_axis_text_tuser(source_user),
        .m_data(output_byte),.m_keep(output_keep),.m_valid(output_valid),.m_ready(output_ready),.m_piece_last(output_piece_last),.m_sequence_last(output_sequence_last),.m_user(output_user),
        .class_req_valid(class_req_valid),.class_req_ready(class_req_ready),.class_req_codepoint(class_cp),.class_rsp_valid(class_rsp_valid),.class_rsp_ready(class_rsp_ready),.class_rsp_class(class_value),.class_rsp_status(class_status),
        .mem_valid(cmd_valid[1]),.mem_ready(cmd_ready[1]),.mem_write(cmd_write[1]),.mem_addr(cmd_addr[45:23]),.mem_bytes(cmd_bytes[7:4]),.mem_data(cmd_data[143:72]),
        .mem_rsp_valid(rsp_valid[1]),.mem_rsp_ready(rsp_ready[1]),.mem_rsp_data(injected_data),.mem_rsp_status(injected_status),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_status(error_status),.error_user(error_user),.idle(idle));
    assign cmd_write[0]=0;assign cmd_data[71:0]=0;
    unicode_external_lookup classes(
        .clk(clk),.rst(rst),.cfg_unlock(1'b0),.class_base(active_class_base),.req_valid(class_req_valid),.req_ready(class_req_ready),.req_codepoint(class_cp),
        .rsp_valid(class_rsp_valid),.rsp_ready(class_rsp_ready),.rsp_class(class_value),.rsp_status(class_status),.idle(class_idle),
        .mem_rd_valid(cmd_valid[0]),.mem_rd_ready(cmd_ready[0]),.mem_rd_addr(cmd_addr[22:0]),.mem_rd_bytes(cmd_bytes[3:0]),
        .mem_rsp_valid(rsp_valid[0]),.mem_rsp_ready(rsp_ready[0]),.mem_rsp_data(rsp_data[71:0]),.mem_rsp_status(rsp_status[7:0]));
    external_memory_fabric #(.CLIENTS(2)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(inv),.invalidate_ready(inv_ready),
        .s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_data(rsp_data),.rsp_status(rsp_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
        .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),
        .rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),
        .wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),.bresp(bresp),.bvalid(bvalid),.bready(bready),
        .read_fault(read_fault),.fault_line(fault_line),.write_fault(write_fault));
    byte unsigned raw[0:131071],expected_byte[0:131071];
    bit expected_keep[0:131071],expected_piece_last[0:131071],expected_sequence_last[0:131071];
    integer expected_records=0,record_index=0,expected_context=0,expected_error=0,expected_status=0;
    integer sequences=0,completed=0,errors=0,pieces=0,bytes_out=0;
    bit stalled=0,error_stalled=0,mem_stalled=0,class_stalled=0;
    logic [26:0] held_output;logic [31:0] held_error;logic [99:0] held_mem;logic [20:0] held_cp;
    always @(negedge clk)output_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!output_valid||held_output!=={output_user,output_sequence_last,output_piece_last,output_keep,output_byte}))$fatal(1,"Pretokenizer output changed while stalled");
        stalled=output_valid&&!output_ready;held_output={output_user,output_sequence_last,output_piece_last,output_keep,output_byte};
        if(error_stalled&&(!error_valid||held_error!=={error_user,error_code,error_status}))$fatal(1,"Pretokenizer error changed while stalled");
        error_stalled=error_valid&&!error_ready;held_error={error_user,error_code,error_status};
        if(mem_stalled&&(!cmd_valid[1]||held_mem!=={cmd_write[1],cmd_addr[45:23],cmd_bytes[7:4],cmd_data[143:72]}))$fatal(1,"Workspace command changed while stalled");
        mem_stalled=cmd_valid[1]&&!cmd_ready[1];held_mem={cmd_write[1],cmd_addr[45:23],cmd_bytes[7:4],cmd_data[143:72]};
        if(class_stalled&&(!class_req_valid||held_cp!==class_cp))$fatal(1,"Class query changed while stalled");
        class_stalled=class_req_valid&&!class_req_ready;held_cp=class_cp;
        if(cmd_valid[1]&&cmd_ready[1])begin
            command_is_write=cmd_write[1];
            if(cmd_addr[45:23]<23'h484400||cmd_bytes[7:4]!=8)$fatal(1,"Workspace command escaped allocation");
            if(command_is_write)workspace_writes++;else workspace_reads++;
        end
        if(source_valid&&source_ready&&idle)$fatal(1,"Early idle at ingress admission");
        if(output_valid&&output_ready)begin
            if(record_index>=expected_records||output_user!=expected_context||output_byte!==expected_byte[record_index]||output_keep!=expected_keep[record_index]||output_piece_last!=expected_piece_last[record_index]||output_sequence_last!=expected_sequence_last[record_index])
                $fatal(1,"Pretokenizer mismatch sequence=%0d record=%0d data=%h piece_last=%0d EOS=%0d",sequences,record_index,output_byte,output_piece_last,output_sequence_last);
            record_index++;if(output_keep)bytes_out++;if(output_piece_last)pieces++;if(output_sequence_last)completed++;
        end
        if(error_valid&&error_ready)begin
            if(error_code!=expected_error||error_status!=expected_status||error_user!=expected_context)$fatal(1,"Unexpected pretokenizer error code=%0d/%0d status=%0d/%0d",error_code,expected_error,error_status,expected_status);
            errors++;
        end
    end
    task automatic invalidate;
        @(negedge clk);inv=1;
        do @(posedge clk);while(!inv_ready);
        @(negedge clk);inv=0;
    endtask
    task automatic send_packet(input integer n,input integer context_number);
        integer position,used;bit first;
        position=0;first=1;
        do begin
            repeat($urandom_range(0,2))@(negedge clk);
            @(negedge clk);source_keep=0;source_data='1;used=0;
            for(integer lane=0;lane<16;lane++)if(position+used<n&&($urandom_range(0,1)||lane==15)&&!(fault_mode==4&&used==1))begin
                source_keep[lane]=1;source_data[lane*8+:8]=raw[position+used];used++;
            end
            source_last=position+used==n;source_user=(fault_mode==4&&position>0)?context_number+1:context_number;
            source_valid=1;
            if(first)begin
                admit=0;
                repeat(3)begin @(posedge clk);if(source_ready||!idle)$fatal(1,"Unadmitted pending sequence blocked quiescence or was accepted");end
                @(negedge clk);admit=1;
            end
            do @(posedge clk);while(!source_ready);
            @(negedge clk);source_valid=0;position+=used;
            if(first)begin
                // These changes must not affect the admitted sequence, and
                // disabling admission must still let its remaining beats drain.
                profile=3;workspace_base=23'h7fffff;workspace_bytes='1;class_base=23'h7fffff;admit=0;first=0;
            end
        end while(position<n);
    endtask
    initial begin:driver
        integer fd,rc,n,p,context_number,capacity,mode,nrecords,v,k,l,e,target,before_writes;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing pretokenizer fixtures");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d %d %d %d",n,p,context_number,capacity,expected_error,expected_status,mode,nrecords);
            if(rc==8)begin
                if(n>131072||nrecords>131072)$fatal(1,"Frontend fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",v);if(rc!=1)$fatal(1,"Missing raw text");raw[i]=v;end
                for(integer i=0;i<nrecords;i++)begin rc=$fscanf(fd,"%d %d %d %d",v,k,l,e);if(rc!=4)$fatal(1,"Missing output byte");expected_byte[i]=v;expected_keep[i]=k;expected_piece_last[i]=l;expected_sequence_last[i]=e;end
                if(!idle||!fabric_idle||!class_idle)$fatal(1,"Prior sequence not drained");
                invalidate();workspace_reads=0;workspace_writes=0;command_is_write=0;
                profile=p;workspace_base=mode==1?23'h7fffff:23'h484400;workspace_bytes=mode==1?24'hffffff:capacity;
                class_base=mode==5?23'h7fffff:23'h440000;admit=1;fault_mode=mode;
                read_fault=mode==6||mode==8;fault_line=mode==6?23'h440000:23'h484400;write_fault=mode==7;
                expected_records=nrecords;record_index=0;expected_context=context_number;sequences++;target=completed+(expected_error==0);before_writes=memory_model.writes;
                send_packet(n,context_number);
                if(expected_error)begin
                    wait(error_valid);repeat(8)begin @(negedge clk);if(!error_valid||idle||source_ready)$fatal(1,"Error not retained through backpressure");end
                    error_ready=1;@(posedge clk);@(negedge clk);error_ready=0;
                end else wait(completed==target);
                wait(idle);@(negedge clk);
                if(record_index!=expected_records||!fabric_idle||!class_idle)$fatal(1,"Frontend did not retire all records/commands");
                if((expected_error==1||expected_error==2||expected_error==3)&&memory_model.writes!=before_writes)$fatal(1,"Invalid allocation/profile issued workspace writes");
                read_fault=0;write_fault=0;fault_mode=0;
            end else if(!$feof(fd))$fatal(1,"Invalid frontend fixture");
        end
        $fclose(fd);
        if(sequences<600||pieces<1000||errors!=12)$fatal(1,"Insufficient frontend coverage sequences=%0d pieces=%0d errors=%0d",sequences,pieces,errors);
        $display("PASS: integrated RTL pretokenizer: %0d sequences, %0d exact pieces/%0d bytes, %0d rejected; sparse 128-bit input, all profiles, external classes/workspace, snapshot/admission barriers, faults and stalls",sequences,pieces,bytes_out,errors);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"Integrated pretokenizer timeout");end
endmodule
