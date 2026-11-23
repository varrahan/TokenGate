"""Timing-only registered neighbors, defaulting to the Parser decoder.

This is not a functional AXI adapter: it models arbitrary neighboring source
and sink registers so core timing is measured with real routed clock paths.
External package timing is intentionally outside this harness's proof scope.
"""
import argparse
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--top",default="proto_json_decoder")
    parser.add_argument("--harness-top",default="parser_timing_harness")
    args=parser.parse_args()
    source=args.source.read_text(encoding="utf-8")
    if not all(re.fullmatch(r"[A-Za-z_]\w*",name)for name in(args.top,args.harness_top)):raise ValueError("Invalid module name")
    match=re.search(r"module\s+"+re.escape(args.top)+r"\s*#\((.*?)\)\s*\((.*?)\);",source,re.S)
    if not match:raise ValueError("Could not identify the complete module interface")
    parameters,header=match.groups()
    header=re.sub(r"//[^\n]*","",header)
    ports=[];direction=width=None
    for declaration in header.split(","):
        port=re.fullmatch(r"\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*",declaration)
        if not port:raise ValueError(f"Unsupported port declaration: {declaration}")
        new_direction,new_width,name=port.groups()
        if new_direction is not None:direction,width=new_direction,new_width or ""
        if direction is None:raise ValueError("Missing port direction")
        ports.append((direction,width,name))
    names=[p[2]for p in ports]
    if len(names)!=len(set(names))or names.count("clk")!=1 or "inout"in header:
        raise ValueError("Unsupported or ambiguous module interface")
    parameter_names=re.findall(r"parameter\s+integer\s+(\w+)\s*=",parameters)
    lines=["`timescale 1ns/1ps","`default_nettype none",
           "// TIMING ONLY. Independent input/output registers do not implement AXI flow control.",
           f"module {args.harness_top} #(",parameters,
           ")("]
    lines.extend(f"    {direction} {'wire'if direction=='input'else'reg'} {width} {name}{','if i+1<len(ports)else''}"
                 for i,(direction,width,name)in enumerate(ports))
    lines.extend([");","    wire core_clk;","    BUFG timing_clock_buffer (.I(clk),.O(core_clk));"])
    for direction,width,name in ports:
        if name!="clk":lines.append(f"    {'reg'if direction=='input'else'wire'} {width} timing_{name};")
    lines.append("    always @(posedge core_clk) begin")
    for direction,_,name in ports:
        if name=="clk":continue
        lines.append(f"        timing_{name} <= {name};"if direction=="input"else f"        {name} <= timing_{name};")
    lines.extend(["    end",f"    {args.top} #(",
                  ",\n".join(f"        .{name}({name})"for name in parameter_names),"    ) core ("])
    lines.append(",\n".join(f"        .{name}({'core_clk'if name=='clk'else'timing_'+name})"for _,_,name in ports))
    lines.extend(["    );","endmodule","`default_nettype wire",""])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text("\n".join(lines),encoding="utf-8")
    print(f"Generated registered timing neighbors for all {len(ports)} {args.top} ports")


if __name__=="__main__":main()
