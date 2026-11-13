#!/usr/bin/env python3
"""Paint the beacon slot as bands on the next boot, before the MMU comes on.

fi70/fi71 settled the frame buffer question for good: an EL1 kernel cannot write 0xFC400000. The
mapping exists and the store does not fault - it is simply dropped (protected display aperture on
this SoC). The firmware and the pre-MMU trampoline can write it; that is where the green and blue
bars come from.

So a checkpoint (fb_beacon) records its tag into kernel BSS, and this cave - injected at the MAIR
setup, where the MMU is still off and physical addresses are directly addressable - reads the slot
back and paints it as nine bands:

    band 0        white: the readout itself ran
    bands 1..8    bit0..bit7 of the recorded tag, white = set

The frame buffer's physical address is constant across this board's boots (loader prints
video base=0xfc400000 every time), and so is the kernel's slide, so the slot's physical address is
computed at build time from the kernel's own symbols rather than read from boot_args.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB800
SITE = 0xFFFFFFF00AD832C8       # mov x0, xzr (orr x0,xzr,xzr), first insn of the MAIR setup
KERNEL_VA = 0xFFFFFFF007004000  # loader-reported, stable on this board
KERNEL_PA = 0x8C0004000
SLOT_OFFSET = 0x800
BAND_ROWS = 20                  # pixels per tag band
ROW_BYTES = 5760                # 1440 px * 4
BAND_BYTES = BAND_ROWS * ROW_BYTES          # 0x1c200
FILL_WORDS = BAND_BYTES // 8                # stp writes 2 words at a time
SCREEN_ROWS = 3200
MARKER_ROWS = 200               # the bottom marker band, impossible to confuse with any other bar
TAG_TOP_ROW = 2800              # tag bands sit at 2800..2960, just above the marker
TAG_OFF = TAG_TOP_ROW * ROW_BYTES
MARKER_FILL = MARKER_ROWS * ROW_BYTES // 8

ASM = """.text
.global _start
_start:
  movz x3, #{pa_lo}, lsl #0
  movk x3, #{pa_16}, lsl #16
  movk x3, #{pa_32}, lsl #32
  movk x3, #{pa_48}, lsl #48
  ldr  w20, [x3]                 /* recorded tag, physical read */

  movz x10, #{fb_lo}, lsl #0
  movk x10, #{fb_16}, lsl #16    /* x10 = frame buffer physical base */
  movz x9, #{tag_off_lo}
  movk x9, #{tag_off_hi}, lsl #16
  add  x10, x10, x9              /* skip to TAG_TOP_ROW */

  mov  x14, #8                   /* eight tag bands, bit7..bit0 top to bottom */
1:
  sub  x17, x14, #1
  lsr  x15, x20, x17
  and  x15, x15, #1
  cbz  x15, 2f
  movz w12, #0xffff
  movk w12, #0xffff, lsl #16     /* bit set: white */
  b    3f
2:
  movz w12, #0
  movk w12, #0, lsl #16          /* bit clear: black */
3:
  mov  x16, #{band_fill}
4:
  stp  w12, w12, [x10], #8
  subs x16, x16, #1
  b.ne 4b
  subs x14, x14, #1
  b.ne 1b

  /* marker band: 200 rows of solid white at the very bottom, proving this cave ran */
  movz w12, #0xffff
  movk w12, #0xffff, lsl #16
  movz x16, #{mk_lo}
  movk x16, #{mk_hi}, lsl #16
5:
  stp  w12, w12, [x10], #8
  subs x16, x16, #1
  b.ne 5b

  .inst {displaced}
  b    back
.ltorg
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-slot-bands'))
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location('probe', args.probe_tool)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    syms = probe.kernel_symbols(args.kernel)
    names = {n: va for va, n in syms.items() if isinstance(va, int)}
    pt = names['_boot_progress_panic_text']
    slot_pa = pt + SLOT_OFFSET - KERNEL_VA + KERNEL_PA

    site_off = probe.file_offset(SITE)
    displaced = struct.unpack_from('<I', data, site_off)[0]
    if displaced not in (0xD2800000, 0xAA1F03E0):
        raise SystemExit(f'{SITE:#x} is {displaced:#010x}, expected mov x0, xzr')

    args.workdir.mkdir(parents=True, exist_ok=True)
    asm = ASM.format(pa_lo=f'{slot_pa & 0xffff:#x}', pa_16=f'{(slot_pa >> 16) & 0xffff:#x}',
                     pa_32=f'{(slot_pa >> 32) & 0xffff:#x}', pa_48=f'{(slot_pa >> 48) & 0xffff:#x}',
                     fb_lo='0x0000', fb_16='0xfc40',
                     tag_off_lo=f'{TAG_OFF & 0xffff:#x}', tag_off_hi=f'{(TAG_OFF >> 16) & 0xffff:#x}',
                     band_fill=f'{FILL_WORDS:#x}',
                     mk_lo=f'{MARKER_FILL & 0xffff:#x}', mk_hi=f'{(MARKER_FILL >> 16) & 0xffff:#x}',
                     displaced=f'{displaced:#010x}')
    blob = probe.assemble(asm, CAVE_BASE, {'back': SITE + 4}, args.workdir)
    off = probe.file_offset(CAVE_BASE)
    data[off:off + len(blob)] = blob
    struct.pack_into('<I', data, site_off, probe.branch(SITE, CAVE_BASE))
    args.kernel.write_bytes(bytes(data))
    print(f'slot bands {len(blob)} bytes at {CAVE_BASE:#x}; slot PA {slot_pa:#x} '
          f'(_boot_progress_panic_text {pt:#x} + {SLOT_OFFSET:#x})')


if __name__ == '__main__':
    main()
