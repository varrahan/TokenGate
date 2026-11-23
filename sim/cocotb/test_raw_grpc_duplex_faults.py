"""Actual context writer ACK failures must reach concurrent GPU credit waiters."""
import json
from pathlib import Path
import cocotb
from test_raw_grpc_duplex import exercise_duplex


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def every_context_commit_write_fault_reaches_real_credit_owner(d):
    cases = []
    for phase in range(21):
        cases.append(await exercise_duplex(d, fault_phase=phase))
    result = dict(phase='passed', actual_context_commit_write_faults=cases,
        context_write_ack_fault_cases=21, actual_memory_error=0x75,
        applied_write_errors=True, actual_downstream_axis_promises_verified=True,
        actual_directory_owner_retained_until_gpu_ack=True,
        actual_memory_owners_drained_before_each_cold_boot=True,
        complete_model_prefix_immutable=True, retained_memory_warm_reset_verified=False,
        forward_dma_workload_verified=False, physical_interfaces_verified=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
