#!/usr/bin/env python3
"""Map the framebuffer into the kernel's TTBR1 at a private slot.

The old patch-fb-map.py put the mapping in TTBR0's L1 index 3/4 - that slot
covers 0xC0000000..0xFFFFFFFF, which is ordinary DRAM the kernel is actively
using, so overwriting it killed the kernel (fi52b/fi53/fi57 all hung).

TTBR1 is the kernel's own KVA table and the trampoline only fills index 0xC0
(the kernel image), so index 1 is free: it sits 47 TiB below the image and no
DRAM window maps there. This builds an L2 on bootstrap pool page 4 with 64 2 MiB
device blocks covering the 128 MiB from the framebuffer base, and points TTBR1
L1[1] at it. KVA 0xFFFFFFC000000000 then aliases PA 0xFC400000.

Runs at the MAIR setup site, where x25 holds the pool base and the MMU is still
off, so every access below is a physical one (V=P).
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB000
FB_BASE   = 0xFC400000
FB_BLOCKS = 64                 # 64 * 2 MiB = 128 MiB, the frame buffer is 17.6 MiB

ASM = """.text
.global _start
_start:
  /* pool page 4 -> L2 for TTBR1 L1[1] */
  add   x9, x25, #4, lsl #12
  mov   x11, #0x200
1:
  stp   xzr, xzr, [x9], #16
  subs  x11, x11, #1
  b.ne  1b
  add   x12, x25, #4, lsl #12
  orr   x13, x12, #3
  str   x13, [x25, #0x1008]      /* TTBR1 root (pool page 1) + L1 index 1 */
  movz  x15, #0xfc40, lsl #16
  mov   x17, #{blocks}
2:
  mov   x16, #0x40d              /* block + AttrIdx 3 (Device) + AF */
  orr   x16, x16, x15
  str   x16, [x12], #8
  add   x15, x15, #0x200, lsl #12
  subs  x17, x17, #1
  b.ne  2b
  .inst {restore}
  b     back
.ltorg
"""

SITE = 0xFFFFFFF00AD832C8       # mov x0, xzr (orr x0,xzr,xzr), first insn of the MAIR setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-fb-ttbr1'))
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location('probe', args.probe_tool)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)
    args.workdir.mkdir(parents=True, exist_ok=True)

    site_off = probe.file_offset(SITE)
    old = struct.unpack_from('<I', data, site_off)[0]
    if old not in (0xD2800000, 0xAA1F03E0):      # movz x0,#0 / orr x0,xzr,xzr
        raise SystemExit(f'{SITE:#x} is {old:#010x}, expected mov x0, xzr')

    blob = probe.assemble(ASM.format(blocks=FB_BLOCKS, restore=f'{old:#010x}'),
                          CAVE_BASE, {'back': SITE + 4}, args.workdir)
    off = probe.file_offset(CAVE_BASE)
    data[off:off + len(blob)] = blob
    struct.pack_into('<I', data, site_off, probe.branch(SITE, CAVE_BASE))
    args.kernel.write_bytes(bytes(data))
    print(f'fb map (TTBR1 L1[1]) cave {len(blob)} bytes at {CAVE_BASE:#x}')
    print(f'  PA {FB_BASE:#x} .. +{FB_BLOCKS * 0x200000:#x} -> KVA 0xFFFFFFC000000000')


if __name__ == '__main__':
    main()
