"""Full cold-load/replacement plans and independent multi-model references."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tiktoken
from tokenizers import Tokenizer,models,pre_tokenizers,decoders,trainers
from vocabulary_image import compile_image,tiktoken_vocabulary,huggingface_vocabulary
from unicode_profiles import export_unicode_image
from external_memory_image import build_external_image
from tokenizer_programming import programming_plan,write_plan,profile_for


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(out.parent/"tiktoken-cache"));export_unicode_image(out/"unicode")
    corpus=["", "hello world", "we're testing dynamic vocabulary", "café 🙂 中文 日本語", "1234567890\n  tabs\t",
            'JSON: "quote" and \\ newline\n',"ABCD We're I'VE DON'T", "a"*65,"\x00"*129, "alpha beta gamma alpha beta"]
    custom=Tokenizer(models.BPE());custom.pre_tokenizer=pre_tokenizers.ByteLevel(add_prefix_space=False,use_regex=True);custom.decoder=decoders.ByteLevel()
    custom.train_from_iterator(corpus*20,trainers.BpeTrainer(vocab_size=400,initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),special_tokens=["<|end|>"]))
    custom_path=out/"custom.json";custom.save(str(custom_path))
    entries=[]
    for index,name in enumerate(("cl100k_base","r50k_base","custom"),1):
        vocabulary=tiktoken_vocabulary(name)if name!="custom"else huggingface_vocabulary(custom_path)
        directory=out/name;compile_image(vocabulary,directory/"source")
        manifest=build_external_image(directory/"source",out/"unicode",directory/"image")
        profile=profile_for(manifest)
        image_name=name+"-image.bin";plan_name=name+"-plan.bin";vectors_name=name+"-vectors.txt"
        shutil.copy2(directory/"image/external_memory.bin",out/image_name)
        plan=write_plan(programming_plan(directory/"image",epoch=index),out/plan_name)
        golden=tiktoken.get_encoding(name)if name!="custom"else custom
        with(out/vectors_name).open("w",encoding="ascii")as stream:
            for context,text in enumerate(corpus,index*100):
                raw=text.encode();ids=golden.encode_ordinary(text)if name!="custom"else golden.encode(text).ids
                assert (golden.decode_bytes(ids)if name!="custom"else golden.decode(ids).encode())==raw
                stream.write(f"{len(raw)} {len(ids)} {context}\n"+" ".join(map(str,raw))+"\n"+" ".join(map(str,ids))+"\n")
        entry={"model":name,"image":image_name,"plan":plan_name,"vectors":vectors_name,"epoch":index,"profile":profile,
               "weight_bytes":manifest["workspace_base"],"vocabulary_entries":manifest["vocabulary_entries"],"merge_pairs":manifest["merge_pairs"],"image_sha256":manifest["image_sha256"],"programming_plan":plan}
        entries.append(entry)
        print(f"Generated full {name}: {entry['vocabulary_entries']} entries, {entry['weight_bytes']} weight bytes, {plan['operations']} MMIO operations",flush=True)
    (out/"models.txt").write_text("".join(f"{entry['image']} {entry['plan']} {entry['vectors']} {entry['weight_bytes']}\n"for entry in entries),encoding="ascii")
    (out/"models.json").write_text(json.dumps({"abi":1,"initial_memory_preloaded":False,"models":entries},indent=2)+"\n")


if __name__=="__main__":main()
