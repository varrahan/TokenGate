import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(ROOT/"build"/"tiktoken-cache"))
from external_memory_image import build_external_image,validate_vocabulary
from vocabulary_image import compile_image,tiktoken_vocabulary,decode_image
from unicode_profiles import export_unicode_image
from trie_image import validate_trie


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    directory=tmp_path_factory.mktemp("external-memory")
    vocabulary=tiktoken_vocabulary("cl100k_base")
    compile_image(vocabulary,directory/"vocab")
    export_unicode_image(directory/"unicode")
    manifest=build_external_image(directory/"vocab",directory/"unicode",directory/"external")
    return directory,vocabulary,manifest


def test_complete_vocabulary_is_retained_in_external_memory(sources):
    directory,vocabulary,manifest=sources
    image=(directory/"external"/"external_memory.bin").read_bytes()
    regions={region["name"]:region for region in manifest["regions"]}
    assert [region["base"]for region in manifest["regions"]]==[0,0x100000,0x200000,0x440000,0x484000,0x484400,0x5c1c40]
    assert manifest["workspace_base"]==0x695700
    assert manifest["workspace_capacity"]==1485056
    assert len(image)==8*1024*1024
    assert hashlib.sha256(image).hexdigest()==manifest["image_sha256"]
    for region in manifest["regions"]:
        assert hashlib.sha256(image[region["base"]:region["base"]+region["bytes"]]).hexdigest()==region["sha256"]
    index=regions["directory"];pool=regions["string_pool"]
    directory_bytes=image[index["base"]:index["base"]+index["bytes"]]
    pool_bytes=image[pool["base"]:pool["base"]+pool["bytes"]]
    for token_id,expected in vocabulary.tokens.items():assert decode_image(directory_bytes,pool_bytes,token_id)==expected
    trie_nodes=regions["trie_nodes"];trie_edges=regions["trie_edges"]
    assert validate_trie(image[trie_nodes["base"]:trie_nodes["base"]+trie_nodes["bytes"]],
                         image[trie_edges["base"]:trie_edges["base"]+trie_edges["bytes"]],
                         {key:value for key,value in vocabulary.tokens.items()if key not in vocabulary.special})
    # Nine-byte hash entries deliberately cross word/cache-line boundaries.
    hash_region=regions["merge_hash"]
    source_hash=(directory/"vocab"/"merge_hash.bin").read_bytes()
    for slot in range(256):
        address=hash_region["base"]+9*slot
        aligned=address&~7
        words=int.from_bytes(image[aligned:aligned+16],"little")
        actual=words>>((address&7)*8)&((1<<72)-1)
        assert actual==int.from_bytes(source_hash[slot*9:slot*9+9],"little")


def test_capacity_and_integrity_failures_are_explicit(sources,tmp_path):
    directory,_,_=sources
    with pytest.raises(ValueError,match="external capacity"):
        build_external_image(directory/"vocab",directory/"unicode",tmp_path/"small",capacity=1024*1024)
    copy=tmp_path/"corrupted"
    shutil.copytree(directory/"vocab",copy)
    raw=bytearray((copy/"merge_hash.bin").read_bytes());raw[0]^=1
    (copy/"merge_hash.bin").write_bytes(raw)
    with pytest.raises(ValueError,match="integrity"):validate_vocabulary(copy)


def update_checksum(directory,name,data):
    (directory/name).write_bytes(data)
    manifest=json.loads((directory/"manifest.json").read_text())
    manifest["files"][name]["sha256"]=hashlib.sha256(data).hexdigest()
    (directory/"manifest.json").write_text(json.dumps(manifest))


def test_self_hashed_but_invalid_tables_cannot_be_loaded(sources,tmp_path):
    directory,_,_=sources
    bad_pool=tmp_path/"bad-pool";shutil.copytree(directory/"vocab",bad_pool)
    index=bytearray((bad_pool/"directory.bin").read_bytes())
    pool_length=(bad_pool/"string_pool.bin").stat().st_size
    struct.pack_into("<Q",index,0,(1<<48)|(pool_length<<16)|2)
    update_checksum(bad_pool,"directory.bin",index)
    with pytest.raises(ValueError,match="outside string pool"):validate_vocabulary(bad_pool)
    bad_hash=tmp_path/"bad-hash";shutil.copytree(directory/"vocab",bad_hash)
    raw=bytearray((bad_hash/"merge_hash.bin").read_bytes())
    slots=[int.from_bytes(raw[i:i+9],"little")for i in range(0,len(raw),9)]
    occupied=next(i for i,word in enumerate(slots)if word)
    empty=next(i for i,word in enumerate(slots)if not word)
    raw[empty*9:empty*9+9]=raw[occupied*9:occupied*9+9]
    raw[occupied*9:occupied*9+9]=bytes(9)
    update_checksum(bad_hash,"merge_hash.bin",raw)
    with pytest.raises(ValueError,match="Unreachable merge"):validate_vocabulary(bad_hash)
