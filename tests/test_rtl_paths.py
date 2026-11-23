from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path, source_relative


def test_nested_rtl_and_flat_frozen_bundle_use_the_same_source_name(tmp_path):
    primary, snapshot = tmp_path / 'primary', tmp_path / 'snapshot'
    original = primary / 'rtl/parser/decoder/example.v'
    original.parent.mkdir(parents=True)
    original.write_text('module example; endmodule\n')
    relative = source_relative(original, primary)
    assert relative == Path('rtl/example.v')
    assert source_path(primary, relative) == original
    frozen = snapshot / relative
    frozen.parent.mkdir(parents=True)
    frozen.write_bytes(original.read_bytes())
    assert source_path(snapshot, relative).read_bytes() == original.read_bytes()
    assert source_path(primary, 'sim/example.sv') == primary / 'sim/example.sv'
    assert source_path(primary, 'rtl/new.v') == primary / 'rtl/new.v'
    assert source_relative(primary, primary) == Path('.')


def test_ambiguous_rtl_and_paths_outside_the_snapshot_are_rejected(tmp_path):
    for group in ('parser', 'tokenizer'):
        path = tmp_path / 'rtl' / group / 'duplicate.v'
        path.parent.mkdir(parents=True)
        path.write_text('module duplicate; endmodule\n')
    with pytest.raises(ValueError, match='Ambiguous RTL source'):
        source_path(tmp_path, 'rtl/duplicate.v')
    with pytest.raises(ValueError):
        source_relative(tmp_path.parent / 'outside.v', tmp_path)


def sync_fixture(tmp_path, monkeypatch):
    primary = tmp_path / 'primary'
    script = primary / 'scripts/sync_wsl_workspace.py'
    script.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / 'scripts/sync_wsl_workspace.py', script)
    relative = Path('rtl/parser/decoder/example.v')
    source = primary / relative
    source.parent.mkdir(parents=True)
    source.write_text('module example; endmodule\n')
    home = tmp_path / 'home'
    target = home / 'development/hardware/parser'
    old = target / 'rtl/example.v'
    old.parent.mkdir(parents=True)
    old.write_bytes(source.read_bytes())
    manifest = target / '.codex-parser-sync.json'
    manifest.write_text(json.dumps({'rtl/example.v': hashlib.sha256(old.read_bytes()).hexdigest()}))
    spec = importlib.util.spec_from_file_location('rtl_sync_check', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(sys, 'argv', [str(script)])
    return module, source, target, relative


def test_workspace_sync_relocates_only_unchanged_owned_rtl(tmp_path, monkeypatch):
    module, source, target, relative = sync_fixture(tmp_path, monkeypatch)
    module.main()
    assert (target / relative).read_bytes() == source.read_bytes()
    assert not (target / 'rtl/example.v').exists()
    manifest = json.loads((target / '.codex-parser-sync.json').read_text())
    assert relative.as_posix() in manifest and 'rtl/example.v' not in manifest


@pytest.mark.parametrize('changed', ['rtl/example.v', 'rtl/parser/decoder/example.v'])
def test_workspace_sync_preserves_independent_edits_during_relocation(tmp_path, monkeypatch, changed):
    module, source, target, relative = sync_fixture(tmp_path, monkeypatch)
    edited = target / changed
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text('independent edit\n')
    manifest = (target / '.codex-parser-sync.json').read_bytes()
    with pytest.raises(ValueError, match='Preserving modified WSL file'):
        module.main()
    assert edited.read_text() == 'independent edit\n'
    assert (target / 'rtl/example.v').exists()
    assert (target / '.codex-parser-sync.json').read_bytes() == manifest
