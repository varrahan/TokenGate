import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from runtime_memory_plan import Limits,runtime_plan


@pytest.fixture(scope='module')
def model():
    directory=ROOT/'build/scu35/image'
    return json.loads((directory/'external_manifest.json').read_text()),(directory/'external_memory.bin').read_bytes()


LIMITS=Limits(connections=3,rpc_slots=3,rpc_payload_bytes=131072,max_text_bytes=16384,
              header_block_bytes=16384,header_scratch_bytes=32768,hpack_table_bytes=4096,descriptor_slots=16)


def test_full_image_and_all_live_work_regions_are_disjoint(model):
    manifest,image=model;plan=runtime_plan(manifest,image,LIMITS)
    assert len(image)==8*1024*1024 and plan['image_sha256']==hashlib.sha256(image).hexdigest()
    assert manifest['workspace_base']==0x695700 and not manifest['workspace_plan_verified']
    occupied=set()
    for region in plan['regions']:
        addresses=set(range(region['base'],region['base']+region['bytes']))
        assert not occupied&addresses
        assert region['base']>=0 and region['base']+region['bytes']<=len(image)
        occupied.update(addresses)
    assert len(plan['transport']['connections'])==3 and len(plan['transport']['rpc_payloads'])==3
    response=plan['transport']['response_progress']
    assert response['bytes']==32*LIMITS.rpc_slots and response['base']>=max(r['base']+r['bytes']for r in plan['transport']['rpc_payloads'])
    config=plan['tokenizer_config']
    assert config[4:7]==[216750,216749,0x695700]
    assert config[8]==config[10]==8*16384 and config[12]==4*16384
    assert plan['static_layout_verified'] and not plan['runtime_ownership_verified'] and not plan['full_system_verified']
    assert plan['remaining_bytes']>0


def test_exhaustion_and_invalid_limits_do_not_shrink_the_model(model):
    manifest,image=model
    with pytest.raises(ValueError,match='exceed external capacity'):runtime_plan(manifest,image,replace(LIMITS,rpc_slots=16))
    for limits in[replace(LIMITS,max_text_bytes=0),replace(LIMITS,connections=-1),replace(LIMITS,rpc_slots=True)]:
        with pytest.raises(ValueError,match='Invalid working limit'):runtime_plan(manifest,image,limits)
    no_dynamic=runtime_plan(manifest,image,replace(LIMITS,hpack_table_bytes=0))
    assert all(r['hpack_table']['bytes']==0 for r in no_dynamic['transport']['connections'])
    assert no_dynamic['image_sha256']==manifest['image_sha256']


def test_manifest_and_actual_image_integrity_are_checked(model):
    manifest,image=model
    corrupted=bytearray(image);corrupted[0]^=1
    with pytest.raises(ValueError,match='checksum'):runtime_plan(manifest,corrupted,LIMITS)
    overlap=copy.deepcopy(manifest);overlap['regions'][1]['base']=0
    overlap['regions'][1]['sha256']=hashlib.sha256(image[:overlap['regions'][1]['bytes']]).hexdigest()
    with pytest.raises(ValueError,match='Overlapping model'):runtime_plan(overlap,image,LIMITS)
    invalid=copy.deepcopy(manifest);invalid['workspace_capacity']+=64
    with pytest.raises(ValueError,match='workspace capacity'):runtime_plan(invalid,image,LIMITS)


def test_runtime_route_policy_shares_capacity_without_aliasing_live_work(model):
    manifest,image=model
    policy=runtime_plan(manifest,image,replace(LIMITS,route_entries=2,route_string_bytes=1024))
    old=runtime_plan(manifest,image,LIMITS)
    table=policy['transport']['route_table'];keys=policy['transport']['route_strings']
    assert table['bytes']==64 and keys['bytes']==1024
    assert table['base']>=max(r['base']+r['bytes']for r in policy['transport']['rpc_payloads'])
    assert keys['base']>=table['base']+table['bytes']
    assert policy['remaining_bytes']==old['remaining_bytes']-1088
    assert policy['tokenizer_config']==old['tokenizer_config']
    for limits in[replace(LIMITS,route_entries=1),replace(LIMITS,route_string_bytes=1)]:
        with pytest.raises(ValueError,match='allocated together'):runtime_plan(manifest,image,limits)
    with pytest.raises(ValueError,match='exceed external capacity'):
        runtime_plan(manifest,image,replace(LIMITS,route_entries=2,route_string_bytes=1<<20))
