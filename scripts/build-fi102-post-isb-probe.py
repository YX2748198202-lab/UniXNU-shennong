#!/usr/bin/env python3
"""Build the shennong fi102 post-ISB reset probe from the exact red-band control.

Diagnostic only: it deliberately stops the boot at the probe, requesting a
PSCI system reset after 16 seconds. Use only via temporary fastboot boot.
"""

import argparse
import hashlib
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile

CONTROL_SHA256 = "2a3df2dc544b69e1446e346349cc1159f9fc457a5ce8485f01dfc70bcd7a3072"
BAND_SITE = 0xFFFFFFF00AD8341C
BAND_VA = 0xFFFFFFF00AD81F20
ISB_VA = 0xFFFFFFF00AD81F84
BRANCH_VA = ISB_VA + 4
CONTINUATION_VA = 0xFFFFFFF00AD83420
# Band 15 saves eight registers in [0x...1f90, 0x...1fd0).
CAVE_VA = 0xFFFFFFF00AD81FD0
CAVE_CAPACITY = 0x30  # Stay in the same 4 KiB page as the original ISB.
ASM = """\
.text
    mrs x1, cntfrq_el0
    mrs x2, cntpct_el0
1:  isb
    mrs x3, cntpct_el0
    sub x3, x3, x2
    cmp x3, x1, lsl #4
    b.lo 1b
    movz w0, #0x8400, lsl #16
    movk w0, #9
    smc #0
2:  b 2b
"""


def assemble(clang, objcopy):
    with tempfile.TemporaryDirectory(prefix="fi102-post-isb-") as directory:
        obj = Path(directory) / "probe.o"
        raw = obj.with_suffix(".bin")
        subprocess.run([clang, "--target=aarch64-none-elf", "-x", "assembler",
                        "-c", "-", "-o", str(obj)], input=ASM, text=True, check=True)
        subprocess.run([objcopy, "-j", ".text", "-O", "binary", str(obj), str(raw)],
                       check=True)
        return raw.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--objcopy", default="llvm-objcopy-18")
    args = parser.parse_args()
    if args.out.exists():
        parser.exit(1, f"refusing to overwrite {args.out}\n")

    helpers = runpy.run_path(str(Path(__file__).with_name("build-fi102-entry-marker.py")))
    locate = helpers["locate"]
    read_pinned = helpers["read_pinned"]
    branch_target = helpers["branch_target"]
    branch_to = helpers["branch_to"]
    try:
        image = read_pinned(args.control, CONTROL_SHA256)
        pristine = read_pinned(args.pristine, helpers["PRISTINE_SHA256"])
        site = locate(image, BAND_SITE, 4)
        if branch_target(struct.unpack_from("<I", image, site)[0], BAND_SITE) != BAND_VA:
            raise ValueError("unexpected band 15 dispatch")
        isb = locate(image, ISB_VA, 8)
        before_isb, before_branch = struct.unpack_from("<II", image, isb)
        if before_isb != 0xd5033fdf or branch_target(before_branch, BRANCH_VA) != CONTINUATION_VA:
            raise ValueError("expected original ISB followed by the original continuation")
        cave = locate(image, CAVE_VA, CAVE_CAPACITY)
        end = cave + CAVE_CAPACITY
        if (locate(pristine, CAVE_VA, CAVE_CAPACITY) != cave
                or image[cave:end] != bytes(CAVE_CAPACITY)
                or pristine[cave:end] != bytes(CAVE_CAPACITY)):
            raise ValueError("RX cave must be zero at the same offset in both inputs")
        probe = assemble(args.clang, args.objcopy)
        if len(probe) != 44 or len(probe) > CAVE_CAPACITY:
            raise ValueError(f"unexpected probe size: {len(probe)}")
        new_branch = branch_to(BRANCH_VA, CAVE_VA)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}; no output was written\n")

    branch = isb + 4
    with args.out.open("xb") as out:
        out.write(image[:branch])
        out.write(new_branch)
        out.write(image[branch + 4:cave])
        out.write(probe)
        out.write(image[cave + len(probe):])
    print(f"Original ISB preserved at {ISB_VA:#x} (file {isb:#x})")
    print(f"VA {BRANCH_VA:#x} file {branch:#x}: {image[branch:branch+4].hex()} -> {new_branch.hex()}")
    print(f"__TEXT_EXEC RX cave: VA {CAVE_VA:#x}, file [{cave:#x}, {cave + len(probe):#x})")
    for i in range(0, len(probe), 4):
        print(f"VA {CAVE_VA + i:#x} file {cave + i:#x}: 00000000 -> {probe[i:i+4].hex()}")
    with args.out.open("rb") as out:
        print(f"{hashlib.file_digest(out, 'sha256').hexdigest()}  {args.out}")


if __name__ == "__main__":
    main()
