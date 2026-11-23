import hashlib
import json
import os
import struct
from pathlib import Path
import sys

import pytest
import regex
import tiktoken

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from vocabulary_image import (Vocabulary, compile_image, decode_image,
                              pair_hash, tiktoken_vocabulary, huggingface_vocabulary)

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(ROOT / "build" / "tiktoken-cache"))


@pytest.fixture(scope="module")
def image(tmp_path_factory):
    directory=tmp_path_factory.mktemp("cl100k")
    vocab=tiktoken_vocabulary("cl100k_base")
    manifest=compile_image(vocab,directory)
    return vocab,directory,manifest


def test_every_vocabulary_entry_matches_reference(image):
    vocab,directory,manifest=image
    index=(directory/"directory.bin").read_bytes()
    pool=(directory/"string_pool.bin").read_bytes()
    for token_id,expected in vocab.tokens.items():
        assert decode_image(index,pool,token_id)==expected
        assert decode_image(index,pool,token_id,strip_special=True)==(b"" if token_id in vocab.special else expected)
    assert manifest["max_token_bytes"]==128
    assert manifest["uram288_blocks"]==128
    assert len(pool)>65536
    for name,metadata in manifest["files"].items():
        data=(directory/name).read_bytes()
        assert len(data)==metadata["bytes"]
        assert hashlib.sha256(data).hexdigest()==metadata["sha256"]


def test_all_merge_pairs_survive_hash_collisions(image):
    vocab,directory,manifest=image
    raw=(directory/"merge_hash.bin").read_bytes()
    slots=[int.from_bytes(raw[i:i+9],"little") for i in range(0,len(raw),9)]
    id_mask=(1<<17)-1
    for left,right,result,rank in vocab.merges:
        addr=pair_hash(left,right,18)
        for _ in range(len(slots)):
            word=slots[addr]
            assert word>>68 & 1, (left,right,"missing pair")
            if word&id_mask==left and word>>17&id_mask==right:
                assert word>>34&id_mask==result
                assert word>>51&id_mask==rank
                break
            addr=(addr+1)%len(slots)
        else:
            pytest.fail("Lookup failed to terminate")
    assert manifest["merge_pairs"]==233378
    assert manifest["max_hash_probe"]>1


def test_invalid_directory_entries_are_rejected(image):
    _,directory,_=image
    index=(directory/"directory.bin").read_bytes()
    pool=(directory/"string_pool.bin").read_bytes()
    for invalid in [-1,100256,131072]:
        with pytest.raises(ValueError):decode_image(index,pool,invalid)
    corrupt=struct.pack("<Q",20<<48 | (len(pool)-1)<<16 | 2)
    with pytest.raises(ValueError):decode_image(corrupt,pool,0)


def test_byte_vocabulary_and_exact_multilingual_roundtrip(image):
    _,directory,_=image
    enc=tiktoken.get_encoding("cl100k_base")
    byte_ids=struct.unpack("<256I",(directory/"byte_tokens.bin").read_bytes())
    index=(directory/"directory.bin").read_bytes()
    pool=(directory/"string_pool.bin").read_bytes()
    for byte,token_id in enumerate(byte_ids):
        assert decode_image(index,pool,token_id)==bytes([byte])
    text='Hello \\" JSON\n café 中文 🙂 العربية 123456789'
    ids=enc.encode_ordinary(text)
    assert b"".join(decode_image(index,pool,t) for t in ids)==text.encode()


def test_capacity_failures_are_explicit(tmp_path):
    vocab=tiktoken_vocabulary("cl100k_base")
    for options in [{"id_bits":16},{"hash_bits":17},{"pool_bits":8}]:
        with pytest.raises(ValueError):compile_image(vocab,tmp_path,**options)


def test_huggingface_bytelevel_model_reload(tmp_path):
    from tokenizers import Tokenizer,models,pre_tokenizers,decoders,trainers
    tokenizer=Tokenizer(models.BPE())
    tokenizer.pre_tokenizer=pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder=decoders.ByteLevel()
    tokenizer.train_from_iterator(["hello world", "dynamic vocabulary hello world", "hello café 🙂"]*10,
        trainers.BpeTrainer(vocab_size=300,initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),special_tokens=["<eos>"]))
    path=tmp_path/"tokenizer.json"
    tokenizer.save(str(path))
    vocab=huggingface_vocabulary(path)
    out=tmp_path/"image"
    manifest=compile_image(vocab,out,hash_bits=10,vocab_bits=9,pool_bits=10)
    index=(out/"directory.bin").read_bytes()
    pool=(out/"string_pool.bin").read_bytes()
    for text in ["hello world","dynamic vocabulary", "café 🙂"]:
        ids=tokenizer.encode(text).ids
        assert b"".join(decode_image(index,pool,t) for t in ids)==text.encode()
    assert manifest["pretokenizer"]["kind"]=="huggingface"


def test_unsupported_huggingface_profiles_are_rejected(tmp_path):
    path=tmp_path/"tokenizer.json"
    path.write_text(json.dumps({"model":{"type":"Unigram"}}))
    with pytest.raises(ValueError):huggingface_vocabulary(path)
