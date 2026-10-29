#!/usr/bin/env python3
"""Probe whether the prelinked kernel exports can resolve the IOBlockStorageDevice imports ShengUfs needs."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kits' / 'XnuPrelink'))
import native_prelink as np


def nm_undefined(path):
    for tool in (['llvm-nm'], ['nm']):
        try:
            out = subprocess.run(tool + ['-u', path], capture_output=True, text=True, check=True).stdout
        except Exception:
            continue
        names = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == 'U':
                names.append(parts[1])
        return names
    raise SystemExit('no nm available')


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--macho', required=True)
parser.add_argument('--plan', default='')
parser.add_argument('--archive', required=True)
parser.add_argument('--out', default='')
args = parser.parse_args()

undef = [n for n in dict.fromkeys(nm_undefined(args.archive)) if 'IOBlockStorageDevice' in n]

data = Path(args.macho).read_bytes()
image = np.macho(data)
table = np.exports(data, image)
by_name = {name: va for va, names in table.items() for name in names}

plan = {}
if args.plan and Path(args.plan).is_file():
    plan = json.loads(Path(args.plan).read_text())
extents = [e for e in plan.get('extents', []) if e.get('module') == 'com.apple.iokit.IOStorageFamily']

report = {
    'macho': str(args.macho),
    'macho_size': len(data),
    'macho_sha256': hashlib.sha256(data).hexdigest(),
    'plan_candidate_sha256': plan.get('candidate_sha256'),
    'plan_original_sha256': plan.get('original_sha256'),
    'exports_total': len(by_name),
    'storage_extents': extents,
    'undefined': [],
}
for name in undef:
    report['undefined'].append({'name': name, 'resolved': hex(by_name[name]) if name in by_name else None})

missing = [r['name'] for r in report['undefined'] if not r['resolved']]
report['missing'] = missing
report['resolved_count'] = len(report['undefined']) - len(missing)

text = json.dumps(report, indent=2)
print(text)
if args.out:
    Path(args.out).write_text(text + '\n')
print('PROBE resolved %d/%d, exports %d, missing %d'
      % (report['resolved_count'], len(report['undefined']), len(by_name), len(missing)))
for name in missing:
    print('MISSING ' + name)