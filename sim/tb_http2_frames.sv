`timescale 1ns/1ps
module tb_http2_frames;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic start_valid=0,start_fresh=0;wire start_ready;logic [15:0] start_user=0;logic [159:0] cfg_state=0;
    logic [23:0] cfg_max_frame_bytes=16384;logic cfg_server_role=1,cfg_allow_push=0;
    logic [511:0] s_axis_rx_tdata=0;logic [63:0] s_axis_rx_tkeep=0;logic s_axis_rx_tvalid=0,s_axis_rx_tlast=0;logic [15:0] s_axis_rx_tuser=0;wire s_axis_rx_tready;
    wire event_valid;logic event_ready=0;wire [1:0] event_kind;wire [7:0] event_data,event_type,event_flags;wire [23:0] event_length;
    wire [30:0] event_stream;wire event_payload_last;wire [31:0] event_error;wire [15:0] event_user;
    wire completion_valid,completion_failed,idle;logic completion_ready=0;wire [31:0] completion_error;wire [7:0] completion_detail;wire [159:0] completion_state;wire [15:0] completion_user;
    http2_axis_ingress dut(.*);
    integer fields[0:11],raw[0:65535],golden[0:65535][0:7];reg [159:0] saved[0:15];
    integer received=0,total=0,events_total=0,wire_bytes=0,errors=0,stream_errors=0,header_events=0,body_events=0,end_events=0;
    bit event_stalled=0,result_stalled=0;logic [129:0] held_event;logic [216:0] held_result;
    wire [129:0] event_bundle={event_kind,event_data,event_length,event_type,event_flags,event_stream,event_payload_last,event_error,event_user};
    wire [216:0] result_bundle={completion_failed,completion_error,completion_detail,completion_state,completion_user};
    always @(negedge clk)event_ready=$urandom_range(0,3)!=0;
    always @(posedge clk)if(!rst)begin
        if(event_stalled&&(!event_valid||held_event!==event_bundle))$fatal(1,"HTTP/2 event changed under stall");
        event_stalled=event_valid&&!event_ready;held_event=event_bundle;
        if(result_stalled&&(!completion_valid||held_result!==result_bundle))$fatal(1,"HTTP/2 result changed under stall");
        result_stalled=completion_valid&&!completion_ready;held_result=result_bundle;
        if((^{event_valid,completion_valid,start_ready,s_axis_rx_tready})===1'bx)$fatal(1,"Unknown framing handshake");
        if(event_valid&&((^event_bundle)===1'bx))$fatal(1,"Unknown frame event");
        if(completion_valid&&((^result_bundle)===1'bx))$fatal(1,"Unknown fragment state");
        if(completion_valid&&(start_ready||s_axis_rx_tready))$fatal(1,"Unacknowledged result admitted new packet");
        if(event_valid&&event_ready)begin
            if(received>=fields[7]||event_kind!=golden[received][0]||event_data!=golden[received][1]||event_length!=golden[received][2]||
               event_type!=golden[received][3]||event_flags!=golden[received][4]||event_stream!=golden[received][5]||
               event_payload_last!=golden[received][6]||event_error!=golden[received][7]||event_user!=16'(fields[0]+16'h1200))
                $fatal(1,"Frame event mismatch fragment=%0d event=%0d got kind=%0d type=%0d len=%0d data=%0d expected=%0d/%0d/%0d/%0d",total,received,event_kind,event_type,event_length,event_data,golden[received][0],golden[received][3],golden[received][2],golden[received][1]);
            case(event_kind)0:header_events++;1:body_events++;2:end_events++;3:stream_errors++;endcase
            received++;events_total++;
        end
    end
    task beat(input [511:0] data,input [63:0] keep,input last,input [15:0] context_value);
        begin
            repeat($urandom_range(0,3))@(negedge clk);s_axis_rx_tdata=data;s_axis_rx_tkeep=keep;s_axis_rx_tlast=last;s_axis_rx_tuser=context_value;s_axis_rx_tvalid=1;
            do @(posedge clk);while(!s_axis_rx_tready);@(negedge clk);s_axis_rx_tvalid=0;
        end
    endtask
    initial begin:driver
        integer fd,rc,position,context_number,scanned;reg [511:0] data;reg [63:0] keep;bit sent_last,separate_last;
        for(integer i=0;i<16;i++)saved[i]=0;
        repeat(5)@(negedge clk);rst=0;fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing HTTP/2 vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d",fields[0]);
            if(rc==1)begin
                for(integer i=1;i<12;i++)begin rc=$fscanf(fd,"%d",fields[i]);if(rc!=1)$fatal(1,"Bad fragment fixture");end
                if(fields[0]>15||fields[6]>65536||fields[7]>65536)$fatal(1,"Frame fixture capacity");
                for(integer i=0;i<fields[6];i++)begin rc=$fscanf(fd,"%h",raw[i]);if(rc!=1)$fatal(1,"Missing frame byte");end
                for(integer i=0;i<fields[7];i++)for(integer j=0;j<8;j++)begin rc=$fscanf(fd,"%d",scanned);if(rc!=1)$fatal(1,"Missing frame event");golden[i][j]=scanned;end
                context_number=fields[0]+16'h1200;received=0;
                @(negedge clk);start_fresh=fields[1]!=0;start_user=16'(context_number);cfg_state=fields[5]==3?'1:saved[fields[0]];
                cfg_server_role=fields[2]!=0;cfg_allow_push=fields[3]!=0;cfg_max_frame_bytes=24'(fields[4]);start_valid=1;
                do @(posedge clk);while(!start_ready);@(negedge clk);start_valid=0;cfg_state='1;cfg_max_frame_bytes=0;cfg_server_role=!cfg_server_role;cfg_allow_push=!cfg_allow_push;start_user=0;start_fresh=0;
                if(total%11==0)beat(0,0,0,16'(context_number));
                position=0;sent_last=0;separate_last=$urandom_range(0,1)!=0;
                while(position<fields[6])begin
                    data=0;keep=0;
                    for(integer lane=0;lane<64;lane++)if(position<fields[6]&&$urandom_range(0,3)!=0)begin
                        data[lane*8+:8]=8'(raw[position]);keep[lane]=1;position++;
                    end
                    sent_last=position==fields[6]&&!separate_last;
                    beat(data,keep,sent_last,16'(context_number^(fields[5]==2?1:0)));
                end
                if(!sent_last)beat(0,0,1,16'(context_number^(fields[5]==2?1:0)));
                wait(completion_valid);repeat($urandom_range(3,12))@(negedge clk);
                if(received!=fields[7]||completion_failed!=fields[8]||completion_error!=fields[9]||completion_detail!=fields[10]||completion_user!=16'(context_number))
                    $fatal(1,"Fragment result mismatch case=%0d events=%0d/%0d error=%0d/%0d detail=%0d/%0d",total,received,fields[7],completion_error,fields[9],completion_detail,fields[10]);
                if(completion_failed)begin errors++;if(completion_state!==160'd0)$fatal(1,"Failure exposed reusable connection state");end
                else if(fields[11]&&completion_state!==((160'd1<<135)|160'd24))$fatal(1,"Incorrect canonical frame boundary state");
                saved[fields[0]]=completion_state;wire_bytes+=fields[6];
                completion_ready=1;@(posedge clk);@(negedge clk);completion_ready=0;wait(idle);total++;
                if(total%50==0)$display("PROGRESS: %0d HTTP/2 DMA fragments",total);
            end else if(!$feof(fd))$fatal(1,"Bad fragment fixture header");
        end
        $fclose(fd);if(total<100||errors<19||stream_errors!=1||header_events<50||body_events<50000)$fatal(1,"Frame coverage failure %0d/%0d/%0d/%0d",total,errors,header_events,body_events);
        $display("PASS: HTTP/2 512-bit ingress: %0d fragments/%0d wire bytes/%0d exact events (%0d headers/%0d body/%0d ends/%0d stream errors), %0d failed fragments; native h2 client/server wire, cross-packet preface/header/payload, interleaved saved connections, CONTINUATION, reserved/unknown flags/types, sparse AXIS, stalls/snapshots, protocol failures and recovery",total,wire_bytes,events_total,header_events,body_events,end_events,stream_errors,errors);$finish;
    end
    initial begin #(64'd10000000000);$fatal(1,"Frame test timeout fragment=%0d state=%0d",total,dut.reader.state);end
endmodule
