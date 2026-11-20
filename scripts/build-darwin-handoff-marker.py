#!/usr/bin/env python3
"""Build a cache-complete framebuffer marker for the archived fi102 EFI driver.

This is an offline diagnostic, not a firmware update or a general PE patcher.
The only supported input is the exact archived, unsigned DarwinBoot.efi. Its
DarwinEnter is a dedicated RX section at RVA 0xa000, without any relocations in
that section (see llvm-readobj). Never apply this to a different build by offset.
"""

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

BASELINE = "cd9f343a04740f836f0e5461aedce2f2d4aea8b96b78c0a2d1d8de2fb33a4e9b"
OFFSET = 0x6800
SIZE = 0x94


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    args = parser.parse_args()

    original = args.original.read_bytes()
    if hashlib.sha256(original).hexdigest() != BASELINE:
        parser.exit(1, "unsupported DarwinBoot SHA-256; no output was written\n")
    if args.output.exists():
        parser.exit(1, f"refusing to overwrite {args.output}\n")
    source = Path(__file__).with_name("darwin-handoff-marker.S")
    with tempfile.TemporaryDirectory(prefix="darwin-handoff-") as work:
        obj = Path(work) / "darwin-handoff.o"
        raw = obj.with_suffix(".bin")
        subprocess.run([args.clang, "--target=aarch64-none-elf", "-c", str(source),
                        "-o", str(obj)], check=True)
        subprocess.run([args.objcopy, "-j", ".text", "-O", "binary", str(obj), str(raw)],
                       check=True)
        marker = raw.read_bytes()

    end = OFFSET + SIZE
    previous = original[OFFSET:end]
    if (len(marker) != SIZE or marker[:4] != previous[:4]
            or marker[0x10:0x50] != previous[0x2c:0x6c]
            or marker[0x6c:] != previous[0x6c:]):
        parser.exit(1, "unexpected DarwinEnter code size, cache sequence or branch tail\n")
    if marker[0x50:0x6c] == previous[0x50:0x6c]:
        parser.exit(1, "expected late marker loop is missing\n")

    patched = original[:OFFSET] + marker + original[end:]
    with args.output.open("xb") as stream:
        stream.write(patched)
    for i in range(0, SIZE, 4):
        before, after = previous[i:i + 4], marker[i:i + 4]
        if before != after:
            print(f"RVA {0xa000 + i:04x} file {OFFSET + i:04x}: {before.hex()} -> {after.hex()}")
    print(f"{hashlib.sha256(patched).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()
