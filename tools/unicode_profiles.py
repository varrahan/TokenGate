"""Programmable Unicode classes and executable pretokenizer profile model.

This host model specifies the upcoming RTL boundary FSM. Its results must
match independent regex references before transcription into hardware.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import regex

OTHER,LETTER,NUMBER,SPACE=0,1,2,3
CL100K="cl100k"
LLAMA3="llama3"
GPT2="gpt2"
# Patterns are public tokenizer interfaces, independently used for tests.
# https://github.com/meta-llama/llama3/blob/main/llama/tokenizer.py
LLAMA3_PATTERN=r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"
GPT2_PATTERN=r"'s|'t|'re|'ve|'m|'ll|'d| ?[\p{L}]+| ?[\p{N}]+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"
GPT2_COMPACT_PATTERN=r"'(?:[sdmt]|ll|ve|re)| ?\p{L}++| ?\p{N}++| ?[^\s\p{L}\p{N}]++|\s++$|\s+(?!\S)|\s"
CL100K_COMPACT_PATTERN=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"


@lru_cache(maxsize=1)
def unicode_classes():
    text="".join(map(chr,range(0x110000)))
    classes=bytearray(len(text))
    for pattern,value in [(r"\p{L}+",LETTER),(r"\p{N}+",NUMBER),(r"\s+",SPACE)]:
        for match in regex.finditer(pattern,text):
            classes[match.start():match.end()]=bytes([value])*(match.end()-match.start())
    return bytes(classes)


def packed_unicode_classes():
    classes=unicode_classes()
    return bytes(classes[i]|classes[i+1]<<2|classes[i+2]<<4|classes[i+3]<<6
                 for i in range(0,len(classes),4))


def export_unicode_image(directory:Path):
    directory.mkdir(parents=True,exist_ok=True)
    data=packed_unicode_classes()
    (directory/"unicode_classes.bin").write_bytes(data)
    manifest={"abi":1,"codepoints":0x110000,"class_bits":2,"codepoints_per_word":4,
              "word_address_bits":19,"word_data_bits":8,"memory_primitive":"block",
              "regex_package_version":regex.__version__,"bytes":len(data),
              "sha256":hashlib.sha256(data).hexdigest(),"bram36_blocks_estimate":128,
              "classes":{"other":OTHER,"letter":LETTER,"number":NUMBER,"whitespace":SPACE}}
    (directory/"unicode_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def split_profile(text:str,profile:str=CL100K):
    if profile not in (CL100K,LLAMA3,GPT2):raise ValueError("Unsupported pretokenizer profile")
    cps=list(map(ord,text))
    classes=unicode_classes()
    flags=[classes[cp]for cp in cps]
    n=len(cps);i=0;pieces=[]
    def lower(cp):
        if profile==GPT2:return cp
        return cp+32 if 65<=cp<=90 else 115 if cp==0x17f else cp
    while i<n:
        end=None
        # Priority 1: contractions, before the optional-prefix letter branch.
        if cps[i]==39 and i+1<n:
            a=lower(cps[i+1]);b=lower(cps[i+2])if i+2<n else -1
            if a in map(ord,"sdmt"):end=i+2
            elif (a,b)in[(108,108),(118,101),(114,101)]:end=i+3
        # Priority 2: Unicode letters with a single allowed prefix codepoint.
        if end is None:
            prefix=(cps[i]==32)if profile==GPT2 else flags[i]not in(LETTER,NUMBER)and cps[i]not in(10,13)
            start=i if flags[i]==LETTER else i+1 if prefix and i+1<n and flags[i+1]==LETTER else -1
            if start>=0:
                end=start
                while end<n and flags[end]==LETTER:end+=1
        # Priority 3: at most three number codepoints, or GPT-2's full run.
        if end is None:
            start=i if flags[i]==NUMBER else i+1 if profile==GPT2 and cps[i]==32 and i+1<n and flags[i+1]==NUMBER else -1
            if start>=0:
                end=start
                while end<n and flags[end]==NUMBER and (profile==GPT2 or end-start<3):end+=1
        # Priority 4: punctuation/marks/emoji, optional ASCII space, newlines.
        if end is None:
            start=i if flags[i]==OTHER else i+1 if cps[i]==32 and i+1<n and flags[i+1]==OTHER else -1
            if start>=0:
                end=start
                while end<n and flags[end]==OTHER:end+=1
                if profile!=GPT2:
                    while end<n and cps[end]in(10,13):end+=1
        if end is None:
            assert flags[i]==SPACE
            stop=i
            last_newline=-1
            while stop<n and flags[stop]==SPACE:
                if cps[stop]in(10,13):last_newline=stop
                stop+=1
            if profile==CL100K and stop==n:end=stop
            elif profile!=GPT2 and last_newline>=i:end=last_newline+1
            elif stop==n:end=stop
            elif stop-i>1:end=stop-1
            else:end=i+1
        assert end>i
        pieces.append(text[i:end]);i=end
    return pieces
