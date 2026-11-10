#!/usr/bin/env python3
"""Map the framebuffer twice and prove the cave runs.

Extends patch-fb-map.py with three things learned from the failed first
attempt:

* a white band painted *before* the MMU comes on, so a photo proves the cave
  itself executed (that write goes straight to the physical address);
* a second mapping in the KVA root, so post-MMU code can reach the same
  memory through the table the kernel definitely walks for kernel addresses;
* both mappings use 2 MiB device blocks taken from pool pages 4-7.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB000
BAND_BYTES = (5760 * 3200 // 16) & ~7

ASM = """.text
.global _start
_start:
  /* identity map: V=P root[3]/[4] -> pool pages 4/5 */
  add  x9,  x25, #4, lsl #12
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
  /* KVA alias: KVA root[195]/[196] -> pool pages 6/7 */
  add  x9,  x25, #6, lsl #12
  add  x10, x25, #7, lsl #12
  mov  x11, #0x200
5:
  stp  xzr, xzr, [x9], #16
  subs x11, x11, #1
  b.ne 5b
  mov  x11, #0x200
6:
  stp  xzr, xzr, [x10], #16
  subs x11, x11, #1
  b.ne 6b
  add  x13, x25, #0x1000
  add  x12, x25, #6, lsl #12
  orr  x12, x12, #3
  str  x12, [x13, #1560]
  add  x12, x25, #7, lsl #12
  orr  x12, x12, #3
  str  x12, [x13, #1568]
  movz x15, #0xfc40, lsl #16
  add  x12, x25, #6, lsl #12
  add  x12, x12, #3856
  mov  x17, #30
7:
  mov  x16, #0x40d
  orr  x16, x16, x15
  str  x16, [x12], #8
  add  x15, x15, #0x200, lsl #12
  subs x17, x17, #1
  b.ne 7b
  movz x15, #1, lsl #32
  add  x12, x25, #7, lsl #12
  mov  x17, #8
8:
  mov  x16, #0x40d
  orr  x16, x16, x15
  str  x16, [x12], #8
  add  x15, x15, #0x200, lsl #12
  subs x17, x17, #1
  b.ne 8b
  /* white band 0, written with the MMU still off */
  movz x15, #0xfc40, lsl #16
  movz x16, #0xffff
  movk x16, #0xffff, lsl #16
  movz x17, #0x9400
  movk x17, #0x11, lsl #16
9:
  stp  w16, w16, [x15], #8
  subs x17, x17, #8
  b.ne 9b
  mov  x0, xzr
  b    back
.ltorg
"""

SITE = 0xFFFFFFF00AD832C8


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
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-fb2'))
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
    print(f'fb map v2: {len(blob)} bytes at {CAVE_BASE:#x}; site {SITE:#x} was {old:#010x}')
    print(f'  identity VA {0xFC400000:#x} + KVA alias {0xFFFFFFF0FC400000:#x} -> PA 0xFC400000, {BAND_BYTES:#x} B/band')


if __name__ == '__main__':
    main()
