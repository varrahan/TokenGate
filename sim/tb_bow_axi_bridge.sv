`timescale 1ns/1ps
module bridge_channel_checker #(parameter integer SEED=1)(
    input logic clk, input logic rst, input logic drive_enable,
    output logic [127:0] s_data, output logic [15:0] s_keep,
    output logic s_valid, input logic s_ready,
    output logic s_last, output logic [15:0] s_user,
    input logic [127:0] m_data, input logic [15:0] m_keep,
    input logic m_valid, output logic m_ready,
    input logic m_last, input logic [15:0] m_user,
    output integer accepted, output integer delivered,
    output integer occupancy, output integer stalled_cycles
);
    logic [160:0] expected[0:16383];
    logic [160:0] held;
    logic held_valid, source_accepted;
    integer write_idx, read_idx;
    logic [31:0] rng = SEED;
    function automatic [31:0] next_random(input [31:0] x);
        reg [31:0] t;
        begin t=x^(x<<13); t=t^(t>>17); next_random=t^(t<<5); end
    endfunction
    always @(negedge clk) begin
        rng = next_random(rng);
        if (rst) begin
            s_valid=0; s_data=0; s_keep=0; s_last=0; s_user=0; m_ready=0;
        end else begin
            m_ready = !drive_enable || rng[2:0] < 5;
            if (!s_valid || source_accepted) begin
                s_valid = drive_enable && rng[6:4] < 6;
                s_data = {rng,32'(write_idx),~rng,32'(SEED)};
                s_keep = rng[31:16];
                s_last = rng[10:8] == 0;
                s_user = rng[15:0];
            end
        end
    end
    always @(posedge clk) begin
        if (rst) begin
            accepted=0; delivered=0; occupancy=0; stalled_cycles=0;
            write_idx=0; read_idx=0; held_valid=0; source_accepted=0;
        end else begin
            if (held_valid) begin
                if (!m_valid || {m_user,m_last,m_keep,m_data} !== held)
                    $fatal(1,"AXI payload changed under backpressure, channel %0d",SEED);
            end
            held_valid = m_valid && !m_ready;
            held = {m_user,m_last,m_keep,m_data};
            if (held_valid) stalled_cycles++;
            if (m_valid && m_ready) begin
                if (occupancy == 0) $fatal(1,"Output without queued input");
                if ({m_user,m_last,m_keep,m_data} !== expected[read_idx])
                    $fatal(1,"Payload/order/context mismatch on channel %0d index %0d",SEED,read_idx);
                read_idx++; occupancy--; delivered++;
            end
            source_accepted = s_valid && s_ready;
            if (source_accepted) begin
                expected[write_idx] = {s_user,s_last,s_keep,s_data};
                write_idx++; occupancy++; accepted++;
            end
            if (occupancy > 2) $fatal(1,"Skid buffer overflow");
        end
    end
endmodule

module tb_bow_axi_bridge;
    logic clk=0, rst=1, drive_enable=1;
    always #2 clk=~clk;
    wire [127:0] sd[0:1],md[0:1];
    wire [15:0] sk[0:1],mk[0:1],su[0:1],mu[0:1];
    wire [1:0] sv,sr,sl,mv,mr,ml;
    integer accepted[0:1],delivered[0:1],occupancy[0:1],stalled[0:1];
    bow_axi_bridge dut (
        .clk(clk),.rst(rst),
        .s_ingress_tdata(sd[0]),.s_ingress_tkeep(sk[0]),.s_ingress_tvalid(sv[0]),
        .s_ingress_tready(sr[0]),.s_ingress_tlast(sl[0]),.s_ingress_tuser(su[0]),
        .m_ingress_tdata(md[0]),.m_ingress_tkeep(mk[0]),.m_ingress_tvalid(mv[0]),
        .m_ingress_tready(mr[0]),.m_ingress_tlast(ml[0]),.m_ingress_tuser(mu[0]),
        .s_egress_tdata(sd[1]),.s_egress_tkeep(sk[1]),.s_egress_tvalid(sv[1]),
        .s_egress_tready(sr[1]),.s_egress_tlast(sl[1]),.s_egress_tuser(su[1]),
        .m_egress_tdata(md[1]),.m_egress_tkeep(mk[1]),.m_egress_tvalid(mv[1]),
        .m_egress_tready(mr[1]),.m_egress_tlast(ml[1]),.m_egress_tuser(mu[1]));
    for(genvar g=0;g<2;g++) begin: checks
        bridge_channel_checker #(.SEED(32'h12345678+g)) checker_i (
            .clk(clk),.rst(rst),.drive_enable(drive_enable),
            .s_data(sd[g]),.s_keep(sk[g]),.s_valid(sv[g]),.s_ready(sr[g]),
            .s_last(sl[g]),.s_user(su[g]),.m_data(md[g]),.m_keep(mk[g]),
            .m_valid(mv[g]),.m_ready(mr[g]),.m_last(ml[g]),.m_user(mu[g]),
            .accepted(accepted[g]),.delivered(delivered[g]),
            .occupancy(occupancy[g]),.stalled_cycles(stalled[g]));
    end
    initial begin
        repeat(4) @(negedge clk); #0.1 rst=0;
        repeat(1000) @(negedge clk); #0.1 rst=1;
        repeat(4) @(negedge clk); #0.1 rst=0;
        repeat(6000) @(negedge clk); #0.1 drive_enable=0;
        repeat(20) @(negedge clk);
        for(integer c=0;c<2;c++) begin
            if (occupancy[c]!=0 || accepted[c]!=delivered[c] || delivered[c]<1000 || stalled[c]<100)
                $fatal(1,"Coverage/drain failure channel %0d: accepted %0d delivered %0d stalled %0d",c,accepted[c],delivered[c],stalled[c]);
            $display("CHANNEL %0d delivered=%0d stalled_cycles=%0d",c,delivered[c],stalled[c]);
        end
        $display("PASS: simultaneous independent AXI channels, sparse/empty keeps, stalls, reset, context and ordering");
        $finish;
    end
    initial begin #100000; $fatal(1,"Timeout"); end
endmodule
