"""Full-vocabulary inverse-lookup regression against independent tiktoken bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import tiktoken
from external_memory_image import build_external_image
from unicode_profiles import export_unicode_image
from vocabulary_image import compile_image, tiktoken_vocabulary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(args.output.parent / "tiktoken-cache"))
    if args.image is None:
        compile_image(tiktoken_vocabulary("cl100k_base"), args.output / "source")
        export_unicode_image(args.output / "unicode")
        args.image = args.output / "image"
        build_external_image(args.output / "source", args.output / "unicode", args.image)
    manifest = json.loads((args.image / "external_manifest.json").read_text())
    assert manifest["model"] == "cl100k_base"
    assert {r["name"]: r["base"] for r in manifest["regions"]}["string_pool"] == 0x100000
    image = (args.image / "external_memory.bin").read_bytes()
    assert hashlib.sha256(image).hexdigest() == manifest["image_sha256"]
    enc = tiktoken.get_encoding("cl100k_base")
    # The emulator needs only the first 2 MiB (directory and byte pool). The
    # full image remains intact; forward hash/class regions are unused here.
    with (args.output / "memory.mem").open("w", encoding="ascii") as stream:
        for offset in range(0, 0x200000, 8):
            stream.write(f"{int.from_bytes(image[offset:offset+8], 'little'):016x}\n")
    ids = sorted(enc._mergeable_ranks.values())
    packets = [(ids[i:i+64], False) for i in range(0, len(ids), 64)]
    specials = list(enc._special_tokens.values())
    packets += [(specials, True), (specials, False)]
    with (args.output / "vectors.txt").open("w", encoding="ascii") as stream:
        for sequence, (tokens, strip) in enumerate(packets, 1):
            expected = b"" if strip else b"".join(enc.decode_single_token_bytes(t) for t in tokens)
            stream.write(f"{len(tokens)} {len(expected)} {sequence} {int(strip)}\n")
            stream.write(" ".join(map(str, tokens)) + "\n")
            stream.write(" ".join(map(str, expected)) + "\n")
    print(f"Generated {len(packets)} packets covering all {len(ids)} ordinary and {len(specials)} special tokens")


if __name__ == "__main__":
    main()
