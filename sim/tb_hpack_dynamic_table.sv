`timescale 1ns/1ps
module tb_hpack_dynamic_table;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic req_valid=0,rsp_ready=0;wire req_ready,rsp_valid,idle;
    logic [1:0] req_op=0;logic [31:0] req_argument=0,req_name_bytes=0,req_value_bytes=0;
    logic [22:0] req_source_base=0,req_table_base=0;logic [23:0] req_table_bytes=0;
    logic [31:0] req_maximum=0,req_allowed_maximum=0,req_used=0,req_entries=0;logic [15:0] req_user=0;
    wire [7:0] rsp_status,rsp_memory_status;wire [31:0] rsp_maximum,rsp_used,rsp_entries,rsp_name_bytes,rsp_value_bytes;
    wire rsp_lookup_valid,rsp_inserted;wire [22:0] rsp_name_base,rsp_value_base;wire [15:0] rsp_user;
    wire mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data,mem_rsp_data;
    wire [7:0] mem_rsp_status;wire [1:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;
    wire [45:0] cmd_addr;wire [7:0] cmd_bytes;wire [143:0] cmd_data,response_data;wire [15:0] response_status;
    logic helper_valid=0,helper_write=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;logic [71:0] helper_data=0;
    integer mode=0;bit fault_injected=0,last_write=0;
    assign mem_ready=cmd_ready[0];assign mem_rsp_valid=response_valid[0];assign mem_rsp_data=response_data[0+:72];
    wire fault_phase=(mode==2&&!last_write)||(mode==3&&last_write)||
        (mode==6&&dut.state==dut.COPY_WAIT)||(mode==7&&dut.state==dut.COPY_WWAIT)||
        (mode==8&&dut.state==dut.NEW_HEADER_WAIT)||(mode==9&&dut.state==dut.SOURCE_WAIT)||
        (mode==10&&dut.state==dut.PAYLOAD_WAIT)||(mode==11&&dut.state==dut.HEADER_WAIT);
    assign mem_rsp_status=!fault_injected&&fault_phase?(mode==2?8'h31:mode==3?8'h52:(mode==6||mode==9||mode==11)?8'h63:8'h64):response_status[0+:8];
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={helper_write,mem_write};assign cmd_addr={helper_addr,mem_addr};
    assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={helper_data,mem_data};assign response_ready={helper_rsp_ready,mem_rsp_ready};
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    hpack_dynamic_table dut(.*);
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
    bit mem_stalled=0,response_stalled=0;logic [99:0] held_mem;logic [239:0] held_response;
    wire [239:0] response_bundle={rsp_status,rsp_memory_status,rsp_maximum,rsp_used,rsp_entries,rsp_lookup_valid,rsp_inserted,rsp_name_base,rsp_value_base,rsp_name_bytes,rsp_value_bytes,rsp_user};
    always @(posedge clk)if(!rst)begin
        if(mem_stalled&&(!mem_valid||held_mem!=={mem_write,mem_addr,mem_bytes,mem_data}))$fatal(1,"Table command changed under stall");
        mem_stalled=mem_valid&&!mem_ready;held_mem={mem_write,mem_addr,mem_bytes,mem_data};
        if(response_stalled&&(!rsp_valid||held_response!==response_bundle))$fatal(1,"Table response changed under stall");
        response_stalled=rsp_valid&&!rsp_ready;held_response=response_bundle;
        if(mem_valid&&mem_ready)last_write=mem_write;
        if(mem_rsp_valid&&mem_rsp_ready&&fault_phase)fault_injected<=1;
        if(rsp_valid&&(req_ready||mem_valid))$fatal(1,"Table pointer lease allowed new operation/write");
    end
    task helper(input bit wr,input integer address,input integer size,input [71:0] data,output reg [71:0] result);
        begin
            @(negedge clk);helper_valid=1;helper_write=wr;helper_addr=23'(address);helper_bytes=4'(size);helper_data=data;
            do @(posedge clk);while(!cmd_ready[1]);@(negedge clk);helper_valid=0;
            repeat($urandom_range(0,5))@(negedge clk);helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[1]);
            if(response_status[8+:8]!=0)$fatal(1,"Helper memory failed");result=response_data[72+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    integer payload[0:8191],expected_image[0:8191],lookup[0:8191];integer total=0,successes=0,errors=0,lookups=0,checked_bytes=0;
    initial begin:driver
        integer fd,rc,fields[0:23],n,b,chunk,base,source,op;reg [71:0] data,result;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing dynamic table vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<24;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad table fixture header");end
                mode=fields[20];fault_injected=0;
                for(integer k=0;k<3;k++)begin
                    n=fields[21+k];if(n>8192)$fatal(1,"Table fixture overflow");
                    for(integer i=0;i<n;i++)begin
                        rc=$fscanf(fd,"%h",b);if(rc!=1)$fatal(1,"Missing table byte");
                        if(k==0)payload[i]=b;else if(k==1)expected_image[i]=b;else lookup[i]=b;
                    end
                end
                base=fields[5];source=fields[4];op=fields[0];
                for(integer i=0;i<fields[21];i+=8)begin
                    chunk=fields[21]-i;if(chunk>8)chunk=8;data=0;
                    for(integer lane=0;lane<chunk;lane++)data[lane*8+:8]=8'(payload[i+lane]);
                    helper(1,source+i,chunk,data,result);
                end
                if(mode==4)helper(1,base,8,72'h00ffffffffffffffff,result);
                @(negedge clk);
                req_op=2'(fields[0]);req_argument=32'(fields[1]);req_name_bytes=32'(fields[2]);req_value_bytes=32'(fields[3]);
                req_source_base=23'(source);req_table_base=23'(base);req_table_bytes=24'(fields[6]);req_maximum=32'(fields[7]);
                req_allowed_maximum=32'(fields[8]);req_used=32'(fields[9]);req_entries=32'(fields[10]);req_user=16'(fields[11]);req_valid=1;
                do @(posedge clk);while(!req_ready);
                @(negedge clk);req_valid=0;req_op=3;req_argument='1;req_name_bytes='1;req_value_bytes='1;req_table_base='1;req_source_base='1;
                req_table_bytes=0;req_maximum=0;req_allowed_maximum=0;req_used=0;req_entries=0;req_user=0;
                wait(rsp_valid);@(negedge clk);
                if(rsp_status!=fields[12]||rsp_memory_status!=fields[13]||rsp_maximum!=fields[14]||rsp_used!=fields[15]||rsp_entries!=fields[16]||
                   rsp_inserted!=fields[17]||rsp_name_bytes!=fields[18]||rsp_value_bytes!=fields[19]||rsp_user!=fields[11]||rsp_lookup_valid!=(op==0&&fields[12]==0))
                    $fatal(1,"Table response mismatch case=%0d op=%0d status=%0d/%0d used=%0d/%0d count=%0d/%0d",total,op,rsp_status,fields[12],rsp_used,fields[15],rsp_entries,fields[16]);
                if(fields[12]==0)begin
                    successes++;
                    for(integer i=0;i<fields[22];i++)begin
                        b=memory_model.memory[(base+i)>>3][((base+i)&7)*8+:8];
                        if(b!=expected_image[i])$fatal(1,"Physical table mismatch case=%0d offset=%0d got=%02x expected=%02x",total,i,b,expected_image[i]);checked_bytes++;
                    end
                    if(op==0)begin
                        lookups++;
                        if((rsp_name_bytes==0&&rsp_name_base!=0)||(rsp_value_bytes==0&&rsp_value_base!=0))$fatal(1,"Empty field returned live pointer");
                        for(integer field_number=0;field_number<2;field_number++)begin
                            n=field_number==0?rsp_name_bytes:rsp_value_bytes;source=field_number==0?rsp_name_base:rsp_value_base;
                            for(integer i=0;i<n;i+=8)begin
                                chunk=n-i;if(chunk>8)chunk=8;helper(0,source+i,chunk,0,result);
                                for(integer lane=0;lane<chunk;lane++)if(result[lane*8+:8]!=lookup[(field_number==0?0:rsp_name_bytes)+i+lane])$fatal(1,"Leased lookup data mismatch");
                            end
                        end
                    end
                end else begin
                    errors++;if(rsp_name_base!=0||rsp_value_base!=0)$fatal(1,"Failure exposed stale pointers");
                    if((mode==2||mode==3||mode>=6)&&!fault_injected)$fatal(1,"Fault was not exercised");
                end
                repeat($urandom_range(1,12))@(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
                wait(idle&&fabric_idle);total++;if(total%100==0)$display("PROGRESS: %0d external HPACK table operations",total);
            end else if(!$feof(fd))$fatal(1,"Bad table fixture");
        end
        $fclose(fd);if(total<800||errors<10||lookups<80)$fatal(1,"Insufficient dynamic table coverage %0d/%0d/%0d",total,errors,lookups);
        $display("PASS: external HPACK dynamic table: %0d operations/%0d successful/%0d errors; %0d leased lookups/%0d physical bytes checked, interleaved contexts, eviction/resize/oversize, acknowledged unaligned moves, request snapshots, backpressure, memory faults/corruption and recovery",total,successes,errors,lookups,checked_bytes);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Dynamic table timeout");end
endmodule
