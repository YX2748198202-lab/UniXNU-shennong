#!/usr/bin/env python3
"""Audit emitted PORT_CONST metadata; this is not runtime page-permission proof."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


class MachO:
    def __init__(self, data, base=0):
        self.data, self.base = data, base
        if data[base:base+4] != bytes.fromhex('cffaedfe'):
            raise ValueError('Expected Mach-O 64 little-endian')
        count, size = struct.unpack_from('<II', data, base+16)
        at, end = base+32, base+32+size
        if end > len(data):
            raise ValueError('Load commands exceed file')
        self.commands, self.segments, self.entries = {}, {}, {}
        for _ in range(count):
            cmd, length = struct.unpack_from('<II', data, at)
            if length < 8 or at+length > end:
                raise ValueError('Invalid command bounds')
            self.commands[cmd] = at
            if cmd == 0x19:
                name = data[at+8:at+24].split(b'\0')[0].decode()
                va, size, offset, file_size, maxprot, initprot, nsects = struct.unpack_from('<QQQQIII', data, at+24)
                if offset+file_size > len(data):
                    raise ValueError('Segment exceeds file')
                if 72+nsects*80 > length:
                    raise ValueError('Sections exceed command')
                sections = {}
                for i in range(nsects):
                    q = at+72+i*80
                    sn = data[q:q+16].split(b'\0')[0].decode()
                    sv, sz = struct.unpack_from('<QQ', data, q+32)
                    sections[sn] = dict(va=sv, size=sz)
                self.segments[name] = dict(va=va, size=size, fileoff=offset, filesize=file_size,
                                           maxprot=maxprot, initprot=initprot, sections=sections)
            elif cmd == 0x80000035:
                va, offset, name_offset = struct.unpack_from('<QQI', data, at+8)
                name = data[at+name_offset:at+length].split(b'\0')[0].decode()
                self.entries[name] = offset
            at += length
        if at != end:
            raise ValueError('Command count/size disagreement')

    def split_info(self):
        if 0x1e not in self.commands:
            raise ValueError('Missing LC_SEGMENT_SPLIT_INFO; pointer chains do not relocate instructions')
        at = self.commands[0x1e]
        offset, size = struct.unpack_from('<II', self.data, at+8)
        if size < 2 or offset+size > len(self.data) or self.data[offset] != 0x7f:
            raise ValueError('Expected complete split-segment v2 payload')
        return dict(fileoff=offset, size=size)

    def port_segment(self):
        s = self.segments.get('__PORT_CONST')
        if not s or not s['size']:
            raise ValueError('Missing or empty PORT_CONST')
        if s['initprot'] != 3 or s['maxprot'] != 3:
            raise ValueError('PORT_CONST must be RW/NX in boot metadata')
        return s

    def symbols(self):
        at = self.commands.get(2)
        if at is None:
            raise ValueError('Native unstripped kernel has no LC_SYMTAB')
        symoff, count, stroff, strsize = struct.unpack_from('<IIII', self.data, at+8)
        if symoff+16*count > len(self.data) or stroff+strsize > len(self.data):
            raise ValueError('Symbol table exceeds file')
        symbols = {}
        for i in range(count):
            index, kind, section, desc, value = struct.unpack_from('<IBBHQ', self.data, symoff+i*16)
            if index >= strsize:
                raise ValueError('String index exceeds symbol strings')
            end = self.data.find(b'\0', stroff+index, stroff+strsize)
            if end < 0:
                raise ValueError('Unterminated symbol')
            name = self.data[stroff+index:end].decode(errors='replace')
            if value and section:
                symbols[name] = value
        return symbols


def audit(native_path, fileset_path=None, probe=False):
    data = native_path.read_bytes()
    native = MachO(data)
    segment, split = native.port_segment(), native.split_info()
    const = segment['sections'].get('__const')
    if not const or not const['size']:
        raise ValueError('PORT_CONST has no live __const section')
    measured = dict(native_sha256=hashlib.sha256(data).hexdigest(), port_const=segment, split_info=split)
    if not probe:
        symbols = native.symbols()
        found = {}
        for name in ['_segPORTCONSTB', '_segSizePORTCONST']:
            matches = {n: v for n, v in symbols.items() if n == name or n.startswith(name+'.')}
            if not matches or not all(const['va'] <= v < const['va']+const['size'] for v in matches.values()):
                raise ValueError(f'Compiled late-const state missing/misplaced: {name}')
            found.update(matches)
        measured['compiled_state_symbols'] = found
    if fileset_path:
        output = fileset_path.read_bytes()
        root = MachO(output)
        embedded = MachO(output, root.entries['com.apple.kernel'])
        rs, ns = root.port_segment(), embedded.port_segment()
        for key in ['va', 'size', 'fileoff', 'filesize']:
            if rs[key] != ns[key]:
                raise ValueError(f'Root/native PORT_CONST disagree: {key}')
        measured['fileset_sha256'] = hashlib.sha256(output).hexdigest()
        measured['emitted_port_const'] = rs
    return measured


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native', type=Path, required=True)
    ap.add_argument('--fileset', type=Path)
    ap.add_argument('--probe', action='store_true')
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    result = audit(args.native, args.fileset, args.probe)
    if args.out:
        with args.out.open('x') as f:
            json.dump(result, f, indent=2)
            f.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
