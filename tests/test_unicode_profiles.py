import random
import os
import sys
from pathlib import Path

import regex
import tiktoken

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(Path(__file__).resolve().parents[1]/"build"/"tiktoken-cache"))
from unicode_profiles import (CL100K,LLAMA3,GPT2,LLAMA3_PATTERN,GPT2_PATTERN,
                              split_profile,unicode_classes,packed_unicode_classes,export_unicode_image)


def test_class_image_covers_every_unicode_codepoint(tmp_path):
    classes=unicode_classes();packed=packed_unicode_classes()
    assert len(classes)==0x110000
    for cp,value in enumerate(classes):assert packed[cp>>2]>>((cp&3)*2)&3==value
    manifest=export_unicode_image(tmp_path)
    assert manifest["bytes"]==278528
    assert (tmp_path/"unicode_classes.bin").read_bytes()==packed


def test_profile_boundaries_match_independent_regex_references():
    patterns=[(CL100K,tiktoken.get_encoding("cl100k_base")._pat_str),(LLAMA3,LLAMA3_PATTERN),(GPT2,GPT2_PATTERN),
              (GPT2,tiktoken.get_encoding("r50k_base")._pat_str)]
    rng=random.Random(20261104)
    alphabet="aBzZ09²Ⅸ\t\r\n \v\f\u0085\u00a0\u2028\u3000!?'\\-_.é中🙂\u0301ſ"
    texts=["", "I'm WE'RE THEY'LL I'VE DON'T", "'ſ'll've'RE", " \n\t  "," \n\t  x", "\n\r\n\tend",
           "!word !!word 123456789", "a"*4096, " "*100+"word"]
    texts.extend("".join(rng.choice(alphabet)for _ in range(rng.randrange(0,100)))for _ in range(10000))
    for profile,pattern in patterns:
        matcher=regex.compile(pattern)
        for text in texts:
            assert split_profile(text,profile)==matcher.findall(text),(profile,text,split_profile(text,profile),matcher.findall(text))
