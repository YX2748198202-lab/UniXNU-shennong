#!/usr/bin/env python3
"""Dump the device-tree property names a kernel function asks for.

The shipped kernel is newer than the source tree we have, so a closed routine
such as the CPU-topology parser cannot be read as C.  What it *does* leave
behind is the sequence `adrp` + `add`/`ldr` that materialises the address of
each property-name string it passes to SecureDT.  This tool decodes a VA range,
reassembles those pairs, and prints the strings they point at, in order.

    scripts/dump-dt-props.py KERNEL --around 0xfffffff0086473d4 [--back 0x400]
"""

from __future__ import annotations

import argparse
import importlib.util
import struct
import sys
from pathlib import Path

KERNEL_BASE = 0xFFFFFFF007004000


def load_patcher(repo: Path):
    path = repo / 'scripts' / 'patch-xnu-entry-probe.py'
    spec = importlib.util.spec_from_file_location('patcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def c_string(data: bytes, va: int) -> str | None:
    off = va - KERNEL_BASE
    if not (0 <= off < len(data)):
        return None
    end = data.find(b'\0', off, off + 160)
    if end < 0 or end == off:
        return None
    raw = data[off:end]
    if not all(32 <= b < 127 or b in (9,) for b in raw):
        return None
    return raw.decode('ascii')


def adrp_target(ins: int, va: int) -> int:
    immlo = (ins >> 29) & 3
    immhi = (ins >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    if imm & 0x100000:
        imm -= 0x200000
    return (va & ~0xFFF) + (imm << 12)


def decode(ins: int, va: int, symbols: dict[int, str]) -> str:
    if ins == 0xD65F03C0:
        return 'ret'
    if (ins & 0x9F000000) == 0x90000000:
        return f'adrp x{ins & 0x1F}, {adrp_target(ins, va):#x}'
    if (ins & 0xFFC00000) == 0x91000000:
        return (f'add  x{ins & 0x1F}, x{(ins >> 5) & 0x1F}, '
                f'#{(ins >> 10) & 0xFFF:#x}')
    if (ins & 0xFFC00000) == 0x39400000:
        return (f'ldrb w{ins & 0x1F}, [x{(ins >> 5) & 0x1F}, '
                f'#{(ins >> 10) & 0xFFF:#x}]')
    if (ins & 0xFFC00000) == 0x71000000:
        return f'cmp  x{(ins >> 5) & 0x1F}, #{(ins >> 10) & 0xFFF:#x}'
    if (ins & 0xFC000000) == 0x94000000:
        imm = ins & 0x3FFFFFF
        if imm & 0x2000000:
            imm -= 0x4000000
        target = va + imm * 4
        name = symbols.get(target)
        return f'bl   {target:#x}' + (f'  <{name}>' if name else '')
    if (ins & 0xFC000000) == 0x14000000:
        imm = ins & 0x3FFFFFF
        if imm & 0x2000000:
            imm -= 0x4000000
        return f'b    {va + imm * 4:#x}'
    if (ins & 0x7E000000) == 0x34000000:
        imm = (ins >> 5) & 0x7FFFF
        if imm & 0x40000:
            imm -= 0x80000
        op = 'cbnz' if ins & 0x01000000 else 'cbz '
        return f'{op} x{ins & 0x1F}, {va + imm * 4:#x}'
    if (ins & 0xFF000000) == 0x54000000:
        imm = (ins >> 5) & 0x7FFFF
        if imm & 0x40000:
            imm -= 0x80000
        return f'b.{ins & 0xF:#x}  {va + imm * 4:#x}'
    return f'.word {ins:#010x}'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel', type=Path)
    ap.add_argument('--around', required=True,
                    help='VA of the instruction whose strings are wanted')
    ap.add_argument('--back', type=lambda s: int(s, 0), default=0x400)
    ap.add_argument('--forward', type=lambda s: int(s, 0), default=0x200)
    ap.add_argument('--disassemble', action='store_true')
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    patcher = load_patcher(repo)
    symbols = patcher.kernel_symbols(args.kernel)          # va -> name
    data = args.kernel.read_bytes()

    site = int(args.around, 0) if isinstance(args.around, str) else args.around
    lo, hi = site - args.back, site + args.forward
    function = max((va for va in symbols if va <= site), default=None)
    print(f'nearest symbol: 0x{function:x} {symbols.get(function, "?")}'
          if function else 'nearest symbol: none')

    ordered = sorted(symbols)
    strings: list[tuple[int, str]] = []
    pending: dict[int, int] = {}
    for va in range(lo, hi, 4):
        ins = struct.unpack_from('<I', data, va - KERNEL_BASE)[0]
        if args.disassemble:
            marker = '>>' if va == site else '  '
            print(f'{marker} 0x{va:014x}  {decode(ins, va, symbols)}')
        if (ins & 0x9F000000) == 0x90000000:
            pending[ins & 0x1F] = adrp_target(ins, va)
            continue
        if (ins & 0xFFC00000) == 0x91000000:
            rn, rd = (ins >> 5) & 0x1F, ins & 0x1F
            base = pending.get(rn)
            if base is not None:
                va_str = base + ((ins >> 10) & 0xFFF)
                text = c_string(data, va_str)
                if text:
                    # 只认落在主内核 __cstring 里的名字，排除页内巧合
                    owner = max((v for v in ordered if v <= va_str), default=0)
                    strings.append((va, f'{text!r}   @0x{va_str:x} '
                                         f'(near {symbols.get(owner, "?")})'))

    print(f'\nstrings referenced in 0x{lo:x}..0x{hi:x}: {len(strings)}')
    seen = set()
    for va, text in strings:
        if text in seen:
            continue
        seen.add(text)
        print(f'  0x{va:014x} -> {text}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
