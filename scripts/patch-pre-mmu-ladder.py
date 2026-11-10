#!/usr/bin/env python3
"""Band ladder through the MMU-off window just before the MMU comes on.

The kernel paints a white band at 0xAD81560 immediately before it installs
SCTLR_EL1, but the screen still shows the loader's magenta band there, so the
kernel never reaches that point.  Everything between 0xAD832CC (MAIR/TCR2 setup)
and 0xAD83418 (the branch into 0xAD81560) runs with the MMU off, so a band
painted there is always visible: one band per checkpoint pinpoints the exact
instruction that kills the boot.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4F6000
BAND_BYTES = (5760 * 3200 // 16) & ~7
COLOURS = [0xFFFFFFFF, 0xFFFF0000, 0xFFFF8000, 0xFFFFFF00, 0xFF80FF00,
           0xFF00FF00, 0xFF00FF80, 0xFF00FFFF, 0xFF0080FF, 0xFF0000FF,
           0xFF8000FF, 0xFFFF00FF, 0xFFFF0080, 0xFF804000, 0xFF808080,
           0xFFC0FF00]
SITES = [
    0xFFFFFFF00AD832CC,   # after mair build starts (x0 = attr bits)
    0xFFFFFFF00AD8330C,   # msr mair_el1
    0xFFFFFFF00AD83314,   # tlbi vmalle1
    0xFFFFFFF00AD83320,   # vbar setup
    0xFFFFFFF00AD83330,   # pac key constants
    0xFFFFFFF00AD83360,   # pac keys mid
    0xFFFFFFF00AD833A0,   # pac keys late
    0xFFFFFFF00AD833F0,   # apdbkey writes
    0xFFFFFFF00AD83404,   # isb after apgakey
    0xFFFFFFF00AD83408,   # guard constant setup
    0xFFFFFFF00AD83418,   # branch into 0xAD81560 (paints white, installs SCTLR)
]

ASM = """.text
.global _start
_start:
  movz x9, #0xfc40, lsl #16
  movz x10, #0x{off_lo}
  movk x10, #0x{off_hi}, lsl #16
  add  x9, x9, x10
  movz x12, #0x9400
  movk x12, #0x11, lsl #16
  movz w11, #0x{col_lo}
  movk w11, #0x{col_hi}, lsl #16
1:
  stp  w11, w11, [x9], #8
  subs x12, x12, #8
  b.ne 1b
  {tail}
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
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-pre'))
    args = parser.parse_args()
    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)
    args.workdir.mkdir(parents=True, exist_ok=True)
    for index, site in enumerate(SITES):
        site_off = probe.file_offset(site)
        original = struct.unpack_from('<I', data, site_off)[0]
        offset = index * BAND_BYTES
        colour = COLOURS[index]
        asm = ASM.format(off_lo=f'{offset & 0xFFFF:04x}', off_hi=f'{(offset >> 16) & 0xFFFF:04x}',
                         col_lo=f'{colour & 0xFFFF:04x}', col_hi=f'{(colour >> 16) & 0xFFFF:04x}',
                         tail=f'.inst {original:#010x}')
        cave = CAVE_BASE + index * 0x100
        blob = probe.assemble(asm, cave, {'back': site + 4}, args.workdir)
        assert len(blob) <= 0x100, f'cave {index} is {len(blob)} bytes'
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        print(f'  band {index:2d} at {site:#x} colour {colour:#010x} ({len(blob)} bytes)')
    args.kernel.write_bytes(bytes(data))
    print(f'pre-MMU ladder: {len(SITES)} checkpoints')


if __name__ == '__main__':
    main()
