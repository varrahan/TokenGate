# Architecture

[README](../README.md) · [Configuration](configuration.md) · [Development](development.md) · [Status](status.md)

## System scope

The required system is a bidirectional Parser/Tokenizer pair with runtime model
and schema programming. Parser/transport targets AU15P; Tokenizer targets SCU35
with external vocabulary memory. The original combined SCU35 project remains a
decoder/reference baseline. The larger Parser split preserves the complete
functional scope.

The requirements include:

- Independent 512-bit QDMA packet directions at a 250 MHz application target,
  preserving `TKEEP`, `TLAST`, and `TUSER` context under stalls.
- HTTP/1.1 and HTTP/2 gRPC request handling, programmable JSON/Protobuf field
  selection, JSON escapes, and multi-byte Protobuf varints.
- HTTP/2 preface, SETTINGS/ACK, HEADERS/CONTINUATION, static/dynamic HPACK and
  Huffman decoding, interleaved streams, DATA/padding, flow control,
  WINDOW_UPDATE, PING/ACK, RST_STREAM, GOAWAY, and trailers. Unsupported
  compression modes must produce explicit protocol errors.
- Model-specific Unicode pretokenization, trie lookup, ranked BPE merges,
  complete vocabulary support, and 512-bit token-ID packaging.
- Inverse vocabulary lookup, cross-token UTF-8, configurable special-token
  filtering, JSON/SSE and Protobuf serialization, and transport framing.
- Quiesced model/schema updates without mixing generations, plus whole-RPC,
  GPU, memory, and response ownership through cancellation and reset.
- Exact native-tokenizer and response-byte comparisons, resource/timing
  evidence, and measured throughput on the final composition.

The [status guide](status.md) distinguishes implemented subsets from these
requirements. HTTP/1.1/SSE transport and several system integration requirements
remain open.

## Datapaths

RTL follows the two device responsibilities, with common infrastructure shared:

```text
rtl/
  parser/
    top/                  Application and transport compositions
    transport/http2/      Frames, routing, credits, and connection control
    transport/hpack/      Header compression decoding
    transport/grpc/       Message reassembly, directories, and payload ownership
    decoder/              Transactional application decoder and receive FIFO
    decoder/json/         JSON grammar, scanning, and string normalization
    decoder/protobuf/     Wire tags, lengths, and varints
    decoder/schema/       Field selection and host registers
    response/             RPC returns, framing, UTF-8 chunks, and serializers
    control/              Directory lock arbitration and maintenance probes
  tokenizer/
    top/                  Application, memory, and programming wrappers
    bpe/                  Pretokenization, ranked merging, and token packaging
    trie/                 Byte-to-token trie lookup
    unicode/              UTF-8 scalar decoding and Unicode classes
    detokenizer/          Token-to-byte reconstruction
    memory/hyperram/      AXI frontend, clock crossing, startup, and word engine
    control/              Vocabulary epochs and host registers
  shared/
    axis/                 Packing, buffering, windows, and frame arbitration
    memory/               RAM, cache, fabric, and command slots
    link/                 Buffered BoW boundary and packet clock crossing
```

```text
Request bytes -> HTTP/2 + HPACK + gRPC -> JSON/Protobuf extraction
              -> 128-bit text link -> pretokenizer + trie + ranked BPE
              -> 512-bit token DMA -> host/GPU

Generated IDs -> inverse vocabulary -> 128-bit text link
              -> incremental UTF-8 + JSON/Protobuf serializer
              -> HTTP/2 response HEADERS + DATA + trailers -> response bytes
```

Parser owns transport state, route/admission policy, RPC directory and payload
leases, response progress, UTF-8 carry, and serialization. Tokenizer owns
pretokenization, BPE, inverse lookup, token packaging, and its vocabulary/cache
and working-memory clients. The partitions use separate local memory fabrics.

Relevant entry points are
[`http2_parser_fpga_application`](../rtl/parser/transport/http2/http2_parser_fpga_application.v),
[`tokenizer_fpga_application`](../rtl/tokenizer/top/tokenizer_fpga_application.v), and the
`tokenizer_hyperram_subsystem` emitted by the
[`HyperRAM assembly generator`](../tools/generate_tokenizer_hyperram_experiment.py).
These are logical application/controller tops; board adapters remain required.

The maintained source entry points are:

| Area | Source root |
| --- | --- |
| HTTP/2 Parser application | [`http2_enveloped_parser_application`](../rtl/parser/top/http2_enveloped_parser_application.v) |
| Application decoder | [`proto_json_decoder`](../rtl/parser/decoder/proto_json_decoder.v) |
| Schema peripheral and decoder | [`parser_schema_mmio_decoder`](../rtl/parser/decoder/schema/parser_schema_mmio_decoder.v) |
| Tokenizer with local cache/fabric | [`tokenizer_fpga_memory_subsystem`](../rtl/tokenizer/top/tokenizer_fpga_memory_subsystem.v) |
| Tokenizer host programming | [`scu35_tokenizer_mmio_subsystem`](../rtl/tokenizer/top/scu35_tokenizer_mmio_subsystem.v) |
| Asynchronous external-memory controller | [`axi_hyperram_async_controller`](../rtl/tokenizer/memory/hyperram/axi_hyperram_async_controller.v) |

Generated experiments apply additional changes to these source families.
Component tops and older transport variants also remain where regression
benches or generators consume them. A module outside the current application
hierarchy can still be required to regenerate or verify that application.
The schema-integrated application requires its matching generated core: the
loose root schema wrapper currently has ports absent from the root enveloped
core. Use the qualified matching snapshot for full schema integration.

TLS termination and PCIe electrical/PHY blocks are integration boundaries.
Transport receives decrypted, ordered connection bytes with context metadata.
The host interface must distinguish raw requests, generated IDs, prompt-token
DMA, and packaged responses. Direct GPU-memory DMA requires separate endpoint,
driver, and platform validation.

## Stream and memory contracts

| Boundary | Contract |
| --- | --- |
| Packet ingress/egress | Independent 512-bit AXI4-Stream channels |
| Forward/reverse text | Independent 128-bit AXI4-Stream channels with context |
| Token engine | 32-bit token IDs; forward packager emits 512-bit DMA words |
| Model programming | 32-bit AXI-Lite data, 16-bit byte register addresses |
| External-memory fabric | 64-bit AXI master; byte-addressed client commands of 1–9 bytes |

A stalled valid transaction retains its payload and identity until acceptance.
The BoW boundary uses buffering in both directions, with no combinational ready
path across it or input-dependent combinational valid/data. The RTL bridge is a
logical boundary, not a physical BoW implementation.

The physical inter-FPGA protocol must preserve byte enables, packet boundaries,
RPC/generation identity, model/schema epochs, ordered commands/results, and
cancellation. It needs buffering, credits, integrity checks, and actual clock
crossing. Independently synchronizing its control wires is insufficient.

The nominal text interface offers 4 GB/s per direction; each packet interface
offers 16 GB/s before overhead. Neither figure measures sustained throughput.
Endpoint placement determines whether the board link also carries token DMA or
raw packets, so a text-only bandwidth budget cannot qualify every topology.

## Parsing and token completion

[`proto_json_decoder`](../rtl/parser/decoder/proto_json_decoder.v) accepts reassembled
application packets. It captures format and context before queuing. Defaults
select JSON keys `prompt`/`text` and Protobuf field 1. Selected JSON values must
be strings; repeated selected strings concatenate in document order.

Extraction remains tentative until the entire packet passes syntax and Unicode
scalar UTF-8 checks. Invalid or oversized extraction produces an error and no
text packet. JSON errors use parser codes, Protobuf errors are ORed with `0x40`,
and extraction overflow is `0x80`. Errors must be accepted before the next
packet. Schema writes require a quiesced grant and an idle decoder.

[`bpe_tokenizer_engine`](../rtl/tokenizer/bpe/bpe_tokenizer_engine.v) captures its runtime
profile and memory allocation at the first accepted text beat. BPE applies the
lowest-ranked adjacent merge, breaking ties leftmost; trie membership alone
does not determine a merge. The current engine performs iterative queries and
rescans, so passing correctness tests does not prove ingress-rate processing.

All forward tokens are staged until whole-sequence computation succeeds.
Release readback can still fail after a tentative prefix has reached DMA. A
failed started stream closes with zero-keep/TLAST and a failed completion with
count zero. Consumers must discard that sequence's tentative tokens. An empty
successful sequence has a terminal packet and successful zero-count completion.
**TLAST alone does not mean success.**

Success completion contains the exact count and original context and remains
held until acknowledged. The shared wrapper also waits for the packager's last
512-bit word to be accepted. Cancellation drains accepted memory commands and
responses; it cannot withdraw a stalled transaction.

## RPC, credit, and response ownership

GPU descriptors carry connection/stream/generation, model/schema epochs,
ordinal, token, and EOS. Admission validates the real directory and sidecar
before lookup or transmission. Directory LOAD ownership remains pinned through
lookup, accepted response output, and acknowledged progress writes, preventing
CLOSE/reuse while that transaction is active.

Per-generation response progress stores ordinal, UTF-8 carry, and captured
policy. A later persistence failure may occur after bytes reached the wire.
The first uncertain memory cause must remain observable; fence/quarantine the
affected owner instead of retrying from old progress and duplicating output.
Wire acceptance, durable commit, and retirement are distinct events.

Receive credits must be backed by actual buffer capacity. Reclaim payload only
after its consumer releases ownership, persist the reclaimed ordinal, then
return credit. Stream refusal must preserve existing calls, shared HPACK state,
and accounting for already-sent padded DATA. Send-window reservations and final
wire retirement must complete before their owners are released.

Local idle and per-token completion do not release the whole RPC/GPU image
lease. [Configuration maintenance](configuration.md#maintenance-and-recovery)
requires a coordinated drain across both devices and the host. Retained reset
must recover or explicitly revoke old directory, GPU, memory, and wire ownership.

## Board integration

SCU35 has 48 BRAM36 blocks, no UltraRAM, and no integrated PCIe/transceivers.
Complete models use external memory with native BRAM caches; the old on-chip
UltraRAM backend remains a simulation/reference option. The board's 64 Mb
HyperRAM provides 8 MiB storage, shared by model and working allocations.

The pinned SCU35 board definition is the official revision
`29bbdfd89b7048cac72bf971bcd4b18f6ca50c5a`, board part
`xilinx.com:scu35:part0:1.0`. It declares a 100 MHz differential clock on
`SYSCLK_P=F23`, `SYSCLK_N=E23`. It does not provide the complete HyperRAM/HSIO
parallel-data pin map. Preserve authoritative package constraints, clock
generation, DDR/RWDS calibration, reset/power sequencing, and CDC requirements
when building the physical top; core timing does not qualify those paths.

References: [pinned board files](https://github.com/Xilinx/XilinxBoardStore/tree/29bbdfd89b7048cac72bf971bcd4b18f6ca50c5a/boards/Xilinx/scu35/1.0),
[SCU35 HyperRAM](https://docs.amd.com/r/en-US/ug1713-scu35-eval-bd/HyperRAM-Memory),
[SCU35 HSIO](https://docs.amd.com/r/en-US/ug1713-scu35-eval-bd/HSIO).
