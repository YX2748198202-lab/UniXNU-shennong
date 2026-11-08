#!/usr/bin/env python3
"""Probe the gap between the MMU enable and _arm_init.

Paints one band per checkpoint, so a single photo says where the kernel died:

  band 0 white        first instruction after `msr sctlr_el1`
  band 1 red          the SCTLR magic self-check fell through
  band 2 green        _arm_init entered
  band 3 orange       synchronous exception taken at EL1h
  band 4 yellow       IRQ at EL1h
  band 5 yellow-green FIQ at EL1h
  band 6 cyan         SError at EL1h

The exception caves use no stack and no literal pool, so they still paint when
the translation regime is the thing that broke.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

FB_BASE = 0xFC400000
BAND_BYTES = (5760 * 3200 // 16) & ~7
CAVE_BASE = 0xFFFFFFF00B4F9700
CAVE_STRIDE = 0xE0

PAINT = """  movz x1, #{base_lo}
  movk x1, #{base_hi}, lsl 16
  movz w2, #{size_lo}
  movk w2, #{size_hi}, lsl 16
  mov x3, #{band}
  mul x4, x2, x3
  add x1, x1, x4
  movz w6, #{colour_lo}
  movk w6, #{colour_hi}, lsl 16
1:
  stp w6, w6, [x1], #8
  subs x2, x2, #8
  b.hi 1b
  dsb sy
"""

STEP = """.text
.global _start
_start:
  stp x29, x30, [sp, #-16]!
  stp x0, x1, [sp, #-16]!
  stp x2, x3, [sp, #-16]!
  stp x4, x5, [sp, #-16]!
{paint}  ldp x4, x5, [sp], #16
  ldp x2, x3, [sp], #16
  ldp x0, x1, [sp], #16
  ldp x29, x30, [sp], #16
  {displaced}
  b back
.ltorg
"""

TRAP = """.text
.global _start
_start:
{paint}  b .
.ltorg
"""

# (label, site, kind, displaced asm, band, colour)
MARKERS = [
    ('post-mmu',   0xFFFFFFF00AD8341C, 'step', 'isb',               0, 0xFFFFFFFF),
    ('guard-pass', 0xFFFFFFF00AD83438, 'step', 'mov x0, #0x300000',  1, 0xFFFF0000),
    ('arm-init',   0xFFFFFFF00B4768D0, 'step', 'pacibsp',            2, 0xFF00FF00),
    ('sync',       0xFFFFFFF00AD7C200, 'trap', '',                   3, 0xFFFF8000),
    ('irq',        0xFFFFFFF00AD7C280, 'trap', '',                   4, 0xFFFFFF00),
    ('fiq',        0xFFFFFFF00AD7C300, 'trap', '',                   5, 0xFF80FF00),
    ('serror',     0xFFFFFFF00AD7C380, 'trap', '',                   6, 0xFF00FFFF),
]


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
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-gap'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)  # validates the Mach-O the same way the other tools do

    args.workdir.mkdir(parents=True, exist_ok=True)
    for index, (label, site, kind, displaced, band, colour) in enumerate(MARKERS):
        cave = CAVE_BASE + index * CAVE_STRIDE
        paint = PAINT.format(
            base_lo=f'{FB_BASE & 0xFFFF:#x}', base_hi=f'{(FB_BASE >> 16) & 0xFFFF:#x}',
            size_lo=f'{BAND_BYTES & 0xFFFF:#x}',
            size_hi=f'{(BAND_BYTES >> 16) & 0xFFFF:#x}', band=index,
            colour_lo=f'{colour & 0xFFFF:#x}', colour_hi=f'{(colour >> 16) & 0xFFFF:#x}')
        if kind == 'step':
            source = STEP.format(paint=paint, displaced=displaced)
            binds = {'back': site + 4}
        else:
            source = TRAP.format(paint=paint)
            binds = {}
        blob = probe.assemble(source, cave, binds, args.workdir)
        if len(blob) > CAVE_STRIDE:
            raise SystemExit(f'cave {index} needs {len(blob)} bytes')
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        site_off = probe.file_offset(site)
        old = struct.unpack_from('<I', data, site_off)[0]
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        print(f'  band {index} {label:10s} site {site:#x} was {old:#010x} -> b {cave:#x} '
              f'({len(blob)} bytes)')
    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel}')


if __name__ == '__main__':
    main()
