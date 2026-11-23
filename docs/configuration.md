# Configuration

[README](../README.md) · [Architecture](architecture.md) · [Development](development.md) · [Status](status.md)

## Build complete model images

Run with the Python environment from the [development guide](development.md):

```bash
.venv-sim/bin/python tools/vocabulary_image.py --tiktoken cl100k_base --output build/vocab/cl100k_base
.venv-sim/bin/python tools/generate_unicode_vectors.py --output build/unicode
.venv-sim/bin/python tools/external_memory_image.py --vocabulary build/vocab/cl100k_base --unicode build/unicode --output build/scu35/image
```

For a deterministic HuggingFace ByteLevel BPE model, replace the vocabulary
command with:

```bash
.venv-sim/bin/python tools/vocabulary_image.py --huggingface tokenizer.json --output build/vocab/custom
```

Use that output directory when assembling the external image. Unsupported
normalizers, added-token matching profiles, incompatible regexes, or capacity
overflow are explicit errors. Images are runtime programming data, not fixed
HDL vocabulary ROMs. Never truncate a model to make it fit.

The compiler validates checksums, directory bounds/flags, all base-byte tokens,
merge consistency and hash reachability, and the complete ordinary-token trie.
The generated manifest is authoritative for the selected model's region sizes.

## Image and working-memory layout

Binary model fields are little endian. The reference complete cl100k image uses
this 8 MiB layout; other models must use their generated manifest:

| Region | Byte address range |
| --- | --- |
| Inverse directory | `0x000000..0x0fffff` |
| String pool reserved capacity | `0x100000..0x1fffff` |
| Packed merge hash | `0x200000..0x43ffff` |
| Packed Unicode classes | `0x440000..0x483fff` |
| Byte vocabulary | `0x484000..0x4843ff` |
| Six-byte trie nodes | `0x484400..0x5c1c13` |
| Four-byte trie edges | `0x5c1c40..0x6956f3` |
| Working allocation | `0x695700..0x7fffff` |

Directory entries are 64-bit words: length `[63:48]`, 32-bit string-pool byte
offset `[47:16]`, valid bit 1, special/control bit 0, other flag bits zero.
The byte vocabulary has 256 32-bit IDs. With default 17-bit IDs/ranks, each
nine-byte merge slot contains left `[16:0]`, right `[33:17]`, result `[50:34]`,
rank `[67:51]`, and valid bit 68. Hash probing compares complete IDs.

The remaining 1,485,056 bytes must cover tokenizer and transport work without
overlap. A standalone one-sequence example reserves 524,288 bytes each for
scalar and merge records at `0x695700`/`0x715700`, and 436,480 bytes for staged
token IDs at `0x795700`. This example is not a joint transport allocation.
Merge nodes store a 32-bit token and a 32-bit next index; `0xffffffff` ends
the list. Working regions must lie above the protected model floor.

[`runtime_memory_plan.py`](../tools/runtime_memory_plan.py) validates image
hashes and allocates disjoint transport/tokenizer regions. Limits are explicit
runtime capacities, not consequences of the packet width:

```bash
.venv-sim/bin/python tools/runtime_memory_plan.py \
  --image-directory build/scu35/image --output build/scu35/runtime-plan.json \
  --connections 3 --rpc-slots 3 --rpc-payload-bytes 131072 \
  --max-text-bytes 16384 --header-block-bytes 16384 \
  --header-scratch-bytes 32768 --hpack-table-bytes 4096 --descriptor-slots 16
```

Keep `workspace_plan_verified` distinct from static layout validation. A valid
layout alone does not establish runtime leases or simultaneous-stream safety.

## Tokenizer registers

[`tokenizer_mmio`](../rtl/tokenizer/control/tokenizer_mmio.v) exposes aligned 32-bit words on a
16-bit byte address bus. AW/W are independent; B/R remain stable under stalls.
WSTRB preserves untouched bytes. Configuration writes require `cfg_unlock`
and datapath idle. Misaligned writes return SLVERR; unsupported/read-only
writes and unsupported/misaligned reads return DECERR. Invalid values fail
without changing configuration; zero-strobe writes have no effect.

| Offset | Register / meaning |
| --- | --- |
| `0x00` | Read-only ID `0x50545831` |
| `0x04` | Read-only status |
| `0x08` | Control action |
| `0x0c` | Read-only committed epoch |
| `0x10` | Tables valid, bit 0 |
| `0x14` | Read-only last downstream memory status |
| `0x18` | Memory byte address, default 23 bits |
| `0x1c` | Memory byte count, 1–9 when submitted |
| `0x20`, `0x24`, `0x28` | Payload bits `[31:0]`, `[63:32]`, `[71:64]`; other high bits zero |
| `0x2c` | Memory doorbell: write 1 |
| `0x30` | Regex profile: 0 cl100k, 1 Llama-3, 2 GPT-2 |
| `0x34`, `0x38` | Unicode class base, merge-hash base |
| `0x3c`, `0x40` | Trie node base, edge base |
| `0x44`, `0x48` | Trie node count, edge count |
| `0x4c` | Working floor: end of protected model storage |
| `0x50`, `0x54` | Scalar workspace base, byte capacity |
| `0x58`, `0x5c` | Merge workspace base, byte capacity |
| `0x60`, `0x64` | Token staging base, byte capacity |
| `0x68`, `0x6c` | Inverse directory base, string-pool base |
| `0x70` | Strip special tokens, bit 0 |
| `0x74` | Clear sticky errors: bit 0 protocol, bit 1 loader |

Status bits are: 0 unlock, 1 draining, 2 vocabulary valid, 3 datapath idle,
4 memory/invalidation busy, 5 sticky epoch protocol error, 6 sticky loader
error. Control accepts exactly one action: 1 request update, 2 commit, 4 abort,
8 invalidate cache. Invalid combinations fail. Invalid commit/abort also
record the epoch protocol error.

### Loading sequence

1. Obtain [whole-system maintenance authority](#maintenance-and-recovery).
   Write control=1 and wait for `cfg_unlock`; existing sequences, completions,
   and external-memory responses must drain.
2. Program configuration and every protected model byte. For each 1–9 byte
   payload, write address/count/data and doorbell=1. Wait for B and check its
   response. Doorbell completion waits for external-memory acknowledgment;
   nonzero memory status produces SLVERR and a sticky loader error.
3. Validate the full image, profile, checksums, bounds, and working allocation.
   Configuration/payload writes and accepted doorbells clear `tables_valid`.
   Set it only after validation and all data acknowledgments succeed.
4. Invalidate with control=8, wait for completion, then commit with control=2.
   Check vocabulary-valid and the incremented epoch before resuming traffic.
   Abort keeps traffic disabled until a complete valid load/commit.

[`tokenizer_programming.py`](../tools/tokenizer_programming.py) validates the
image and emits a host programming plan:

```bash
.venv-sim/bin/python tools/tokenizer_programming.py build/scu35/image --epoch 1 --output build/scu35/load.bin
```

`programming_plan`/`execute_plan` use `read32`/`write32` adapters. Writes must
wait for AXI-Lite B and raise on bus errors, stopping before later operations
or commit. Validate serialized plans with `read_plan` before execution. Plan
records are eight bytes, **big endian**: 16-bit operation, 16-bit CSR byte
address, 32-bit value. Operations 1/2/3 mean write/masked poll/exact read
assertion. Poll values put the mask above the wanted 16-bit value. Model
payloads in the CSRs remain little endian.

## Parser schema registers

[`parser_schema_mmio`](../rtl/parser/decoder/schema/parser_schema_mmio.v) programs the live CAM
through [`parser_schema_mmio_decoder`](../rtl/parser/decoder/schema/parser_schema_mmio_decoder.v).
The HTTP/2 integration exposes the bus as `s_axi_schema_*` in
[`http2_schema_mmio_application`](../rtl/parser/transport/http2/http2_schema_mmio_application.v).

| Offset | Register / meaning |
| --- | --- |
| `0x0000` | Read-only ID `0x50534331` |
| `0x0004` | Status: bit 0 apply busy, 1 maintenance grant, 2 idle |
| `0x0008` | Apply doorbell: write 1, reads zero |
| `0x000c` | Read-only durable row-apply epoch |
| `0x0010` | Staged index, `0..ENTRIES-1`, at most sixteen |
| `0x0014` | Staged normalized JSON key length, 0–32 bytes |
| `0x0018` | Staged enables: bit 0 JSON, 1 Protobuf; others zero |
| `0x001c` | Staged 29-bit Protobuf field number |
| `0x0020..0x003c` | Eight key words; first byte is bits `[7:0]` at `0x0020` |

Keys are normalized UTF-8, zero-padded to 32 bytes. Enabled JSON keys reject
nonzero bytes beyond the declared length; enabled Protobuf selectors require
a nonzero field number. Partial writes merge into staged values. Staging can
occur during traffic; it does not alter the live schema.

Apply validates staging, waits for the CAM handshake and all 32 key rows, then
increments the row epoch and acknowledges B. Epoch wrap rejects the apply.
Reset restores the default schema but does not recover retained RPC contexts.
Hold the maintenance grant through B; a command handshake alone is not durable
completion. Multi-entry updates require a fence through every apply and are
not an atomic whole-table commit.

The HTTP/2 wrapper additionally requires `cfg_unlock`, packet/message admission
off, and `cfg_quiescent`. Its `schema_row_epoch` differs from the host-published
`cfg_schema_epoch`. Update route metadata and publish coherent model/schema
identities before releasing admission. Route records use schema epoch bytes
16–19; bytes 24–31 are reserved zero. Use the actual
[`http2_route_lookup`](../rtl/parser/transport/http2/http2_route_lookup.v) and planner ABI when writing
records rather than deriving offsets from a row counter.

## Durable response progress

Each 128-byte RPC directory slot has a disjoint 32-byte progress record at
`progress_base + (rpc_address - stream_base) / 4`. Its four little-endian
64-bit words contain:

| Word | Fields |
| --- | --- |
| 0 | Magic `0x52535031` in `[31:0]`, generation in `[63:32]` |
| 1 | Model epoch `[31:0]`, schema epoch `[63:32]` |
| 2 | Next ordinal `[31:0]`, UTF-8 carry `[55:32]`, count `[57:56]`, closed bit 58; remaining bits zero |
| 3 | Protobuf field `[28:0]`, format `[30:29]`, replacement bit 31, strip-special bit 32; remaining bits zero |

Initialize a new generation only at ordinal zero after directory/sidecar
validation. Preserve captured policy on later tokens. Reject stale generations,
closed records, malformed carry/reserved fields, epoch mismatches, wrong
ordinals, and ordinal exhaustion. Persist by invalidating the marker, writing
words 1–3, then committing word 0, acknowledging every write. Post-wire failures
require fencing; old progress cannot authorize a retry. See
[`rpc_generated_response`](../rtl/parser/response/rpc_generated_response.v) for the implementation.

## Maintenance and recovery

This sequence is a system integration requirement; a complete automatic
cross-device coordinator remains open:

1. Fence new RPC admission and allow already accepted BEGIN operations to
   settle. Keep existing DATA, trailers, flow-control, DMA, and GPU returns
   progressing with their original image/schema identities.
2. Finish or durably cancel old calls. Obtain a fresh host/GPU fence tied to
   the old identity, covering submitted work and pending returns even when
   FPGA pipelines are idle.
3. Under directory/pool authority, retire affected RPC/recovery records and
   drain leases, payloads, both links, DMA, results, memory commands, and ACKs.
   An unlocked scan or local idle snapshot does not establish this condition.
4. Stop packet/message admission once old calls no longer need transport
   progress. Hold image/schema grants through loader validation, invalidation,
   every schema apply, route update, and all configuration responses.
5. Publish coherent identities, reject exhausted epochs/stale completions,
   then resume traffic.

Reset withdraws admission and write grants. Recover retained ownership or
revoke it through an explicit fresh host fence before restarting. An aborted
update that overwrote any old image bytes must remain fenced until a valid
coherent commit or explicit recovery; it cannot restore the old epoch by
re-enabling traffic.
