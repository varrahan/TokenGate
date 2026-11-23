# Development

[README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Status](status.md)

## Environment

Use Python 3.12, the pinned [`requirements-test.txt`](../requirements-test.txt),
and Vivado 2025.2 for FPGA builds. Portable RTL tests use Icarus Verilog or
Verilator; cocotb uses the project-local environment:

```bash
python3 -m venv .venv-sim
.venv-sim/bin/python -m pip install -r requirements-test.txt
.venv-sim/bin/python -m pytest tests -q
```

The Python tests cover vocabulary/image integrity, Unicode profiles, trie
generation, and runtime allocation. Native reference generation can require
the complete tokenizer vocabulary to be available in the tokenizer cache.
Generated fixtures, logs, snapshots, and evidence belong under `build/`.

## Active scripts

| Workflow | Entry points |
| --- | --- |
| Portable SV regression suites | [`run_wsl_tests.ps1`](../scripts/run_wsl_tests.ps1), [`run_wsl_sv_tests.py`](../scripts/run_wsl_sv_tests.py) |
| Cocotb integration and immutable snapshots | [`run_cocotb.py`](../scripts/run_cocotb.py), [`run_cocotb_snapshot.py`](../scripts/run_cocotb_snapshot.py), and the `run_cocotb_*.ps1` launchers |
| Full raw RPC/cancellation/credit regressions | [`run_raw_envelope_tests.py`](../scripts/run_raw_envelope_tests.py) |
| Native component and Python tests | [`run_all_tests.ps1`](../scripts/run_all_tests.ps1) |
| Registered-neighbor implementation | [`run_registered_subsystem_implementation.ps1`](../scripts/run_registered_subsystem_implementation.ps1), [`implement_registered_subsystem.tcl`](../scripts/implement_registered_subsystem.tcl) |
| Separate-device assembly and projects | [`generate_dual_fpga_hyperram_integration.py`](../tools/generate_dual_fpga_hyperram_integration.py), [`create_dual_fpga_source_projects.py`](../tools/create_dual_fpga_source_projects.py) |
| Models and memory allocation | [`vocabulary_image.py`](../tools/vocabulary_image.py), [`external_memory_image.py`](../tools/external_memory_image.py), [`runtime_memory_plan.py`](../tools/runtime_memory_plan.py), [`tokenizer_programming.py`](../tools/tokenizer_programming.py) |

The [architecture guide](architecture.md#datapaths) identifies the maintained
RTL roots. Keep fixture generators, `verify_*.py` oracles, formal checks, and
experiment generators with the workflows they support: several generators read
earlier RTL variants as transformation inputs. Forward BPE and Unicode coverage
uses the maintained `external_merge`, `pretokenizer`, `tokenizer`, and
`tokenizer_subsystem` suites rather than the retired on-chip demo benches.

Source collectors discover RTL recursively. Frozen experiments retain their
flat logical `rtl/<module>.v` names; [`rtl_paths.py`](../tools/rtl_paths.py)
resolves those names against either the maintained hierarchy or a frozen bundle.
This keeps existing source manifests and isolated RTL overrides usable.

## Linux RTL tests

The suite list and exact compile inputs are maintained in
[`run_wsl_sv_tests.py`](../scripts/run_wsl_sv_tests.py). For example:

```bash
python3 scripts/run_wsl_sv_tests.py ram --simulator iverilog
python3 scripts/run_wsl_sv_tests.py packager
```

Most larger suites require generated fixtures. Their generators and expected
output paths are listed in [`run_wsl_tests.ps1`](../scripts/run_wsl_tests.ps1).
Generate those inputs before invoking the Linux runner directly; the Windows
launcher handles generation and synchronization.

| Area | Suite names |
| --- | --- |
| Tokenizer | `splitter`, `pretokenizer`, `trie`, `external_merge`, `tokenizer`, `tokenizer_subsystem`, `tokenizer_bulk` |
| Application parsing | `schema`, `decoder`, `grpc_application`, `message_replay` |
| HPACK | `huffman`, `hpack_integer`, `hpack_table`, `hpack_static`, `hpack_string`, `hpack_headers` |
| HTTP/2 | `http2_frames`, `http2_connections`, `http2_transport`, `http2_hpack`, `http2_names`, `http2_requests`, `http2_routes`, `http2_admission`, `http2_prefill` |
| gRPC ownership | `grpc_messages`, `grpc_streams`, `grpc_descriptors`, `grpc_engine`, `grpc_parser`, `grpc_prefill` |
| Serialization | `serializer`, `utf8_chunks` |

The default Linux memory backend defines `PARSER_PORTABLE_SIM`. It models the
used no-ECC RAM/FIFO behavior, including retention, latency, ordering, and
quiesced writes. It does not qualify unused ECC/sleep/collision behavior,
vendor reset-busy timing, analog CDC, or board interfaces. Synthesis must retain
native XPM; a guard rejects accidental synthesis of the portable backend.

## Windows and WSL

Create the Windows fixture environment from the repository root:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements-test.txt
.\scripts\run_wsl_tests.ps1
.\scripts\run_wsl_tests.ps1 -Suites http2_prefill
.\scripts\run_cocotb_tests.ps1 -Suite mmio
.\scripts\run_cocotb_tests.ps1 -Suite mmio_system
```

The default SV suites cover RAM, packager, pretokenizer, trie, external BPE,
forward tokenization, and the shared bidirectional subsystem. Other examples:

```powershell
.\scripts\run_wsl_tests.ps1 -Suites external_merge,tokenizer,tokenizer_subsystem
.\scripts\run_wsl_tests.ps1 -Suites grpc_messages,message_replay,grpc_application,decoder
.\scripts\run_cocotb_generated_response.ps1
.\scripts\run_cocotb_rpc_response.ps1
.\scripts\run_cocotb_bidirectional.ps1
.\scripts\run_cocotb_two_fpga.ps1
```

Launchers use `.venv312` for native references and copy source/data into
`~/development/hardware/parser` in WSL. Create `.venv-sim` there separately for
cocotb. Synchronization excludes Git metadata, virtual environments, and
generated Windows executables. A hash manifest refuses to overwrite independent
WSL edits. Reports are copied to `build/wsl-reports/` with input provenance.
Workspace sync preserves the RTL hierarchy. Previously synced flat RTL copies
are removed only after their new copies succeed and their old contents still
match the sync manifest. Independent edits on either path stop synchronization.

The runner rechecks source/fixture hashes after execution and rejects a run
whose inputs changed even if its simulator printed PASS. Do not replace or
synchronize a running fixture. Keep baseline and experimental evidence bound
to their own exact inputs.

The full vendor-model WSL workload uses a separately qualified Verilator
build with a local whole-array release fix. Its recorded two-state result is
distinct from the ordinary portable tests and native four-state XSim. See
[status](status.md); a default installed Verilator is not an interchangeable
substitute for that qualified compiler.

## Vivado projects

From PowerShell:

```powershell
& 'C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch -source create_parser.tcl
.\scripts\run_project_simulation.ps1
```

[`create_parser.tcl`](../create_parser.tcl) opens or creates `Parser/Parser.xpr`,
preserves an existing part/board selection, and uses `proto_json_decoder` as
the temporary application top and `tb_decoder` as the simulation top. A new
project defaults to SCU35. This is the application-decoder baseline, not the
complete separate-device physical system.

`Parser/` is a local workspace excluded from version control. Project-based
simulation and registered implementation scripts recreate a missing project
through `create_parser.tcl`; existing saved part/board selections are preserved.

Local packaged projects and board files live under ignored `FPGA/`. The
[`source-project builder`](../tools/create_dual_fpga_source_projects.py)
can create separate projects from a previously verified native elaboration
snapshot under `build/validation/`; those generated inputs are prerequisites
and are not distributed with a source checkout. Maintained source is in `rtl/`.
Existing packaged projects may represent an older qualified snapshot than the
latest experiment.

Use new run names for implementation experiments and retain source digests,
constraints, part, clock domains, setup/hold reports, and CDC findings.
Register-neighbor harness results exclude package paths. Only the final source
composition with its complete constraints can qualify the final system.

## Vivado administrator review

Some Windows invocations have been blocked by Code Integrity event 3077,
including generated `xsimk.exe` kernels and the Vivado 2025.2
`lib/win64.o/veam/kintexuplus/kintexuplus.dll` device library. Successful later
GUI builds do not establish that security policy changed or that every future
binary will be allowed.

For the original DLL incident, the review scope is one exact installed
file/version, subject to administrator/vendor validation. The recorded file
was 102,289,920 bytes, reported `NotSigned`, and had SHA-256:

```text
E03157AC794784EA065C7BA067438C242DF2733015062933F8945D6A437A9692
```

The blocking policy was Windows-managed `VerifiedAndReputableDesktop`, GUID
`{0283ac0f-fff1-49ae-ada1-8a933130cad6}`. Recollect current file/event data
before treating an incident as the same case. Code Integrity's `SHA256 Hash`
and plain-file `SHA256 Flat Hash` are separate fields.

[`prepare_vivado_admin_review.ps1`](../scripts/prepare_vivado_admin_review.ps1)
collects current diagnostics and this guide in a local package. It verifies
the matching library hash and policy and refuses to overwrite an existing
package. It does not deploy policy or change security settings. Its inputs
include the original build/crash logs, so it is an incident helper, not a
prerequisite for ordinary simulation.

An administrator should verify the AMD installation and seek a compatible
signed vendor update or supported managed application-control arrangement.
Windows-managed Smart App Control cannot be assumed to accept an enterprise
per-file supplemental-policy exception. Review artifacts are not deployment
approval. After an approved remedy, rerun the actual affected build under a
new name and check its checkpoint, reports, completion markers, and current
Code Integrity events. Linux RTL work can continue while this is reviewed.

References: [Windows-managed policies](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/inbox-appcontrol-policies),
[Smart App Control](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview).
