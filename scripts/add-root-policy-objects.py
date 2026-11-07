#!/usr/bin/env python3
"""Append the VerifiedRoot policy tables to a SHNGROOT root image.

The header-only policy form keeps the per-window block hash tables out of the kernel:
the driver reads them back from the root image object "<window>.vroot"
(NativeUfs::readPolicyTable). scripts/unixnu/userdata.py writes objects only at image
creation time, and rebuilding that image means re-reading the whole IPSW, so this
appends them in place:

  - the windows keep their offsets, so the tables (and their hashes) stay valid
  - the manifest is rewritten as version 2 with the two object entries
  - every object is 1 MiB aligned, block_size 4096 and flags 3, exactly as the builder
    writes them; the manifest's own trailing SHA-256 is recomputed
"""
import argparse
import hashlib
import struct
from pathlib import Path

MIB = 1 << 20
ENTRY = 128


def align(value, unit=MIB):
    return (value + unit - 1) // unit * unit


def read_manifest(image):
    with open(image, 'rb') as source:
        manifest = source.read(4096)
    if manifest[:8] != b'SHNGROOT':
        raise SystemExit('not a SHNGROOT image')
    version, count, total = struct.unpack_from('<IIQ', manifest, 8)
    manifest = bytearray(manifest)
    entries = []
    for index in range(count):
        name, offset, size, block, flags, digest = struct.unpack_from(
            '<32sQQII32s', manifest, 24 + ENTRY * index)
        entries.append({'name': name.rstrip(b'\0').decode(), 'offset': offset, 'size': size,
                        'block': block, 'flags': flags, 'sha256': digest})
    return manifest, version, total, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--object', action='append', default=[],
                        help='NAME=PATH; the object name must match "<window>.vroot"')
    parser.add_argument('--report', type=Path, help='write a JSON description of the layout')
    args = parser.parse_args()
    if not args.object:
        raise SystemExit('nothing to add')

    manifest, version, total, entries = read_manifest(args.image)
    if version != 1 or any(e['flags'] != 1 for e in entries):
        raise SystemExit(f'image already carries objects (version {version})')
    names = {e['name'] for e in entries}

    offset = align(total)
    objects = []
    # r+b, not ab: in append mode every write goes to end-of-file whatever we seek to,
    # which silently offsets every object after the first one.
    with open(args.image, 'r+b') as target:
        target.truncate(offset)
        for spec in args.object:
            name, path = spec.split('=', 1)
            if name in names:
                raise SystemExit(f'{name} is already an entry')
            data = Path(path).read_bytes()
            # RootLayout.h rejects an entry whose offset is not 4 KiB aligned and requires
            # the 4 KiB-rounded size to fit inside image_bytes, so place every object on a
            # 4 KiB boundary and record exactly where the bytes went.
            offset = align(offset, 4096)
            target.seek(offset)
            target.write(data)
            objects.append({'name': name, 'path': path, 'offset': offset, 'size': len(data),
                            'sha256': hashlib.sha256(data).digest()})
            offset += len(data)

    final = offset
    # The driver rejects a manifest whose image_bytes is not a multiple of 4096 (bounds
    # check, status 4), and fastboot cannot re-sparse an unaligned file, so the image ends
    # on a 1 MiB boundary and the manifest reports that length.
    padded = align(final)
    entries.extend({'name': o['name'], 'offset': o['offset'], 'size': o['size'],
                    'block': 4096, 'flags': 3, 'sha256': o['sha256']} for o in objects)
    struct.pack_into('<IIQ', manifest, 8, 2, len(entries), padded)
    for index, entry in enumerate(entries):
        struct.pack_into('<32sQQII32s40s', manifest, 24 + ENTRY * index,
                         entry['name'].encode(), entry['offset'], entry['size'],
                         entry['block'], entry['flags'], entry['sha256'], bytes(40))
    manifest = bytearray(manifest)
    manifest[4064:4096] = hashlib.sha256(bytes(manifest[:4064])).digest()
    with open(args.image, 'r+b') as target:
        target.seek(0)
        target.write(manifest)
        target.truncate(padded)

    # Read the objects back from where the manifest says they are: the driver trusts those
    # offsets, so a mismatch here only shows up on the device as a hash-table failure.
    with open(args.image, 'rb') as check:
        for o in objects:
            check.seek(o['offset'])
            stored = check.read(o['size'])
            if hashlib.sha256(stored).digest() != o['sha256']:
                raise SystemExit(f"{o['name']}: stored bytes do not match at offset {o['offset']}")
    # Mirror RootLayout.h's bounds check (manifestStatus 4) so a layout mistake fails here.
    if padded % 4096:
        raise SystemExit(f'image_bytes {padded} is not 4 KiB aligned')
    for entry in entries:
        offset, size = entry['offset'], entry['size']
        if offset % 4096 or offset < 4096 or not size or offset >= padded:
            raise SystemExit(f"{entry['name']}: bad offset/size ({offset}, {size})")
        if size > padded - offset or (size + 4095) // 4096 * 4096 > padded - offset:
            raise SystemExit(f"{entry['name']}: does not fit in image_bytes")
    print(f'image {args.image}: version 2, {len(entries)} entries, {final} bytes, padded to {padded} (objects read back, bounds ok)')
    for o in objects:
        print(f"  {o['name']}: off {o['offset']} size {o['size']} sha256 {o['sha256'].hex()[:16]}...")
    if args.report:
        import json
        args.report.write_text(json.dumps([{k: (v.hex() if isinstance(v, bytes) else v)
                                            for k, v in o.items()} for o in objects], indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
