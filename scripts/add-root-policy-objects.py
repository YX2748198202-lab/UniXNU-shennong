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
    with open(args.image, 'ab') as target:
        target.truncate(offset)
        for spec in args.object:
            name, path = spec.split('=', 1)
            if name in names:
                raise SystemExit(f'{name} is already an entry')
            data = Path(path).read_bytes()
            offset = align(offset)
            target.seek(offset)
            target.write(data)
            objects.append({'name': name, 'path': path, 'offset': offset, 'size': len(data),
                            'sha256': hashlib.sha256(data).digest()})
            offset += len(data)

    final = offset
    entries.extend({'name': o['name'], 'offset': o['offset'], 'size': o['size'],
                    'block': 4096, 'flags': 3, 'sha256': o['sha256']} for o in objects)
    struct.pack_into('<IIQ', manifest, 8, 2, len(entries), final)
    for index, entry in enumerate(entries):
        struct.pack_into('<32sQQII32s40s', manifest, 24 + ENTRY * index,
                         entry['name'].encode(), entry['offset'], entry['size'],
                         entry['block'], entry['flags'], entry['sha256'], bytes(40))
    manifest = bytearray(manifest)
    manifest[4064:4096] = hashlib.sha256(bytes(manifest[:4064])).digest()
    with open(args.image, 'r+b') as target:
        target.seek(0)
        target.write(manifest)
        target.truncate(final)

    print(f'image {args.image}: version 2, {len(entries)} entries, {final} bytes')
    for o in objects:
        print(f"  {o['name']}: off {o['offset']} size {o['size']} sha256 {o['sha256'].hex()[:16]}...")
    if args.report:
        import json
        args.report.write_text(json.dumps([{k: (v.hex() if isinstance(v, bytes) else v)
                                            for k, v in o.items()} for o in objects], indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
