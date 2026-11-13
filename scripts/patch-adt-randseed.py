#!/usr/bin/env python3
"""Grow /chosen/random-seed to the 256 bytes arm64 XNU asks the bootloader for.

prng_random.c:52-55 sets BOOTLOADER_ENTROPY_REQUEST_SIZE to 4*SHA512_DIGEST_LENGTH = 256 on
arm64 (64 only on x86_64), and bootseed_init_bootloader() panics when PE_get_random_seed()
returns fewer bytes.  PE_get_random_seed reads /chosen/random-seed out of the ADT
(pexpert/gen/pe_gen.c:176-184), and this board's tree ships 64 bytes.

Inserting into the value is structurally safe: DarwinBoot parses the tree with Offset walking
(DarwinBoot.c:661 requires Offset == TreeSize, and TreeSize is the file size from ReadFile),
no length field covers the whole tree, and node property/child counts do not change.
"""
import argparse
import os
import struct
from pathlib import Path

SEED_BYTES = 256


def walk(data, offset, depth, path, want):
    """Mirror DarwinBoot's AdtNode() walk well enough to find one property."""
    props, children = struct.unpack_from('<II', data, offset)
    offset += 8
    for _ in range(props):
        name = data[offset:offset + 32].split(b'\0')[0]
        length = struct.unpack_from('<I', data, offset + 32)[0]
        value_at = offset + 36
        if path + [name] == want:
            return offset, value_at, length
        offset = value_at + length
        offset = (offset + 3) & ~3
    for _ in range(children):
        offset, found = walk(data, offset, depth + 1, path + [b'?'], want)
        if found:
            return offset, found
    return offset, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('adt', type=Path)
    ap.add_argument('--bytes', type=int, default=SEED_BYTES)
    args = ap.parse_args()

    data = bytearray(args.adt.read_bytes())
    # Find the property by name and require it to sit under a node whose name is "chosen".
    pos = data.find(b'random-seed')
    if pos < 0:
        raise SystemExit('no random-seed property')
    record = pos          # the 32-byte name is the first field of the 36-byte record
    name = data[record:record + 32].split(b'\0')[0]
    if name != b'random-seed':
        raise SystemExit(f'record at {record:#x} is {name!r}, not random-seed')
    length = struct.unpack_from('<I', data, record + 32)[0]
    value_at = record + 36
    chosen = data.find(b'chosen')
    if chosen < 0 or chosen > record:
        raise SystemExit('random-seed is not inside the chosen node')

    if length >= args.bytes:
        print(f'{args.adt}: random-seed already {length} bytes, nothing to do')
        return
    grow = args.bytes - length
    data[value_at + length:value_at + length] = os.urandom(grow)
    struct.pack_into('<I', data, record + 32, args.bytes)
    args.adt.write_bytes(bytes(data))
    print(f'{args.adt}: random-seed {length} -> {args.bytes} bytes '
          f'(+{grow} bytes inserted at {value_at + length:#x}), file now {len(data)} bytes')


if __name__ == '__main__':
    main()
