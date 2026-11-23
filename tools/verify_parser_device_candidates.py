"""Record installed part metadata and the limited AU15P license probe."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'build/parser-candidates'
    metadata = (folder / 'xcau15p-properties.txt').read_text()
    expected = dict(NAME='xcau15p-ffvb676-2-e', FAMILY='artixuplus',
                    LUT_ELEMENTS='77760', FLIPFLOPS='155520', BLOCK_RAMS='144',
                    DSP='576', GTHE4_TRANSCEIVERS='12', PCI_BUSES='1')
    for name, value in expected.items():
        found = re.search(rf'^{name}\s+\S+\s+true\s+(\S+)', metadata, re.M)
        assert found and found[1] == value, (name, value)
    probe = json.loads((folder / 'xcau15p-license-probe.json').read_text())
    assert probe['part'] == expected['NAME'] and probe['tiny_synthesis_phase'] == 'passed'
    assert not probe['parser_fit_verified'] and not probe['project_target_changed']
    log = root / 'build/parser-candidate-license-quoted.log'
    log_text = log.read_text()
    assert 'PARSER_CANDIDATE_LICENSE_PROBE=passed PART=xcau15p-ffvb676-2-e' in log_text
    assert '0 Critical Warnings and 0 Errors encountered.' in log_text
    files = [folder / name for name in ('xcau15p-properties.txt', 'xcau20p-properties.txt',
                                        'xcau15p-license-probe.json', 'parser_license_probe.v')]
    files += [root / 'scripts/inspect_parser_candidates.tcl',
              root / 'scripts/probe_parser_candidate_license.tcl', log, Path(__file__).resolve()]
    result = dict(phase='tool_metadata_and_tiny_license_probe_verified',
                  verified_utc=datetime.now(timezone.utc).isoformat(),
                  parser_candidate=expected, license_probe=probe,
                  source_sha256={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in files},
                  user_approved_larger_parser=True, tokenizer_baseline='xcsu35p-sbvb625-2-e',
                  parser_part_selected=False, parser_standalone_synthesis_verified=False,
                  parser_fit_verified=False, physical_link_verified=False,
                  project_target_changed=False, full_system_complete=False)
    output = root / 'build/validation/parser-device-candidates.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
