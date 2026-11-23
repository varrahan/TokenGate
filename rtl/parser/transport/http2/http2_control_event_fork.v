`timescale 1ns/1ps
`default_nettype none
// Preserve complete semantic events for a transport controller before dispatch.
// Control acknowledgement precedes forwarding of that event. The controller
// must retain any connection-scoped work across DMA fragments and retire it
// on packet/persistence errors; this buffer does not implement credit ledgers.
// Reset requires the same ownership fence as the attached transport controller.
module http2_control_event_fork #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire s_valid,output wire s_ready,input wire [3:0] s_kind,input wire [7:0] s_data,
    input wire [31:0] s_arg0,s_arg1,input wire [23:0] s_length,input wire [7:0] s_type,s_flags,
    input wire [30:0] s_stream,input wire [USER_WIDTH-1:0] s_user,
    output wire m_valid,input wire m_ready,output reg [3:0] m_kind,output reg [7:0] m_data,
    output reg [31:0] m_arg0,m_arg1,output reg [23:0] m_length,output reg [7:0] m_type,m_flags,
    output reg [30:0] m_stream,output reg [USER_WIDTH-1:0] m_user,
    output wire control_valid,input wire control_ready,output wire [3:0] control_kind,
    output wire [7:0] control_data,output wire [31:0] control_arg0,control_arg1,
    output wire [23:0] control_length,output wire [7:0] control_type,control_flags,
    output wire [30:0] control_stream,output wire [USER_WIDTH-1:0] control_user,output wire idle
);
    reg held,selected,control_done;
    assign control_valid=!rst&&held&&selected&&!control_done;
    assign m_valid=!rst&&held&&(!selected||control_done);
    assign s_ready=!rst&&(!held||(m_valid&&m_ready));
    assign idle=!held&&!s_valid;
    assign control_kind=m_kind;assign control_data=m_data;
    assign control_arg0=m_arg0;assign control_arg1=m_arg1;assign control_length=m_length;
    assign control_type=m_type;assign control_flags=m_flags;
    assign control_stream=m_stream;assign control_user=m_user;
    always @(posedge clk)begin
        if(rst)begin
            held<=0;selected<=0;control_done<=0;m_kind<=0;m_data<=0;m_arg0<=0;m_arg1<=0;
            m_length<=0;m_type<=0;m_flags<=0;m_stream<=0;m_user<=0;
        end else begin
            if(s_valid&&s_ready)begin
                held<=1;selected<=s_kind==0||s_kind==3||s_kind>=4;control_done<=0;
                m_kind<=s_kind;m_data<=s_data;m_arg0<=s_arg0;m_arg1<=s_arg1;m_length<=s_length;
                m_type<=s_type;m_flags<=s_flags;m_stream<=s_stream;m_user<=s_user;
            end else if(m_valid&&m_ready)held<=0;
            if(control_valid&&control_ready)control_done<=1;
        end
    end
endmodule
`default_nettype wire
