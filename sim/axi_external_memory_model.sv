`timescale 1ns/1ps
// Verification-only AXI slave: independent AW/W, random latency, response
// faults and exact burst checking. The model's array represents external RAM.
module axi_external_memory_model #(
    parameter integer ADDR_WIDTH=23,parameter integer MEMORY_BYTES=8388608,
    parameter INIT_FILE="memory.mem"
)(
    input wire clk,input wire rst,
    input wire [ADDR_WIDTH-1:0] araddr,input wire [7:0] arlen,input wire [2:0] arsize,input wire [1:0] arburst,
    input wire arvalid,output logic arready=0,
    output logic [63:0] rdata=0,output logic [1:0] rresp=0,output logic rlast=0,output logic rvalid=0,input wire rready,
    input wire [ADDR_WIDTH-1:0] awaddr,input wire [7:0] awlen,input wire [2:0] awsize,input wire [1:0] awburst,
    input wire awvalid,output logic awready=0,
    input wire [63:0] wdata,input wire [7:0] wstrb,input wire wlast,input wire wvalid,output logic wready=0,
    output logic [1:0] bresp=0,output logic bvalid=0,input wire bready,
    input wire read_fault,input wire [ADDR_WIDTH-1:0] fault_line,input wire write_fault
);
    logic [63:0] memory[0:MEMORY_BYTES/8-1];
    integer reads=0,writes=0,w_before_aw=0;
    bit read_active=0,read_accepted=0,b_accepted=0,aw_have=0,w_have=0,b_pending=0;
    bit read_fault_latched=0,write_fault_latched=0;
    integer read_word=0,read_beat=0,write_word=0,write_count=0,write_length=0;
    logic [63:0] write_data[0:1];logic [7:0] write_strobes[0:1];bit write_last[0:1];
    bit ar_stalled=0,aw_stalled=0,w_stalled=0;
    logic [ADDR_WIDTH+12:0] ar_held,aw_held;
    logic [72:0] w_held;
    initial begin
        if(INIT_FILE!="")$readmemh(INIT_FILE,memory);
        else for(integer i=0;i<MEMORY_BYTES/8;i++)for(integer lane=0;lane<8;lane++)
            memory[i][lane*8+:8]=8'((i*8+lane)*37+((i*8+lane)>>5)*19+7);
    end
    always @(negedge clk)begin
        arready=!rst&&!read_active&&!rvalid&&$urandom_range(0,3)!=0;
        if(!rvalid||read_accepted)begin
            rvalid=!rst&&read_active&&$urandom_range(0,3)!=0;
            if(rvalid)begin rdata=memory[read_word+read_beat];rlast=read_beat==7;rresp=read_fault_latched&&read_beat==3?2:0;end
        end
        // W may arrive before AW; either channel may wait for the other VALID.
        awready=!rst&&!aw_have&&!b_pending&&!bvalid&&(wvalid||write_count>0)&&$urandom_range(0,2)!=0;
        wready=!rst&&!w_have&&!b_pending&&!bvalid&&(awvalid||aw_have)&&$urandom_range(0,2)!=0;
        if(b_accepted)bvalid=0;
        else if(!bvalid&&b_pending&&$urandom_range(0,2)!=0)begin bvalid=1;bresp=write_fault_latched?2:0;end
    end
    always @(posedge clk)begin
        read_accepted=rvalid&&rready;b_accepted=bvalid&&bready;
        if(rst)begin read_active=0;aw_have=0;w_have=0;b_pending=0;write_count=0;ar_stalled=0;aw_stalled=0;w_stalled=0;end
        else begin
            if(ar_stalled&&(!arvalid||ar_held!=={araddr,arlen,arsize,arburst}))$fatal(1,"AR changed under backpressure");
            if(aw_stalled&&(!awvalid||aw_held!=={awaddr,awlen,awsize,awburst}))$fatal(1,"AW changed under backpressure");
            if(w_stalled&&(!wvalid||w_held!=={wdata,wstrb,wlast}))$fatal(1,"W changed under backpressure");
            ar_stalled=arvalid&&!arready;ar_held={araddr,arlen,arsize,arburst};
            aw_stalled=awvalid&&!awready;aw_held={awaddr,awlen,awsize,awburst};
            w_stalled=wvalid&&!wready;w_held={wdata,wstrb,wlast};
            if(arvalid&&arready)begin
                if(araddr+64>MEMORY_BYTES||araddr[5:0]!=0||arlen!=7||arsize!=3||arburst!=1)$fatal(1,"Bad refill burst");
                read_word=araddr>>3;read_beat=0;read_active=1;reads++;read_fault_latched=read_fault&&araddr==fault_line;
            end
            if(read_accepted)begin if(rlast)read_active=0;else read_beat++;end
            if(b_accepted)begin aw_have=0;w_have=0;b_pending=0;write_count=0;end
            if(awvalid&&awready)begin
                if(awaddr+(awlen+1)*8>MEMORY_BYTES||awaddr[2:0]!=0||awlen>1||awsize!=3||awburst!=1)$fatal(1,"Bad write burst");
                if(write_count>0)w_before_aw++;
                aw_have=1;write_word=awaddr>>3;write_length=awlen+1;write_fault_latched=write_fault;
            end
            if(wvalid&&wready)begin
                if(write_count>=2)$fatal(1,"Too many write beats");
                write_data[write_count]=wdata;write_strobes[write_count]=wstrb;write_last[write_count]=wlast;
                write_count++;if(wlast)w_have=1;
            end
            if(aw_have&&w_have&&!b_pending)begin
                if(write_count!=write_length)$fatal(1,"AW/W length mismatch");
                for(integer beat=0;beat<write_count;beat++)begin
                    if(write_last[beat]!=(beat+1==write_count))$fatal(1,"Incorrect WLAST");
                    if(!write_fault_latched)for(integer lane=0;lane<8;lane++)if(write_strobes[beat][lane])
                        memory[write_word+beat][lane*8+:8]=write_data[beat][lane*8+:8];
                end
                b_pending=1;writes++;
            end
        end
    end
endmodule
