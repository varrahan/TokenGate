from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = [
    'validate_project_simulation.tcl',
    'implement_registered_parser.tcl',
    'implement_registered_tokenizer.tcl',
    'implement_registered_subsystem.tcl',
]


@pytest.mark.skipif(shutil.which('tclsh') is None, reason='Tcl interpreter unavailable')
@pytest.mark.parametrize('entry', ENTRY_POINTS)
@pytest.mark.parametrize('state', ['missing', 'existing', 'creation_failure'])
def test_project_entry_points_create_missing_projects_and_preserve_existing_ones(tmp_path, entry, state):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in (entry, 'rtl_sources.tcl'):
        shutil.copy2(ROOT / 'scripts' / name, scripts / name)
    project = tmp_path / 'Parser/Parser.xpr'
    original = b'<Project><Option Name="Part" Val="xcau15p-ffvb676-2-e"/></Project>\n'
    if state == 'existing':
        project.parent.mkdir()
        project.write_bytes(original)
    creator = '''
set marker [open [file join [file dirname [info script]] creation_called] w]
close $marker
'''
    if state == 'creation_failure':
        creator += 'error creation_failed\n'
    else:
        creator += '''
file mkdir [file join [file dirname [info script]] Parser]
set project [open [file join [file dirname [info script]] Parser Parser.xpr] w]
puts $project {<Project><Option Name="Part" Val="xcsu35p-sbvb625-2-e"/></Project>}
close $project
'''
    (tmp_path / 'create_parser.tcl').write_text(creator)
    driver = tmp_path / 'check.tcl'
    driver.write_text('''
set argv {proto_json_decoder project_bootstrap_test}
proc open_project {path} {
    if {![file isfile $path]} {error missing_project}
    error project_accessed
}
proc get_parts {args} {error project_accessed}
set code [catch {source [file join [file dirname [info script]] scripts ''' + entry + ''']} message]
puts "$code:$message"
''')
    result = subprocess.run(['tclsh', str(driver)], capture_output=True, text=True, check=True)
    assert not result.stderr
    expected = 'creation_failed' if state == 'creation_failure' else 'project_accessed'
    assert result.stdout.strip() == '1:' + expected
    assert (tmp_path / 'creation_called').exists() == (state != 'existing')
    if state == 'existing':
        assert project.read_bytes() == original
    elif state == 'missing':
        assert 'xcsu35p-sbvb625-2-e' in project.read_text()
    else:
        assert not project.exists()
