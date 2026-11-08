#!/usr/bin/env python3
"""Fetch single members out of a remote .ipsw with HTTP range requests.

A full iPhone17,1 restore image is 12.3 GB; the kernelcache is ~40 MB, so read
the zip's central directory (zip64 aware) and pull only the entry asked for.
"""
import struct, subprocess, sys, zlib

URL = sys.argv[2] if len(sys.argv) > 2 else ''
TOTAL = 0

def rng(start, end):
    out = subprocess.run(['curl', '-sL', '--max-time', '900', '-r', f'{start}-{end}', URL],
                         capture_output=True, check=True).stdout
    return out

def size_of():
    head = subprocess.run(['curl', '-sIL', '--max-time', '120', URL], capture_output=True, check=True).stdout
    for line in head.decode('latin-1').splitlines():
        if line.lower().startswith('content-length:'):
            return int(line.split(':', 1)[1].strip())
    raise SystemExit('the server did not report a content length')

def tail(n):
    return rng(TOTAL - n, TOTAL - 1)

def find_eocd(blob):
    i = blob.rfind(b'PK\x05\x06')
    if i < 0:
        raise SystemExit('no end-of-central-directory record')
    return i, struct.unpack_from('<IHHHHIIH', blob, i)

def central_directory():
    blob = tail(256 * 1024)
    pos, eocd = find_eocd(blob)
    _, disk, cd_disk, n_disk, n_all, cd_size, cd_off, comment = eocd
    if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        loc = blob.rfind(b'PK\x06\x07', 0, pos)
        if loc < 0:
            raise SystemExit('zip64 locator missing')
        _, disk64, off64, total_disk = struct.unpack_from('<IIQI', blob, loc)
        rec = rng(off64, off64 + 55)
        sig, size = struct.unpack_from('<IQ', rec, 0)
        if sig != 0x06064B50:
            raise SystemExit('zip64 end record missing')
        fields = struct.unpack_from('<HHIIQQQQ', rec, 12)
        n_all, cd_size, cd_off = fields[5], fields[6], fields[7]
    return rng(cd_off, cd_off + cd_size - 1), n_all

def entries(cd, count):
    out, at = [], 0
    for _ in range(count):
        sig, = struct.unpack_from('<I', cd, at)
        if sig != 0x02014B50:
            raise SystemExit(f'central directory entry {_} has signature {sig:#x}')
        (_, _, _, method, _, _, _, csize, usize, nlen, elen, clen,
         _, _, _, lho) = struct.unpack_from('<HHHHHHIIIHHHHHII', cd, at + 4)
        name = cd[at + 46:at + 46 + nlen].decode('utf-8', 'replace')
        extra = cd[at + 46 + nlen:at + 46 + nlen + elen]
        p = 0
        while p + 4 <= len(extra):
            tag, size = struct.unpack_from('<HH', extra, p)
            if tag == 0x0001:
                q, vals = p + 4, []
                while q + 8 <= p + 4 + size:
                    vals.append(struct.unpack_from('<Q', extra, q)[0]); q += 8
                if usize == 0xFFFFFFFF and vals: usize = vals.pop(0)
                if csize == 0xFFFFFFFF and vals: csize = vals.pop(0)
                if lho == 0xFFFFFFFF and vals: lho = vals.pop(0)
            p += 4 + size
        out.append({'name': name, 'method': method, 'csize': csize,
                    'usize': usize, 'lho': lho})
        at += 46 + nlen + elen + clen
    return out

def member(entry):
    head = rng(entry['lho'], entry['lho'] + 29)
    (_, _, _, _, _, _, _, _, _, nlen, elen) = struct.unpack('<IHHHHHIIIHH', head)
    start = entry['lho'] + 30 + nlen + elen
    data = rng(start, start + entry['csize'] - 1)
    if len(data) != entry['csize']:
        raise SystemExit(f"short read for {entry['name']}: {len(data)} of {entry['csize']}")
    if entry['method'] == 8:
        data = zlib.decompress(data, -15)
    return data

if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit('usage: fetch-ipsw-member.py MEMBER-SUBSTRING IPSW-URL [OUT-DIR]')
    TOTAL = size_of()
    cd, count = central_directory()
    table = entries(cd, count)
    want = sys.argv[1] if len(sys.argv) > 1 else 'kernelcache'
    hits = [e for e in table if want.lower() in e['name'].lower()]
    print(f'{len(table)} members in the central directory')
    for e in hits:
        print(f"  {e['name']}  compressed={e['csize']:,} uncompressed={e['usize']:,}")
    if not hits:
        raise SystemExit(f'nothing matches {want!r}')
    pick = hits[0]
    data = member(pick)
    out = sys.argv[2].split('/')[-1] if False else pick['name'].split('/')[-1]
    target = f'{sys.argv[2].rsplit("/",1)[0]}/{out}' if len(sys.argv) > 2 else out
    target = out
    open(target, 'wb').write(data)
    print(f"wrote {target} ({len(data):,} bytes)")
