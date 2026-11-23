"""Generate a synchronous branch ROM from RFC 7541 Appendix B protocol data."""
import argparse
from collections import deque
import hashlib
from pathlib import Path
import struct
from hpack.huffman_constants import REQUEST_CODES,REQUEST_CODES_LENGTH


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    root={}
    assert len(REQUEST_CODES)==len(REQUEST_CODES_LENGTH)==257
    for symbol,(code,length)in enumerate(zip(REQUEST_CODES,REQUEST_CODES_LENGTH)):
        node=root
        for shift in range(length-1,-1,-1):
            assert "symbol"not in node;node=node.setdefault(code>>shift&1,{})
        assert not node;node["symbol"]=symbol
    internal=[];queue=deque([root]);indices={}
    while queue:
        node=queue.popleft()
        if "symbol"in node:continue
        assert set(node)=={0,1};indices[id(node)]=len(internal);internal.append(node);queue.extend((node[0],node[1]))
    assert len(internal)==256
    words=[]
    for node in internal:
        edges=[512|node[bit]["symbol"]if "symbol"in node[bit]else indices[id(node[bit])]for bit in(0,1)]
        words.append(edges[0]|edges[1]<<10)
    digest=hashlib.sha256(b"".join(struct.pack(">IB",code,length)for code,length in zip(REQUEST_CODES,REQUEST_CODES_LENGTH))).hexdigest()
    lines=["`timescale 1ns/1ps","`default_nettype none",
           "// Fixed HTTP/2 protocol codebook; model vocabularies remain runtime data.",
           "// Data: https://www.rfc-editor.org/rfc/rfc7541#appendix-B",
           "// 257 symbols, 256 internal nodes; codebook SHA-256: "+digest,
           "module hpack_huffman_rom(input wire clk,input wire en,input wire [7:0] address,output reg [19:0] data);",
           '    (* rom_style="block" *) reg [19:0] branches[0:255];',"    initial begin"]
    lines += [f"        branches[8'd{i}]=20'h{word:05x};"for i,word in enumerate(words)]
    lines += ["    end","    always @(posedge clk)if(en)data<=branches[address];","endmodule","`default_nettype wire",""]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text("\n".join(lines),encoding="ascii")
    print(f"Generated 256x20 protocol branch ROM, codebook SHA-256 {digest}")


if __name__=="__main__":main()
