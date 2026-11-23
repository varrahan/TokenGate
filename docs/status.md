# Implementation status

[README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Development](development.md)

Recorded results as of 2026-11-22. These are existing verification records,
not new runs performed during the documentation cleanup. Results apply to
their exact source/model/tool snapshots; separate experiment passes do not
qualify an untested composition. The complete system remains under implementation.

## Functional evidence

| Area | Recorded result | Local evidence / audit |
| --- | --- | --- |
| Raw HTTP/2/gRPC round trip | Sixteen complete calls, 2,828 actual forward DMA IDs fed through inverse lookup, and native response-byte comparisons | `build/validation/raw-enveloped-parser.json` |
| Separate Parser/Tokenizer with HyperRAM | Two complete 8 MiB model programs/readbacks, 32 calls, 11,091 actual DMA/GPU returns, 11,193 wire frames | `build/validation/dual-fpga-hyperram.json`; `2e24ad59fccef5f2` |
| Schema programming | Full native 77/31-module workload, actual AXI-Lite schema applies and route-epoch updates, all 32 calls | `292670e03a24501d` |
| Composed schema/frame/owner revision | Complete native two-image workload with all calls, DMA returns, frames, and configuration events | `3072016f57de6d32` |
| Capacity-backed receive credits | Resolves the legal 64 KiB single-message deadlock; interleaved partial messages and slot reuse pass | `1116ddc2e15eedbf` |
| Payload reclamation | Nine- and 21-message workloads, complete corpus, lifecycle/extended suites, and all 99 actual-backend ACK faults | `a1a0c92139811b39`; `954daaa0ea84129c` |
| Capacity FORMAT arbitration | Directed owner test, all seven lifecycle/five extended suites, 42 initial-grant faults, three large workloads, and complete corpus | `2ad2339cea44fec0`; `1ed454ad98c4122f`; `5c25325d35ca3718` |
| Combined 79/31-module vendor-model workload in WSL | Both images, all 32 calls, 11,091 returns and 11,193 frames using unchanged vendor models and a qualified simulator fix | Two-state execution; `8fb8ae00b3a15fbc` |
| Stream-local refusal V7 | Preserves old RPCs, passes directed traffic and all 46 physical refused-DATA ACK faults; full controller workload passes | `12513e8bd9c65f5d`; two-state workload `87ec8e2e97954f2e` |
| Refusal/GPU concurrency | Both actual wire orders and five closed-history policy cases pass | `ccb78082e6e7fae1`; `739d5b1f6e49fc75` |

Native XSim runtime for some newer combined snapshots remains blocked by
Windows Code Integrity. Compilation/elaboration alone is not a runtime pass.
Earlier native workloads, portable-memory tests, and the newer two-state
vendor-model workloads retain separate scopes.

An earlier admission-fence-only experiment closed an existing partial RPC
when refusing a new stream (`d246ef849f723296`). The later stream-local refusal
work addresses that case; the old fence alone is not a safe maintenance path.
Default-open equivalence does not cover dynamic refusal or retained recovery.

## Timing and device evidence

| Snapshot | Target / scope | Recorded timing |
| --- | --- | --- |
| Tokenizer/cache/HyperRAM, pipelined rank and capacity | SCU35, 250/200 MHz core harness | Setup `+0.030 ns`, hold `+0.011 ns`; audit `344c37158dba0b39` |
| Shared-reset controller assembly | SCU35 isolated 250/200 MHz domains | Setup `+0.434 ns`, hold `+0.013 ns`, zero critical CDC findings; audit `8eac375d696056ed` |
| Eight-byte JSON decoder | AU15P component | Setup `+0.344 ns`, hold `+0.011 ns`; full Parser timing remains separate |
| Registered response success predicate | AU15P 77-module candidate | Setup `-1.026 ns`, hold `+0.010 ns`; audit `8c907c792fcd8218` |
| Refusal V7 | AU15P 78-module non-MMIO harness | Setup `-2.755 ns`, hold `+0.007 ns`; audit `8a31f4604e3ce120` |
| Registered frame selection | AU15P non-MMIO harness, 53,982 LUTs, 47,249 registers, 54.5 BRAM tiles | Setup `-2.412 ns`, hold `+0.011 ns`; audit `08b68b7637c13024` |

The listed Parser candidates fit AU15P but miss the 4 ns setup target. Different
module compositions explain why these results are not one comparable timing
series. They exclude package paths and do not qualify final MMIO, memory,
PCIe, or board-link integration.

The receive payload-address pipeline has source/settling qualification
`15296e49232b3409`, based on a reachable consumption-state lemma and a
sole-consumer source certificate. It is not a passing direct all-output miter.
Its native build and application tests were still running in the recorded
snapshot; no completed timing result is claimed here.

SCU35 board selection passes audit `9bb9c281cb8e2936` against pinned official
files. This establishes software metadata selection, not physical pin/PHY
timing or hardware measurements. No physical boards are available.

## Remaining work

- Close 250 MHz timing on the final Parser composition and repeat complete
  functional, fault, reset, and CDC qualification on the exact final pair.
- Finish the receive/error/cancellation/lifecycle matrix, including retained
  arenas, uncertain writes, concurrent GPU faults, and dynamic refusal/reset.
- Implement distributed whole-RPC/GPU/model/schema maintenance and retained
  recovery. Existing local idle proofs and host-supplied test fences are not
  production update authority.
- Complete the HTTP/1.1/SSE endpoint and configurable response templates;
  application JSON/SSE serialization does not establish a complete SSE endpoint.
- Complete PCIe/QDMA adapters, queue/context routing, host programming,
  physical inter-FPGA link, board clocks/pins, and DDR/RWDS memory PHY. Digital
  controller models and captured DMA IDs do not establish physical GPU DMA.
- Measure sustained throughput, latency, and concurrent-stream scheduling.
  Iterative BPE and scalar conversion paths remain performance constraints.

## Reading verification records

`tools/verify_*.py` contains the independent checks; generated inputs, logs,
source digests, reports, and immutable evidence live locally under `build/`.
They are not included in a source checkout. Audit IDs identify recorded
snapshots and do not by themselves revalidate current files.

Retain the selected part, source/model/tool hashes, memory backend, clocks,
excluded paths, and test boundary when reporting a result. A unit pass does
not establish full HTTP/2 compliance, complete tokenizer-profile support,
measured performance, or final timing closure.
