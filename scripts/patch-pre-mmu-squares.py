#!/usr/bin/env python3
"""Small-square ladder across the MMU-off window before SCTLR is installed.

The kernel paints band 1 blue at its entry (0xAD81500) and band 2 white right
before it installs SCTLR_EL1 (0xAD81560), yet the screen keeps the loader's
magenta band 2, so execution stops between the entry and 0xAD83418.  That whole
window runs with the MMU off, so painting there is always visible.

Each checkpoint paints a 60x60 square in a fixed grid slot, which lifts the
16-band limit and keeps the ladder readable: the first missing square is the
checkpoint that was never reached.  The cave only uses x7, x8, x16 and x17,
which the trampoline does not touch in this window, and it never touches the
stack (SP is still an unmapped kernel virtual address).
"""
import argparse
import importlib.util
import struct
from pathlib import Path

# verified zero-filled padding inside __TEXT_EXEC: 0xB4F9688 .. 0xB4FC000
CAVE_BASE = 0xFFFFFFF00B4F9700
CAVE_STRIDE = 0x80           # 18 instructions per cave, so 0x80 is enough
COLOURS = [0xFFFFFFFF, 0xFFFF0000, 0xFF0000FF]
SITES = [
    # -- prologue (kernel entry -> bootstrap pool zeroed) --
    0xFFFFFFF00AD8305C,   # msr oslar_el1 (very first instruction)
    0xFFFFFFF00AD83060,   # msr daifset
    0xFFFFFFF00AD83064,   # mov x20, x0 (boot_args PA)
    0xFFFFFFF00AD83070,   # add x0,x0,#0 (after adrp of the early VBAR)
    0xFFFFFFF00AD83074,   # msr vbar_el1 (physical vectors)
    0xFFFFFFF00AD83078,   # ldr x22 = VirtualBase
    0xFFFFFFF00AD83080,   # ldr x24 = MemorySize
    0xFFFFFFF00AD8308C,   # msr tpidrro_el0 (after adrp x25 = bootstrap pool)
    0xFFFFFFF00AD83088,   # ldr x26 = [args+0x470]
    0xFFFFFFF00AD83098,   # add x0,x0,#0 (after adrp of the IRQ stack)
    0xFFFFFFF00AD830A4,   # msr spsel, #1
    0xFFFFFFF00AD830B0,   # add x0,x0,#0 (after adrp of the FIQ stack)
    0xFFFFFFF00AD830BC,   # msr spsel, #0
    0xFFFFFFF00AD830C8,   # add x30,x30,#0x8d0 (after adrp of _arm_init)
    0xFFFFFFF00AD830D4,   # pool zero setup
    0xFFFFFFF00AD830E4,   # pool zero loop
    0xFFFFFFF00AD830F4,   # add x0,x0,#0 (after adrp of the collection header)
    # -- relocation + page-table build --
    0xFFFFFFF00AD83128,   # relocation applied (x18)
    0xFFFFFFF00AD83144,   # L1/L2 loop setup
    0xFFFFFFF00AD83164,   # one L2 page per iteration
    0xFFFFFFF00AD831C4,   # L2 block descriptor store
    0xFFFFFFF00AD831EC,   # second window phase
    0xFFFFFFF00AD83238,   # second phase block fill
    0xFFFFFFF00AD83290,   # dsb ish before TCR
    # -- control registers --
    0xFFFFFFF00AD832A4,   # movk x1, T0SZ
    0xFFFFFFF00AD832A8,   # msr tcr_el1
    0xFFFFFFF00AD832B8,   # returned from _set_mmu_ttb (TTBR0 installed)
    0xFFFFFFF00AD832BC,   # add x0 = KVA root page
    0xFFFFFFF00AD832CC,   # MAIR attribute build
    0xFFFFFFF00AD8330C,   # msr mair_el1
    0xFFFFFFF00AD83314,   # tlbi vmalle1
    0xFFFFFFF00AD83320,   # ic iallu
    0xFFFFFFF00AD8332C,   # warm-boot TTBR1 reload
    0xFFFFFFF00AD83348,   # msr vbar_el1
    0xFFFFFFF00AD8335C,   # PAC key seed from cntpct_el0
    0xFFFFFFF00AD833C8,   # PAC key load
    0xFFFFFFF00AD833CC,   # msr apiakeylo_el1
    0xFFFFFFF00AD83404,   # isb after the key writes
    0xFFFFFFF00AD83414,   # movk x0 = SCTLR value (right before the branch)
    # -- MMU switch and the white band painter --
    0xFFFFFFF00AD81560,   # entry of the band-2 white painter
    0xFFFFFFF00AD81598,   # white band-2 loop finished (args/FB writes were fine)
    0xFFFFFFF00AD8159C,   # msr sctlr_el1 -- the MMU switch itself
]

ASM = """.text
.global _start
_start:
  movz x8, #0xfc40, lsl #16
  movz x16, #0x{off_lo}
  movk x16, #0x{off_hi}, lsl #16
  add  x8, x8, x16
  movz w17, #0x{col_lo}
  movk w17, #0x{col_hi}, lsl #16
  mov  x7, #48
1:
  mov  x16, #48
2:
  str  w17, [x8], #4
  subs x16, x16, #1
  b.ne 2b
  sub  x8, x8, #192
  movz x16, #0x1680
  add  x8, x8, x16
  subs x7, x7, #1
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
                        default=Path('/tmp/probe/patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-squares'))
    args = parser.parse_args()
    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)
    args.workdir.mkdir(parents=True, exist_ok=True)
    stride = 5760          # rowBytes from boot_args Video[2] (bytes per row)
    for index, site in enumerate(SITES):
        site_off = probe.file_offset(site)
        original = struct.unpack_from('<I', data, site_off)[0]
        x = 8 + (index % 20) * 72
        y = 8 + (index // 20) * 56
        offset = y * stride + x * 4
        colour = COLOURS[min(index // 20, 2)]
        asm = ASM.format(off_lo=f'{offset & 0xFFFF:04x}', off_hi=f'{(offset >> 16) & 0xFFFF:04x}',
                         col_lo=f'{colour & 0xFFFF:04x}', col_hi=f'{(colour >> 16) & 0xFFFF:04x}',
                         tail=f'.inst {original:#010x}')
        cave = CAVE_BASE + index * CAVE_STRIDE
        blob = probe.assemble(asm, cave, {'back': site + 4}, args.workdir)
        assert len(blob) <= CAVE_STRIDE, f'cave {index} is {len(blob)} bytes'
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        print(f'  #{index:02d} site {site:#x} square ({x},{y}) colour {colour:#010x}')
    assert CAVE_BASE + len(SITES) * CAVE_STRIDE <= 0xFFFFFFF00B4FC000, 'caves leave the padding'
    args.kernel.write_bytes(bytes(data))
    print(f'pre-MMU square ladder: {len(SITES)} checkpoints in padding {CAVE_BASE:#x}')


if __name__ == '__main__':
    main()
