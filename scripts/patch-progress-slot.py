#!/usr/bin/env python3
"""Record early boot progress in DRAM and show it on the *next* boot.

Painting after the MMU comes on has proven unreliable: the framebuffer sits
outside the 256 MiB bootstrap window and every attempt to map it back in has
produced no visible output.  This probe sidesteps the problem completely:

* each marker inside _arm_init stores its index into a fixed slot in DRAM
  (a plain store through the kernel's KVA window, no framebuffer involved);
* the cave that runs *before* the MMU comes on reads that slot with the MMU
  off, paints one white band plus eight bit bands, and clears the slot.

So the screen of boot N+1 reports the last marker reached by boot N, drawn at
a stage where framebuffer writes are known to work.

Slot: PA 0x0DBF804000 == boot_args.PhysicalBase + 0xF800000,
      VA 0xFFFFFFF016804000 (inside the handed-over window).
"""
import argparse
import importlib.util
import struct
from pathlib import Path

READ_BASE = 0xFFFFFFF00B4F8000
MARK_BASE = 0xFFFFFFF00B4F9000
MARK_STRIDE = 0x80
BAND_BYTES = (5760 * 3200 // 16) & ~7
SLOT_PA = 0x0DB58B4000 + 0xF000   # bootstrap pool page 15 (runtime: x25 + 0xF000)
SLOT_VA = 0xFFFFFFF00C8BF000     # same page seen through the KVA window
INJECT = 0xFFFFFFF00AD83088      # ldr x26,[x20,#0x470]; x25 (pool) set, pool not zeroed yet
WHITE = 0xFFFFFFFF
BLACK = 0xFF000000

READ_ASM = """.text
.global _start
_start:
  /* read the slot with the MMU off: bootstrap pool page 15, before it is zeroed */
  add  x9, x25, #0xf, lsl #12
  ldr  w19, [x9]
  str  wzr, [x9]
  /* band 0: white, proves the readout ran */
  movz x10, #0xfc40, lsl #16
  movz x11, #0x9400
  movk x11, #0x11, lsl #16
  mov  x16, x11
  movz w12, #0xffff
  movk w12, #0xffff, lsl #16
1:
  stp  w12, w12, [x10], #8
  subs x16, x16, #8
  b.ne 1b
  /* bands 1..8: bit0..bit7 of the recorded index, white = set */
  mov  x13, #1
  mov  x14, #8
2:
  and  x15, x19, x13
  cbz  x15, 3f
  movz w12, #0xffff
  movk w12, #0xffff, lsl #16
  b    4f
3:
  movz w12, #0x0000
  movk w12, #0x0000, lsl #16
4:
  mov  x16, x11
5:
  stp  w12, w12, [x10], #8
  subs x16, x16, #8
  b.ne 5b
  lsl  x13, x13, #1
  subs x14, x14, #1
  b.ne 2b
  {tail}
  b    back
.ltorg
"""

MARK_ASM = """.text
.global _start
_start:
  stp  x29, x30, [sp, #-0x10]!
  stp  x0, x1, [sp, #-0x10]!
  movz x1, #0x{slot_lo}
  movk x1, #0x{slot_hi}, lsl #16
  movk x1, #0x{slot_hi2}, lsl #32
  movk x1, #0x{slot_top}, lsl #48
  movz w0, #{index}
  str  w0, [x1]
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


def chunks(value):
    return [(value >> shift) & 0xFFFF for shift in (32, 48)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path('/tmp/probe/patch-xnu-entry-probe.py'))
    parser.add_argument('--markers', type=int, default=20)
    parser.add_argument('--pre-sites', default='',
                        help='comma separated value@address markers placed before _arm_init')
    parser.add_argument('--start-index', type=int, default=1)
    parser.add_argument('--sites', default='',
                        help='value@target[,...] where target is sym:NAME or 0xADDR; replaces the default plan')
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-slot'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    raw_symbols = probe.kernel_symbols(args.kernel)
    symbols = {name: va for va, name in raw_symbols.items()}
    args.workdir.mkdir(parents=True, exist_ok=True)

    lo_, hi_, hi2_, top_ = [(SLOT_VA >> s) & 0xFFFF for s in (0, 16, 32, 48)]
    # readout cave, injected before the MMU comes on
    site_off = probe.file_offset(INJECT)
    displaced = struct.unpack_from('<I', data, site_off)[0]
    asm = READ_ASM.format(tail=f'.inst {displaced:#010x}')
    blob = probe.assemble(asm, READ_BASE, {'back': INJECT + 4}, args.workdir)
    off = probe.file_offset(READ_BASE)
    data[off:off + len(blob)] = blob
    site_off = probe.file_offset(INJECT)
    print(f'readout cave {len(blob)} bytes at {READ_BASE:#x}; slot PA {SLOT_PA:#x}')
    struct.pack_into('<I', data, site_off, probe.branch(INJECT, READ_BASE))

    # marker caves inside _arm_init
    low, high = probe.function_range(raw_symbols, '_arm_init')
    calls = [va for va in range(low, high, 4)
             if struct.unpack_from('<I', data, probe.file_offset(va))[0] >> 26 == 0b100101]
    explicit = []
    for item in filter(None, (piece.strip() for piece in args.sites.split(','))):
        value, target = item.split('@')
        target = target.strip()
        address = symbols[target[4:]] if target.startswith('sym:') else int(target, 0)
        explicit.append((int(value, 0), address))
    if explicit:
        for value, address in explicit:
            site_off = probe.file_offset(address)
            original = struct.unpack_from('<I', data, site_off)[0]
            asm = MARK_ASM.format(slot_lo=f'{lo_:04x}', slot_hi=f'{hi_:04x}',
                                  slot_hi2=f'{hi2_:04x}', slot_top=f'{top_:04x}',
                                  index=value, tail=f'.inst {original:#010x}')
            cave = MARK_BASE + (value - 1) * MARK_STRIDE
            blob = probe.assemble(asm, cave, {'back': address + 4}, args.workdir)
            assert len(blob) <= MARK_STRIDE, f'cave {value} is {len(blob)} bytes'
            off = probe.file_offset(cave)
            data[off:off + len(blob)] = blob
            struct.pack_into('<I', data, site_off, probe.branch(address, cave))
            print(f'  marker {value:2d} -> {address:#x}')
        args.kernel.write_bytes(bytes(data))
        print(f'patched {args.kernel} with {len(explicit)} chain markers')
        return
    pre = []
    for item in filter(None, (piece.strip() for piece in args.pre_sites.split(','))):
        value, address = item.split('@')
        pre.append((int(value, 0), int(address, 0)))
    if pre:
        for value, address in pre:
            site_off = probe.file_offset(address)
            original = struct.unpack_from('<I', data, site_off)[0]
            asm = MARK_ASM.format(slot_lo=f'{lo_:04x}', slot_hi=f'{hi_:04x}',
                                  slot_hi2=f'{hi2_:04x}', slot_top=f'{top_:04x}',
                                  index=value, tail=f'.inst {original:#010x}')
            cave = MARK_BASE + (value - 1) * MARK_STRIDE
            blob = probe.assemble(asm, cave, {'back': address + 4}, args.workdir)
            assert len(blob) <= MARK_STRIDE, f'pre cave {value} is {len(blob)} bytes'
            off = probe.file_offset(cave)
            data[off:off + len(blob)] = blob
            struct.pack_into('<I', data, site_off, probe.branch(address, cave))
    sites = [symbols['_arm_init']] + calls[:args.markers]
    for index, site in enumerate(sites, start=args.start_index + len(pre)):
        site_off = probe.file_offset(site)
        original = struct.unpack_from('<I', data, site_off)[0]
        asm = MARK_ASM.format(slot_lo=f'{lo_:04x}', slot_hi=f'{hi_:04x}',
                              slot_hi2=f'{hi2_:04x}', slot_top=f'{top_:04x}',
                              index=index, tail=f'.inst {original:#010x}')
        cave = MARK_BASE + (index - 1) * MARK_STRIDE
        blob = probe.assemble(asm, cave, {'back': site + 4}, args.workdir)
        assert len(blob) <= MARK_STRIDE, f'cave {index} is {len(blob)} bytes'
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel} with {len(pre)} pre markers and {len(sites)} arm_init markers'
          f' (indices {args.start_index}..{args.start_index + len(pre) + len(sites) - 1})')


if __name__ == '__main__':
    main()
