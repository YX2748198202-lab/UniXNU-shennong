#!/usr/bin/env python3
"""Prepend a boot_args-independent red marker in the archived fi102 probe slot.

Use only with the exact yellow-marker DarwinBoot built in a33f4f4, on shennong.
The marker consumes x11 as a framebuffer cursor; this is a diagnostic pairing,
not a general DarwinBoot ABI. The input files are never modified.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

FI102_SHA256 = "800b4412fd125aef002035d552d4ff47af8588902a3da2de8f19ebd11f94a976"
PRISTINE_SHA256 = "31e33289e188085f21a63599809e7e69d75f53d5b5b8c29dddc79bb9de9af1f7"
LOADER_SHA256 = "3f4683aeca36644eb715f7124b0f5129a649141b7f2b518bfedb78341b848184"
ENTRY_VA = 0xfffffff00ad81488
PROBE_VA = 0xfffffff00ad81500
START_FIRST_CPU_VA = 0xfffffff00ad8305c
SLOT_SIZE = 0x60
ORIGINAL_SIZE = 0x40
MARKER_SIZE = SLOT_SIZE - ORIGINAL_SIZE


def read_pinned(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"unexpected SHA-256 for {path}")
    return data


def locate(data, va, length):
    magic, cputype, _, filetype, ncmds = struct.unpack_from("<IIIII", data)
    if (magic, cputype, filetype) != (0xfeedfacf, 0x0100000c, 0xc):
        raise ValueError("expected an arm64 Mach-O fileset")
    matches = []
    entries = []
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if size < 8 or off + size > len(data):
            raise ValueError("invalid load command size")
        if cmd == 0x19:
            name, base, vsize, fbase, fsize, _, prot = struct.unpack_from("<16sQQQQii", data, off + 8)
            if base <= va and va + length <= base + min(vsize, fsize):
                if name.rstrip(b"\0") != b"__TEXT_EXEC" or prot != 5:
                    raise ValueError("probe extent is not in RX __TEXT_EXEC")
                matches.append(fbase + va - base)
        if cmd == 5:
            entries.append(struct.unpack_from("<Q", data, off + 16 + 32 * 8)[0])
        off += size
    if entries != [ENTRY_VA] or len(matches) != 1 or matches[0] + length > len(data):
        raise ValueError("unexpected LC_UNIXTHREAD or file-backed mapping")
    return matches[0]


def branch_target(word, pc):
    if word >> 26 != 0b000101:
        raise ValueError(f"expected an A64 B at {pc:#x}")
    imm = word & 0x03ffffff
    return pc + ((imm ^ 0x02000000) - 0x02000000) * 4


def branch_to(pc, dest):
    delta = dest - pc
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError("A64 B displacement not encodable")
    return struct.pack("<I", 0x14000000 | ((delta // 4) & 0x03ffffff))


def assemble(clang, objcopy):
    source = Path(__file__).with_name("fi102-entry-marker.S")
    with tempfile.TemporaryDirectory(prefix="fi102-entry-marker-") as tmp:
        obj = Path(tmp) / "marker.o"
        raw = obj.with_suffix(".bin")
        subprocess.run([clang, "--target=aarch64-none-elf", "-c", str(source), "-o", str(obj)],
                       check=True)
        subprocess.run([objcopy, "-j", ".text", "-O", "binary", str(obj), str(raw)], check=True)
        return raw.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--fi102", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    args = parser.parse_args()
    if args.out.exists():
        parser.exit(1, f"refusing to overwrite {args.out}\n")
    try:
        read_pinned(args.loader, LOADER_SHA256)
        pristine = read_pinned(args.pristine, PRISTINE_SHA256)
        fi102 = read_pinned(args.fi102, FI102_SHA256)
        entry = locate(fi102, ENTRY_VA, 4)
        start = locate(fi102, PROBE_VA, SLOT_SIZE)
        pristine_start = locate(pristine, PROBE_VA, SLOT_SIZE)
        end = start + SLOT_SIZE
        if pristine_start != start or pristine[start:end] != bytes(SLOT_SIZE):
            raise ValueError("pristine probe slot is not all zero")
        if branch_target(struct.unpack_from("<I", fi102, entry)[0], ENTRY_VA) != PROBE_VA:
            raise ValueError("entry branch does not target the stage-1 probe")
        before = fi102[start:end]
        if before[ORIGINAL_SIZE:] != bytes(MARKER_SIZE):
            raise ValueError("fi102 probe tail is not empty")
        tail_pc = PROBE_VA + ORIGINAL_SIZE - 4
        target = branch_target(struct.unpack_from("<I", before, ORIGINAL_SIZE - 4)[0], tail_pc)
        if target != START_FIRST_CPU_VA:
            raise ValueError("unexpected original continuation")
        marker = assemble(args.clang, args.objcopy)
        if len(marker) != MARKER_SIZE:
            raise ValueError(f"marker is {len(marker)} bytes, expected {MARKER_SIZE}")
        continuation = branch_to(tail_pc + MARKER_SIZE, target)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}; no output was written\n")

    after = marker + before[:ORIGINAL_SIZE - 4] + continuation
    with args.out.open("xb") as out:
        out.write(fi102[:start])
        out.write(after)
        out.write(fi102[end:])
    print(f"__TEXT_EXEC RX slot: VA {PROBE_VA:#x}, file [{start:#x}, {end:#x})")
    print(f"original blue probe preserved; tail B {tail_pc:#x} -> {tail_pc + MARKER_SIZE:#x}, target {target:#x}")
    for i in range(0, SLOT_SIZE, 4):
        print(f"VA {PROBE_VA + i:#x} file {start + i:#x}: {before[i:i+4].hex()} -> {after[i:i+4].hex()}")
    with args.out.open("rb") as out:
        print(f"{hashlib.file_digest(out, 'sha256').hexdigest()}  {args.out}")


if __name__ == "__main__":
    main()
