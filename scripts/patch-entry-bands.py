#!/usr/bin/env python3
"""Paint a differently coloured band at each checkpoint inside _start_first_cpu.

The kernel dies between the entry and `msr sctlr_el1` without a word: no panic, no reset.
`_start_first_cpu` already stores boot_args in x20 and the frame buffer geometry is at
boot_args+0x28/+0x38/+0x48, so every checkpoint can paint without needing any kernel
subsystem - and it works with the MMU still off.

Each checkpoint is a branch into a cave that
  * saves x0..x7 (PAINT clobbers x1..x6, and the displaced instruction may read x0/x1),
  * paints band N at base + N * (rowBytes*height/16),
  * restores x0..x7,
  * replays the displaced instruction,
  * branches back to site+4.

Band N corresponds to checkpoint N, so the highest visible band is the last checkpoint
reached. Colours are BGRA little-endian: 0xAARRGGBB.

Usage: patch-entry-bands.py KERNEL
"""
import importlib.util
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('probe', ROOT / 'patch-xnu-entry-probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

# (site VA, band, BGRA colour, what the checkpoint proves)
CHECKPOINTS = [
    (0xFFFFFFF00AD830D4, 3,  0xFFFF0000, 'stacks set up'),
    (0xFFFFFFF00AD83128, 4,  0xFF00FF00, 'Mach-O header check passed'),
    (0xFFFFFFF00AD83138, 5,  0xFF00FFFF, 'x4 = x0 before loop'),
    (0xFFFFFFF00AD83150, 6,  0xFFFF00FF, 'load memSize into x5'),
    (0xFFFFFFF00AD83164, 7,  0xFF0080FF, 'x2 advanced to next L2 page'),
    (0xFFFFFFF00AD83174, 8,  0xFFFFFF00, 'x0 masked for L1 index'),
    (0xFFFFFFF00AD83190, 9,  0xFF8000FF, 'ABOUT TO WRITE FIRST L1 ENTRY'),
    (0xFFFFFFF00AD83194, 10, 0xFFFFFFFF, 'first L1 entry written'),
    (0xFFFFFFF00AD831C4, 11, 0xFF00FF80, 'inner loop writing L2 entries'),
    (0xFFFFFFF00AD831CC, 12, 0xFFFF0080, 'inner loop counter decremented'),
]

FINE_CHECKPOINTS = [
    # (site VA, band, BGRA colour, what it proves, which register holds boot_args)
    (0xFFFFFFF00AD83060, 3,  0xFFFF0000, 'DAIF masked (1st instruction survived)', 'x0'),
    (0xFFFFFFF00AD83064, 4,  0xFF00FF00, 'x20 = boot_args', 'x0'),
    (0xFFFFFFF00AD83078, 5,  0xFF00FFFF, 'VBAR_EL1 set', 'x20'),
    (0xFFFFFFF00AD83088, 6,  0xFFFF00FF, 'boot_args+8/0x10/0x18/0x470 read', 'x20'),
    (0xFFFFFFF00AD83094, 7,  0xFFFFFF00, 'TPIDR_EL0/TPIDRRO_EL0 cleared', 'x20'),
    (0xFFFFFFF00AD830A4, 8,  0xFF0080FF, 'SPSel = 1', 'x20'),
    (0xFFFFFFF00AD830A8, 9,  0xFF8000FF, 'SP_EL1 written', 'x20'),
    (0xFFFFFFF00AD830C4, 10, 0xFFFFFFFF, 'SPSel = 0 and SP_EL0 written', 'x20'),
]

# The 1456 bytes between the end of the panic screen blob (0xb4f7a47) and 0xb4f8000 are
# verified all-zero in the pristine kernel; 0xb4f8000 itself is a REAL FUNCTION (starts
# with pacibsp), which is why fi80 overwrote live code and never got as far as the blue bar.
CAVE_BASE = 0xFFFFFFF00B4F9688
CAVE_STRIDE = 0xB4

PAINT = """
  ldr x1, [x20, #0x28]
  ldr x2, [x20, #0x38]
  ldr x3, [x20, #0x48]
  mul x2, x2, x3
  lsr x2, x2, #4
  bic x2, x2, #7
  mov x4, #{band}
  mul x5, x2, x4
  add x1, x1, x5
  movz w6, #{lo}
  movk w6, #{hi}, lsl #16
1:
  stp w6, w6, [x1], #8
  subs x2, x2, #8
  b.hi 1b
  dsb sy
"""

# sp is NOT usable here: _start_first_cpu points it at a high VA that only becomes valid
# once the MMU is on, and this code runs with the MMU off. Park the registers in a buffer
# inside the cave itself, addressed through x16 (IP0, unused throughout the entry body).
SAVE = """
  adrp x16, scratch
  add  x16, x16, :lo12:scratch
  stp  x0, x1, [x16]
  stp  x2, x3, [x16, #16]
  stp  x4, x5, [x16, #32]
  stp  x6, x7, [x16, #48]
"""

RESTORE = """
  ldp  x0, x1, [x16]
  ldp  x2, x3, [x16, #16]
  ldp  x4, x5, [x16, #32]
  ldp  x6, x7, [x16, #48]
"""

SCRATCH = """
  .balign 8
scratch:
  .space 64
"""


def main():
    kernel = Path(sys.argv[1])
    data = bytearray(kernel.read_bytes())
    probe.load_segments(bytes(data))

    # The entry body must be the pristine one: a checkpoint site that already holds a branch
    # means this kernel was patched before, and replaying a branch would change control flow.
    points = FINE_CHECKPOINTS if len(sys.argv) > 2 and sys.argv[2] == '--fine' else [
        (site, band, colour, why, 'x20') for site, band, colour, why in CHECKPOINTS]
    for site, band, colour, why, _reg in points:
        word = struct.unpack_from('<I', data, probe.file_offset(site))[0]
        # 0xad8328c is `b .` - a dead loop this probe deliberately replaces, so it is exempt.
        if (word & 0xFC000000) == 0x14000000 and site != 0xFFFFFFF00AD8328C:
            raise SystemExit(f'{site:#x} already branches; start from a pristine kernel')

    # Refuse to write over live code: the whole cave window must be zero in the input.
    window_lo = CAVE_BASE
    window_hi = CAVE_BASE + len(points) * CAVE_STRIDE
    raw = data[probe.file_offset(window_lo):probe.file_offset(window_hi)]
    if any(raw):
        raise SystemExit(f'cave window {window_lo:#x}..{window_hi:#x} is not all zero '
                         f'({sum(1 for x in raw if x)} non-zero bytes) - pick another address')

    written = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, (site, band, colour, why, reg) in enumerate(points):
            cave = CAVE_BASE + index * CAVE_STRIDE
            displaced = struct.unpack_from('<I', data, probe.file_offset(site))[0]
            source = (".text\n.global _start\n_start:\n"
                      + SAVE
                      + PAINT.format(args=reg, band=band, lo=f'{colour & 0xFFFF:#06x}',
                                     hi=f'{(colour >> 16) & 0xFFFF:#06x}')
                      + RESTORE
                      + f'  .inst {displaced:#010x}\n'
                      + '  b target\n' + SCRATCH)
            code = probe.assemble(source, cave, {'target': site + 4}, Path(tmp))
            if len(code) > CAVE_STRIDE:
                raise SystemExit(f'cave for {site:#x} needs {len(code):#x} > {CAVE_STRIDE:#x}')
            data[probe.file_offset(cave):probe.file_offset(cave) + len(code)] = code
            struct.pack_into('<I', data, probe.file_offset(site), probe.branch(site, cave))
            written.append((site, band, colour, cave, len(code), why))

    kernel.write_bytes(bytes(data))
    print(f'{kernel.name}: {len(written)} checkpoints painted')
    for site, band, colour, cave, size, why in written:
        print(f'  band {band:2d} {colour:#010x}  site {site:#x} -> cave {cave:#x} '
              f'({size:#04x} B)  {why}')


if __name__ == '__main__':
    main()
