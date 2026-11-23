"""Bind HyperBus word-level checks to executed sources and independent traces."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    cases = {}
    frequencies = (85000000, 104000000, 133000000, 166000000, 200000000)
    names = [f'ca_latency_masks_{hz}_even_clock' for hz in frequencies]
    names.append('axi_to_hyperbus_words_initial')
    for index, name in enumerate(names):
        archive = root / 'build/wsl-reports' / ('hyperram_engine_' + name)
        read = lambda n: json.loads((archive / n).read_text())
        inputs, report, state, accepted = (read(n) for n in
            ('inputs.json', 'report.json', 'snapshot.json', 'acceptance.json'))
        assert state['exit_code'] == 0 and report['phase'] == accepted['phase'] == 'passed'
        assert report['input_sha256'] == inputs
        assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
        for path, digest in inputs.items():
            assert sha(archive / 'execution-sources' / path) == digest
            # The original integration run predates the driver's clock-profile option.
            if index < 5 or path != 'scripts/run_hyperram_engine_tests.py':
                assert sha(root / path) == digest, path
        xml = ET.parse(archive / 'results.xml')
        assert len(xml.findall('.//testcase')) == 1
        assert not xml.findall('.//failure') and not xml.findall('.//error')
        assert accepted['full_image_sha256'] == inputs['build/scu35/image/external_memory.bin']
        trace = read('hyperbus_trace.json')
        assert len(trace) == accepted['hyperbus_word_transactions']
        for txn in trace:
            ca = int(txn['ca_hex'], 16)
            assert txn['ca_words'] == [(ca >> shift) & 65535 for shift in (32, 16, 0)]
            assert ca >> 47 == int(not txn['write'])
            assert (ca >> 46) & 1 == int(txn['register'])
            assert (ca >> 45) & 1
            assert (((ca >> 16) & ((1 << 19) - 1)) << 4 | (ca & 7) << 1) == txn['address']
            assert txn['cs_cycles'] <= (frequencies[index] if index < 5 else 200000000) // 1000000 * 9 // 10
            assert all(0 <= mask <= 3 for mask in txn['write_masks'])
        if index < 5:
            hz = frequencies[index]
            assert [accepted[n] for n in ('accepted_requests', 'hyperbus_word_transactions',
                'rejected_requests', 'actual_partial_write_words')] == [117, 107, 10, 4]
            assert accepted['configured_clock_hz'] == hz
            assert accepted['minimum_latency_tested'] == index + 3
            assert accepted['simulated_clock_period_ps'] % 2 == 0
            assert accepted['simulated_clock_period_ps'] * hz >= 10**12
            assert accepted['actual_timeout_cs_cycles'] == hz // 1000000 * 9 // 10
            assert accepted['variable_latency_transactions'] == 48
            assert accepted['extended_latency_transactions'] >= 48
        else:
            assert [accepted[n] for n in ('axi_reads', 'axi_writes', 'hyperbus_word_transactions',
                'rejected_axi_requests', 'simultaneous_read_write_rounds')] == [156, 89, 230, 15, 17]
            assert accepted['actual_axi_and_hyperbus_modules_connected']
        for flag in ('pin_level_ddr_phy_verified', 'rwds_cdc_verified',
                     'device_initialization_manager_verified', 'native_timing_verified', 'full_system_complete'):
            assert accepted[flag] is False
        cases[name] = dict(acceptance=accepted, input_sha256=inputs,
            archive_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()})
    structural = root / 'build/validation/hyperram-engine-structural.log'
    assert 'Found and reported 0 problems.' in structural.read_text()
    assert 'ERROR:' not in structural.read_text()
    generation = json.loads((root / 'build/hyperram-engine/fixture-generation.json').read_text())
    assert generation['generator_sha256'] == sha(root / 'tools/generate_axi_hyperram_engine_fixture.py')
    assert generation['fixture_sha256'] == sha(root / 'sim/cocotb_axi_hyperram_engine_top.sv')
    assert generation['port_parser_sha256'] == sha(root / 'tools/generate_bidirectional_application.py')
    assert all(sha(root / p) == digest for p, digest in generation['input_sha256'].items())
    result = dict(phase='hyperram_word_engine_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        cases=cases, structural_log_sha256=sha(structural), fixture_generation=generation,
        manufacturer_pdf_sha256=sha(root / 'tmp/pdfs/infineon-s27ks0642.pdf'),
        pin_level_ddr_phy_verified=False, rwds_cdc_verified=False,
        device_initialization_manager_verified=False, native_timing_verified=False,
        application_instantiation_verified=False, full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    (root / 'build/validation/hyperram-word-engine.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=result['key'], clock_profiles=5,
                         integrated_axi_transactions=245)))


if __name__ == '__main__':
    main()
