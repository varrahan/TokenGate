"""Predict the acknowledged-close scope at its existing coherent capture edges."""
import hashlib
import json
from pathlib import Path
import shutil


def main():
    root=Path(__file__).resolve().parents[1];original=root/'rtl/rpc_grpc_http2_return.v';source=original.read_text()
    scope=('context_base','context_bytes','window_base','window_bytes','work_floor')
    expression='&&'.join('saved_closed_'+n+'==saved_frame_cfg_'+n for n in scope)
    marker='wire closed_scope_matches='+expression+';'
    assert source.count(marker)==1
    close='window_rsp_valid&&window_rsp_ready&&window_rsp_status==0&&window_rsp_binding_valid&&window_rsp_send_closed'
    descriptor='s_axis_tokens_tvalid&&s_axis_tokens_tready'
    assert 'if('+close+')begin'in source
    both='&&'.join('closing_'+n+'==cfg_'+n for n in scope)
    new_descriptor='&&'.join('saved_closed_'+n+'==cfg_'+n for n in scope)
    new_close='&&'.join('closing_'+n+'==saved_frame_cfg_'+n for n in scope)
    replacement='''// The comparison changes only when the actual acknowledged-close scope
// or accepted descriptor scope changes. Predict their post-edge equality at
// those existing captures; no lookup, close, memory or wire latency is added.
reg closed_scope_matches;
always @(posedge clk)begin
    // Both stored scopes reset to zero, so their original equality is true.
    if(rst)closed_scope_matches<=1;
    else if('''+descriptor+'&&'+close+')closed_scope_matches<='+both+''';
    else if('''+descriptor+')closed_scope_matches<='+new_descriptor+''';
    else if('''+close+')closed_scope_matches<='+new_close+''';
end'''
    target=root/'build/experiments/registered-close-scope/rtl';target.mkdir(parents=True,exist_ok=True)
    (target/original.name).write_text(source.replace(marker,replacement))
    compact=root/'build/experiments/compact-grpc-headers/rtl/grpc_response_headers.v'
    shutil.copy2(compact,target/compact.name);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (target.parent/'generation.json').write_text(json.dumps(dict(phase='isolated_registered_close_scope_generated',
        original_top_sha256=sha(original),compact_header_sha256=sha(compact),generator_sha256=sha(Path(__file__)),
        outputs={p.name:sha(p)for p in target.glob('*.v')},production_rtl_changed=False),indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
