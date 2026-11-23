`timescale 1ns/1ps
`default_nettype none
// a_pause prevents new A/DATA selection. An A frame already offered
// on the wire drains unchanged, including first-beat stalls and gaps.
// a_paused permits private A-source abort; B/control ownership is untouched.
// The parent owns reservation accounting and complete RPC cancellation.
// Frame-level round robin. A presented first beat locks the source even before
// READY; gaps inside a frame never allow the other source to interleave.
// There is no output queue: input acceptance is the actual wire handshake,
// preserving ACK/return retirement. Both production sources register VALID/data.
module axis_cancellable_frame_arbiter #(
    parameter integer DATA_WIDTH=512,KEEP_WIDTH=DATA_WIDTH/8,USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [DATA_WIDTH-1:0] a_axis_tdata,input wire [KEEP_WIDTH-1:0] a_axis_tkeep,
    input wire a_axis_tvalid,output wire a_axis_tready,input wire a_axis_tlast,input wire [USER_WIDTH-1:0] a_axis_tuser,
    input wire [DATA_WIDTH-1:0] b_axis_tdata,input wire [KEEP_WIDTH-1:0] b_axis_tkeep,
    input wire b_axis_tvalid,output wire b_axis_tready,input wire b_axis_tlast,input wire [USER_WIDTH-1:0] b_axis_tuser,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,output wire [KEEP_WIDTH-1:0] m_axis_tkeep,
    output wire m_axis_tvalid,input wire m_axis_tready,output wire m_axis_tlast,output wire [USER_WIDTH-1:0] m_axis_tuser,
    output wire idle
,
    input wire  a_pause,
    output wire  a_paused
);
    reg locked,owner,prefer_b;
    wire a_allowed=!a_pause||locked&&!owner;
    wire selected=locked?owner:a_axis_tvalid&&a_allowed&&b_axis_tvalid?prefer_b:b_axis_tvalid;
    assign m_axis_tdata=selected?b_axis_tdata:a_axis_tdata;
    assign m_axis_tkeep=selected?b_axis_tkeep:a_axis_tkeep;
    assign m_axis_tlast=selected?b_axis_tlast:a_axis_tlast;
    assign m_axis_tuser=selected?b_axis_tuser:a_axis_tuser;
    assign m_axis_tvalid=!rst&&(selected?b_axis_tvalid:a_axis_tvalid&&a_allowed);
    assign a_axis_tready=!rst&&!selected&&a_allowed&&m_axis_tready;
    assign a_paused=!rst&&a_pause&&(!locked||owner);
    assign b_axis_tready=!rst&&selected&&m_axis_tready;
    assign idle=!locked&&!a_axis_tvalid&&!b_axis_tvalid;
    always @(posedge clk)begin
        if(rst)begin locked<=0;owner<=0;prefer_b<=0;end
        else if(m_axis_tvalid)begin
            if(m_axis_tready&&m_axis_tlast)begin locked<=0;prefer_b<=!selected;end
            else begin locked<=1;owner<=selected;end
        end
    end
endmodule
`default_nettype wire
