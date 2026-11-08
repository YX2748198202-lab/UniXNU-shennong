#!/usr/bin/env python3
"""Turn the silent SCTLR self-loop into a recorded, non-fatal check.

After installing SCTLR_EL1 the trampoline compares the readback with the
constant 0xFC54793D and spins forever at 0xAD83434 when they differ.  A core
that reports different RES1 bits (ARMv9.x) therefore hangs without a trace.
This patch keeps the comparison, records 0x81 in the second slot word when it
fails, and continues on the normal path either way.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE = 0xFFFFFFF00B4F8800
SITE = 0xFFFFFFF00AD83430          # cmp x0, x1
RESUME = 0xFFFFFFF00AD83438        # mov x0, #0x300000
SLOT_VA = 0xFFFFFFF00C8BF000

ASM = """.text
.global _start
_start:
  cmp  x0, x1
  b.eq 2f
  movz x2, #0xf000
  movk x2, #0xc8b, lsl #16
  movk x2, #0xfff0, lsl #32
  movk x2, #0xffff, lsl #48
  add  x2, x2, #4
  mov  w3, #0x81
  str  w3, [x2]
2:
  b    back
.ltorg
"""


def load_probe(path):
    spec = importlib.util.spec_from_file_location('probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path('/tmp/probe/patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-guard'))
    args = parser.parse_args()
    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)
    args.workdir.mkdir(parents=True, exist_ok=True)
    blob = probe.assemble(ASM, CAVE, {'back': RESUME}, args.workdir)
    off = probe.file_offset(CAVE)
    data[off:off + len(blob)] = blob
    site_off = probe.file_offset(SITE)
    old_cmp = struct.unpack_from('<I', data, site_off)[0]
    old_bne = struct.unpack_from('<I', data, site_off + 4)[0]
    struct.pack_into('<I', data, site_off, probe.branch(SITE, CAVE))
    struct.pack_into('<I', data, site_off + 4, 0xD503201F)   # nop
    args.kernel.write_bytes(bytes(data))
    print(f'mmu guard patched: cave {len(blob)} bytes at {CAVE:#x}; '
          f'site {SITE:#x} was {old_cmp:#010x}/{old_bne:#010x}')


if __name__ == '__main__':
    main()
