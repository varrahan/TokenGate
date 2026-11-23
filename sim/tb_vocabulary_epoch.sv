`timescale 1ns/1ps
module tb_vocabulary_epoch;
    logic clk=0,rst=1,update_req=0,commit=0,abort_update=0,tables_valid=0,datapath_idle=1;
    always #2 clk=~clk;
    wire admit,cfg_unlock,vocab_valid,protocol_error,draining;
    wire [31:0] epoch;
    logic cfg_valid=0,rd_valid=0;
    wire cfg_ready,rd_ready,rsp_valid;
    logic [7:0] cfg_addr=0,rd_addr=0;
    logic [31:0] cfg_data=0;
    wire [31:0] rsp_data;
    vocabulary_epoch_control controller (
        .clk(clk),.rst(rst),.update_req(update_req),.commit(commit),.abort_update(abort_update),
        .tables_valid(tables_valid),.datapath_idle(datapath_idle),.admit_sequences(admit),
        .cfg_unlock(cfg_unlock),.epoch(epoch),.vocabulary_valid(vocab_valid),
        .protocol_error(protocol_error),.draining(draining));
    programmable_small_table table_i (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(cfg_valid),.cfg_ready(cfg_ready),
        .cfg_addr(cfg_addr),.cfg_data(cfg_data),.rd_valid(rd_valid),.rd_ready(rd_ready),
        .rd_addr(rd_addr),.rsp_valid(rsp_valid),.rsp_data(rsp_data));
    task automatic tick;
        @(posedge clk); #0.1;
    endtask
    task automatic start_update;
        @(negedge clk);update_req=1;
        tick();
        @(negedge clk);update_req=0;
        while(!cfg_unlock) tick();
    endtask
    task automatic write_entry(input [31:0] value);
        @(negedge clk);cfg_addr=7;cfg_data=value;cfg_valid=1;
        do tick();while(!cfg_ready);
        @(negedge clk);cfg_valid=0;
    endtask
    task automatic valid_commit;
        @(negedge clk);tables_valid=1;commit=1;
        tick();
        @(negedge clk);commit=0;
    endtask
    task automatic read_entry(input [31:0] expected);
        @(negedge clk);rd_valid=1;rd_addr=7;
        tick();
        if(!rsp_valid || rsp_data!==expected) $fatal(1,"Distributed RAM read mismatch");
        @(negedge clk);rd_valid=0;
    endtask
    initial begin
        repeat(4) @(negedge clk);rst=0;
        tick();if(admit || cfg_unlock || vocab_valid) $fatal(1,"Traffic enabled before initial model load");
        @(negedge clk);commit=1;tick();
        if(!protocol_error || admit) $fatal(1,"Premature commit accepted");
        @(negedge clk);commit=0;
        start_update();
        if(rd_ready || !cfg_ready) $fatal(1,"Runtime read allowed while configuring");
        write_entry(32'h12345678);
        @(negedge clk);commit=1;tables_valid=0;tick();
        if(!protocol_error || admit || !cfg_unlock || epoch!=0) $fatal(1,"Invalid model commit accepted");
        @(negedge clk);commit=0;
        // A valid image must not become live while its final external write
        // or completion is still outstanding.
        @(negedge clk);datapath_idle=0;tables_valid=1;commit=1;tick();
        if(!protocol_error || admit || !cfg_unlock || epoch!=0)$fatal(1,"Commit accepted with pending external writes");
        @(negedge clk);commit=0;datapath_idle=1;
        valid_commit();
        if(!admit || !vocab_valid || epoch!=1 || cfg_ready) $fatal(1,"First epoch commit failed");
        read_entry(32'h12345678);
        @(negedge clk);datapath_idle=0;update_req=1;
        #0.1;if(admit) $fatal(1,"New work admitted during update request");
        tick();
        @(negedge clk);update_req=0;
        repeat(10) begin
            tick();if(!draining || cfg_unlock || admit || !vocab_valid || epoch!=1)
                $fatal(1,"Active model changed before drain");
        end
        @(negedge clk);datapath_idle=1;tick();
        if(!cfg_unlock || vocab_valid) $fatal(1,"No configuration grant after drain");
        write_entry(32'hdeadbeef);valid_commit();
        if(epoch!=2 || !admit) $fatal(1,"Reload epoch failed");
        read_entry(32'hdeadbeef);
        start_update();
        @(negedge clk);abort_update=1;tick();
        @(negedge clk);abort_update=0;tick();
        if(admit || vocab_valid || cfg_unlock || epoch!=2) $fatal(1,"Aborted partial image reenabled traffic");
        start_update();write_entry(32'hcafef00d);valid_commit();read_entry(32'hcafef00d);
        if(epoch!=3) $fatal(1,"Recovery epoch failed");
        $display("PASS: quiesce/drain, invalid commits, atomic model epochs, abort/recovery, native distributed RAM reload");
        $finish;
    end
    initial begin #100000;$fatal(1,"Timeout");end
endmodule
