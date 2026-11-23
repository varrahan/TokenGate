"""Disjoint full-model and transport/tokenizer working allocations for SCU35.

This proves a static layout for explicitly supplied working limits. Runtime
RPC ownership, leases, epochs and hardware acceptance remain separate checks.
"""
import argparse
from dataclasses import asdict,dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class Limits:
    connections:int
    rpc_slots:int
    rpc_payload_bytes:int
    max_text_bytes:int
    header_block_bytes:int
    header_scratch_bytes:int
    hpack_table_bytes:int
    descriptor_slots:int
    route_entries:int=0
    route_string_bytes:int=0


def runtime_plan(manifest,image,limits):
    if manifest.get('abi')!=1 or manifest.get('target')!='xcsu35p-sbvb625-2-e':
        raise ValueError('Unsupported external image ABI/target')
    capacity=manifest['capacity_bytes'];floor=manifest['workspace_base']
    if capacity!=len(image) or capacity>1<<23 or not 0<=floor<=capacity or manifest['workspace_capacity']!=capacity-floor:
        raise ValueError('Invalid model/workspace capacity')
    if hashlib.sha256(image).hexdigest()!=manifest['image_sha256']:
        raise ValueError('External image checksum mismatch')
    for name,value in asdict(limits).items():
        if type(value)is not int or value<0 or value==0 and name not in('hpack_table_bytes','route_entries','route_string_bytes'):
            raise ValueError(f'Invalid working limit: {name}')
    if bool(limits.route_entries)!=bool(limits.route_string_bytes):
        raise ValueError('Route records and key storage must be allocated together')
    regions=[];names=set()
    for region in manifest['regions']:
        name=region['name'];base=region['base'];size=region['bytes'];reserved=region['capacity']
        if name in names or not 0<=base<=floor or not 0<=size<=reserved or base+reserved>floor:
            raise ValueError('Invalid or overlapping model allocation')
        if hashlib.sha256(image[base:base+size]).hexdigest()!=region['sha256']:
            raise ValueError(f'Model region checksum mismatch: {name}')
        names.add(name);regions.append({'name':name,'base':base,'bytes':reserved,'owner':'model'})
    for left,right in zip(sorted(regions,key=lambda r:r['base']),sorted(regions,key=lambda r:r['base'])[1:]):
        if left['base']+left['bytes']>right['base']:raise ValueError('Overlapping model allocations')
    model={r['name']:r for r in manifest['regions']}
    required={'unicode_classes','merge_hash','trie_nodes','trie_edges','directory','string_pool'}
    if not required<=model.keys():raise ValueError('Incomplete model image')
    if model['trie_nodes']['bytes']%6 or model['trie_edges']['bytes']%4:
        raise ValueError('Invalid packed trie lengths')
    cursor=floor
    def allocate(name,size,owner):
        nonlocal cursor
        if name in names:raise ValueError(f'Duplicate runtime region name: {name}')
        names.add(name)
        cursor=(cursor+63)&~63
        if size<0 or cursor+size>capacity:
            raise ValueError(f'Working allocations exceed external capacity at {name}: need {size}, available {capacity-cursor}')
        item={'name':name,'base':cursor,'bytes':size,'owner':owner};regions.append(item);cursor+=size
        return item
    # Eight bytes per worst-case ASCII scalar, eight per byte-ID merge node,
    # and at most one four-byte token ID per input byte. No fixed 512 KiB pools.
    scalar=allocate('scalar_workspace',8*limits.max_text_bytes,'tokenizer')
    merge=allocate('merge_workspace',8*limits.max_text_bytes,'tokenizer')
    commit=allocate('token_commit',4*limits.max_text_bytes,'tokenizer')
    contexts=allocate('http2_contexts',256*limits.connections,'transport')
    streams=allocate('rpc_directory',128*limits.rpc_slots,'transport')
    descriptors=allocate('message_descriptors',32*limits.descriptor_slots,'transport')
    connections=[]
    for index in range(limits.connections):
        block=allocate(f'header_block_{index}',limits.header_block_bytes,'transport')
        table=allocate(f'hpack_table_{index}',limits.hpack_table_bytes,'transport')
        scratch=allocate(f'header_scratch_{index}',limits.header_scratch_bytes,'transport')
        connections.append({'record_base':contexts['base']+256*index,'header_buffer':block,'hpack_table':table,'header_scratch':scratch})
    payloads=[allocate(f'rpc_payload_{index}',limits.rpc_payload_bytes,'rpc')for index in range(limits.rpc_slots)]
    # Policy is allocated after the existing work regions to keep their ABI
    # stable. Route records and exact path keys must never alias model tables.
    route_table=allocate('route_table',32*limits.route_entries,'policy')
    route_strings=allocate('route_strings',limits.route_string_bytes,'policy')
    # One generation-tagged carry/ordinal/policy record per RPC slot. Append
    # this arena so existing ingress, tokenizer and route addresses stay stable.
    response_progress=allocate('response_progress',32*limits.rpc_slots,'response')
    config=[model['unicode_classes']['base'],model['merge_hash']['base'],model['trie_nodes']['base'],model['trie_edges']['base'],
            model['trie_nodes']['bytes']//6,model['trie_edges']['bytes']//4,floor,
            scalar['base'],scalar['bytes'],merge['base'],merge['bytes'],commit['base'],commit['bytes']]
    return {'abi':1,'target':manifest['target'],'model':manifest['model'],'image_sha256':manifest['image_sha256'],
            'capacity_bytes':capacity,'workspace_base':floor,'limits':asdict(limits),'regions':regions,
            'allocated_end':cursor,'remaining_bytes':capacity-cursor,'static_layout_verified':True,
            'runtime_ownership_verified':False,'full_system_verified':False,'tokenizer_config':config,
            'transport':{'context_pool':contexts,'stream_pool':streams,'descriptor_queue':descriptors,'connections':connections,'rpc_payloads':payloads,
                         'route_table':route_table,'route_strings':route_strings,'response_progress':response_progress}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image-directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    for name,field in Limits.__dataclass_fields__.items():
        parser.add_argument('--'+name.replace('_','-'),type=int,required=name not in('route_entries','route_string_bytes'),default=field.default if name in('route_entries','route_string_bytes')else None)
    args=parser.parse_args();directory=args.image_directory
    manifest=json.loads((directory/'external_manifest.json').read_text())
    limits=Limits(**{name:getattr(args,name)for name in Limits.__dataclass_fields__})
    plan=runtime_plan(manifest,(directory/'external_memory.bin').read_bytes(),limits)
    plan['planner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    plan['image_manifest_sha256']=hashlib.sha256((directory/'external_manifest.json').read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(plan,indent=2)+'\n')
    print(f"Static joint layout verified: {len(plan['regions'])} regions, {plan['remaining_bytes']} working bytes free; runtime ownership/full-system acceptance pending")


if __name__=='__main__':main()
