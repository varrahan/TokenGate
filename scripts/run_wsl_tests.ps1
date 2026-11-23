param(
    [ValidateSet('serializer','utf8_chunks','http2_names','schema','ram','packager','pretokenizer','trie','splitter','external_merge','tokenizer','tokenizer_subsystem','tokenizer_bulk','huffman','hpack_integer','hpack_table','hpack_static','hpack_string','hpack_headers','http2_frames','http2_connections','http2_transport','http2_hpack','http2_requests','http2_routes','http2_admission','http2_prefill','grpc_messages','decoder','grpc_application','message_replay','grpc_descriptors','grpc_streams','grpc_engine','grpc_parser','grpc_prefill')]
    [string[]]$Suites=@('ram','packager','pretokenizer','trie','external_merge','tokenizer','tokenizer_subsystem'),
    [string]$Distro='Ubuntu'
)
$ErrorActionPreference='Stop'
$workspacePath=Split-Path -Parent $PSScriptRoot
$referencePython=Join-Path $workspacePath '.venv312\Scripts\python.exe'
$fixtureArguments=@()
if($Suites -contains 'serializer') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_serializer_vectors.py') --output (Join-Path $workspacePath 'build\serializer-stream\serializer_vectors.txt')
    if($LASTEXITCODE -ne 0) { throw 'Serializer references failed' }
    $fixtureArguments+=@('--fixture','serializer-stream')
}
if($Suites -contains 'utf8_chunks') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_utf8_chunk_vectors.py') --output (Join-Path $workspacePath 'build\utf8-chunks')
    if($LASTEXITCODE -ne 0) { throw 'Incremental UTF-8 references failed' }
    $fixtureArguments+=@('--fixture','utf8-chunks')
}
if($Suites -contains 'http2_names') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_name_vectors.py') --output (Join-Path $workspacePath 'build\http2-names')
    if($LASTEXITCODE -ne 0) { throw 'Header-name references failed' }
    $fixtureArguments+=@('--fixture','http2-names')
}
if($Suites -contains 'http2_prefill') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_prefill_vectors.py') --output (Join-Path $workspacePath 'build\http2-prefill')
    if($LASTEXITCODE -ne 0) { throw 'Raw HTTP/2 full-model prefill references failed' }
    $fixtureArguments+=@('--fixture','http2-prefill')
}
if($Suites -contains 'http2_routes') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_request_vectors.py') --include-route-cases --output (Join-Path $workspacePath 'build\http2-routes')
    if($LASTEXITCODE -ne 0) { throw 'Raw HTTP/2 route packets failed' }
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_route_vectors.py') --output (Join-Path $workspacePath 'build\http2-routes')
    if($LASTEXITCODE -ne 0) { throw 'Runtime route references failed' }
    $fixtureArguments+=@('--fixture','http2-routes')
}
if($Suites -contains 'http2_requests') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_request_vectors.py') --output (Join-Path $workspacePath 'build\http2-requests')
    if($LASTEXITCODE -ne 0) { throw 'Raw HTTP/2 request-header fixtures failed' }
    $fixtureArguments+=@('--fixture','http2-requests')
}
if($Suites -contains 'grpc_prefill') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_grpc_prefill_vectors.py') --output (Join-Path $workspacePath 'build\grpc-prefill')
    if($LASTEXITCODE -ne 0) { throw 'Complete-model gRPC prefill fixtures failed' }
    $fixtureArguments+=@('--fixture','grpc-prefill')
}
if($Suites -contains 'grpc_parser') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_grpc_parser_vectors.py') --output (Join-Path $workspacePath 'build\grpc-parser')
    if($LASTEXITCODE -ne 0) { throw 'Committed gRPC Parser fixtures failed' }
    $fixtureArguments+=@('--fixture','grpc-parser')
}
if($Suites -contains 'grpc_engine') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_grpc_engine_vectors.py') --output (Join-Path $workspacePath 'build\grpc-engine')
    if($LASTEXITCODE -ne 0) { throw 'Automatic gRPC ingress fixtures failed' }
    $fixtureArguments+=@('--fixture','grpc-engine')
}
if($Suites -contains 'grpc_application') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_grpc_application_vectors.py') --output (Join-Path $workspacePath 'build\grpc-application')
    if($LASTEXITCODE -ne 0) { throw 'gRPC application fixtures failed' }
    $fixtureArguments+=@('--fixture','grpc-application')
}
if($Suites -contains 'decoder') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_decoder_vectors.py') --output (Join-Path $workspacePath 'build\decoder\decoder_vectors.mem')
    if($LASTEXITCODE -ne 0) { throw 'Decoder fixtures failed' }
    $fixtureArguments+=@('--fixture','decoder')
}
if($Suites -contains 'grpc_messages') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_grpc_message_vectors.py') --output (Join-Path $workspacePath 'build\grpc-messages')
    if($LASTEXITCODE -ne 0) { throw 'gRPC message fixtures failed' }
    $fixtureArguments+=@('--fixture','grpc-messages')
}
if($Suites -contains 'pretokenizer') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_pretokenizer_vectors.py') --output (Join-Path $workspacePath 'build\pretokenizer')
    if($LASTEXITCODE -ne 0) { throw 'Pretokenizer fixture generation failed' }
    $fixtureArguments+=@('--fixture','pretokenizer')
}
if($Suites -contains 'trie') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_trie_vectors.py') --output (Join-Path $workspacePath 'build\trie-pipeline')
    if($LASTEXITCODE -ne 0) { throw 'Trie fixture generation failed' }
    $fixtureArguments+=@('--fixture','trie-pipeline')
}
if($Suites -contains 'splitter') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_splitter_vectors.py') --output (Join-Path $workspacePath 'build\splitter\vectors.txt')
    if($LASTEXITCODE -ne 0) { throw 'Splitter fixture generation failed' }
    $fixtureArguments+=@('--fixture','splitter')
}
if($Suites -contains 'external_merge') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_external_merge_vectors.py') --output (Join-Path $workspacePath 'build\external-merge')
    if($LASTEXITCODE -ne 0) { throw 'External merge fixture generation failed' }
    $fixtureArguments+=@('--fixture','external-merge')
}
if(($Suites -contains 'tokenizer') -or ($Suites -contains 'tokenizer_subsystem')) {
    & $referencePython (Join-Path $workspacePath 'tools\generate_tokenizer_vectors.py') --output (Join-Path $workspacePath 'build\tokenizer-engine')
    if($LASTEXITCODE -ne 0) { throw 'Tokenizer fixture generation failed' }
    $fixtureArguments+=@('--fixture','tokenizer-engine')
}
if($Suites -contains 'tokenizer_bulk') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_bulk_tokenizer_vectors.py') --output (Join-Path $workspacePath 'build\tokenizer-bulk')
    if($LASTEXITCODE -ne 0) { throw 'Bulk MMIO/model fixtures failed' }
    $fixtureArguments+=@('--fixture','tokenizer-bulk')
}
if($Suites -contains 'huffman') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_huffman_vectors.py') --output (Join-Path $workspacePath 'build\hpack-huffman')
    if($LASTEXITCODE -ne 0) { throw 'HPACK Huffman fixtures failed' }
    $fixtureArguments+=@('--fixture','hpack-huffman')
}
if($Suites -contains 'hpack_integer') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_integer_vectors.py') --output (Join-Path $workspacePath 'build\hpack-integer')
    if($LASTEXITCODE -ne 0) { throw 'HPACK integer fixtures failed' }
    $fixtureArguments+=@('--fixture','hpack-integer')
}
if($Suites -contains 'http2_hpack') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_hpack_vectors.py') --output (Join-Path $workspacePath 'build\http2-hpack')
    if($LASTEXITCODE -ne 0) { throw 'Raw HTTP/2 HPACK fixtures failed' }
    $fixtureArguments+=@('--fixture','http2-hpack')
}
if($Suites -contains 'http2_transport') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_transport_vectors.py') --output (Join-Path $workspacePath 'build\http2-transport')
    if($LASTEXITCODE -ne 0) { throw 'HTTP/2 transport fixtures failed' }
    $fixtureArguments+=@('--fixture','http2-transport')
}
if($Suites -contains 'http2_connections') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_frame_vectors.py') --output (Join-Path $workspacePath 'build\http2-connections')
    if($LASTEXITCODE -ne 0) { throw 'HTTP/2 connection fixtures failed' }
    $fixtureArguments+=@('--fixture','http2-connections')
}
if($Suites -contains 'http2_frames') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_http2_frame_vectors.py') --output (Join-Path $workspacePath 'build\http2-frames')
    if($LASTEXITCODE -ne 0) { throw 'HTTP/2 frame fixtures failed' }
    $fixtureArguments+=@('--fixture','http2-frames')
}
if($Suites -contains 'hpack_headers') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_header_vectors.py') --output (Join-Path $workspacePath 'build\hpack-headers')
    if($LASTEXITCODE -ne 0) { throw 'HPACK header block fixtures failed' }
    $fixtureArguments+=@('--fixture','hpack-headers')
}
if($Suites -contains 'hpack_string') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_string_vectors.py') --output (Join-Path $workspacePath 'build\hpack-string')
    if($LASTEXITCODE -ne 0) { throw 'HPACK string fixtures failed' }
    $fixtureArguments+=@('--fixture','hpack-string')
}
if($Suites -contains 'hpack_static') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_static_table.py') --rtl (Join-Path $workspacePath 'rtl\parser\transport\hpack\hpack_static_table.v') --output (Join-Path $workspacePath 'build\hpack-static')
    if($LASTEXITCODE -ne 0) { throw 'HPACK static table generation failed' }
    $fixtureArguments+=@('--fixture','hpack-static')
}
if($Suites -contains 'hpack_table') {
    & $referencePython (Join-Path $workspacePath 'tools\generate_hpack_table_vectors.py') --output (Join-Path $workspacePath 'build\hpack-table')
    if($LASTEXITCODE -ne 0) { throw 'HPACK table fixtures failed' }
    $fixtureArguments+=@('--fixture','hpack-table')
}
$linuxSource=(& wsl.exe --distribution $Distro --exec wslpath -a -u $workspacePath).Trim()
if($LASTEXITCODE -ne 0) { throw 'Could not map the primary source path into WSL' }
& wsl.exe --distribution $Distro --exec python3 "$linuxSource/scripts/sync_wsl_workspace.py" @fixtureArguments
if($LASTEXITCODE -ne 0) { throw 'WSL source synchronization failed; independent WSL changes were preserved' }
$linuxWorkspace=(& wsl.exe --distribution $Distro --exec python3 -c 'from pathlib import Path; print(Path.home()/"development/hardware/parser")').Trim()
if($LASTEXITCODE -ne 0) { throw 'Could not resolve the WSL workspace' }
foreach($suite in $Suites) {
    if($suite -eq 'ram') {
        & wsl.exe --distribution $Distro --exec python3 "$linuxWorkspace/scripts/run_wsl_sv_tests.py" $suite --simulator iverilog
        if($LASTEXITCODE -ne 0) { throw 'WSL four-state RAM test failed' }
    }
    & wsl.exe --distribution $Distro --exec python3 "$linuxWorkspace/scripts/run_wsl_sv_tests.py" $suite
    if($LASTEXITCODE -ne 0) { throw "WSL test failed: $suite" }
}
& wsl.exe --distribution $Distro --exec python3 "$linuxSource/scripts/collect_wsl_reports.py" @Suites
if($LASTEXITCODE -ne 0) { throw 'WSL result archival failed' }
