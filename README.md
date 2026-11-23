# Parser / Tokenizer

FPGA hardware for converting network requests into LLM token IDs and generated
tokens back into responses. The design combines HTTP/2 and gRPC transport,
JSON/Protobuf parsing, programmable BPE tokenization, inverse vocabulary lookup,
and response serialization.

The system is under implementation. Complete reference workloads pass on specific
simulation snapshots, but final Parser timing, distributed maintenance, physical
interfaces, and sustained throughput remain open. See [status](docs/status.md)
for the verified scope.

## Design targets

| Component | Target |
| --- | --- |
| Parser and transport | AU15P, `xcau15p-ffvb676-2-e` |
| Tokenizer and vocabulary memory | SCU35, `xcsu35p-sbvb625-2-e`, external HyperRAM |
| Application clock | 250 MHz |
| Tokenizer memory clock | 200 MHz in the current controller assembly |
| Packet streams | Independent 512-bit AXI4-Stream directions |
| Parser/Tokenizer text streams | Independent 128-bit AXI4-Stream directions |
| FPGA tools | Vivado 2025.2 |

These widths and clocks are interface targets. They do not establish measured
throughput or board timing. No physical boards are available for validation.

## Quick start

Use Python 3.12 and the pinned reference packages:

```bash
python3 -m venv .venv-sim
.venv-sim/bin/python -m pip install -r requirements-test.txt
.venv-sim/bin/python -m pytest tests -q
```

RTL simulation additionally needs Icarus Verilog or Verilator. The
[development guide](docs/development.md) covers fixtures, simulation, Vivado,
and Windows/WSL workflows.

## Documentation

- [Architecture](docs/architecture.md): requirements, datapaths, interfaces, and ownership.
- [Configuration](docs/configuration.md): model images, memory layout, registers, and safe updates.
- [Development](docs/development.md): setup, tests, builds, and troubleshooting.
- [Status](docs/status.md): recorded verification results and remaining work.

## Repository layout

| Path | Contents |
| --- | --- |
| [`rtl/parser/`](rtl/parser/) | Request transport, application decoding, RPC state, and responses |
| [`rtl/tokenizer/`](rtl/tokenizer/) | BPE, vocabulary lookup, token packaging, and HyperRAM |
| [`rtl/shared/`](rtl/shared/) | Shared AXI streams, memory fabric, and link utilities |
| [`sim/`](sim/) | SystemVerilog benches, cocotb tests, and reference data |
| [`tests/`](tests/) | Python image and allocation tests |
| [`tools/`](tools/) | Image compilers, fixture generators, and verification tools |
| [`scripts/`](scripts/) | Simulation and Vivado launchers |
| [`constraints/`](constraints/) | Source timing constraints |
| [`create_parser.tcl`](create_parser.tcl) | Recreate/update the saved application-decoder project |

`build/` holds generated images, experiments, and verification evidence.
`Parser/` is the local decoder-project workspace, recreated when needed by
the Vivado launchers. `FPGA/` holds local source bundles, board definitions,
and packaged Vivado projects. These directories are excluded from version
control; maintained RTL is in `rtl/`.
