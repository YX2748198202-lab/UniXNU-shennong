#!/usr/bin/env python3
"""Raise the memory window and DRAM size inside an existing DarwinBoot ADT.

DarwinBoot fills boot_args from this tree only (DarwinBoot.c:361-363 reads
`darwinboot-memory-size`, DarwinBoot.c:750 puts it into Args->MemorySize), so the
kernel's bootstrap tables cover exactly that window.  The phone's frame buffer sits
1.09 GiB past the window start, and a 256 MiB window is also too little VM for a
94 MiB prelinked kernel, so both cells have to be raised.

Format (DarwinBoot.c:273-372 AdtNode): every property is a 36-byte record, 32 bytes of
NUL-padded name followed by a little-endian u32 length, and the value follows the record
directly.  Both numbers are little-endian u64s.

The tree itself is never rebuilt: only these 16 value bytes change, so the strict parser
(which requires `Offset == TreeSize`) sees the same structure it already accepted.
"""
import argparse
import struct
from pathlib import Path

DRAM = 0x218        # dram-size value, right after its record at 0x1f4 + 36
BASE = 0x1ec        # dram-base value, right after its record at 0x1c8 + 36
WINDOW = 0x244      # darwinboot-memory-size value, record at 0x220 + 36
WINDOW_MIN = 0x10000000
WINDOW_MAX = 0x200000000


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('adt', type=Path)
    p.add_argument('--dram-base', type=lambda s: int(s, 0), default=None)
    p.add_argument('--dram-size', type=lambda s: int(s, 0), required=True)
    p.add_argument('--window', type=lambda s: int(s, 0), required=True)
    args = p.parse_args()

    if not (WINDOW_MIN <= args.window <= WINDOW_MAX) or (args.window & 0x1FFFFF):
        raise SystemExit('window must be 256 MiB..8 GiB in 2 MiB steps (DarwinWindowSizeValid)')
    data = bytearray(args.adt.read_bytes())
    checks = [(DRAM, b'dram-size'), (WINDOW, b'darwinboot-memory-size')]
    if args.dram_base is not None:
        checks.append((BASE, b'dram-base'))
    for offset, tag in checks:
        name = data[offset - 36:offset - 4].split(b'\0')[0]
        if name != tag:
            raise SystemExit(f'{offset:#x} does not follow a {tag.decode()} record (found {name!r})')
        if struct.unpack_from('<I', data, offset - 4)[0] != 8:
            raise SystemExit(f'{tag.decode()} length is not 8 bytes')
    before = (struct.unpack_from('<Q', data, DRAM)[0], struct.unpack_from('<Q', data, WINDOW)[0],
              struct.unpack_from('<Q', data, BASE)[0])
    struct.pack_into('<Q', data, DRAM, args.dram_size)
    struct.pack_into('<Q', data, WINDOW, args.window)
    if args.dram_base is not None:
        struct.pack_into('<Q', data, BASE, args.dram_base)
    args.adt.write_bytes(bytes(data))
    print(f'{args.adt}: dram-size {before[0]:#x} -> {args.dram_size:#x}, '
          f'window {before[1]:#x} -> {args.window:#x}'
          + (f', dram-base {before[2]:#x} -> {args.dram_base:#x}' if args.dram_base is not None else '')
          + f' ({len(data)} bytes unchanged)')


if __name__ == '__main__':
    main()
