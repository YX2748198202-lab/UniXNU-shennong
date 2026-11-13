#!/usr/bin/env python3
"""Map the frame buffer with one L2 table taken from the LAST page of the bootstrap pool.

scripts/patch-fb-map.py takes pool pages 4 and 5, but the trampoline builds its own tables
from page 2 up (two roots at +0x0000/+0x1000, then one L2 page per GiB of window, first for
the V=P root and then for the KVA root).  For a 4 GiB window that is 2 + 4 + 4 = 10 pages, so
pages 4 and 5 are the window's own L2 tables and the old cave overwrote them.

The pool is 16 pages (0xad830e4 clears 0x2000 qwords = 0x10000 bytes) and the trampoline aborts
into `b .` at 0xad8328c if it would run past +0x10000, so page 15 is the one page no window size
up to 6 GiB can take.  The frame buffer is 1440x3200x4 = 17.6 MiB, i.e. 9 blocks of 2 MiB, and a
single L2 table covers a whole GiB, so one page and one L1 slot (index 3 for VA 0xFC400000,
entry at root + 24) is enough.

Attributes: block + AttrIdx 3 + AF.  MAIR_EL1's byte 3 is 0x00 in this kernel (the value built at
0xad832c8 is 0x0c0000ff00bb44ff, whose bytes are ff 44 bb 00 ff 00 0c 00), i.e. Device-nGnRnE.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB000
SITE = 0xFFFFFFF00AD832C8          # `mov x0, xzr`, the first instruction of the MAIR setup
POOL_PAGE = 15                     # x25 + 0xF000
FB_BASE = 0xFC400000
FB_BLOCKS = 64                     # 64 x 2 MiB = 128 MiB, covers the 17.6 MiB frame buffer

ASM = f""".text
.global _start
_start:
  add  x9, x25, #{POOL_PAGE}, lsl #12
  mov  x11, #0x200
1:
  stp  xzr, xzr, [x9], #16
  subs x11, x11, #1
  b.ne 1b
  add  x12, x25, #{POOL_PAGE}, lsl #12
  orr  x12, x12, #3
  str  x12, [x25, #24]
  movz x15, #{FB_BASE >> 16:#x}, lsl #16
  add  x12, x25, #{POOL_PAGE}, lsl #12
  mov  x17, #{FB_BLOCKS}
2:
  mov  x16, #0x40d
  orr  x16, x16, x15
  str  x16, [x12], #8
  add  x15, x15, #0x200, lsl #12
  subs x17, x17, #1
  b.ne 2b
  dsb  ish
  mov  x0, xzr
  b    back
.ltorg
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-fb-simple'))
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location('probe', args.probe_tool)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
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
    print(f'fb simple cave {len(blob)} bytes at {CAVE_BASE:#x}; site {SITE:#x} was {old:#010x}')
    print(f'fb {FB_BASE:#x} + {FB_BLOCKS * 0x200000:#x} -> TTBR0 L1[3] via pool page {POOL_PAGE}')


if __name__ == '__main__':
    main()
