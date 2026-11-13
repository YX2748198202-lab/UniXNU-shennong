#!/usr/bin/env python3
"""Write progress tags into a kernel BSS slot, inline, with no helper function.

The kernel cannot write the frame buffer (fi70/fi71), so progress has to be recorded in memory and
painted on the next boot by the trampoline (scripts/patch-slot-bands.py). Doing that through a
helper in xnu-panic-screen.c meant patch-beacons had to re-assemble that whole translation unit and
land on exactly the same byte layout as --panic-screen did - which it never did, so every build
carried two copies of the blob and a `bl` into one of them.

A tag is one store, so it is inlined here instead: no blob, no symbol, no layout coupling. x9/x10
are caller-saved, so clobbering them at a function's first instruction is harmless, and the
displaced instruction is replayed verbatim.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

ASM = """.text
.global _start
_start:
  movz x9, #{slot_lo}
  movk x9, #{slot_16}, lsl #16
  movk x9, #{slot_32}, lsl #32
  movk x9, #{slot_48}, lsl #48
  movz x10, #{tag}
  str  x10, [x9]
  bic  x9, x9, #63
  dc   civac, x9
  dsb  sy
  .inst {displaced}
  b    back
.ltorg
"""

KERNEL_VA = 0xFFFFFFF007004000
KERNEL_PA = 0x8C0004000
SLOT_OFFSET = 0x800


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('kernel', type=Path)
    ap.add_argument('--mark', action='append', required=True,
                    help='SYMBOL:TAG (repeatable); TAG is a small integer')
    ap.add_argument('--probe-tool', type=Path,
                    default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    ap.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-marks'))
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location('probe', args.probe_tool)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    syms = probe.kernel_symbols(args.kernel)
    names = {n: va for va, n in syms.items() if isinstance(va, int)}
    slot = names['_boot_progress_panic_text'] + SLOT_OFFSET
    args.workdir.mkdir(parents=True, exist_ok=True)

    for item in args.mark:
        symbol, _, tag = item.partition(':')
        if symbol not in names:
            raise SystemExit(f'no symbol {symbol}')
        site = names[symbol]
        displaced = struct.unpack_from('<I', data, probe.file_offset(site))[0]
        asm = ASM.format(slot_lo=f'{slot & 0xffff:#x}', slot_16=f'{(slot >> 16) & 0xffff:#x}',
                         slot_32=f'{(slot >> 32) & 0xffff:#x}', slot_48=f'{(slot >> 48) & 0xffff:#x}',
                         tag=f'{int(tag, 0)}', displaced=f'{displaced:#010x}')
        cave = 0xFFFFFFF00B4FB900
        blob = probe.assemble(asm, cave, {'back': site + 4}, args.workdir)
        off = probe.file_offset(cave)
        data[off:off + len(blob)] = blob
        struct.pack_into('<I', data, probe.file_offset(site), probe.branch(site, cave))
        print(f'  {symbol} @ {site:#x} -> tag {int(tag,0):#x}: inline mark {len(blob)} bytes '
              f'at {cave:#x} (replays .inst {displaced:#010x})')

    args.kernel.write_bytes(bytes(data))
    print(f'{args.kernel}: inline slot marks wired (slot {slot:#x})')


if __name__ == '__main__':
    main()
