"""Predict saved cancellation-scope equality at its existing coherent captures."""
import hashlib
import json
from pathlib import Path
import shutil


SCOPE = ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor')


def pairs():
    return [('envelope_frozen_user', 'envelope_owner', 'freeze_user', 's_axis_tokens_tuser'),
            ('envelope_frozen_stream', 'envelope_stream', 'freeze_stream', 's_stream')] + [
                ('envelope_frozen_' + n, 'saved_frame_cfg_' + n, 'freeze_cfg_' + n, 'cfg_' + n) for n in SCOPE]


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/context-commit-guard/rtl'
    target = root / 'build/experiments/registered-envelope-scope/rtl'; target.mkdir(parents=True, exist_ok=True)
    for p in previous.glob('*.v'): shutil.copy2(p, target / p.name)
    original = previous / 'rpc_grpc_http2_return.v'; text = original.read_text()
    expression = '&&'.join(a + '==' + b for a, b, _, _ in pairs())
    marker = 'wire envelope_saved_match=grant_frozen&&envelope_owned&&' + expression + ';'
    assert text.count(marker) == 1
    descriptor = 's_axis_tokens_tvalid&&s_axis_tokens_tready'; freeze = 'freeze_valid&&freeze_ready'
    assert 'if(' + descriptor + ')begin envelope_owner<=' in text
    assert 'if(' + freeze + ')begin envelope_frozen_user<=' in text
    both = '&&'.join(c + '==' + d for _, _, c, d in pairs())
    accepted = '&&'.join(a + '==' + d for a, _, _, d in pairs())
    frozen = '&&'.join(c + '==' + b for _, b, c, _ in pairs())
    replacement = '''// Both scopes change only at actual descriptor/freeze handshakes.
// Predict their post-edge equality, including simultaneous captures. Incoming
// same-edge cancellation remains combinational and retains its original timing.
reg envelope_scope_matches;
always @(posedge clk)begin
    if(rst)envelope_scope_matches<=1;
    else if(''' + descriptor + '&&' + freeze + ')envelope_scope_matches<=' + both + ''';
    else if(''' + descriptor + ')envelope_scope_matches<=' + accepted + ''';
    else if(''' + freeze + ')envelope_scope_matches<=' + frozen + ''';
end
wire envelope_saved_match=grant_frozen&&envelope_owned&&envelope_scope_matches;'''
    (target / original.name).write_text(text.replace(marker, replacement))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(phase='isolated_registered_envelope_scope_generated',
        previous_overrides={p.name: sha(p) for p in previous.glob('*.v')},
        generated_sha256={p.name: sha(p) for p in target.glob('*.v')}, generator_sha256=sha(Path(__file__)),
        production_active_rtl_changed=False, full_system_complete=False)
    (target.parent / 'generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(target)


if __name__ == '__main__': main()
