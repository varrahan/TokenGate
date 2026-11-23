"""Independent full-corpus oracle for native HTTP/2 + AXI-Lite schema updates."""
import argparse
import codecs
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import Frame
import tiktoken

from verify_joint_hyperram_grpc_native import load_frames, load_ids, varint


def observed_case_windows(log,calls):
    pattern=r'^JOINT_CASE_WINDOW stage=(start|forward|end) epoch=(\d+) case=(\d+) cycle=(\d+) bytes=(\d+) tokens=(\d+) reads=(\d+) writes=(\d+) hyperbus=(\d+)$'
    rows=re.findall(pattern,log,re.M)
    assert len(rows)==len(calls)*3==96
    windows={}
    for stage,epoch,case,cycle,raw,tokens,reads,writes,hyperbus in rows:
        key=(int(epoch),int(case));group=windows.setdefault(key,{})
        assert stage not in group
        group[stage]=dict(cycle=int(cycle),raw=int(raw),tokens=int(tokens),reads=int(reads),writes=int(writes),hyperbus=int(hyperbus))
    result=[];previous_end=-1
    for call in calls:
        group=windows[(call['epoch'],call['case'])];assert set(group)=={'start','forward','end'}
        start,forward,end=[group[k]for k in('start','forward','end')]
        assert previous_end<=start['cycle']<forward['cycle']<end['cycle'];previous_end=end['cycle']
        for point in(start,forward,end):
            assert point['raw']==call['raw_request_bytes']and point['tokens']==call['tokens']
        assert all(start[k]<=forward[k]<=end[k]for k in('reads','writes','hyperbus'))
        fc=forward['cycle']-start['cycle'];rc=end['cycle']-start['cycle']
        result.append(dict(epoch=call['epoch'],case=call['case'],tokens=call['tokens'],raw_request_bytes=call['raw_request_bytes'],
            start_cycle=start['cycle'],forward_complete_cycle=forward['cycle'],retired_cycle=end['cycle'],
            forward_cycles=fc,return_and_retirement_cycles=rc-fc,complete_call_cycles=rc,
            forward_token_ids_per_cycle=call['tokens']/fc,forward_raw_request_bytes_per_cycle=call['raw_request_bytes']/fc,
            forward_parser_reads=forward['reads']-start['reads'],forward_parser_writes=forward['writes']-start['writes'],
            forward_hyperbus_transactions=forward['hyperbus']-start['hyperbus'],
            complete_parser_reads=end['reads']-start['reads'],complete_parser_writes=end['writes']-start['writes'],
            complete_hyperbus_transactions=end['hyperbus']-start['hyperbus'],
            complete_call_microseconds_at_simulated_250mhz=rc*0.004))
    return dict(nominal_application_clock_period_ns=4.0,nominal_memory_clock_period_ns=5.0,
        cases=result,complete_call_window_sum_cycles=sum(c['complete_call_cycles']for c in result),
        image_programming_and_readback_excluded=True,fixture_backpressure_and_directory_handshakes_included=True,
        host_gpu_compute_time_included=False,physical_clock_or_throughput_verified=False,
        peak_sustained_throughput_established=False)


def verify_wsl_capacity_sources(folder,root,report,generation):
    """Audit simulator scope independently of its launcher success record."""
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    source=folder/'execution-sources'
    assert report['phase']=='full_workload_completed_independent_oracle_pending' and report['simulation_passed']
    assert report['parser_modules']==79 and report['tokenizer_modules']==31
    assert report['full_images']==2 and report['full_requests']==32 and report['simulator_two_state']
    assert report['all_production_rtl_unmodified'] and report['all_original_assertions_and_traffic_preserved']
    assert report['vendor_sources_unmodified'] and report['testbench_assertions_enabled'] and not report['vendor_assertions_disabled']
    inputs=report['inputs_sha256'];original=generation['outputs_sha256']
    assert original==report['original_generation_inputs_sha256']
    edit=report['testbench_memory_driver_edit']
    if edit:
        assert edit['path']=='joint_parser_axi_memory.svh' and edit['exact_inverse_verified']
        replacements=[['if(parser_b_accepted)p_axi_bvalid=0;','if(parser_b_accepted)p_axi_bvalid<=0;'],
            ['p_axi_rlast=pr_index+1==pr_beats;p_axi_rvalid=1;','p_axi_rlast=pr_index+1==pr_beats;p_axi_rvalid<=1;']]
        assert edit['replacements']==replacements
        text=(source/edit['path']).read_bytes().decode()
        for before,after in reversed(replacements):
            assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==original[edit['path']]==edit['old_sha256']
        assert sha(source/edit['path'])==inputs[edit['path']]==edit['new_sha256']
    assert {n for n in original if original[n]!=inputs[n]}==({'joint_parser_axi_memory.svh'} if edit else set())
    assert inputs.keys()==original.keys()
    for n,h in inputs.items():assert sha(source/n)==h,n
    for n,h in report['outputs_sha256'].items():assert sha(folder/n)==h,n
    assert set(report['elaboration_artifacts_sha256'])=={'elaboration.json','elaboration.meta.json','elaboration.log'}
    for n,h in report['elaboration_artifacts_sha256'].items():assert sha(folder/n)==h,n
    assert sha(folder/'build.log')==report['build_log_sha256']
    assert report['driver_sha256']==sha(folder/'run_joint_capacity_verilator_wsl.py')
    assert report['generation_sha256']==sha(folder/'generation.json')
    if report.get('refusal_execution_pack',False):
        if report.get('registered_selection_execution_pack',False):
            from generate_registered_selection_execution_pack import validate_pack
            assert report['source_candidate']==('joint-rpc-receive-payload-v1'if report.get('payload_pipeline_execution_pack',False)else'joint-rpc-registered-select-v1')
            checker='generate_registered_selection_execution_pack.py'
        else:
            from generate_rpc_refusal_execution_pack import validate_pack
            assert report['source_candidate']=='joint-rpc-refusal-v7-v2'
            checker='generate_rpc_refusal_execution_pack.py'
        assert report['source_assembly_kind']=='strict_two_state_elaboration'
        pack=root/'build/experiments'/report['source_candidate'];assembly=validate_pack(root,pack)
        assert read(folder/'source-assembly.json')==assembly
        assert sha(source/checker)==sha(pack/checker)
        assert assembly['key']==report['native_assembly_audit_key']
        assert assembly['generation_sha256']==sha(folder/'generation.json')
        assert generation==read(pack/'generation.json')
    else:
        assembly=read(root/'build/validation/joint-capacity-success-native-assembly.json')
        assert assembly['key']==report['native_assembly_audit_key']=='e346244ae567e5d1'
        assert assembly['generation_sha256']==sha(folder/'generation.json') and assembly['native_elaboration_verified']
    from verify_two_fpga_application import closure
    assert {n:sha(p) for n,p in closure('http2_schema_mmio_application',source/'joint').items()}==assembly['executed_parser_sha256']
    assert {n:sha(p) for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',source/'joint').items()}==assembly['executed_tokenizer_sha256']
    tool=report['isolated_simulator_build'];patch=report.get('isolated_simulator_patch')
    label='verilator-v5.054-whole-release-v1' if patch else 'verilator-v5.054'
    tests=read(root/'build/validation'/(label+'-upstream-selected.json'))
    assert tool['commit']=='bbb60a403932a9f695cb6ff001ceb73de6ad9234'
    binary_sha=tool['executable_sha256']
    if patch:
        assert patch['base_simulator_binary_sha256']==binary_sha and patch['actual_semantic_checks']==33
        assert patch['phase']=='focused_regression_passed_upstream_suite_pending'
        assert patch['source_edit']['path']=='src/V3Force.cpp' and patch['source_edit']['exact_inverse_verified']
        assert patch['amd_sources_modified'] is False and patch['original_released_tool_modified'] is False
        assert tests['local_whole_release_patch']==patch
        binary_sha=patch['simulator_binary_sha256']
    assert tests['phase']=='passed' and tests['simulator_binary_sha256']==binary_sha==report['simulator_binary_sha256']
    assert 'Verilator 5.054' in report['simulator_version']
    commands=report['commands'];assert len(commands)==3
    for command in commands[:2]:
        assert '--timing' in command and '--assert' in command and '-DOBSOLETE' in command
        assert not any(n in command for n in ('-DONESPIN','--no-assert','--no-timing'))
        if report.get('refusal_execution_pack',False):assert '--bbox-unsup'not in command
    tree=read(folder/'elaboration.json');metadata=read(folder/'elaboration.meta.json')
    file_id=next(k for k,v in metadata['files'].items() if v['filename']=='joint/vendor/xpm_memory.sv')
    vendor=(source/'joint/vendor/xpm_memory.sv').read_text().splitlines()
    start=next(i for i,s in enumerate(vendor,1) if 'if (ECC_MODE != 0) begin : ecc_behav_logic' in s)
    end=next(i for i,s in enumerate(vendor,1) if 'end : ecc_behav_logic' in s)
    stack=[tree];nodes=[]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            if 'type' in item:nodes.append(item)
            stack.extend(v for v in item.values() if isinstance(v,(dict,list)))
        elif isinstance(item,list):stack.extend(item)
    for n in nodes:
        loc=n.get('loc','').split(',')
        assert not (len(loc)>1 and loc[0]==file_id and start<=int(loc[1].split(':')[0])<=end)
        assert not any(s in n['type'].lower() for s in ('deassign','unsupported','blackbox'))
    modes=[n for n in nodes if n['type']=='VAR' and n.get('origName')=='ECC_MODE' and 'xpm_memory_base_inst' in n.get('name','')]
    assert len(modes)==8 and all(len(n.get('valuep',[]))==1 and n['valuep'][0]['type']=='CONST' and n['valuep'][0]['name']=="32'sh0" for n in modes)
    names=[n.get('name','') for n in nodes]
    assert any('glbl.GSR_int' in n for n in names) and any('glblGSR_xpmcdc' in n for n in names)
    assert sum(n['type']=='STOP' for n in nodes)>=300
    assert not any('ecc_behav_logic' in n for n in names)
    return assembly


def verify(folder, root, *, wsl_capacity=False):
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    source=folder/'execution-sources' if wsl_capacity else folder
    report=read(folder/'report.json');generation=read(folder/'generation.json');ref=read(source/'reference.json')
    if wsl_capacity:
        assembly=verify_wsl_capacity_sources(folder,root,report,generation)
    else:
        assert report['phase']=='native_simulation_completed_protocol_oracle_pending' and report['simulation_passed']
        assert report['parser_modules']==77 and report['tokenizer_modules']==31 and report['schema_mmio']
        assert report['inputs_sha256']==generation['outputs_sha256']
        assert report['generation_sha256']==sha(folder/'generation.json')
        for name,digest in report['inputs_sha256'].items():assert sha(folder/name)==digest,name
        for name,digest in report['outputs_sha256'].items():assert sha(folder/name)==digest,name
        assert report['driver_sha256']==sha(folder/'run_joint_hyperram_grpc_native.py')
    assert generation['route_word_offsets']==dict(schema_epoch=16,model_epoch=20)
    owned_quiet=generation.get('owned_quiet',False)
    assembly_name='http2-schema-owned-quiet-assembly' if owned_quiet else 'http2-schema-mmio-assembly'
    if not wsl_capacity:
        assembly=read(root/'build/validation'/(assembly_name+'.json'))
        assert assembly['run']==folder.name and assembly['generation_sha256']==sha(folder/'generation.json')
        assert assembly['generator_replay_exact'] and assembly['production_configuration_wiring_verified']
        assert assembly['native_elaboration_verified']
        frozen=root/'build/validation'/(assembly_name+'-evidence')/assembly['key']
        if owned_quiet:assert assembly['canonical_owned_quiet_induction_verified'] and assembly['frame_event_buffer_integrated']
        assert read(frozen/'audit.json')==assembly
        assert sha(frozen/'verify_http2_schema_mmio_assembly.py')==assembly['verifier_sha256']
        assert sha(folder/'production.prj')==assembly['production_project_sha256']
        assert sha(folder/'xelab.log')==assembly['elaboration_log_sha256']
        assert report['production_compiled_as_verilog'] and report['native_vendor_memory'] and not report['portable_backend']
        assert report['testbench_assertions_enabled'] and report['normal_global_startup'] and report['compatibility_defines']==['OBSOLETE']
    vendor=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')
    for name in ('cdc','memory','fifo'):
        assert sha(source/f'joint/vendor/xpm_{name}.sv')==sha(vendor/f'xpm_{name}/hdl/xpm_{name}.sv')
    log=(folder/('simulation.log' if wsl_capacity else 'xsim.log')).read_text(errors='replace')
    assert log.count('JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS')==1
    assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',log,re.M)
    assert len(re.findall(r'^JOINT_CORPUS_CASE ',log,re.M))==32
    for epoch in range(2):
        for operation in ('WRITE','READ'):
            assert list(map(int,re.findall(r'^JOINT_IMAGE_'+operation+' epoch='+str(epoch)+r' bytes=(\d+)',log,re.M)))==list(range(1048576,8388609,1048576))
        assert re.findall(r'^JOINT_ROUTE_SCHEMA epoch='+str(epoch)+r' entry=(\d+) schema_epoch=(\d+)',log,re.M)==[(str(i),str(10+epoch)) for i in range(2)]
        assert re.findall(r'^JOINT_ROUTE_EPOCH epoch='+str(epoch)+r' entry=(\d+) model_epoch=(\d+)',log,re.M)==[(str(i),str(23+epoch)) for i in range(2)]
    schema_events=[line.split() for line in (folder/'schema.log').read_text().splitlines()]
    assert all(event[0] in ('WRITE','READ','ACCEPT','DURABLE') for event in schema_events)
    for epoch in range(2):
        events=[e for e in schema_events if int(e[1])==epoch]
        key=('message','content')[epoch].encode();field=(37,2712)[epoch]
        expected_writes=[]
        for index in range(2):
            padded=(key if index==0 else b'').ljust(32,b'\0')
            expected_writes += [(16,index),(20,len(key) if index==0 else 0),(24,3 if index==0 else 0),(28,field if index==0 else 0)]
            expected_writes += [(32+4*i,int.from_bytes(padded[4*i:4*i+4],'little')) for i in range(8)]
            expected_writes += [(8,1)]
        assert [(int(e[2],16),int(e[3],16)) for e in events if e[0]=='WRITE']==expected_writes
        assert [(int(e[2],16),int(e[3],16)) for e in events if e[0]=='READ']==[(0,0x50534331),(12,0),(12,1),(12,2)]
        accepted=[e for e in events if e[0]=='ACCEPT'];durable=[e for e in events if e[0]=='DURABLE']
        assert [tuple(map(int,e[2:6]))+(int(e[6],16),) for e in accepted]==[(0,len(key),field,3,int.from_bytes(key,'little')),(1,0,0,0,0)]
        assert [int(e[2]) for e in durable]==[1,2]
        accepted_positions=[i for i,e in enumerate(events) if e[0]=='ACCEPT']
        durable_positions=[i for i,e in enumerate(events) if e[0]=='DURABLE']
        apply_positions=[i for i,e in enumerate(events) if e[0]=='WRITE' and int(e[2],16)==8]
        # The two doorbell lines have identical values; compare their actual
        # positions rather than list.index(), which would find the first one.
        assert len(accepted_positions)==len(durable_positions)==len(apply_positions)==2
        for index in range(2):assert accepted_positions[index]<durable_positions[index]<apply_positions[index]
    assert len(schema_events)==2*(26+4+2+2)
    corpus=read(root/'build/validation/json-simd-corpus.json');assert corpus['key']=='2509134d2630b47e'
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    path=original/'build/bidirectional-fixtures/reference_cases.json'
    assert sha(path)==corpus['inputs_sha256']['build/bidirectional-fixtures/reference_cases.json']
    prompts=read(path)['cases'];assert len(prompts)==16
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    base=tiktoken.get_encoding('cl100k_base');mapping=bytes.maketrans(b'eE',b'Ee')
    swapped=tiktoken.Encoding(name='schema_native_eE_swap',pat_str=base._pat_str,
        mergeable_ranks={key.translate(mapping):value for key,value in base._mergeable_ranks.items()},special_tokens=base._special_tokens)
    frames,beats=load_frames(folder/'wire.log');dma=load_ids(folder/'dma.log');gpu=load_ids(folder/'gpu.log',gpu=True)
    calls=[]
    for epoch,encoding in enumerate((base,swapped)):
        assert len(encoding._mergeable_ranks)==100256 and len(encoding._special_tokens)==5
        schema=ref['schemas'][epoch]
        assert schema==dict(json_key=('message','content')[epoch],protobuf_field=(37,2712)[epoch],transport_schema_epoch=10+epoch)
        client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
        client.initiate_connection();client.update_settings({4:1<<20});client.increment_flow_control_window(1<<20)
        initial=client.data_to_send();assert initial.hex()==ref['epochs'][epoch]['initial_request_hex']
        initial_events=[]
        for raw in frames[epoch,-1]:initial_events+=client.receive_data(raw)
        assert sum(type(e).__name__=='RemoteSettingsChanged' for e in initial_events)==1
        values=iter(map(int,(source/f'epoch{epoch}.vectors').read_text().split()))
        size=next(values);assert bytes(next(values) for _ in range(size))==initial
        assert next(values)==16
        for index,prompt in enumerate(prompts):
            stream=index*2+1;mode=2 if index&1 else 0;text=bytes.fromhex(prompt['prompt_utf8_hex']).decode('utf8')
            expected_ids=encoding.encode(text);assert dma[epoch,index]==expected_ids
            assert gpu[epoch,index]==[(token,int(i+1==len(expected_ids))) for i,token in enumerate(expected_ids)]
            client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
                (':path','/parser.Tokenize/Proto' if mode==2 else '/parser.Tokenize/Json'),
                ('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json'),('te','trailers')])
            raw=text.encode('utf8')
            body=(json.dumps({schema['json_key']:text},ensure_ascii=False,separators=(',',':')).encode()
                if mode==0 else varint(schema['protobuf_field']<<3|2)+varint(len(raw))+raw)
            record=b'\0'+len(body).to_bytes(4,'big')+body
            for offset in range(0,len(record),16384):client.send_data(stream,record[offset:offset+16384],end_stream=offset+16384>=len(record))
            request=client.data_to_send();fields=[next(values) for _ in range(6)]
            assert fields==[index,stream,mode,100+int(mode==2),len(request),len(expected_ids)]
            assert bytes(next(values) for _ in range(fields[4]))==request
            assert [next(values) for _ in range(fields[5])]==expected_ids
            decoder=codecs.getincrementaldecoder('utf8')('replace');expected=bytearray()
            for ordinal,token in enumerate(expected_ids):
                decoded=decoder.decode(encoding.decode_single_token_bytes(token),final=ordinal+1==len(expected_ids));raw=decoded.encode('utf8')
                payload=(json.dumps({'choices':[{'delta':{'content':decoded}}]},ensure_ascii=False,separators=(',',':')).encode()
                    if mode==0 else varint(17<<3|2)+varint(len(raw))+raw)
                expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
            events=[event for raw in frames[epoch,index] for event in client.receive_data(raw)]
            if wsl_capacity:
                config=ref['base_configuration'];stream_limit=config['cfg_payload_slot_bytes']+5
                connection_limit=config['cfg_stream_bytes']//128*stream_limit
                updates=[]
                for raw in frames[epoch,index]:
                    frame,size=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
                    assert frame.serialize()==raw
                    if frame.type==8:updates.append((frame.stream_id,frame.window_increment))
                # All vectors end the request in this same input packet.
                # The real reclaimer skips remote-ended RPCs (progress[163]);
                # their CLOSE returns consumed DATA to the connection only.
                # Its first update also retires the still-pending bootstrap
                # credit. There is no stream update for an ended request.
                assert updates==[(0,len(record)+(connection_limit-65535 if index==0 else 0))],(epoch,index,updates)
                assert client.outbound_flow_control_window==connection_limit
            for event_name in ('ResponseReceived','TrailersReceived','StreamEnded'):
                assert sum(type(e).__name__==event_name for e in events)==1
            assert all(getattr(e,'stream_id',stream)==stream for e in events if type(e).__name__!='WindowUpdated')
            assert all(e.stream_id in (0,stream) for e in events if type(e).__name__=='WindowUpdated')
            responses=[e for e in events if type(e).__name__=='ResponseReceived']
            trailers=[e for e in events if type(e).__name__=='TrailersReceived']
            assert responses[0].headers==[(':status','200'),('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json')]
            assert trailers[0].headers==[('grpc-status','0')]
            assert not any(type(e).__name__ in ('StreamReset','ConnectionTerminated') for e in events)
            actual=b''.join(e.data for e in events if type(e).__name__=='DataReceived');assert actual==expected,(epoch,index)
            calls.append(dict(epoch=epoch,case=index,tokens=len(expected_ids),raw_request_bytes=len(request),
                response_bytes=len(actual),response_sha256=hashlib.sha256(actual).hexdigest()))
        assert next(values,None) is None
        before=(source/'parser-image.bin').read_bytes();after=(folder/f'parser-final{epoch}.bin').read_bytes()
        model=(source/f'image{epoch}.bin').read_bytes();final=(folder/f'tokenizer-final{epoch}.bin').read_bytes()
        assert len(before)==len(after)==len(model)==len(final)==8388608
        floor=ref['protected_model_bytes'];assert floor==6903552
        assert before[:floor]==after[:floor] and model[:floor]==final[:floor]
        assert hashlib.sha256(model).hexdigest()==ref['epochs'][epoch]['image_sha256']
        for entry in range(2):
            start=ref['base_configuration']['cfg_route_base']+32*entry
            assert before[start:start+16]==after[start:start+16] and before[start+24:start+32]==after[start+24:start+32]
            assert int.from_bytes(after[start+20:start+24],'little')==23+epoch
            assert int.from_bytes(after[start+16:start+20],'little')==10+epoch
        if wsl_capacity:
            # Independently reconstruct the complete durable receive ledger,
            # rather than treating a correct-looking wire refund as proof of
            # memory-backed credit or of retirement after wire acceptance.
            config=ref['base_configuration']
            stream_limit=config['cfg_payload_slot_bytes']+5
            connection_limit=config['cfg_stream_bytes']//128*stream_limit
            connection=config['cfg_receive_connection_base']
            geometry=[(config['cfg_context_base'],config['cfg_context_bytes']),
                (config['cfg_stream_base'],config['cfg_stream_bytes']),
                (config['cfg_receive_connection_base'],config['cfg_receive_connection_bytes']),
                (config['cfg_receive_stream_base'],config['cfg_receive_stream_bytes']),
                (config['cfg_payload_base'],config['cfg_payload_bytes'])]
            words=[0x48325243,connection_limit|(stream_limit<<32),0]
            words += [base|(size<<32) for base,size in geometry]
            assert after[connection:connection+64]==b''.join(word.to_bytes(8,'little') for word in words)
            # Serial calls reuse the first free RPC slot. The last generation
            # and stream are 16 and31; CLOSE clears pending/intent, marks the
            # stream closed and leaves its debited original stream window.
            stream_base=config['cfg_receive_stream_base']
            stream_words=[0x48325253|(16<<32),(65535-len(record))|(31<<32)|(1<<63),0,stream_limit]
            assert after[stream_base:stream_base+32]==b''.join(word.to_bytes(8,'little') for word in stream_words)
            assert after[stream_base+32:stream_base+config['cfg_receive_stream_bytes']]==bytes(config['cfg_receive_stream_bytes']-32)
            for address in range(config['cfg_stream_base'],config['cfg_stream_base']+config['cfg_stream_bytes'],128):
                assert after[address:address+8]==bytes(8),('Unretired RPC header',epoch,address)
    assert len(calls)==32 and [sum(c['tokens'] for c in calls if c['epoch']==e) for e in range(2)]==[2828,8263]
    assert sum(map(len,dma.values()))==sum(map(len,gpu.values()))==11091
    return dict(phase='two_state_joint_hyperram_schema_capacity_full_corpus_verified' if wsl_capacity else 'native_joint_hyperram_schema_owned_quiet_full_corpus_verified' if owned_quiet else 'native_joint_hyperram_schema_full_corpus_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=folder.name,assembly_audit_key=assembly['key'],component_audit_key=assembly['capacity_assembly_audit_key'] if wsl_capacity else assembly['component_audit_key'],
        exact_parser_modules=79 if wsl_capacity else 77,exact_tokenizer_modules=31,parser_memory_fabric_modules=4,
        native_complete_grpc_calls=32,actual_dma_ids=11091,actual_captured_dma_ids_returned=11091,
        native_wire_frames=sum(map(len,frames.values())),accepted_wire_beats=beats,
        actual_schema_accepts=4,actual_durable_schema_applies=4,actual_axi_lite_writes=52,actual_axi_lite_reads=8,
        actual_host_route_epoch_write_readback_commands=16,full_image_bytes_each=8388608,
        complete_model_prefixes_immutable=True,native_vendor_runtime_verified=not wsl_capacity,
        two_state_unchanged_vendor_model_runtime_verified=wsl_capacity,capacity_composed=wsl_capacity,
        capacity_closed_request_wire_and_durable_ledger_verified=wsl_capacity,
        full_http2_schema_mmio_functional_workload_verified=True,native_requests_rebuilt_against_actual_hardware_settings=True,
        native_tokenizer_version=version('tiktoken'),native_http2_version=version('h2'),
        global_schema_maintenance_authority_verified=False,whole_rpc_gpu_image_authority_verified=False,
        frame_event_buffer_integrated=owned_quiet,owned_quiet_integrated=owned_quiet,
        full_protocol_fault_matrix_verified=False,native_timing_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        calls=calls,report_sha256=sha(folder/'report.json'),generation_sha256=sha(folder/'generation.json'),
        actual_inputs_sha256=report['inputs_sha256'],actual_outputs_sha256=report['outputs_sha256'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--wsl-capacity',action='store_true');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/wsl-reports'/('joint_capacity_verilator_'+args.name) if args.wsl_capacity else root/'build/validation'/args.name
    result=verify(folder,root,wsl_capacity=args.wsl_capacity)
    runtime=json.loads((folder/'report.json').read_text())
    refusal=args.wsl_capacity and runtime.get('refusal_execution_pack',False)
    registered=refusal and runtime.get('registered_selection_execution_pack',False)
    payload=registered and runtime.get('payload_pipeline_execution_pack',False)
    if refusal:
        result.update(phase='two_state_joint_rpc_refusal_full_corpus_verified',
            source_candidate=runtime['source_candidate'],refusal_branch_exercised=False,
            admission_default_open=True,new_refusal_fault_matrix_verified=False)
        if registered:result['phase']='two_state_joint_registered_selection_full_corpus_verified'
        if payload:result['phase']='two_state_joint_receive_payload_full_corpus_verified'
    if payload:
        source=folder/'execution-sources'
        assert (source/'hyperram_device_and_host.svh').read_text().count('initial forever #2000 app_clk=~app_clk;')==1
        assert (source/'hyperram_device_and_host.svh').read_text().count('initial begin #700;forever #2500 mem_clk=~mem_clk;end')==1
        result['observed_simulation_windows']=observed_case_windows((folder/'simulation.log').read_text(),result['calls'])
    result['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    audit_name='joint-hyperram-schema-capacity-wsl' if args.wsl_capacity else 'joint-hyperram-schema-owned-quiet' if result['owned_quiet_integrated'] else 'joint-hyperram-schema'
    if refusal:audit_name='joint-rpc-refusal-v7-full-corpus-wsl'
    if registered:audit_name='joint-rpc-registered-select-full-corpus-wsl'
    if payload:audit_name='joint-rpc-receive-payload-full-corpus-wsl'
    evidence=root/'build/validation'/(audit_name+'-evidence')/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    shutil.copy2(root/'tools/verify_joint_hyperram_grpc_native.py',evidence/'verify_joint_hyperram_grpc_native.py')
    if refusal:shutil.copy2(root/'tools/generate_rpc_refusal_execution_pack.py',evidence/'generate_rpc_refusal_execution_pack.py')
    if registered:
        shutil.copy2(root/'tools/generate_registered_selection_execution_pack.py',evidence/'generate_registered_selection_execution_pack.py')
        shutil.copy2(root/'tools/verify_registered_frame_select.py',evidence/'verify_registered_frame_select.py')
    if payload:shutil.copy2(root/'tools/verify_receive_payload_settling.py',evidence/'verify_receive_payload_settling.py')
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/(audit_name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','native_complete_grpc_calls','actual_dma_ids')}))


if __name__=='__main__':main()
