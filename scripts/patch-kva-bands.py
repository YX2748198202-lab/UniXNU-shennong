#!/usr/bin/env python3
"""Band probes that paint through the framebuffer's KVA alias.

The kernel's bootstrap TTBR1 table is the one it certainly walks for kernel
addresses, so painting through 0xFFFFFFF0FC400000 + band offset shows kernel
progress even when the identity (TTBR0) side is suspect.  Requires
patch-fb-map2.py, which maps that alias and also paints band 0 white before the
MMU comes on so a photo proves the cave executed at all.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4F8000
BAND_BYTES = (5760 * 3200 // 16) & ~7
COLOURS = [0xFFFFFFFF, 0xFFFF0000, 0xFFFF8000, 0xFFFFFF00, 0xFF80FF00,
           0xFF00FF00, 0xFF00FF80, 0xFF00FFFF, 0xFF0080FF, 0xFF0000FF,
           0xFF8000FF, 0xFFFF00FF, 0xFFFF0080, 0xFF804000, 0xFF808080,
           0xFFC0FF00]

PAINT = """.text
.global _start
_start:
  stp  x29, x30, [sp, #-0x10]!
  stp  x0, x1, [sp, #-0x10]!
  stp  x2, x3, [sp, #-0x10]!
  stp  x4, x5, [sp, #-0x10]!
  movz x1, #0xfc40, lsl #16
  movk x1, #0xfff0, lsl #32
  movk x1, #0xffff, lsl #48
  movz x4, #0x{off_lo}
  movk x4, #0x{off_hi}, lsl #16
  add  x1, x1, x4
  movz x2, #0x9400
  movk x2, #0x11, lsl #16
  movz w3, #0x{col_lo}
  movk w3, #0x{col_hi}, lsl #16
1:
  stp  w3, w3, [x1], #8
  subs x2, x2, #8
  b.ne 1b
  ldp  x4, x5, [sp], #0x10
  ldp  x2, x3, [sp], #0x10
  ldp  x0, x1, [sp], #0x10
  ldp  x29, x30, [sp], #0x10
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
                        default=Path('/tmp/probe/patch-xnu-entry-probe.py'))
    parser.add_argument('--from-call', type=int, default=1)
    parser.add_argument('--calls', type=int, default=12)
    parser.add_argument('--no-entry', action='store_true')
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-kva'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)
    args.workdir.mkdir(parents=True, exist_ok=True)

    raw_symbols = probe.kernel_symbols(args.kernel)
    symbols = {name: va for va, name in raw_symbols.items()}
    arm_init = symbols['_arm_init']
    low, high = probe.function_range(raw_symbols, '_arm_init')
    calls = []
    for va in range(low, high, 4):
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        if word >> 26 == 0b100101:
            calls.append(va)
    markers = []
    if not args.no_entry:
        markers.append(('entry', arm_init))
    for i in range(args.from_call, args.from_call + args.calls):
        markers.append((f'call {i}', calls[i - 1]))

    for index, (label, site) in enumerate(markers[:len(COLOURS) - 1]):
        band = index + 1   # band 0 is reserved for the cave's pre-MMU white proof
        colour = COLOURS[band]
        offset = band * BAND_BYTES
        site_off = probe.file_offset(site)
        original = struct.unpack_from('<I', data, site_off)[0]
        asm = PAINT.format(off_lo=f'{offset & 0xFFFF:04x}',
                           off_hi=f'{(offset >> 16) & 0xFFFF:04x}',
                           col_lo=f'{colour & 0xFFFF:04x}',
                           col_hi=f'{(colour >> 16) & 0xFFFF:04x}',
                           tail=f'.inst {original:#010x}')
        cave = CAVE_BASE + band * 0x100
        blob = probe.assemble(asm, cave, {'back': site + 4}, args.workdir)
        assert len(blob) <= 0x100, f'cave {band} is {len(blob)} bytes'
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        print(f'  band {band:2d} {label:8s} site {site:#x} cave {cave:#x} colour {colour:#010x}')
    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel} with {len(markers)} KVA-alias bands')


if __name__ == '__main__':
    main()
