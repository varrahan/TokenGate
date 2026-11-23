"""Bind native four-state memory tests to frozen RTL and routed CDC findings.

This is a scoped word-interface proof. It deliberately retains the two reset
fan-out findings and does not promote the experimental FIFO into primary RTL.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def clean_log(path):
    text = path.read_text(errors='replace')
    assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):', text, re.M), path
    return text


def main():
    assembly = ROOT/'build/validation/hyperram_async_windows_full_image_wide_timeout'
    profiles = ROOT/'build/validation/hyperram_cdc_windows_qualified_profiles'
    native = ROOT/'build/implementation/xcsu35p-sbvb625-2-e/hyperram_clock_bridge_250_200_qualified_reset'
    qualified = ROOT/'build/experiments/hyperram-cdc-qualified-reset'
    syntax = read(assembly/'report.json')
    elaboration = read(assembly/'elaboration-report.json')
    run = read(assembly/'simulation-full_image-report.json')
    clocks = read(profiles/'report.json')
    finding_path = ROOT/'build/validation/hyperram_clock_bridge_250_200_qualified_reset-findings.json'
    finding = read(finding_path)
    provenance = read(native/'source-provenance.json')
    artifacts = set()

    def pin(path, digest):
        assert sha(path) == digest, path
        artifacts.add(path)

    assert syntax['phase'] == 'syntax_compilation_passed' and syntax['exit_code'] == 0
    assert elaboration['elaboration_verified'] and elaboration['exit_code'] == 0
    assert run['phase'] == 'native_full_image_async_memory_passed' and run['simulation_passed']
    assert run['exit_code'] == 0 and not run['runtime_options_changed_for_security']
    assert run['input_sha256'] == syntax['inputs_sha256'] and len(syntax['inputs_sha256']) == 12
    assert clocks['phase'] == 'native_four_state_clock_profiles_passed' and clocks['passed']
    assert not clocks['native_cdc_signoff_verified']
    for report in (run, clocks):
        assert not report['vendor_sva_enabled']
    assert run['independent_testbench_assertions_enabled'] and clocks['independent_assertions_enabled']
    assert syntax['vendor_compatibility_defines'] == clocks['compatibility_defines'] == ['OBSOLETE']
    for folder, inputs in ((assembly, syntax['inputs_sha256']), (profiles, clocks['inputs_sha256'])):
        for name, digest in inputs.items():
            pin(folder/'sources'/name, digest)
            if name.startswith(('rtl/', 'sim/')):
                current = qualified/name if name == 'rtl/cdc_packet_fifo.v' else ROOT/name
                pin(current, digest)
            elif name.startswith('vendor/xpm_'):
                macro = Path(name).stem
                pin(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/macro/'hdl'/(macro+'.sv'), digest)
    for name, record in provenance['files'].items():
        pin(native/'sources'/name, record['sha256'])
    for name in ('rtl/cdc_packet_fifo.v', 'rtl/hyperram_clock_bridge.v'):
        assert syntax['inputs_sha256'][name] == clocks['inputs_sha256'][name] == provenance['files'][name]['sha256']
    glbl = Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v')
    pin(glbl, elaboration['glbl_sha256'])
    pin(assembly/'sources/vendor/glbl.v', elaboration['glbl_sha256'])
    for name, digest in run['snapshot_files_sha256'].items():
        pin(assembly/name, digest)
    for name, digest in finding['artifacts_sha256'].items():
        pin(native/name, digest)
    drivers = [('tools/check_async_hyperram_windows.py', syntax, assembly/'check_async_hyperram_windows.py'),
               ('tools/elaborate_async_hyperram_windows.py', elaboration, assembly/'elaborate_async_hyperram_windows.py'),
               ('tools/run_async_hyperram_windows.py', run, assembly/'run_async_hyperram_windows-full_image.py'),
               ('tools/run_hyperram_cdc_windows.py', clocks, profiles/'run_hyperram_cdc_windows.py')]
    for name, report, frozen in drivers:
        pin(ROOT/name, report['driver_sha256'])
        pin(frozen, report['driver_sha256'])
    assert 'xpm_source' in elaboration['commands'][-1] and 'xpm' not in elaboration['commands'][-1]
    assert 'work.glbl' in elaboration['commands'][-1]
    assert '--nosignalhandlers' not in run['windows_command_line']

    # Re-execute generators in an isolated miniature workspace. No primary
    # sources or historical evidence are overwritten by this reproducibility check.
    generators = ('generate_hyperram_cdc_timing_harness', 'generate_async_hyperram_controller',
                  'generate_hyperram_async_testbench', 'generate_hyperram_cdc_qualified_reset')
    with tempfile.TemporaryDirectory(prefix='hyperram-async-replay-') as temporary:
        replay = Path(temporary)
        for name in generators:
            path = ROOT/'tools'/(name+'.py'); target = replay/'tools'/path.name
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target); artifacts.add(path)
        for name in list(syntax['inputs_sha256']) + ['rtl/cdc_packet_fifo.v']:
            if not name.startswith(('rtl/', 'sim/')):
                continue
            source = ROOT/name; target = replay/name
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        for name in generators[1:]:
            subprocess.run([sys.executable, str(replay/'tools'/(name+'.py'))], check=True, capture_output=True)
        for name in ('rtl/hyperram_word_backend.v', 'rtl/axi_hyperram_async_controller.v', 'sim/tb_axi_hyperram_async.sv'):
            assert sha(replay/name) == syntax['inputs_sha256'][name], name
        assert sha(replay/'build/experiments/hyperram-cdc-qualified-reset/rtl/cdc_packet_fifo.v') == syntax['inputs_sha256']['rtl/cdc_packet_fifo.v']

    digest = 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    pin(assembly/'image.bin', digest)
    pin(ROOT/'build/scu35/image/external_memory.bin', digest)
    assert (assembly/'image.bin').stat().st_size == 8388608 and run['image_sha256'] == digest
    expected = dict(image_bytes=8388608, full_writes=131072, full_reads=131072,
                    axi_writes=131073, axi_reads=131078, reset_epochs=2, timeout_status=2, partial_write_words=4)
    assert run['acceptance'] == expected
    for name in ('simulator-output-full_image.log', 'xsim-full_image.log'):
        path = assembly/name; text = clean_log(path); artifacts.add(path)
        lines = re.findall(r'^ASYNC_HYPERRAM_PASS (.+)$', text, re.M); assert len(lines) == 1
        assert {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', lines[0])} == expected
        for phase in ('WRITE', 'READ'):
            assert [int(n) for n in re.findall(r'^ASYNC_'+phase+r'_PROGRESS bytes=(\d+)', text, re.M)] == list(range(1048576,8388609,1048576))
    total = 0
    for label, values in clocks['profiles'].items():
        assert values['epochs'] == 4 and values['completed'] >= 3000
        assert values['source_holds'] >= 50 and values['response_holds'] >= 50
        total += values['completed']
        for name in (label+'.log', 'xsim-'+label+'.log'):
            path = profiles/name; text = clean_log(path); artifacts.add(path)
            line = re.findall(r'^CDC_TEST_PASS (.+)$', text, re.M); assert len(line) == 1
            assert {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line[0])} == values
    assert len(clocks['profiles']) == 4 and total == 12115
    for folder in (assembly, profiles):
        for path in folder.glob('*.log'):
            clean_log(path); artifacts.add(path)

    assert finding['timing_met'] and finding['setup_slack_ns'] == .552 and finding['hold_slack_ns'] == .012
    assert finding['cdc_counts']['CDC-11']['count'] == 2 and not finding['cdc_signoff_verified']
    assert not any(code in finding['cdc_counts'] for code in ('CDC-1','CDC-7','CDC-10','CDC-13'))
    script = (native/'sources/scripts/implement_hyperram_clock_bridge.tcl').read_text()
    assert script.count('set_false_path') == 2 and 'set_clock_groups' not in script and 'create_waiver' not in script
    body = (assembly/'sources/sim/hyperram_async_test_body.svh').read_text()
    # Model and host compare all bytes, with no command-level substitute for the
    # real engine. Internal diagnostic hierarchy is limited to startup tracing.
    assert body.count('addr<8388608;addr+=64') == 2
    assert 'i<8388608;i++)assert(device_memory[i]==image[i])' in body
    for required in ('Reload/new-address priority', 'Held reload completion/fence', 'Timeout detail lost across CDC',
                     'Partial write detail lost across CDC', 'Stale response after shared reset', 'Reset retained a valid-image claim'):
        assert required in body
    for path in (assembly/'report.json', assembly/'elaboration-report.json', assembly/'simulation-full_image-report.json',
                 profiles/'report.json', finding_path, qualified/'generation.json',
                 ROOT/'build/hyperram-async/generation.json', ROOT/'build/hyperram-async/testbench-generation.json', Path(__file__)):
        artifacts.add(path)
    result = dict(phase='native_async_hyperram_full_image_and_clock_profiles_verified',
                  verified_utc=datetime.now(timezone.utc).isoformat(), acceptance=expected,
                  clock_profiles=clocks['profiles'], completed_clock_test_responses=total,
                  image_sha256=digest, inputs_sha256=syntax['inputs_sha256'], generator_replay_verified=True,
                  vendor_sources_unmodified=True, vendor_sva_enabled=False, independent_assertions_enabled=True,
                  word_interface_assembly_verified=True, isolated_clock_bridge_timing=finding,
                  primary_fifo_modified=False, cdc_signoff_verified=False, open_reset_fanout_findings=2,
                  full_assembly_native_timing_verified=False, tokenizer_instantiation_verified=False,
                  pin_level_ddr_phy_verified=False, rwds_cdc_verified=False, whole_model_epoch_commit_verified=False,
                  full_system_complete=False, artifacts_sha256={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(artifacts)})
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = ROOT/'build/validation/hyperram-async-native-evidence'/result['key']; evidence.mkdir(parents=True, exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result, indent=2)+'\n')
    shutil.copy2(Path(__file__), evidence/Path(__file__).name)
    (ROOT/'build/validation/hyperram-async-native.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','acceptance','completed_clock_test_responses','open_reset_fanout_findings')}))


if __name__ == '__main__':
    main()
