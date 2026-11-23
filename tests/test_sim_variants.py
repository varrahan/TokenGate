import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sim/cocotb'))
import test_rpc_durable_response as rpc
import window_format_witness as window


@pytest.mark.parametrize('keyed,op,expected', [(False, 2, 2), (True, 2, 9), (True, 1, 1), (True, 0, 0)])
def test_window_updates_preserve_binding_unless_lookup_is_by_key(monkeypatch, keyed, op, expected):
    bench = object.__new__(rpc.WindowedBench)
    bench.d = SimpleNamespace(window_rsp_ready=SimpleNamespace(value=0))
    bench.a = dict(stream_base=4096, stream_bytes=512, work_floor=2048)
    bench.context_base, bench.context_bytes = 8192, 4096
    bench.window_base, bench.window_bytes = 12288, 64
    bench.keyed, bench.keyed_updates = keyed, 0
    commands = []
    bench.set = lambda **fields: commands.append(fields)
    bench.send = AsyncMock()
    monkeypatch.setattr(rpc, 'cycles', AsyncMock())
    monkeypatch.setattr(rpc, 'val', lambda d, name: int(name == 'window_rsp_valid'))
    binding = dict(user=2, stream=7, generation=91, slot=3)

    asyncio.run(bench.window(op, binding, 37))

    request = commands[0]
    assert request['window_req_op'] == expected
    assert request['window_req_user'] == 2 and request['window_req_amount'] == 37
    assert request['window_req_stream'] == (0 if op == 0 else 7)
    assert request['window_req_generation'] == (0 if expected == 9 else 91)
    assert request['window_req_record_address'] == (0 if expected == 9 else 4096 + 3 * 128)
    assert bench.keyed_updates == int(expected == 9)
    bench.send.assert_awaited_once_with('window_req_valid', 'window_req_ready')


@pytest.mark.parametrize('progress_errors', [False, True])
@pytest.mark.parametrize('status,rx,tx,accepted', [
    ((0, 0, 0), [0], [0], True),
    ((0, 0, 0), [0], [], False),
    ((5, 7, 0x75), [0x75], [], True),
    ((5, 2, 0x75), [0], [0x75], True),
    ((5, 18, 0x75), [0], [0], 'progress'),
    ((5, 18, 0x75), [0], [], False),
    ((5, 18, 0x75), [0], [0x75], False),
])
def test_format_witness_keeps_ledger_fault_checks(monkeypatch, progress_errors, status, rx, tx, accepted):
    class Edge:
        def __await__(self):
            yield

    core = SimpleNamespace(reverse=SimpleNamespace(directory_service=SimpleNamespace(owned=None)))
    dut = SimpleNamespace(clk=None, dut=SimpleNamespace(core=core))
    signals = dict(zip(window.WindowFormatWitness.fields, (*status, 4, 0, 0, 0, 0)))
    signals.update(control_result_valid=1, control_result_ready=1)
    monkeypatch.setattr(window, 'RisingEdge', lambda clk: Edge())
    monkeypatch.setattr(window, 'value', lambda owner, name: signals.get(name, 0))
    witness = window.WindowFormatWitness(dut, progress_errors=progress_errors)
    witness.active = dict(acks={'26': [dict(status=s) for s in rx], '22': [dict(status=s) for s in tx]},
                          sizes={'26': 8, '22': 8}, commands={'26': list(rx), '22': list(tx)}, held_public_cycles=0)
    observer = witness.observe()
    observer.send(None)
    try:
        if accepted is True or (accepted == 'progress' and progress_errors):
            observer.send(None)
            assert witness.result()[0]['result'][:3] == status
        else:
            with pytest.raises(AssertionError):
                observer.send(None)
    finally:
        observer.close()
