`timescale 1ns/1ps
module tb_hpack_headers;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0;wire start_ready;logic [31:0] start_bytes=0;logic [15:0] start_user=0;
    logic [22:0] cfg_table_base=0,cfg_scratch_base=0;logic [23:0] cfg_table_bytes=0,cfg_scratch_bytes=0;
    logic [31:0] cfg_maximum=0,cfg_allowed_maximum=0,cfg_used=0,cfg_entries=0,cfg_header_list_limit=0,cfg_required_maximum=0;
    logic cfg_required_update=0;logic [7:0] s_data=0;logic s_valid=0;wire s_ready;logic [15:0] s_user=0;
    wire header_valid;logic header_ready=0;wire [22:0] header_name_base,header_value_base;wire [31:0] header_name_bytes,header_value_bytes;
    wire [1:0] header_representation;wire [15:0] header_user;
    wire completion_valid;logic completion_ready=0;wire [7:0] completion_status,completion_detail,completion_aux;
    wire [31:0] completion_maximum,completion_used,completion_entries,completion_headers,completion_list_bytes;wire [15:0] completion_user;wire idle;
    wire [1:0] mem_valid,mem_ready,mem_write,mem_rsp_valid,mem_rsp_ready;wire [45:0] mem_addr;wire [7:0] mem_bytes;wire [143:0] mem_data,mem_rsp_data;wire [15:0] mem_rsp_status;
    wire [2:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [68:0] cmd_addr;wire [11:0] cmd_bytes;wire [215:0] cmd_data,response_data;wire [23:0] response_status;
    logic helper_valid=0,helper_write=0,helper_rsp_ready=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;logic [71:0] helper_data=0;
    integer mode=0;bit injected=0;bit [1:0] last_write=0;
    wire header_fault=!injected&&((mode==2&&!last_write[0])||(mode==3&&last_write[0]));
    wire table_fault=!injected&&((mode==4&&last_write[1])||(mode==5&&!last_write[1]));
    assign mem_ready=cmd_ready[1:0];assign mem_rsp_valid=response_valid[1:0];assign mem_rsp_data=response_data[0+:144];
    assign mem_rsp_status={table_fault?(mode==4?8'h64:8'h63):response_status[8+:8],header_fault?(mode==2?8'h31:8'h52):response_status[0+:8]};
    assign cmd_valid={helper_valid,mem_valid};assign cmd_write={helper_write,mem_write};assign cmd_addr={helper_addr,mem_addr};
    assign cmd_bytes={helper_bytes,mem_bytes};assign cmd_data={helper_data,mem_data};assign response_ready={helper_rsp_ready,mem_rsp_ready};
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    hpack_header_decoder dut(.*);
    external_memory_fabric #(.CLIENTS(3)) fabric(
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
    bit [1:0] mem_stalled=0;logic [99:0] held_mem[0:1];bit header_stalled=0,completion_stalled=0;
    logic [127:0] held_header;logic [199:0] held_completion;
    wire [127:0] header_bundle={header_user,header_representation,header_name_base,header_value_base,header_name_bytes,header_value_bytes};
    wire [199:0] completion_bundle={completion_user,completion_status,completion_detail,completion_aux,completion_maximum,completion_used,completion_entries,completion_headers,completion_list_bytes};
    always @(posedge clk)if(!rst)begin
        if((^mem_valid)===1'bx||header_valid===1'bx||completion_valid===1'bx||s_ready===1'bx||start_ready===1'bx)$fatal(1,"Unknown HPACK handshake");
        if(header_valid&&((^header_bundle)===1'bx))$fatal(1,"Unknown leased header metadata");
        if(completion_valid&&((^completion_bundle)===1'bx))$fatal(1,"Unknown HPACK completion");
        for(integer c=0;c<2;c++)begin
            if(mem_valid[c]&&((^{mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]})===1'bx))$fatal(1,"Unknown header memory command");
            if(mem_stalled[c]&&(!mem_valid[c]||held_mem[c]!=={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]}))$fatal(1,"Header memory request changed");
            mem_stalled[c]=mem_valid[c]&&!mem_ready[c];held_mem[c]={mem_write[c],mem_addr[c*23+:23],mem_bytes[c*4+:4],mem_data[c*72+:72]};
            if(mem_valid[c]&&mem_ready[c])last_write[c]=mem_write[c];
        end
        if(header_fault&&mem_rsp_valid[0]&&mem_rsp_ready[0])injected<=1;
        if(table_fault&&mem_rsp_valid[1]&&mem_rsp_ready[1])injected<=1;
        if(header_stalled&&(!header_valid||held_header!==header_bundle))$fatal(1,"Header metadata changed under lease");
        header_stalled=header_valid&&!header_ready;held_header=header_bundle;
        if(completion_stalled&&(!completion_valid||held_completion!==completion_bundle))$fatal(1,"Block result changed under stall");
        completion_stalled=completion_valid&&!completion_ready;held_completion=completion_bundle;
        if(header_valid&&(mem_valid!=0||start_ready||s_ready))$fatal(1,"Header lease admitted new work");
    end
    task helper(input bit wr,input integer address,input integer size,input [71:0] data,output reg [71:0] result);
        begin
            @(negedge clk);helper_valid=1;helper_write=wr;helper_addr=23'(address);helper_bytes=4'(size);helper_data=data;
            do @(posedge clk);while(!cmd_ready[2]);@(negedge clk);helper_valid=0;
            repeat($urandom_range(0,4))@(negedge clk);helper_rsp_ready=1;
            do @(posedge clk);while(!response_valid[2]);if(response_status[16+:8]!=0)$fatal(1,"Header helper failed");result=response_data[144+:72];
            @(negedge clk);helper_rsp_ready=0;
        end
    endtask
    integer fields[0:23],encoded[0:65535],expected[0:262143],image[0:8191];
    integer names[0:1023],values[0:1023],kinds[0:1023],offsets[0:1023];
    integer total=0,successful=0,errors=0,exact_headers=0,exact_bytes=0,received_headers=0;
    task receive_headers;
        integer n,source,chunk,expected_offset;reg [71:0] result;
        begin
            received_headers=0;
            while(!completion_valid)begin
                @(negedge clk);
                if(header_valid)begin
                    if(header_user!=fields[12])$fatal(1,"Header context mismatch");
                    if(fields[13]==0&&(received_headers>=fields[23]||header_name_bytes!=names[received_headers]||header_value_bytes!=values[received_headers]||header_representation!=kinds[received_headers]))
                        $fatal(1,"Header descriptor mismatch block=%0d field=%0d kind=%0d/%0d",total,received_headers,header_representation,kinds[received_headers]);
                    for(integer part=0;part<2;part++)begin
                        n=part==0?header_name_bytes:header_value_bytes;source=part==0?header_name_base:header_value_base;
                        if(n>32768||n!=0&&(source<fields[9]||source+n>fields[9]+fields[10]))$fatal(1,"Header pointer escaped scratch");
                        if(n==0&&source!=0)$fatal(1,"Empty header field returned pointer");
                        expected_offset=offsets[received_headers]+(part==0?0:names[received_headers]);
                        for(integer i=0;i<n;i+=8)begin
                            chunk=n-i;if(chunk>8)chunk=8;helper(0,source+i,chunk,0,result);
                            if(fields[13]==0)for(integer lane=0;lane<chunk;lane++)begin
                                if(result[lane*8+:8]!==8'(expected[expected_offset+i+lane]))$fatal(1,"Header bytes mismatch block=%0d field=%0d part=%0d byte=%0d",total,received_headers,part,i+lane);
                                exact_bytes++;
                            end
                        end
                    end
                    repeat($urandom_range(1,10))@(negedge clk);header_ready=1;@(posedge clk);@(negedge clk);header_ready=0;received_headers++;
                end
            end
        end
    endtask
    initial begin:driver
        integer fd,rc,b,offset,base;reg [71:0] ignored;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing HPACK block vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<24;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad HPACK block fixture header");end
                if(fields[0]>65536||fields[23]>1024||fields[22]>8192)$fatal(1,"Header fixture overflow");
                for(integer i=0;i<fields[0];i++)begin rc=$fscanf(fd,"%h",encoded[i]);if(rc!=1)$fatal(1,"Missing encoded header byte");end
                offset=0;
                for(integer h=0;h<fields[23];h++)begin
                    rc=$fscanf(fd,"%d %d %d",names[h],values[h],kinds[h]);if(rc!=3)$fatal(1,"Bad header metadata fixture");offsets[h]=offset;
                    for(integer i=0;i<names[h]+values[h];i++)begin rc=$fscanf(fd,"%h",b);if(rc!=1)$fatal(1,"Missing header golden");expected[offset]=b;offset++;end
                end
                for(integer i=0;i<fields[22];i++)begin rc=$fscanf(fd,"%h",image[i]);if(rc!=1)$fatal(1,"Missing table image golden");end
                mode=fields[21];injected=0;base=fields[1];
                if(mode==6)helper(1,base,8,72'h00ffffffffffffffff,ignored);
                @(negedge clk);start_bytes=32'(fields[0]);cfg_table_base=23'(base);cfg_table_bytes=24'(fields[2]);cfg_maximum=32'(fields[3]);cfg_allowed_maximum=32'(fields[4]);
                cfg_used=32'(fields[5]);cfg_entries=32'(fields[6]);cfg_required_update=fields[7]!=0;cfg_required_maximum=32'(fields[8]);
                cfg_scratch_base=23'(fields[9]);cfg_scratch_bytes=24'(fields[10]);cfg_header_list_limit=32'(fields[11]);start_user=16'(fields[12]);start_valid=1;
                do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;cfg_table_base='1;cfg_scratch_base='1;cfg_table_bytes=0;cfg_scratch_bytes=0;
                cfg_maximum=0;cfg_allowed_maximum=0;cfg_used=0;cfg_entries=0;cfg_header_list_limit=0;cfg_required_update=1;cfg_required_maximum=0;start_user=0;start_bytes=0;
                fork
                    begin
                        for(integer i=0;i<fields[0];i++)begin
                            repeat($urandom_range(0,3))@(negedge clk);s_data=8'(encoded[i]);s_user=16'(fields[12]^((mode==1&&i==1)?1:0));s_valid=1;
                            do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
                        end
                    end
                    receive_headers();
                join
                wait(completion_valid);repeat($urandom_range(3,15))@(negedge clk);
                if(completion_status!=fields[13]||completion_detail!=fields[14]||completion_aux!=fields[15]||completion_maximum!=fields[16]||completion_used!=fields[17]||
                   completion_entries!=fields[18]||completion_headers!=fields[19]||completion_list_bytes!=fields[20]||completion_user!=fields[12])
                    $fatal(1,"HPACK block mismatch case=%0d got=%0d/%0d/%0d expected=%0d/%0d/%0d state=%0d/%0d used=%0d/%0d headers=%0d/%0d",total,completion_status,completion_detail,completion_aux,fields[13],fields[14],fields[15],completion_maximum,fields[16],completion_used,fields[17],completion_headers,fields[19]);
                if(fields[13]==0)begin
                    successful++;if(received_headers!=fields[23])$fatal(1,"Header count mismatch");exact_headers+=received_headers;
                    for(integer i=0;i<fields[22];i++)if(memory_model.memory[(base+i)>>3][((base+i)&7)*8+:8]!==8'(image[i]))$fatal(1,"Connection dictionary mismatch block=%0d byte=%0d",total,i);
                end else begin errors++;if(mode>=2&&mode<=5&&!injected)$fatal(1,"Header fault was not exercised");end
                completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;wait(idle&&fabric_idle);total++;
                if(total%50==0)$display("PROGRESS: %0d stateful complete HPACK header blocks",total);
            end else if(!$feof(fd))$fatal(1,"Bad block fixture");
        end
        $fclose(fd);if(total<400||errors<19)$fatal(1,"Insufficient header block coverage %0d/%0d",total,errors);
        $display("PASS: complete HPACK header decoder: %0d valid blocks/%0d failures/%0d exact headers/%0d bytes; all representations/static entries, three persistent external dictionaries, Huffman/raw, eviction/indexed-name leases, settings shrink, block commit, resource/context/memory faults and recovery",successful,errors,exact_headers,exact_bytes);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Header decoder timeout block=%0d state=%0d remaining=%0d",total,dut.state,dut.block_remaining);end
endmodule
