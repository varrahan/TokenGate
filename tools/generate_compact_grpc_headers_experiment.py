"""Build an isolated constant-packet formatter without changing production RTL."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1];original=root/'rtl/grpc_response_headers.v';text=original.read_text()
    start=text.index('    always @*begin');end=text.index('    always @(posedge clk)begin',start)
    constants=[]
    for name,suffix in(('GRPC',b''),('PROTO',b'+proto'),('JSON',b'+json')):
        value=b'application/grpc'+suffix;block=bytes((0x88,0x1f,0x10,len(value)))+value
        constants.append(f"    localparam [207:0] INITIAL_{name}=208'h{int.from_bytes(block,'little'):052x};")
    block='\n'.join(constants)+'''
    wire two_digits=status_code>=10;
    wire [7:0] status_digit=8'h30+(two_digits?status_code[4:0]-5'd10:status_code[4:0]);
    // The literal is byte packed in wire order at fixed offsets. CHECK rejects
    // status values above 16 before BUILD can expose this block.
    wire [127:0] trailer_literal={two_digits?status_digit:8'd0,
        two_digits?8'h31:status_digit,two_digits?8'd2:8'd1,
        88'h7375746174732d63707267,8'd11,8'h10};
    always @*begin
        next_packet=0;payload_bytes=0;
        if(kind==1)begin
            next_packet[72+:128]=trailer_literal;payload_bytes=two_digits?16:15;
        end else case(encoding)
            1:begin
                next_packet[72+:208]=INITIAL_PROTO;payload_bytes=26;
                if(kind==2)begin next_packet[280+:128]=trailer_literal;payload_bytes=26+(two_digits?16:15);end
            end
            2:begin
                next_packet[72+:208]=INITIAL_JSON;payload_bytes=25;
                if(kind==2)begin next_packet[272+:128]=trailer_literal;payload_bytes=25+(two_digits?16:15);end
            end
            default:begin
                next_packet[72+:208]=INITIAL_GRPC;payload_bytes=20;
                if(kind==2)begin next_packet[232+:128]=trailer_literal;payload_bytes=20+(two_digits?16:15);end
            end
        endcase
        cursor=9+payload_bytes;
        next_packet[7:0]=0;next_packet[15:8]=0;next_packet[23:16]=payload_bytes;
        next_packet[31:24]=8'd1;next_packet[39:32]=kind==0?8'h04:8'h05;
        next_packet[47:40]={1'b0,stream_id[30:24]};next_packet[55:48]=stream_id[23:16];
        next_packet[63:56]=stream_id[15:8];next_packet[71:64]=stream_id[7:0];
    end
'''
    text=text[:start]+block+text[end:]
    text=text.replace('integer cursor,content_bytes,index,payload_bytes;','integer cursor,payload_bytes;')
    target=root/'build/experiments/compact-grpc-headers/rtl/grpc_response_headers.v';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (target.parents[1]/'generation.json').write_text(json.dumps(dict(phase='isolated_constant_packet_formatter_generated',
        production_source_sha256=sha(original),generator_sha256=sha(Path(__file__)),output_sha256=sha(target),
        production_rtl_changed=False),indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
