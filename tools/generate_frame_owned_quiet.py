"""Cut the measured ownership/idle feedback with a conservative quiet proof."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_two_fpga_application import closure


def quiet(source):
    before='assign idle=owned_idle&&state==IDLE&&!window_req_valid&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;'
    after='''// A sampled empty-owner proof becomes usable only while every public
// admission offer remains absent. Offers also disqualify the sampled proof,
// covering the cycle before the directory/pool FSMs expose their busy state.
reg owned_quiet;
wire quiet_inputs=!req_valid&&!lease_valid&&!receive_pool_lock_valid&&
    !window_req_valid&&!start_valid&&!frame_req_valid&&!freeze_valid;
always @(posedge clk)begin
    if(rst)owned_quiet<=0;
    else owned_quiet<=owned_idle&&quiet_inputs;
end
assign idle=owned_quiet&&quiet_inputs&&state==IDLE&&!window_req_valid&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;'''
    assert source.count(before)==1
    result=source.replace(before,after);assert result.replace(after,before)==source
    # The exported idle has no internal consumers. Every existing request,
    # state transition, scope check, cancellation and response stays identical.
    body=source[source.index(');')+2:]
    body=re.sub(r'//[^\n]*|/\*.*?\*/','',body,flags=re.S)
    body=body.replace(before,'');body=re.sub(r'\.idle\([^)]*\)','',body)
    assert not re.search(r'\bidle\b',body)
    return result,dict(old=before,new=after)


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text());parent=root/'build/experiments/frame-event-buffer'
    generation=read(parent/'generation.json');units=read(root/'build/validation/frame-event-buffer-units.json')
    assert units['key']=='0629d7b95661f8df' and units['generation_sha256']==sha(parent/'generation.json')
    folder=root/'build/experiments/frame-owned-quiet';folder.mkdir(parents=True,exist_ok=False)
    for name,digest in generation['outputs_sha256'].items():
        assert sha(parent/name)==digest
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/name,path)
    path=folder/'rtl/http2_enveloped_frame_grants.v';text,certificate=quiet(path.read_text());path.write_bytes(text.encode())
    dependencies=closure('http2_enveloped_parser_application',folder);assert len(dependencies)==76
    assert len(closure('http2_enveloped_frame_grants',folder))==7
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    result=dict(phase='frame_owned_quiet_candidate_generated',parent_unit_audit_key=units['key'],
        parent_generation_sha256=sha(parent/'generation.json'),source_edit_certificate=certificate,
        exact_parser_modules=76,only_changed_module='http2_enveloped_frame_grants',
        no_existing_internal_consumer_of_exported_idle=True,all_existing_state_and_handshake_equations_preserved=True,
        conservative_idle_proof_verified=False,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)),outputs_sha256={'rtl/'+p.name:sha(p) for p in (folder/'rtl').glob('*.v')})
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','exact_parser_modules','only_changed_module')}))


if __name__=='__main__':main()
