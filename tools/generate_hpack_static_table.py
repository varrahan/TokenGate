"""Generate the fixed RFC7541 Appendix A table, byte ROM and reference vectors."""
import argparse
import hashlib
from pathlib import Path
from hpack.table import HeaderTable


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rtl',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    pool=bytearray();locations={};descriptors=[]
    for name,value in HeaderTable.STATIC_TABLE:
        offsets=[]
        for text in(name,value):
            if not text:offsets.append(0);continue
            if text not in locations:locations[text]=len(pool);pool.extend(text)
            offsets.append(locations[text])
        descriptors.append((offsets[0],offsets[1],len(name),len(value)))
    assert len(descriptors)==61 and len(pool)<1024 and max(max(d[2:])for d in descriptors)<32
    rows=[]
    for index,(name,value,n,v)in enumerate(descriptors,1):
        rows.append(f"                7'd{index}:begin rsp_name_offset<=10'd{name};rsp_value_offset<=10'd{value};rsp_name_bytes<=5'd{n};rsp_value_bytes<=5'd{v};end")
    data='\n'.join(f"        bytes_rom[{i}]=8'h{b:02x};"for i,b in enumerate(pool))
    digest=hashlib.sha256(bytes(pool)).hexdigest()
    source='''`timescale 1ns/1ps
`default_nettype none
// Generated fixed RFC7541 Appendix A protocol data; not a model vocabulary.
// Byte-pool SHA256: @SHA@
module hpack_static_table #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire [6:0] req_index,input wire [USER_WIDTH-1:0] req_user,
    output reg rsp_valid,input wire rsp_ready,output reg rsp_invalid,
    output reg [9:0] rsp_name_offset,rsp_value_offset,output reg [4:0] rsp_name_bytes,rsp_value_bytes,
    output reg [USER_WIDTH-1:0] rsp_user,
    input wire read_valid,output wire read_ready,input wire [9:0] read_offset,
    output reg byte_valid,input wire byte_ready,output wire [7:0] byte_data,output reg byte_invalid
);
    localparam integer TEXT_BYTES=@SIZE@;
    (* rom_style="block" *) reg [7:0] bytes_rom[0:1023];
    reg [7:0] read_data;
    integer i;
    initial begin
        for(i=0;i<1024;i=i+1)bytes_rom[i]=0;
@DATA@
    end
    assign req_ready=!rst&&(!rsp_valid||rsp_ready);
    assign read_ready=!rst&&(!byte_valid||byte_ready);
    assign byte_data=byte_invalid?8'd0:read_data;
    // ROM storage/data have no reset. Only the valid/error pipeline resets.
    always @(posedge clk)if(read_ready&&read_valid)read_data<=bytes_rom[read_offset];
    always @(posedge clk)begin
        if(rst)begin
            rsp_valid<=0;rsp_invalid<=0;rsp_name_offset<=0;rsp_value_offset<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;rsp_user<=0;
            byte_valid<=0;byte_invalid<=0;
        end else begin
            if(read_ready)begin byte_valid<=read_valid;if(read_valid)byte_invalid<=read_offset>=TEXT_BYTES;end
            if(req_ready)begin
                rsp_valid<=req_valid;
                if(req_valid)begin
                    rsp_user<=req_user;rsp_invalid<=req_index==0||req_index>61;
                    case(req_index)
@ROWS@
                        default:begin rsp_name_offset<=0;rsp_value_offset<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;end
                    endcase
                end
            end
        end
    end
endmodule
`default_nettype wire
'''.replace('@SHA@',digest).replace('@SIZE@',str(len(pool))).replace('@DATA@',data).replace('@ROWS@','\n'.join(rows))
    args.rtl.parent.mkdir(parents=True,exist_ok=True);args.rtl.write_text(source,encoding='ascii')
    args.output.mkdir(parents=True,exist_ok=True)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for index in range(128):
            n,v=HeaderTable.STATIC_TABLE[index-1]if 1<=index<=61 else(b'',b'')
            stream.write(f'{index} {len(n)} {len(v)} {int(index==0 or index>61)}\n')
            stream.write(' '.join(f'{b:02x}'for b in n+v)+'\n')
    print(f'Generated 61 static descriptors/{len(pool)} fixed protocol bytes, SHA256 {digest}')


if __name__=='__main__':main()
