#!/usr/bin/env python3
"""Build the board's trust bundle from the board's own IPSW, both modules unchanged.

The UniXNU loader accepts the trust-cache *bundle* format (a count/offset header followed
by the raw modules), not the IPSW IM4P: packing the IM4P makes the firmware refuse the
payload with "Compromised Data".

`unixnu/scripts/build-original-system-trust.py` used to build this bundle, but it pins
`refer/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`, ProductBuildVersion 21H461 and
DeviceClass j120ap. Once board.toml moved to iPhone17,1 27.0.1 24A446 the CI only had the
iOS 27 IPSW in `refer/`, so that step died with FileNotFoundError (run 42878351134) and the
payload step never ran. A 17.7.11 trust cache also cannot cover the iOS 27 launchd that the
payload is supposed to release, so keeping the old bundle was wrong even when it "worked".

This script derives everything from board.toml instead:

  * IPSW  = basename of `[ipsw] url` inside `refer/` (the workflow hard-links it there)
  * device class = `[ipsw] device_class`
  * static module = `StaticTrustCache`      of the first matching identity
  * system module = `Cryptex1,SystemTrustCache` of the same identity

Both modules are hashed and compared with the sha384 digests recorded in BuildManifest.plist,
so the bundle is provably made of Apple's untouched modules. Every matching identity must
agree on both digests; a platform that personalises them per variant is reported instead of
silently picking one.

Output (same layout the payload step expects):
  build/target-static-system-trust/static-system.bundle
  build/target-static-system-trust/inputs.json      (digests + sizes + provenance)
"""
import argparse
import hashlib
import json
import plistlib
import struct
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def der(data, at):
    if at + 2 > len(data):
        raise SystemExit('Truncated DER at %d' % at)
    tag, size = data[at], data[at + 1]
    at += 2
    if size & 128:
        count = size & 127
        if not 0 < count <= 4 or at + count > len(data):
            raise SystemExit('Invalid DER length at %d' % at)
        size = int.from_bytes(data[at:at + count], 'big')
        at += count
    if at + size > len(data):
        raise SystemExit('DER field exceeds input at %d' % at)
    return tag, data[at:at + size], at + size


def module_from_im4p(blob, what):
    """Return the raw version-2 trust module carried in an IM4P wrapper."""
    tag, sequence, end = der(blob, 0)
    if end != len(blob):
        raise SystemExit('%s: trailing bytes after the sequence' % what)
    fields, cursor = [], 0
    while cursor < len(sequence):
        kind, data, cursor = der(sequence, cursor)
        fields.append((kind, data))
    if tag != 0x30 or [kind for kind, _ in fields] != [0x16, 0x16, 0x16, 0x04]:
        raise SystemExit('%s: unexpected DER layout %s' % (what, [hex(k) for k, _ in fields]))
    if fields[0][1] != b'IM4P':
        raise SystemExit('%s: not an IM4P (magic %r)' % (what, fields[0][1]))
    module = fields[3][1]
    version = struct.unpack_from('<I', module, 0)[0]
    count = struct.unpack_from('<I', module, 20)[0]
    if version != 2:
        raise SystemExit('%s: trust module version %d, need 2' % (what, version))
    if len(module) != 24 + count * 24:
        raise SystemExit('%s: module length %d does not match %d entries' % (what, len(module), count))
    return module, count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', default=str(ROOT / 'board.toml'))
    parser.add_argument('--refer', default='refer')
    parser.add_argument('--out', default='build/target-static-system-trust')
    args = parser.parse_args()

    board = tomllib.load(open(args.board, 'rb'))
    spec = board['ipsw']
    name = Path(spec['url']).name
    device_class = spec['device_class']
    ipsw = Path(args.refer) / name
    if not ipsw.is_file():
        raise SystemExit('Missing %s (workflow hard-links the board IPSW into refer/)' % ipsw)

    with zipfile.ZipFile(ipsw) as archive:
        manifest = plistlib.loads(archive.read('BuildManifest.plist'))
        # Only the product identities carry both modules. iPhone17,1 24A446 also lists a
        # "Recovery Customer Install" identity whose StaticTrustCache is the recovery
        # ramdisk's (Firmware/043-68523-763.dmg.aea.trustcache) and which has no
        # Cryptex1,SystemTrustCache at all, so it must not take part in the pick.
        identities = [i for i in manifest['BuildIdentities']
                      if i['Info']['DeviceClass'] == device_class
                      and i['Manifest'].get('StaticTrustCache')
                      and i['Manifest'].get('Cryptex1,SystemTrustCache')]
        if not identities:
            raise SystemExit('No product BuildIdentity for device class %s in %s'
                             % (device_class, name))

        digests = {}
        for key in ('StaticTrustCache', 'Cryptex1,SystemTrustCache'):
            entries = {(i['Manifest'][key]['Info']['Path'],
                        i['Manifest'][key]['Digest']) for i in identities}
            if len(entries) != 1:
                raise SystemExit('%s differs between the %d %s identities: %s'
                                 % (key, len(identities), device_class, sorted(entries)))
            digests[key] = entries.pop()

        modules = {}
        for key, (path, digest) in digests.items():
            blob = archive.read(path)
            if hashlib.sha384(blob).digest() != digest:
                raise SystemExit('%s digest mismatch for %s' % (key, path))
            modules[key], modules[key + ':count'] = module_from_im4p(blob, key)

    static, system = modules['StaticTrustCache'], modules['Cryptex1,SystemTrustCache']
    bundle = struct.pack('<3I', 2, 12, 12 + len(static)) + static + system
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'static-system.bundle').write_bytes(bundle)
    report = {
        'ipsw': name,
        'product': spec.get('product'),
        'build': manifest['ProductBuildVersion'],
        'device_class': device_class,
        'identities_checked': len(identities),
        'modules': {
            'static': {'entries': modules['StaticTrustCache:count'], 'bytes': len(static),
                       'sha256': hashlib.sha256(static).hexdigest(),
                       'im4p_sha384': digests['StaticTrustCache'][1].hex()},
            'system': {'entries': modules['Cryptex1,SystemTrustCache:count'], 'bytes': len(system),
                       'sha256': hashlib.sha256(system).hexdigest(),
                       'im4p_sha384': digests['Cryptex1,SystemTrustCache'][1].hex()},
        },
        'bundle': {'bytes': len(bundle), 'sha256': hashlib.sha256(bundle).hexdigest()},
        'original_modules_modified': False,
        'apple_personalization_claimed': False,
    }
    (out / 'inputs.json').write_text(json.dumps(report, indent=2) + '\n')

    bundle_sha = report['bundle']['sha256']
    print('static: %d entries, %d B, sha256 %s' % (modules['StaticTrustCache:count'], len(static),
                                                   report['modules']['static']['sha256']))
    print('system: %d entries, %d B, sha256 %s' % (modules['Cryptex1,SystemTrustCache:count'],
                                                   len(system), report['modules']['system']['sha256']))
    print('bundle: %d B sha256 %s' % (len(bundle), bundle_sha))

    pinned = board.get('payload', {}).get('trust_cache_sha256') or []
    if pinned and bundle_sha not in pinned:
        print('::warning::board.toml [payload] trust_cache_sha256 does not list %s' % bundle_sha)
    elif pinned:
        print('board pin matches')
    return 0


if __name__ == '__main__':
    sys.exit(main())
