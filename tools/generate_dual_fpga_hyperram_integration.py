"""Join the real Parser and Tokenizer/controller without merging their RTL versions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from generate_two_fpga_application import balanced
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def net_declaration(text):
    """Keep each net initializer as the same explicit continuous assignment."""
    lexical = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',
                     lambda m: ' ' * len(m[0]), text, flags=re.S)
    if '=' not in lexical:
        return text, '', []
    depth = 0; begin = 0; segments = []
    for index, char in enumerate(lexical[:-1]):
        if char in '([{': depth += 1
        elif char in ')]}': depth -= 1
        elif char == ',' and depth == 0:
            segments.append((begin,index)); begin = index + 1
    segments.append((begin,len(text) - 1))
    declarators = []; drivers = []; prefix = None
    for begin, end in segments:
        segment = lexical[begin:end]
        depth = 0; equals = None
        for index, char in enumerate(segment):
            if char in '([{': depth += 1
            elif char in ')]}': depth -= 1
            elif char == '=' and depth == 0:
                equals = begin + index; break
        left_end = end if equals is None else equals
        lhs = lexical[begin:left_end]
        if prefix is None:
            match = re.fullmatch(r'(wire\s+(?:(?:signed|unsigned)\s+)?(?:\[[^\]]+\]\s*)*)(\w+)\s*', lhs)
            assert match, ('Unsupported net declaration',text)
            prefix = text[begin:begin + match.start(2)]
            name = match[2]
        else:
            name = lhs.strip(); assert re.fullmatch(r'\w+',name), text
        declarators.append(name)
        if equals is not None:
            rhs = text[equals + 1:end]
            drivers.append(dict(name=name,rhs=rhs))
    declaration = prefix + ','.join(declarators) + ';'
    continuation = ''.join('assign ' + row['name'] + '=' + row['rhs'] + ';\n' for row in drivers)
    return declaration, continuation, drivers


def order_declarations(source):
    """Hoist only module-scope constant parameters and uninitialized signals."""
    lexical = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',
                     lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source, flags=re.S)
    header = re.search(r'\bmodule\s+\w+\s*#\s*\(.*?\)\s*\(.*?\);', lexical, re.S)
    assert header and not re.search(r'^\s*`(?:ifdef|ifndef|elsif|else|endif)\b', source, re.M)
    module_end = re.search(r'\bendmodule\b', lexical[header.end():]).start() + header.end()
    depth = 0
    blocks = []
    skip = header.end()
    for match in re.finditer(r'\b(begin|end|function|endfunction|task|endtask|generate|endgenerate|fork|join|join_any|join_none|reg|wire|localparam)\b', lexical):
        if match.start() >= module_end:
            break
        if match.start() < skip:
            continue
        token = match[0]
        if token in ('begin','function','task','generate','fork'):
            depth += 1
        elif token in ('end','endfunction','endtask','endgenerate','join','join_any','join_none'):
            depth -= 1
            assert depth >= 0
        elif depth == 0:
            end = lexical.index(';', match.end()) + 1
            start = match.start()
            assert not lexical[:start].rstrip().endswith('*)'), 'Attributes require explicit handling'
            text = source[start:end]
            assert token != 'reg' or '=' not in text, 'Do not reorder register initializers'
            declaration, continuation, drivers = net_declaration(text) if token == 'wire' else (text,'',[])
            blocks.append(dict(start=start,end=end,kind=token,text=text,declaration=declaration,
                               continuation=continuation,continuous_net_drivers=drivers))
            skip = end
    assert depth == 0 and blocks
    remaining = source
    for block in reversed(blocks):
        remaining = remaining[:block['start']] + block['continuation'] + remaining[block['end']:]
    injected = '\n' + '\n'.join(block['declaration'] for kind in ('localparam','reg','wire') for block in blocks if block['kind'] == kind) + '\n'
    result = remaining[:header.end()] + injected + remaining[header.end():]
    assert result[:header.end()] + result[header.end() + len(injected):] == remaining
    restored = ''; offset = cursor = 0
    for block in blocks:
        count = block['start'] - cursor
        restored += remaining[offset:offset + count] + block['text']
        assert remaining[offset + count:offset + count + len(block['continuation'])] == block['continuation']
        offset += count + len(block['continuation']); cursor = block['end']
    restored += remaining[offset:]
    assert restored == source
    return result, dict(blocks=blocks,insertion_offset=header.end(),injected_text=injected,
                        original_sha256=hashlib.sha256(source.encode()).hexdigest(),
                        reordered_sha256=hashlib.sha256(result.encode()).hexdigest(),
                        only_module_scope_declarations_hoisted=True,
                        net_initializers_preserved_as_identical_continuous_assignments=True)


def namespace(source, names):
    """Rename module declarations/types only; preserve comments, ports and logic."""
    prefix = 'tokenizer_chiplet__'
    assert prefix not in source
    lexical = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',
                     lambda match: ''.join('\n' if c == '\n' else ' ' for c in match[0]), source, flags=re.S)
    replacements = {}
    for match in re.finditer(r'\bmodule\s+(\w+)', lexical):
        assert match[1] in names
        replacements[match.start(1)] = match[1]
    for name in names:
        for match in re.finditer(r'\b' + re.escape(name) + r'\b', lexical):
            start = match.start()
            if start in replacements:
                continue
            end = match.end()
            after = re.match(r'\s*#\s*\(', lexical[end:])
            if after:
                opening = end + after.end() - 1
                end = balanced(lexical, opening) + 1
            separator = r'\s*' if after else r'\s+'
            if re.match(separator + r'\w+(?:\s*\[[^\]]+\])?\s*\(', lexical[end:]):
                replacements[start] = name
    result = source
    for start, name in sorted(replacements.items(), reverse=True):
        assert result[start:start + len(name)] == name
        result = result[:start] + prefix + name + result[start + len(name):]
    restored = re.sub(r'\b' + prefix + r'(\w+)\b', lambda match: match[1], result)
    assert restored == source
    return result, len(replacements)


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--name', default='dual-fpga-hyperram-native-order-v4')
    args = arguments.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+', args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    read = lambda path: json.loads(path.read_text())
    parser_root = root / 'build/experiments/json-simd'
    parser_generation_path = parser_root / 'generation.json'
    parser_generation = read(parser_generation_path)
    component = read(root / 'build/validation/json-simd-decoder.json')
    assert component['key'] == '591275296c40a282' and component['native_timing_verified']
    assert parser_generation['parent_corpus_audit_key'] == '6dd529d376e06926'
    tokenizer_audit_path = root / 'build/validation/tokenizer-hyperram.json'
    tokenizer_audit = read(tokenizer_audit_path)
    assert tokenizer_audit['key'] == 'cac956b2d9ecf6f9'
    assert tokenizer_audit['native_audit_key'] == '344c37158dba0b39'
    tokenizer_root = root / 'build/validation' / tokenizer_audit['simulation'] / 'sources'
    parser_modules = closure('http2_enveloped_parser_application', parser_root)
    tokenizer_modules = closure('tokenizer_hyperram_subsystem', tokenizer_root)
    assert (len(parser_modules), len(tokenizer_modules)) == (76, 31)
    assert len(set(tokenizer_modules.values())) == 30
    scan_path = root / 'build/validation/parser_native_declaration_scan_20261122/report.json'
    scan = read(scan_path)
    assert len(scan) == 76
    affected = {name for name, row in scan.items() if row['exit_code']}
    assert len(affected) == 11
    for row in scan.values():
        assert all('[VRFC 10-3380]' in error or '[VRFC 10-8530]' in error for error in row['errors'])
    folder = root / 'build/experiments' / args.name
    assert not (folder / 'generation.json').exists(), 'Preserve the existing assembly before regenerating'
    inputs = {}
    outputs = {}
    replacements = {}
    declaration_fixes = {}
    def save(relative, data):
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        outputs[relative] = sha(target)
    for label, modules in [('parser', parser_modules), ('tokenizer', tokenizer_modules)]:
        for source in sorted(set(modules.values())):
            digest = sha(source)
            if label == 'parser':
                assert digest == parser_generation['outputs_sha256']['rtl/' + source.name]
            else:
                assert digest == tokenizer_audit['inputs_sha256']['rtl/' + source.name]
            inputs[source_relative(source, root).as_posix()] = digest
            content = source.read_bytes()
            if label == 'parser':
                assert digest == scan[source.name]['source_sha256']
            if label == 'parser' and source.name in affected:
                reordered, certificate = order_declarations(content.decode('utf8'))
                content = reordered.encode('utf8')
                declaration_fixes[source.name] = certificate
            save(label + '/rtl/' + source.name, content)
            if label == 'tokenizer':
                renamed, count = namespace(source.read_bytes().decode('utf8'), set(tokenizer_modules))
                save('joint/rtl/tokenizer_' + source.name, renamed.encode('utf8'))
                replacements[source.name] = count
            else:
                save('joint/rtl/' + source.name, content)
    for relative in ('vendor/xpm_cdc.sv', 'vendor/xpm_memory.sv', 'vendor/xpm_fifo.sv', 'vendor/glbl.v'):
        source = tokenizer_root / relative
        assert sha(source) == tokenizer_audit['inputs_sha256'][relative]
        inputs[source_relative(source, root).as_posix()] = sha(source)
        save('joint/' + relative, source.read_bytes())
    pports = ports((parser_root / 'rtl/http2_enveloped_parser_application.v').read_text(), 'http2_enveloped_parser_application')
    tports = ports((tokenizer_root / 'rtl/tokenizer_hyperram_subsystem.v').read_text(), 'tokenizer_hyperram_subsystem')
    plink = {name: (direction, width) for direction, width, name in pports if name.startswith('link_')}
    tlink = {name: (direction, width) for direction, width, name in tports if name.startswith('link_')}
    assert plink.keys() == tlink.keys() and len(plink) == 91
    normalize = lambda width: re.sub(r'\s+', '', width.replace('MEMORY_ADDR_WIDTH', '23'))
    for name, (direction, width) in plink.items():
        assert direction != tlink[name][0] and normalize(width) == normalize(tlink[name][1]), name
    public = [('input', '', 'app_clk'), ('input', '', 'mem_clk'), ('input', '', 'rst')]
    for label, interface in [('parser', pports), ('tokenizer', tports)]:
        for direction, width, name in interface:
            if name.startswith('link_') or name in ('clk', 'app_clk', 'mem_clk', 'rst'):
                continue
            public.append((direction, width.replace('MEMORY_ADDR_WIDTH', '23'), label + '_' + name))
    assert len({name for _, _, name in public}) == len(public)
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Joint digital validation of two separate FPGA applications.',
        '// Host must hold traffic until tokenizer_image_active and own all RPC/GPU/image',
        '// leases before tokenizer_external_image_grant. No global lease authority is inferred.',
        '// Physical board clocks, inter-FPGA link, PHY and PCIe remain integration boundaries.',
        'module two_fpga_hyperram_application #(',
        'parameter integer USER_WIDTH=16,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,',
        '                  MAX_FIELD_BYTES=16384,CACHE_LOG_LINES=6', ')(',
        ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');']
    lines += [f'wire {w.replace("MEMORY_ADDR_WIDTH", "23")} {n};' for n, (_, w) in plink.items()]
    for label, module, interface, parameters in [
        ('parser', 'http2_enveloped_parser_application', pports,
         '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(23),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)'),
        ('tokenizer', 'tokenizer_chiplet__tokenizer_hyperram_subsystem', tports,
         '.USER_WIDTH(USER_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.CACHE_LOG_LINES(CACHE_LOG_LINES)')]:
        def connection(name):
            if name.startswith('link_') or name in ('app_clk', 'mem_clk', 'rst'):
                return name
            return 'app_clk' if name == 'clk' else label + '_' + name
        lines += [f'{module} #({parameters}) {label}(',
                  ',\n'.join(f'    .{name}({connection(name)})' for _, _, name in interface), ');']
    lines += ['// Keep the vendor global startup model and its normal GSR interval.',
              'glbl glbl();', 'endmodule', '`default_nettype wire', '']
    save('joint/rtl/two_fpga_hyperram_application.v', '\n'.join(lines).encode('utf8'))
    assert len(closure('two_fpga_hyperram_application', folder / 'joint')) == 108
    save('parser/clocks.xdc', b'create_clock -name axis_clk -period 4.000 [get_ports clk]\n')
    save('tokenizer/clocks.xdc', b'create_clock -name app_clk -period 4.000 [get_ports app_clk]\ncreate_clock -name mem_clk -period 5.000 [get_ports mem_clk]\n')
    tcl = '''set bundle [file dirname [file normalize [info script]]]
foreach {label name part top} {
    parser Parser_AU15P xcau15p-ffvb676-2-e http2_enveloped_parser_application
    tokenizer Tokenizer_SCU35 xcsu35p-sbvb625-2-e tokenizer_hyperram_subsystem
} {
    set project_dir [file join $bundle projects $name]
    if {[file exists $project_dir]} {error "Project exists; preserve the previous source context"}
    create_project $name $project_dir -part $part
    set_property target_language Verilog [current_project]
    set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
    add_files -norecurse [lsort [glob [file join $bundle $label rtl *.v]]]
    add_files -fileset constrs_1 -norecurse [list [file join $bundle $label clocks.xdc]]
    set_property top $top [get_filesets sources_1]
    update_compile_order -fileset sources_1
    puts "DUAL_FPGA_SOURCE_PROJECT_CREATED NAME=$name PART=$part TOP=$top IMPLEMENTATION_NOT_RUN=1"
    close_project
}
'''
    save('create_projects.tcl', tcl.encode('utf8'))
    shared = parser_modules.keys() & tokenizer_modules.keys()
    result = dict(phase='exact_source_two_fpga_hyperram_integration_generated', generator_sha256=sha(Path(__file__)),
        parser_parent_corpus_audit_key='6dd529d376e06926', parser_component_audit_key=component['key'],
        tokenizer_functional_audit_key=tokenizer_audit['key'], tokenizer_native_audit_key=tokenizer_audit['native_audit_key'],
        exact_parser_modules=76, exact_tokenizer_modules=31, joint_module_count=108, text_and_control_link_signals=91,
        tokenizer_canonical_sources_byte_identical=True, parser_declaration_order_fixes=declaration_fixes,
        parser_native_declaration_scan_sha256=sha(scan_path),
        no_parser_state_or_data_equations_changed=True, tokenizer_joint_namespace='tokenizer_chiplet__',
        module_type_renames_only=True, namespace_round_trip_byte_identical=True, namespace_replacements_by_file=replacements,
        shared_original_module_names=sorted(shared), different_shared_original_modules=sorted(name for name in shared
            if parser_modules[name].read_bytes() != tokenizer_modules[name].read_bytes()),
        default_parameters=dict(USER_WIDTH=16,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384,CACHE_LOG_LINES=6),
        independent_memory_clock_hz=200000000, application_clock_hz=250000000,
        global_image_grant_authority_implemented=False, physical_interfaces_verified=False,
        elaboration_verified=False, joint_protocol_simulation_verified=False, full_system_complete=False,
        inputs_sha256=inputs, outputs_sha256=outputs)
    (folder / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('phase','exact_parser_modules','exact_tokenizer_modules','joint_module_count','different_shared_original_modules')}))


if __name__ == '__main__':
    main()
