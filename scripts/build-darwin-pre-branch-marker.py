#!/usr/bin/env python3
"""Append a cyan checkpoint immediately before the shennong fi102 kernel branch.

Only for the pinned yellow-marker DarwinBoot. The cyan band is inside the
existing yellow band and disjoint from the red kernel-entry marker. Keep x0
(boot_args), x1 (entry), x11 (framebuffer cursor), SP and NZCV unchanged.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

ORIGINAL_SHA256 = "3f4683aeca36644eb715f7124b0f5129a649141b7f2b518bfedb78341b848184"
RVA, RAW, OLD_SIZE = 0xA000, 0x6800, 0x94
BRANCH = RAW + OLD_SIZE - 4
BR_X1 = bytes.fromhex("20001fd6")
ASM = """\
.text
    cbz x11, 2f
    sub x12, x11, #0x70, lsl #12
    mov w9, #0x40000
    mov w10, #0xff00ffff
1:  stp w10, w10, [x12], #8
    sub w9, w9, #8
    cbnz w9, 1b
    dsb sy
2:  br x1
"""


def patch(data, blob):
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("unsupported DarwinBoot SHA-256")
    (pe,) = struct.unpack_from("<I", data, 0x3C)
    if data[:2] != b"MZ" or data[pe:pe+4] != b"PE\0\0":
        raise ValueError("expected a PE image")
    machine, count = struct.unpack_from("<HH", data, pe+4)
    (optional_size,) = struct.unpack_from("<H", data, pe+20)
    optional = pe+24
    (magic,) = struct.unpack_from("<H", data, optional)
    if machine != 0xaa64 or magic != 0x20b:
        raise ValueError("expected PE32+ Arm64")
    table = optional + optional_size
    sections = [table + 40*i for i in range(count)]
    rows = [(off, *struct.unpack_from("<IIII", data, off+8)) for off in sections]
    candidates = [row for row in rows if row[2] == RVA]
    if len(candidates) != 1:
        raise ValueError("expected a unique DarwinEnter section")
    off, size, _, raw_size, raw = candidates[0]
    (flags,) = struct.unpack_from("<I", data, off+36)
    (alignment,) = struct.unpack_from("<I", data, optional+32)
    end = BRANCH + len(blob)
    new_size = end - RAW
    if (size, raw, flags) != (OLD_SIZE, RAW, 0x60000020) or alignment != 0x1000:
        raise ValueError("unexpected DarwinEnter RX section layout")
    if (len(blob) != 36 or blob[-4:] != BR_X1 or data[BRANCH:BRANCH+4] != BR_X1
            or data[BRANCH-4:BRANCH] != bytes.fromhex("df3f03d5")
            or data[BRANCH+4:end] != bytes(len(blob)-4)
            or new_size > min(raw_size, alignment)
            or any(RVA < row[2] < RVA+new_size for row in rows)):
        raise ValueError("unexpected tail, slack or assembled marker")
    result = bytearray(data)
    struct.pack_into("<I", result, off+8, new_size)
    result[BRANCH:end] = blob
    return result, off+8, new_size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError(f"refusing to overwrite {args.output}")
        data = args.original.read_bytes()
        with tempfile.TemporaryDirectory(prefix="darwin-pre-branch-") as d:
            obj = Path(d) / "marker.o"
            raw = obj.with_suffix(".bin")
            subprocess.run([args.clang, "--target=aarch64-none-elf", "-x", "assembler",
                            "-c", "-", "-o", str(obj)], input=ASM, text=True, check=True)
            subprocess.run([args.objcopy, "-j", ".text", "-O", "binary", str(obj), str(raw)], check=True)
            blob = raw.read_bytes()
        result, size_field, new_size = patch(data, blob)
        with args.output.open("xb") as out:
            out.write(result)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"DarwinEnter VirtualSize (file {size_field:#x}): {OLD_SIZE:#x} -> {new_size:#x}")
    print(f"Replaced BR x1 with cyan checkpoint and BR x1 at file [{BRANCH:#x},{BRANCH+len(blob):#x})")
    print(f"{hashlib.sha256(result).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()
