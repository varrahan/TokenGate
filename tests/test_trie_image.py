import hashlib
import os
from pathlib import Path
import random
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(ROOT/"build"/"tiktoken-cache"))
from trie_image import compile_trie,validate_trie,lookup_step,lookup_token,build_from_vocabulary
from vocabulary_image import tiktoken_vocabulary,compile_image


@pytest.fixture(scope="module")
def full_trie():
    vocab=tiktoken_vocabulary("cl100k_base")
    ordinary={key:value for key,value in vocab.tokens.items()if key not in vocab.special}
    manifest,files=compile_trie(ordinary)
    return vocab,ordinary,manifest,files


def test_every_cl100k_token_and_all_byte_steps_match_independent_vocabulary(full_trie):
    vocab,ordinary,manifest,files=full_trie
    nodes,edges=files["trie_nodes.bin"],files["trie_edges.bin"]
    assert(manifest["nodes"],manifest["edges"],manifest["terminals"])==(216750,216749,100256)
    assert len(nodes)+len(edges)==2167496
    for token_id,data in ordinary.items():assert lookup_token(nodes,edges,data)==token_id
    for byte,token_id in enumerate(vocab.byte_ids):
        node,terminal,found=lookup_step(nodes,edges,0,byte)
        assert node>0 and terminal and found==token_id
    reverse={data:token_id for token_id,data in ordinary.items()}
    rng=random.Random(20261104)
    for _ in range(2000):
        raw=rng.randbytes(rng.randrange(0,64))
        assert lookup_token(nodes,edges,raw)==reverse.get(raw)
    for token_id in vocab.special:assert lookup_token(nodes,edges,vocab.tokens[token_id])!=token_id
    for name,data in files.items():assert hashlib.sha256(data).hexdigest()==manifest["files"][name]["sha256"]


def test_leaf_prefix_zero_and_long_tokens_do_not_depend_on_recursion_or_id_order():
    tokens={7:b"",0:b"a",3:b"ab",4:b"ac",5:b"z",6:b"b"*5000}
    manifest,files=compile_trie(tokens)
    nodes,edges=files["trie_nodes.bin"],files["trie_edges.bin"]
    assert validate_trie(nodes,edges,tokens)==tokens
    for token_id,data in tokens.items():assert lookup_token(nodes,edges,data)==token_id
    assert lookup_token(nodes,edges,b"ad")is None
    assert lookup_token(nodes,edges,b"b"*4999)is None
    assert lookup_step(nodes,edges,0,ord("x"))is None
    assert manifest["max_token_bytes"]==5000
    other_manifest,other_files=compile_trie(dict(reversed(list(tokens.items()))))
    assert other_manifest==manifest and other_files==files


def test_malformed_trie_images_and_capacity_fail_explicitly():
    tokens={0:b"a",1:b"ab",2:b"b"}
    _,files=compile_trie(tokens)
    nodes,edges=files["trie_nodes.bin"],files["trie_edges.bin"]
    bad=bytearray(nodes);bad[5]|=0x80
    with pytest.raises(ValueError,match="node flags"):validate_trie(bad,edges)
    bad=bytearray(edges);bad[3]|=0x80
    with pytest.raises(ValueError,match="edge flags"):validate_trie(nodes,bad)
    bad=bytearray(edges);bad[4:8]=bad[0:4]
    with pytest.raises(ValueError,match="labels"):validate_trie(nodes,bad)
    bad=bytearray(edges);bad[0:4]=bytes([ord("a"),0,0,0])
    with pytest.raises(ValueError,match="child pointer"):validate_trie(nodes,bad)
    bad=bytearray(edges);bad[4:8]=(ord("b")|(1<<8)).to_bytes(4,"little")
    with pytest.raises(ValueError,match="Unreachable/shared"):validate_trie(nodes,bad)
    bad=bytearray(nodes);word=int.from_bytes(bad[:6],"little");bad[:6]=((word&~0x3ffff)|3).to_bytes(6,"little")
    with pytest.raises(ValueError,match="edge range"):validate_trie(bad,edges)
    with pytest.raises(ValueError,match="terminals do not match"):validate_trie(nodes,edges,{0:b"bad"})
    with pytest.raises(ValueError,match="sizes"):validate_trie(nodes[:-1],edges)
    with pytest.raises(ValueError,match="Duplicate ordinary"):compile_trie({0:b"a",1:b"a"})
    with pytest.raises(ValueError,match="ID exceeds"):compile_trie({131072:b"a"})
    with pytest.raises(ValueError,match="ID exceeds"):compile_trie({0:b"a","bad":b"b"})
    with pytest.raises(ValueError,match="node capacity"):compile_trie({0:b"abcdef"},node_bits=2)
    with pytest.raises(ValueError,match="fields exceed"):compile_trie(tokens,id_bits=32,node_bits=24)


def test_programming_files_come_from_the_validated_runtime_vocabulary(tmp_path):
    vocab=tiktoken_vocabulary("cl100k_base")
    compile_image(vocab,tmp_path/"vocab")
    manifest=build_from_vocabulary(tmp_path/"vocab",tmp_path/"trie")
    assert manifest["model"]=="cl100k_base"
    expected={key:value for key,value in vocab.tokens.items()if key not in vocab.special}
    assert validate_trie((tmp_path/"trie"/"trie_nodes.bin").read_bytes(),(tmp_path/"trie"/"trie_edges.bin").read_bytes(),expected)==expected
