#!/usr/bin/env python3
"""Add cluster-type to the ADT's CPU nodes.

DarwinBoot's AdtNode (DarwinBoot.c:273-370) parses `U32 Properties, U32 Children`, then that many
records of [32-byte NUL-padded name][U32 length][value padded to 4]. It requires the parse to
consume exactly TreeSize, so a property cannot simply be appended - the tree is re-serialised here
and the result is re-parsed to prove the round trip.

Why this matters: the kernel is built with __ARM_AMP__ / CONFIG_SCHED_EDGE=1, and its AMP
classifier reads `cluster-type` to decide whether a CPU is an efficiency (E) or performance (P)
core. The ADT this port ships has no such property at all, and the sibling port for the same SoC
(UniXNU-uke) recorded exactly this as a boot blocker: "final prior payload ADT lacks cluster-type
on all 8 CPUs ... AMP classifier rejects that value (panic string not captured)".
"""
import argparse
import struct
from pathlib import Path


def parse(data):
    off = 0

    def node():
        nonlocal off
        props, children = struct.unpack_from('<II', data, off)
        off += 8
        plist = []
        for _ in range(props):
            name = data[off:off + 32].split(b'\0')[0].decode('latin1')
            off += 32
            ln, = struct.unpack_from('<I', data, off)
            off += 4
            val = data[off:off + ln]
            off += ln
            if off % 4:
                off += 4 - (off % 4)
            plist.append([name, val])
        kids = [node() for _ in range(children)]
        return {'props': plist, 'children': kids}

    tree = node()
    return tree, off


def serialise(node, out):
    out += struct.pack('<II', len(node['props']), len(node['children']))
    for name, val in node['props']:
        raw = name.encode('latin1')[:31]
        out += raw + b'\0' * (32 - len(raw))
        out += struct.pack('<I', len(val))
        out += val
        if len(out) % 4:
            out += b'\0' * (4 - len(out) % 4)
    for kid in node['children']:
        serialise(kid, out)


def find(node, name, path=()):
    for key, val in node['props']:
        if key == 'name' and val.rstrip(b'\0').decode('latin1') == name:
            return node, path
    for i, kid in enumerate(node['children']):
        got = find(kid, name, path + (i,))
        if got:
            return got
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('adt', type=Path)
    ap.add_argument('--cpu0', default='E', help='cluster-type for cpu0 (E or P)')
    ap.add_argument('--verify-only', action='store_true')
    args = ap.parse_args()

    data = args.adt.read_bytes()
    tree, consumed = parse(data)
    if consumed != len(data):
        raise SystemExit(f'parse consumed {consumed:#x} of {len(data):#x}; refusing to rewrite')
    print(f'parsed ok: {len(data)} bytes, {consumed:#x} consumed')

    found = find(tree, 'cpu0')
    if not found:
        raise SystemExit('no cpu0 node')
    cpu0, _ = found
    existing = [n for n, _ in cpu0['props']]
    print(f'cpu0 properties: {existing}')
    if 'cluster-type' in existing:
        print('cluster-type already present, nothing to do')
        return

    cpu0['props'].append(['cluster-type', args.cpu0.encode()])
    out = bytearray()
    serialise(tree, out)

    tree2, consumed2 = parse(bytes(out))
    if consumed2 != len(out):
        raise SystemExit(f'round trip failed: {consumed2:#x} of {len(out):#x}')
    cpu0b, _ = find(tree2, 'cpu0')
    names = [n for n, _ in cpu0b['props']]
    if 'cluster-type' not in names:
        raise SystemExit('cluster-type missing after round trip')

    args.adt.write_bytes(bytes(out))
    print(f'{args.adt}: cluster-type added to cpu0 = {args.cpu0!r}; '
          f'{len(data)} -> {len(out)} bytes; round trip verified')


if __name__ == '__main__':
    main()
