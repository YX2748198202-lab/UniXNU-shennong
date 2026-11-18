#!/usr/bin/env python3
"""Validate or refresh the ARM XNU /chosen/random-seed contract.

Only the root's direct chosen node is eligible. Mutation uses a fresh complete
system-CSPRNG value and an atomic replacement; --check never writes. No seed
contents are logged. The original positional argument and --bytes remain.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile

SEED_BYTES = 256
MAX_ADT_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64


def validate_size(size):
    if not isinstance(size, int) or size < SEED_BYTES or size % 4:
        raise ValueError('Seed size must be at least 256 bytes and four-byte aligned')
    if size > MAX_ADT_BYTES - 44:
        raise ValueError('Requested seed exceeds the loader ADT limit')


def parse_adt(data):
    """Return bounded node/property positions, using node names rather than find()."""
    if not 8 <= len(data) <= MAX_ADT_BYTES:
        raise ValueError('ADT size outside loader limits')
    records, nodes = [], []

    def walk(offset, parent, depth):
        if depth > MAX_DEPTH or offset + 8 > len(data):
            raise ValueError('Truncated ADT node or excessive depth')
        properties, children = struct.unpack_from('<II', data, offset)
        offset += 8
        if properties > (len(data) - offset) // 36:
            raise ValueError('Invalid property count')
        pending, node_name = [], None
        for _ in range(properties):
            if offset + 36 > len(data):
                raise ValueError('Truncated property header')
            field = data[offset:offset + 32]
            if b'\0' not in field:
                raise ValueError('Unterminated property name')
            key = field.split(b'\0', 1)[0].decode('ascii')
            length, = struct.unpack_from('<I', data, offset + 32)
            value = offset + 36
            end = value + length
            padded = (end + 3) & ~3
            if end > len(data) or padded > len(data):
                raise ValueError('Property value or alignment exceeds ADT')
            if key == 'name':
                name_bytes = data[value:end]
                if (node_name is not None or not name_bytes.endswith(b'\0') or
                        b'\0' in name_bytes[:-1] or len(name_bytes) > 256):
                    raise ValueError('Invalid or duplicate node name')
                node_name = name_bytes[:-1].decode('ascii')
                if not node_name or '/' in node_name:
                    raise ValueError('Invalid node path component')
            pending.append(dict(name=key, record=offset, value=value,
                                size=length, end=padded))
            offset = padded
        if node_name is None:
            raise ValueError('Missing node name')
        path = parent + (node_name,) if depth else ()
        nodes.append((path, properties, children))
        for record in pending:
            record['path'] = path
            records.append(record)
        if children > (len(data) - offset) // 8:
            raise ValueError('Invalid child count')
        for _ in range(children):
            offset = walk(offset, path, depth + 1)
        return offset

    if walk(0, (), 0) != len(data):
        raise ValueError('Trailing bytes after complete ADT')
    if sum(path == ('chosen',) for path, _, _ in nodes) != 1:
        raise ValueError('Expected exactly one direct /chosen node')
    seeds = [r for r in records if r['path'] == ('chosen',) and r['name'] == 'random-seed']
    if len(seeds) != 1:
        raise ValueError('Expected exactly one /chosen/random-seed property')
    return dict(records=records, nodes=nodes, seed=seeds[0])


def validate(data, required=SEED_BYTES):
    validate_size(required)
    tree = parse_adt(data)
    if tree['seed']['size'] != required:
        raise ValueError(f"/chosen/random-seed is {tree['seed']['size']} bytes; expected {required}")
    return tree


def other_records(data, tree):
    return [(r['path'], r['name'], data[r['record']:r['end']])
            for r in tree['records'] if r is not tree['seed']]


def update_seed(data, required=SEED_BYTES, refresh=False, rng=None):
    validate_size(required)
    tree = parse_adt(data)
    record = tree['seed']
    if record['size'] == required and not refresh:
        return data, False
    rng = os.urandom if rng is None else rng
    seed = rng(required)
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != required or not any(seed):
        raise ValueError('System entropy source returned an invalid seed')
    if seed == data[record['value']:record['value'] + record['size']]:
        raise ValueError('Entropy source repeated the previous seed')
    output = (data[:record['record'] + 32] + struct.pack('<I', required) +
              bytes(seed) + bytes(-required % 4) + data[record['end']:])
    new_tree = validate(output, required)
    if tree['nodes'] != new_tree['nodes'] or other_records(data, tree) != other_records(output, new_tree):
        raise ValueError('Non-seed ADT content changed')
    return output, True


def atomic_replace(path, before, after):
    if path.is_symlink():
        raise ValueError('Symlink input is not supported')
    destination = path.resolve(strict=True)
    mode = stat.S_IMODE(destination.stat().st_mode)
    fd, name = tempfile.mkstemp(prefix='.' + destination.name + '.seed-', dir=destination.parent)
    temporary = Path(name).resolve(strict=True)
    # Both absolute move/delete targets are checked against the selected file's parent.
    if temporary.parent != destination.parent or temporary == destination:
        raise ValueError('Unexpected atomic temporary path')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if destination.read_bytes() != before:
            raise ValueError('Input changed before atomic replacement')
        os.replace(temporary, destination)
        if destination.read_bytes() != after:
            raise ValueError('Atomic replacement readback mismatch')
    finally:
        if temporary.exists():
            if temporary.resolve(strict=True).parent != destination.parent:
                raise ValueError('Unexpected cleanup path')
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('adt', type=Path)
    parser.add_argument('--bytes', type=int, default=SEED_BYTES)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='Validate only; never write')
    group.add_argument('--refresh', action='store_true', help='Replace the complete seed even if its size matches')
    args = parser.parse_args()
    try:
        if args.adt.is_symlink():
            raise ValueError('Symlink input is not supported')
        before = args.adt.read_bytes()
        if args.check:
            validate(before, args.bytes)
            after, changed, action = before, False, 'checked'
        else:
            after, changed = update_seed(before, args.bytes, args.refresh)
            action = 'refreshed' if changed else 'unchanged'
            if changed:
                atomic_replace(args.adt, before, after)
        print(json.dumps(dict(action=action, seed_bytes=args.bytes,
                              bytes_before=len(before), bytes_after=len(after),
                              sha256_before=hashlib.sha256(before).hexdigest(),
                              sha256_after=hashlib.sha256(after).hexdigest()), sort_keys=True))
    except (OSError, ValueError) as error:
        print(f'ADT seed error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
