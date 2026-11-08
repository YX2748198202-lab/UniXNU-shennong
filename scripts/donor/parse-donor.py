"""Read the iPhone17,1 kernelcache: segments, the prelink dictionary, and one kext's Mach-O."""
import re, struct, sys

class Cache:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        self.segments = []
        self.sections = []
        ncmds = struct.unpack_from('<I', self.data, 16)[0]
        off = 32
        for _ in range(ncmds):
            cmd, size = struct.unpack_from('<2I', self.data, off)
            if cmd == 0x19:
                name = self.data[off+8:off+24].rstrip(b'\0').decode()
                va, vmsize, foff, fsize = struct.unpack_from('<4Q', self.data, off+24)
                self.segments.append((name, va, vmsize, foff, fsize))
                nsects = struct.unpack_from('<I', self.data, off+64)[0]
                so = off + 72
                for _ in range(nsects):
                    sname = self.data[so:so+16].rstrip(b'\0').decode()
                    ssize = struct.unpack_from('<Q', self.data, so+40)[0]
                    soff = struct.unpack_from('<I', self.data, so+48)[0]
                    self.sections.append((name, sname, soff, ssize))
                    so += 80
            off += size

    def offset(self, va):
        for name, base, vmsize, foff, fsize in self.segments:
            if base <= va < base + min(vmsize, fsize):
                return foff + (va - base)
        raise SystemExit(f'{va:#x} is not file backed')

    def prelink_info(self):
        at = dict(((seg, sec), (o, s)) for seg, sec, o, s in self.sections)['__PRELINK_INFO', '__info']
        blob = self.data[at[0]:at[0]+at[1]]
        text = blob[:blob.rfind(b'</dict>')+7].decode('utf-8', 'replace')
        ids = {}
        for m in re.finditer(r'<(\w+)([^>]*?)\sID="(\d+)"([^>]*)>(.*?)</\1>', text, re.S):
            ids[m.group(3)] = m.group(5)
        def value(raw):
            ref = re.match(r'^\s*<\w+\s+IDREF="(\d+)"\s*/>\s*$', raw)
            if ref:
                return ids.get(ref.group(1), '')
            own = re.match(r'^\s*<(\w+)[^>]*>(.*?)</\1>\s*$', raw, re.S)
            return own.group(2).strip() if own else raw.strip()
        array = re.search(r'<key>_PrelinkInfoDictionary</key>\s*<array>(.*)</array>', text, re.S)
        if not array:
            raise SystemExit('no _PrelinkInfoDictionary')
        body = array.group(1)
        blocks, depth, start = [], 0, None
        for match in re.finditer(r'<dict>|</dict>', body):
            if match.group() == '<dict>':
                if depth == 0:
                    start = match.end()
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    blocks.append(body[start:match.start()])
        entries = []
        for block in blocks:
            pairs = re.findall(r'<key>(.*?)</key>\s*(<[^>]+>.*?</\w+>|<[^>]+/>)', block, re.S)
            entry = {}
            for key, raw in pairs:
                entry[key] = value(raw)
            entries.append(entry)
        return entries

def kext(cache, identifier):
    for entry in cache.prelink_info():
        if entry.get('CFBundleIdentifier') == identifier:
            return entry
    raise SystemExit(f'{identifier} is not in the prelink dictionary')

def kext_macho(cache, entry):
    load = entry['_PrelinkExecutableLoadAddr']
    if isinstance(load, str):
        load = int(load, 0)
    start = cache.offset(load)
    return start, load

if __name__ == '__main__':
    c = Cache('/tmp/donor/kernelcache.macho')
    entries = c.prelink_info()
    print(f'{len(entries)} kexts in __PRELINK_INFO')
    target = sys.argv[1] if len(sys.argv) > 1 else 'com.apple.driver.AppleMobileFileIntegrity'
    e = kext(c, target)
    print('entry keys:', sorted(e)[:20])
    print('load addr:', e.get('_PrelinkExecutableLoadAddr'), 'size:', e.get('_PrelinkExecutableSize'))
