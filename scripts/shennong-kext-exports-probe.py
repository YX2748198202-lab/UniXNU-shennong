#!/usr/bin/env python3
"""Look up the ShengUfs storage imports in the decompressed original kernelcache symbol table.

kernel.macho only carries kernel-level exports, so kext-local symbols such as
IOBlockStorageDevice::gMetaClass never appear there. The decompressed kernelcache
keeps every kext's own LC_SYMTAB, which is the place to look.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kits' / 'XnuPrelink'))
import native_prelink as np


def nm_tool():
    for candidate in ('llvm-nm', 'nm'):
        found = shutil.which(candidate)
        if found:
            return found
    for candidate in ('/opt/homebrew/opt/llvm/bin/llvm-nm', '/usr/local/opt/llvm/bin/llvm-nm', '/usr/bin/nm'):
        if Path(candidate).is_file():
            return candidate
    raise SystemExit('no nm tool found')


kernelcache, archive = sys.argv[1], sys.argv[2]
NM = nm_tool()
print('KEXTPROBE nm=%s' % NM)


def undefined_storage_symbols(path):
    out = subprocess.run([NM, '-u', path], capture_output=True, text=True).stdout
    names = []
    for line in out.splitlines():
        for token in line.split():
            if token.startswith('_') and 'IOBlockStorageDevice' in token:
                names.append(token)
    return sorted(set(names))


names = undefined_storage_symbols(archive)
data = open(kernelcache, 'rb').read()
image = np.macho(data)
table = np.exports(data, image)
by_name = {name: va for va, exports in table.items() for name in exports}

print('KEXTPROBE undefined=%d kernelcache_exports=%d' % (len(names), len(by_name)))
hits = 0
for name in names:
    if name in by_name:
        hits += 1
        print('HIT  %#x %s' % (by_name[name], name))
    else:
        print('MISS      %s' % name)
print('KEXTPROBE resolved %d/%d' % (hits, len(names)))