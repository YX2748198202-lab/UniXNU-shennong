#!/usr/bin/env python3
"""Map the framebuffer into the kernel bootstrap tables.

The trampoline builds a V=P table (installed as TTBR0 through _set_mmu_ttb) and
a KVA table (TTBR1) covering only the kernel window handed over in boot_args.
The framebuffer lies outside that window, so every band painted after the MMU
comes on faults and the screen stays at the loader bands.  The 16-page
bootstrap pool uses pages 0-1 for the two roots and pages 2-3 for the window's
L2 tables, so this cave takes pages 4-5 for the framebuffer's two 1 GiB L1
slots and fills them with 2 MiB device blocks.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB000
FB_BASE = 0xFC400000
FB_BYTES = 5760 * 3200 * 4

ASM = """.text
.global _start
_start:
  add  x9, x25, #4, lsl #12
  add  x10, x25, #5, lsl #12
  mov  x11, #0x200
1:
  stp  xzr, xzr, [x9], #16
  subs x11, x11, #1
  b.ne 1b
  mov  x11, #0x200
2:
  stp  xzr, xzr, [x10], #16
  subs x11, x11, #1
  b.ne 2b
  add  x12, x25, #4, lsl #12
  orr  x12, x12, #3
  str  x12, [x25, #24]
  add  x12, x25, #5, lsl #12
  orr  x12, x12, #3
  str  x12, [x25, #32]
  movz x15, #0xfc40, lsl #16
  add  x12, x25, #4, lsl #12
  add  x12, x12, #3856
  mov  x17, #30
3:
  mov  x16, #0x40d
  orr  x16, x16, x15
  str  x16, [x12], #8
  add  x15, x15, #0x200, lsl #12
  subs x17, x17, #1
  b.ne 3b
  movz x15, #1, lsl #32
  add  x12, x25, #5, lsl #12
  mov  x17, #8
4:
  mov  x16, #0x40d
  orr  x16, x16, x15
  str  x16, [x12], #8
  add  x15, x15, #0x200, lsl #12
  subs x17, x17, #1
  b.ne 4b
  mov  x0, xzr
  b    back
.ltorg
"""

SITE = 0xFFFFFFF00AD832C8   # mov x0, xzr  (first instruction of the MAIR setup)


def load_probe(path):
    spec = importlib.util.spec_from_file_location('probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-fb'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)

    args.workdir.mkdir(parents=True, exist_ok=True)
    blob = probe.assemble(ASM, CAVE_BASE, {'back': SITE + 4}, args.workdir)
    off = probe.file_offset(CAVE_BASE)
    data[off:off + len(blob)] = blob
    site_off = probe.file_offset(SITE)
    old = struct.unpack_from('<I', data, site_off)[0]
    struct.pack_into('<I', data, site_off, probe.branch(SITE, CAVE_BASE))
    args.kernel.write_bytes(bytes(data))
    print(f'fb map cave {len(blob)} bytes at {CAVE_BASE:#x};'
          f' site {SITE:#x} was {old:#010x}')
    print(f'fb {FB_BASE:#x} + {FB_BYTES:#x} bytes -> L1 3/4, L2 482..511 + 0..7')


if __name__ == '__main__':
    main()
