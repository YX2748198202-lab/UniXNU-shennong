#!/usr/bin/env python3
"""Find the code that references every string inside a __cstring VA range.

One pass over the image: every `adrp` is remembered per register, and an
`add xR, xR, #imm` whose page matches the requested range is a reference.  That
inverts `dump-dt-props.py`: give it a page of driver strings and it hands back
the function(s) that consume them.

    scripts/find-string-refs.py KERNEL --range 0xfffffff007172000:0xfffffff007174000
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
    end = data.find(b'\0', off, off + 200)
    if end < 0 or end - off < 2:
        return None
    raw = data[off:end]
    if not all(32 <= b < 127 or b in (9,) for b in raw):
        return None
    return raw.decode('ascii')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel', type=Path)
    ap.add_argument('--range', required=True, help='LO:HI of the string range')
    ap.add_argument('--min-len', type=int, default=3)
    args = ap.parse_args()

    lo_s, hi_s = args.range.split(':')
    lo, hi = int(lo_s, 0), int(hi_s, 0)
    data = args.kernel.read_bytes()

    repo = Path(__file__).resolve().parent.parent
    patcher = load_patcher(repo)
    symbols = patcher.kernel_symbols(args.kernel)
    ordered = sorted(symbols)

    hits: dict[int, list[int]] = {}
    pages: dict[int, dict[int, int]] = {}       # adrp VA -> {reg: page}
    for off in range(0, len(data) - 4, 4):
        ins = struct.unpack_from('<I', data, off)[0]
        va = KERNEL_BASE + off
        if (ins & 0x9F000000) == 0x90000000:
            immlo = (ins >> 29) & 3
            immhi = (ins >> 5) & 0x7FFFF
            imm = (immhi << 2) | immlo
            if imm & 0x100000:
                imm -= 0x200000
            page = (va & ~0xFFF) + (imm << 12)
            pages.setdefault(va, {})[ins & 0x1F] = page
            continue
        if (ins & 0xFFC00000) != 0x91000000:
            continue
        rn, rd = (ins >> 5) & 0x1F, ins & 0x1F
        regs = pages.get(va - 4) or pages.get(va - 8) or pages.get(va - 12)
        if not regs or rn != rd or rn not in regs:
            continue
        target = regs[rn] + ((ins >> 10) & 0xFFF)
        if lo <= target < hi:
            hits.setdefault(target, []).append(va)

    print(f'{len(hits)} strings referenced from {lo:#x}..{hi:#x}')
    for target in sorted(hits):
        text = c_string(data, target)
        if text is None or len(text) < args.min_len:
            continue
        for site in hits[target]:
            owner = max((v for v in ordered if v <= site), default=0)
            print(f'  0x{site:014x}  {symbols.get(owner, "?"):<38s} '
                  f'-> {text!r}  @0x{target:x}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
