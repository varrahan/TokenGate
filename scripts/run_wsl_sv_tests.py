"""Run source SV regressions with Verilator in the user-selected WSL project.

AMD XPM sources are read from the existing Vivado installation. No generated
Windows executables or Windows application-control settings are used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path, source_relative

SUITES={
    "serializer":("serializer-stream","tb_serializer",["rtl/proto_json_serializer.v","rtl/axis_byte_unpacker.v",
        "rtl/axis_byte_packer.v","rtl/json_escape_encoder.v","sim/tb_serializer.sv"]),
    "utf8_chunks":("utf8-chunks","tb_utf8_chunks",["rtl/utf8_chunk_decoder.v","rtl/utf8_serialized_chunk.v",
        "rtl/proto_json_serializer.v","rtl/axis_byte_unpacker.v","rtl/axis_byte_packer.v","rtl/json_escape_encoder.v","sim/tb_utf8_chunks.sv"]),
    "packager":("token-packager","tb_token_packager",["rtl/token_packager.v","sim/tb_token_packager.sv"]),
    "pretokenizer":("pretokenizer","tb_bpe_pretokenizer",[
        "rtl/axis_byte_unpacker.v","rtl/utf8_codepoint_reader.v","rtl/regex_splitter_fsm.v","rtl/bpe_pretokenizer.v",
        "rtl/programmable_table_ram.v","rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
        "rtl/unicode_external_lookup.v","sim/axi_external_memory_model.sv","sim/tb_bpe_pretokenizer.sv"]),
    "splitter":("splitter","tb_regex_splitter",["rtl/regex_splitter_fsm.v","sim/tb_regex_splitter.sv"]),
    "ram":("programmable-ram","tb_programmable_ram",["rtl/programmable_table_ram.v","sim/tb_programmable_ram.sv"]),
    "trie":("trie-pipeline","tb_trie_pipeline",["rtl/trie_search_pipeline.v","rtl/programmable_table_ram.v","rtl/external_memory_cache.v",
        "rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v","sim/axi_external_memory_model.sv","sim/tb_trie_pipeline.sv"]),
    "external_merge":("external-merge","tb_external_merge",["rtl/bpe_external_merge_unit.v","rtl/bpe_rank_lookup.v",
        "rtl/programmable_table_ram.v","rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
        "sim/axi_external_memory_model.sv","sim/tb_external_merge.sv"]),
    "tokenizer":("tokenizer-engine","tb_tokenizer_engine",["rtl/bpe_tokenizer_engine.v","rtl/memory_command_slot.v",
        "rtl/axis_byte_unpacker.v","rtl/utf8_codepoint_reader.v","rtl/regex_splitter_fsm.v","rtl/bpe_pretokenizer.v",
        "rtl/unicode_external_lookup.v","rtl/trie_search_pipeline.v","rtl/bpe_external_merge_unit.v","rtl/bpe_rank_lookup.v","rtl/token_packager.v",
        "rtl/programmable_table_ram.v","rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
        "sim/axi_external_memory_model.sv","sim/tb_tokenizer_engine.sv"]),
}
SUITES["tokenizer_subsystem"]=("tokenizer-engine","tb_tokenizer_subsystem",[
    *[name for name in SUITES["tokenizer"][2]if name!="sim/tb_tokenizer_engine.sv"],
    "rtl/scu35_tokenizer_subsystem.v","rtl/vocabulary_epoch_control.v","rtl/detokenizer_engine.v","rtl/axis_byte_packer.v",
    "sim/tb_tokenizer_subsystem.sv"])
SUITES["tokenizer_bulk"]=("tokenizer-bulk","tb_tokenizer_mmio_bulk",[
    *[name for name in SUITES["tokenizer_subsystem"][2]if name.startswith("rtl/")],
    "rtl/tokenizer_mmio.v","rtl/scu35_tokenizer_mmio_subsystem.v","sim/axi_external_memory_model.sv","sim/tb_tokenizer_mmio_bulk.sv"])
SUITES["huffman"]=("hpack-huffman","tb_hpack_huffman",["rtl/hpack_huffman_rom.v","rtl/hpack_huffman_decoder.v","sim/tb_hpack_huffman.sv"])
SUITES["hpack_integer"]=("hpack-integer","tb_hpack_integer",["rtl/hpack_integer_decoder.v","sim/tb_hpack_integer.sv"])
SUITES["hpack_static"]=("hpack-static","tb_hpack_static_table",["rtl/hpack_static_table.v","sim/tb_hpack_static_table.sv"])
SUITES["hpack_string"]=("hpack-string","tb_hpack_string",["rtl/hpack_integer_decoder.v","rtl/hpack_huffman_rom.v",
    "rtl/hpack_huffman_decoder.v","rtl/hpack_string_decoder.v","sim/tb_hpack_string.sv"])
SUITES["hpack_table"]=("hpack-table","tb_hpack_dynamic_table",["rtl/hpack_dynamic_table.v","rtl/programmable_table_ram.v",
    "rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_hpack_dynamic_table.sv"])
SUITES["hpack_headers"]=("hpack-headers","tb_hpack_headers",["rtl/hpack_header_decoder.v","rtl/hpack_integer_decoder.v",
    "rtl/hpack_huffman_rom.v","rtl/hpack_huffman_decoder.v","rtl/hpack_string_decoder.v","rtl/hpack_static_table.v",
    "rtl/hpack_dynamic_table.v","rtl/memory_command_slot.v","rtl/programmable_table_ram.v","rtl/external_memory_cache.v",
    "rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v","sim/axi_external_memory_model.sv","sim/tb_hpack_headers.sv"])
SUITES["http2_frames"]=("http2-frames","tb_http2_frames",["rtl/http2_frame_reader.v","rtl/http2_axis_ingress.v","rtl/axis_byte_unpacker.v","sim/tb_http2_frames.sv"])
SUITES["http2_connections"]=("http2-connections","tb_http2_connections",["rtl/http2_connection_ingress.v","rtl/http2_frame_reader.v",
    "rtl/http2_axis_ingress.v","rtl/axis_byte_unpacker.v","rtl/memory_command_slot.v","rtl/programmable_table_ram.v",
    "rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v","sim/axi_external_memory_model.sv","sim/tb_http2_connections.sv"])
SUITES["http2_transport"]=("http2-transport","tb_http2_transport",[*SUITES["http2_connections"][2],
    "rtl/http2_payload_decoder.v","rtl/http2_transport_ingress.v","sim/tb_http2_transport.sv"])
SUITES["http2_hpack"]=("http2-hpack","tb_http2_hpack",[
    *[name for name in SUITES["http2_transport"][2]if name.startswith("rtl/")],
    *[name for name in SUITES["hpack_headers"][2]if name.startswith("rtl/")and name not in SUITES["http2_transport"][2]],
    "rtl/http2_header_dispatch.v","rtl/http2_hpack_ingress.v","sim/axi_external_memory_model.sv","sim/tb_http2_hpack.sv"])
SUITES["grpc_messages"]=("grpc-messages","tb_grpc_messages",[
    "rtl/grpc_message_deframer.v","rtl/memory_command_slot.v","rtl/programmable_table_ram.v",
    "rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_grpc_messages.sv"])
SUITES["http2_names"]=("http2-names","tb_http2_names",["rtl/http2_name_classifier.v","sim/tb_http2_names.sv"])
SUITES["http2_requests"]=("http2-requests","tb_http2_requests",[
    *[name for name in SUITES["http2_hpack"][2] if name.startswith("rtl/")],
    "rtl/http2_name_classifier.v","rtl/http2_request_headers.v","sim/axi_external_memory_model.sv","sim/tb_http2_requests.sv"])
SUITES["http2_routes"]=("http2-routes","tb_http2_routes",[
    *[name for name in SUITES["http2_requests"][2] if name.startswith("rtl/")],
    "rtl/http2_route_lookup.v","rtl/http2_request_router.v","sim/axi_external_memory_model.sv","sim/tb_http2_routes.sv"])
SUITES["http2_admission"]=("http2-admission","tb_http2_admission",[
    "rtl/http2_rpc_admission.v","rtl/grpc_ingress_engine.v","rtl/grpc_stream_store.v","rtl/grpc_message_deframer.v","rtl/grpc_descriptor_queue.v",
    "rtl/memory_command_slot.v","rtl/programmable_table_ram.v","rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_http2_admission.sv"])
SUITES["schema"]=("schema-stream","tb_schema_stream",["rtl/schema_cam_lut.v","sim/tb_schema_stream.sv"])
SUITES["decoder"]=("decoder","tb_decoder",[
    "rtl/proto_json_decoder.v","rtl/rx_framing_fifo.v","rtl/axis_byte_unpacker.v","rtl/axis_skid_buffer.v",
    "rtl/axis_byte_window.v","rtl/schema_cam_lut.v","rtl/speculative_json_fsm.v","rtl/json_string_normalizer.v",
    "rtl/protobuf_wire_fsm.v","rtl/utf8_byte_validator.v","rtl/protobuf_varint_decoder.v","rtl/axis_byte_packer.v","sim/tb_decoder.sv"])
SUITES["grpc_application"]=("grpc-application","tb_grpc_application",[
    *[name for name in SUITES["grpc_messages"][2]if name!="sim/tb_grpc_messages.sv"],
    *[name for name in SUITES["decoder"][2]if name.startswith("rtl/")],
    "rtl/transport_message_replay.v","rtl/grpc_application_decoder.v","sim/tb_grpc_application.sv"])
SUITES["message_replay"]=("message-replay","tb_message_replay",[
    "rtl/transport_message_replay.v","rtl/memory_command_slot.v","sim/tb_message_replay.sv"])
SUITES["grpc_descriptors"]=("grpc-descriptors","tb_grpc_descriptors",[
    "rtl/grpc_descriptor_queue.v","rtl/memory_command_slot.v","rtl/programmable_table_ram.v",
    "rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_grpc_descriptors.sv"])
SUITES["grpc_streams"]=("grpc-streams","tb_grpc_streams",[
    "rtl/grpc_stream_store.v","rtl/memory_command_slot.v","rtl/programmable_table_ram.v",
    "rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_grpc_streams.sv"])
SUITES["grpc_engine"]=("grpc-engine","tb_grpc_engine",[
    "rtl/grpc_ingress_engine.v","rtl/grpc_stream_store.v","rtl/grpc_message_deframer.v","rtl/grpc_descriptor_queue.v",
    "rtl/memory_command_slot.v","rtl/programmable_table_ram.v","rtl/external_memory_cache.v","rtl/external_memory_arbiter.v","rtl/external_memory_fabric.v",
    "sim/axi_external_memory_model.sv","sim/tb_grpc_engine.sv"])
SUITES["grpc_parser"]=("grpc-parser","tb_grpc_parser",[
    *[name for name in SUITES["grpc_engine"][2]if name.startswith("rtl/")],
    *[name for name in SUITES["decoder"][2]if name.startswith("rtl/")],
    "rtl/transport_message_replay.v","rtl/grpc_application_decoder.v","rtl/grpc_ingress_parser.v",
    "sim/axi_external_memory_model.sv","sim/tb_grpc_parser.sv"])
SUITES["grpc_prefill"]=("grpc-prefill","tb_grpc_prefill",[
    *[name for name in SUITES["grpc_parser"][2]if name.startswith("rtl/")],
    *[name for name in SUITES["tokenizer"][2]if name.startswith("rtl/")and name not in SUITES["grpc_parser"][2]],
    "rtl/bow_axi_bridge.v","rtl/grpc_prefill_datapath.v","sim/axi_external_memory_model.sv","sim/tb_grpc_prefill.sv"])
SUITES["http2_prefill"]=("http2-prefill","tb_http2_prefill",[
    *dict.fromkeys(name for suite in("grpc_prefill","http2_routes","http2_admission")for name in SUITES[suite][2]if name.startswith("rtl/")),
    "rtl/http2_grpc_prefill.v","sim/axi_external_memory_model.sv","sim/tb_http2_prefill.sv"])


def file_hash(path):
    digest=hashlib.sha256()
    with path.open("rb")as stream:
        while data:=stream.read(1024*1024):digest.update(data)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("suite",choices=SUITES)
    parser.add_argument("--simulator",choices=("verilator","iverilog"),default="verilator")
    parser.add_argument("--memory-backend",choices=("portable","xpm"),default="portable")
    parser.add_argument("--jobs",type=int,default=2)
    parser.add_argument("--xpm-memory",type=Path,default=Path("/mnt/c/AMDDesignTools/2025.2/Vivado/data/ip/xpm/xpm_memory/hdl/xpm_memory.sv"))
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    name,top,relative_sources=SUITES[args.suite];build=root/"build"/name;build.mkdir(parents=True,exist_ok=True)
    sources=[str(source_path(root, name))for name in relative_sources]
    definitions=[]
    if args.suite in("pretokenizer","ram","trie","external_merge","tokenizer","tokenizer_subsystem","tokenizer_bulk","hpack_table","hpack_headers","http2_connections","http2_transport","http2_hpack","http2_requests","http2_routes","http2_admission","http2_prefill","grpc_messages","schema","decoder","grpc_application","message_replay","grpc_descriptors","grpc_streams","grpc_engine","grpc_parser","grpc_prefill"):
        if args.memory_backend=="xpm":
            sources.insert(0,str(args.xpm_memory))
            if "rtl/rx_framing_fifo.v" in relative_sources:sources.insert(0,str(args.xpm_memory.parents[2]/"xpm_fifo/hdl/xpm_fifo.sv"))
        else:definitions=["-DPARSER_PORTABLE_SIM"]
    if args.simulator=="verilator":
        command=["verilator","--binary","--timing","--assert","-Wno-fatal","-Werror-UNOPTFLAT","--top-module",top,"-j",str(args.jobs),
                 "--Mdir",str(build/"verilator"),"-o",str(build/"verilator"/top),*definitions,*sources]
        execute=[str(build/"verilator"/top)]
    else:
        command=["iverilog","-g2012","-s",top,"-o",str(build/"iverilog.vvp"),*definitions,*sources]
        execute=["vvp",str(build/"iverilog.vvp")]
    # Suites sharing the full-model fixture keep independent executables/logs.
    if args.suite=="tokenizer_subsystem":
        if args.simulator=="verilator":
            command[command.index("--Mdir")+1]=str(build/"verilator-subsystem")
            command[command.index("-o")+1]=str(build/"verilator-subsystem"/top)
            execute=[str(build/"verilator-subsystem"/top)]
        else:
            command[command.index("-o")+1]=str(build/"iverilog-subsystem.vvp");execute=["vvp",str(build/"iverilog-subsystem.vvp")]
    log_prefix=args.simulator+("-subsystem"if args.suite=="tokenizer_subsystem"else"")
    build_log=build/(log_prefix+"-build.log");sim_log=build/(log_prefix+"-simulation.log")
    report_path=build/(log_prefix+"-report.json")
    report={"suite":args.suite,"simulator":args.simulator,"memory_backend":args.memory_backend,
            "source_sha256":{str(source_relative(Path(name), root))if Path(name).is_relative_to(root)else name:hashlib.sha256(Path(name).read_bytes()).hexdigest()for name in [*sources,str(root/'tools/rtl_paths.py')]},
            "fixture_sha256":{path.name:file_hash(path)for path in sorted(build.iterdir())if path.is_file()and path.suffix in(".mem",".txt",".bin",".json")and not path.name.endswith("-report.json")},
            "runner_sha256":file_hash(Path(__file__)),"started_utc":datetime.now(timezone.utc).isoformat(),
            "compile_command":command,"execute_command":execute,"phase":"building"}
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    print(f"SIMULATOR={args.simulator} MEMORY_BACKEND={args.memory_backend}",flush=True)
    with build_log.open("w")as log:
        result=subprocess.run(command,cwd=build,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        report.update(phase="build_failed",returncode=result.returncode);report_path.write_text(json.dumps(report,indent=2)+"\n")
        print(build_log.read_text()[-12000:]);raise SystemExit(result.returncode)
    report["phase"]="running";report_path.write_text(json.dumps(report,indent=2)+"\n")
    with sim_log.open("w")as log:
        result=subprocess.run(execute,cwd=build,stdout=log,stderr=subprocess.STDOUT)
    output=sim_log.read_text();print(output[-8000:])
    changed=[]
    for name,expected_hash in report["fixture_sha256"].items():
        path=build/name
        if not path.is_file() or file_hash(path)!=expected_hash:changed.append("fixture:"+name)
    for name,expected_hash in report["source_sha256"].items():
        path=Path(name)if Path(name).is_absolute()else source_path(root, name)
        if not path.is_file() or file_hash(path)!=expected_hash:changed.append("source:"+name)
    passed=result.returncode==0 and any(line.startswith("PASS:")for line in output.splitlines())
    if changed:
        passed=False
        report["changed_inputs"]=changed
        print("INPUTS_CHANGED_DURING_RUN="+json.dumps(changed))
    report.update(phase="passed"if passed else"simulation_failed",returncode=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    if not passed:raise SystemExit(result.returncode or 1)


if __name__=="__main__":main()
