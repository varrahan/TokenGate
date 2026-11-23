"""Runtime vocabulary image ABI and validated host-side image compiler.

Images are programming data, not HDL ROM initializers. Load only while the
hardware epoch controller grants cfg_unlock, then validate/commit the epoch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Vocabulary:
    name: str
    tokens: dict[int, bytes]
    special: frozenset[int]
    byte_ids: tuple[int, ...]
    # left ID, right ID, result ID, merge priority (smaller wins)
    merges: tuple[tuple[int, int, int, int], ...]
    pretokenizer: dict


def tiktoken_vocabulary(name: str) -> Vocabulary:
    import tiktoken
    encoding = tiktoken.get_encoding(name)
    ranks = encoding._mergeable_ranks
    tokens = {rank: data for data, rank in ranks.items()}
    special = {}
    for spelling, token_id in encoding._special_tokens.items():
        if token_id in tokens:
            raise ValueError(f"Special ID {token_id} collides with a mergeable token")
        special[token_id] = spelling.encode("utf-8")
    pairs = []
    for data, result_id in ranks.items():
        for split in range(1, len(data)):
            left, right = ranks.get(data[:split]), ranks.get(data[split:])
            if left is not None and right is not None:
                pairs.append((left, right, result_id, result_id))
    return Vocabulary(name, tokens | special, frozenset(special),
                      tuple(ranks[bytes([i])] for i in range(256)), tuple(pairs),
                      {"kind": "regex", "pattern": encoding._pat_str,
                       "source": "tiktoken", "encoding": name})


def bytelevel_alphabet() -> dict[str, int]:
    # GPT-2's reversible byte alphabet, also used by HF ByteLevel BPE.
    byte_values = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    codepoints = byte_values.copy()
    n = 0
    for value in range(256):
        if value not in byte_values:
            byte_values.append(value)
            codepoints.append(256 + n)
            n += 1
    return {chr(cp): value for cp, value in zip(codepoints, byte_values)}


def huggingface_vocabulary(path: Path) -> Vocabulary:
    source = json.loads(path.read_text(encoding="utf-8"))
    model = source["model"]
    if model["type"] != "BPE" or model.get("dropout") not in (None, 0):
        raise ValueError("Only deterministic BPE models can be loaded")
    if model.get("continuing_subword_prefix") or model.get("end_of_word_suffix"):
        raise ValueError("Subword affix models require a separate hardware profile")
    if source.get("normalizer") is not None:
        raise ValueError("A hardware normalizer profile is required for this model")
    decoder = source.get("decoder") or {}
    if decoder.get("type") != "ByteLevel":
        raise ValueError("This loader currently supports HF ByteLevel byte vocabularies")
    alphabet = bytelevel_alphabet()
    raw_vocab = model["vocab"]
    tokens = {}
    special = set()
    added = {item["id"]: item for item in source.get("added_tokens", [])}
    for spelling, token_id in raw_vocab.items():
        if token_id in added and added[token_id].get("special"):
            tokens[token_id] = spelling.encode("utf-8")
            special.add(token_id)
        else:
            try:
                tokens[token_id] = bytes(alphabet[c] for c in spelling)
            except KeyError as error:
                raise ValueError(f"Token is not in the ByteLevel alphabet: {spelling!r}") from error
    for token_id, item in added.items():
        if not item.get("special"):
            raise ValueError("Non-special added-token matching needs a hardware matcher profile")
        tokens[token_id] = item["content"].encode("utf-8")
        special.add(token_id)
    byte_map = {data: token_id for token_id, data in tokens.items() if token_id not in special}
    pairs = []
    for rank, pair in enumerate(model["merges"]):
        left, right = pair.split(" ") if isinstance(pair, str) else pair
        pairs.append((raw_vocab[left], raw_vocab[right], raw_vocab[left+right], rank))
    return Vocabulary(path.stem, tokens, frozenset(special),
                      tuple(byte_map[bytes([i])] for i in range(256)), tuple(pairs),
                      {"kind": "huggingface", "pre_tokenizer": source.get("pre_tokenizer"),
                       "post_processor": source.get("post_processor")})


def pair_hash(left: int, right: int, address_bits: int) -> int:
    # Defined unsigned-32-bit arithmetic, shared with the RTL rank lookup.
    x = ((left * 0x9E3779B1) ^ (right * 0x85EBCA6B)) & 0xFFFFFFFF
    x ^= x >> 16
    return x & ((1 << address_bits) - 1)


def compile_image(vocab: Vocabulary, output: Path, *, id_bits=17, rank_bits=17,
                  hash_bits=18, vocab_bits=17, pool_bits=17) -> dict:
    if not 1 <= id_bits <= 32 or not 1 <= rank_bits <= 32:
        raise ValueError("ID and rank widths must be between 1 and 32")
    if max(vocab.tokens) >= 1 << min(id_bits, vocab_bits):
        raise ValueError("Vocabulary token IDs exceed configured hardware capacity")
    entry_bits = 3*id_bits + rank_bits + 1
    if entry_bits > 72:
        raise ValueError("Hash ABI exceeds one 72-bit UltraRAM word; select a wider RTL profile")
    if len(vocab.merges) >= 1 << hash_bits:
        raise ValueError("Merge table exceeds hash capacity")
    directory = bytearray(8 * (1 << vocab_bits))
    pool = bytearray()
    for token_id, data in sorted(vocab.tokens.items()):
        if len(data) >= 1 << 16:
            raise ValueError(f"Token {token_id} is too long for the length field")
        offset = len(pool)
        if offset + len(data) > 8 * (1 << pool_bits):
            raise ValueError("String pool exceeds configured hardware capacity")
        flags = 2 | int(token_id in vocab.special)
        word = len(data) << 48 | offset << 16 | flags
        struct.pack_into("<Q", directory, token_id*8, word)
        pool.extend(data)
    pool.extend(bytes(-len(pool) % 8))
    slots = [0] * (1 << hash_bits)
    max_probe = 0
    for left, right, result, rank in vocab.merges:
        if max(left, right, result) >= 1 << id_bits or rank >= 1 << rank_bits:
            raise ValueError("Merge IDs/ranks exceed hardware word widths")
        address = pair_hash(left, right, hash_bits)
        key = left | right << id_bits
        probe = 0
        while slots[address]:
            if slots[address] & ((1 << (2*id_bits))-1) == key:
                raise ValueError(f"Duplicate merge pair: {(left, right)}")
            address = (address+1) % len(slots)
            probe += 1
        slots[address] = (key | result << (2*id_bits) | rank << (3*id_bits)
                          | 1 << (3*id_bits+rank_bits))
        max_probe = max(max_probe, probe)
    payloads = {
        "directory.bin": directory,
        "string_pool.bin": pool,
        "byte_tokens.bin": struct.pack("<256I", *vocab.byte_ids),
        "merge_hash.bin": b"".join(word.to_bytes(9, "little") for word in slots),
    }
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for filename, data in payloads.items():
        (output / filename).write_bytes(data)
        files[filename] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {
        "abi": 1, "name": vocab.name, "id_bits": id_bits, "rank_bits": rank_bits,
        "hash_addr_bits": hash_bits, "vocab_addr_bits": vocab_bits,
        "pool_word_addr_bits": pool_bits, "vocabulary_entries": len(vocab.tokens),
        "merge_pairs": len(vocab.merges), "max_hash_probe": max_probe,
        "max_token_bytes": max(map(len, vocab.tokens.values())),
        "pretokenizer": vocab.pretokenizer, "files": files,
        "uram288_blocks": (math.ceil((1 << vocab_bits)/4096) +
                           math.ceil((1 << pool_bits)/4096) +
                           math.ceil((1 << hash_bits)/4096)),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


def decode_image(directory: bytes, pool: bytes, token_id: int, *, strip_special=False) -> bytes:
    if token_id < 0 or token_id*8+8 > len(directory):
        raise ValueError("Token ID outside directory")
    word, = struct.unpack_from("<Q", directory, token_id*8)
    if not word & 2:
        raise ValueError("Invalid vocabulary entry")
    length, offset = word >> 48, (word >> 16) & 0xFFFFFFFF
    if offset+length > len(pool):
        raise ValueError("Vocabulary entry points outside string pool")
    return b"" if strip_special and word & 1 else pool[offset:offset+length]


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tiktoken")
    source.add_argument("--huggingface", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    vocab = tiktoken_vocabulary(args.tiktoken) if args.tiktoken else huggingface_vocabulary(args.huggingface)
    print(json.dumps(compile_image(vocab, args.output), indent=2))


if __name__ == "__main__":
    main()
