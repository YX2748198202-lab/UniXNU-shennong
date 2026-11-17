#!/usr/bin/env python3
"""Rebase a measured complete local kernel delta with strict byte preimages.

This preserves the tested local patch set; it does not label every patch as a
probe or add any new permission, PAC, or exception-behaviour changes.
All generated files use exclusive creation. Inputs are never modified.
"""
import argparse
import hashlib
import importlib.util
import json
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def read_input(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return data, dict(path=str(path), size=len(data), sha256=sha(data))


def segments(data):
    if data[:4] != bytes.fromhex('cffaedfe'):
        raise ValueError('Expected a little-endian 64-bit Mach-O')
    end = 32 + struct.unpack_from('<I', data, 20)[0]
    offset = 32
    out = {}
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > end:
            raise ValueError('Invalid load-command bounds')
        if cmd == 0x19:
            name = data[offset+8:offset+24].split(b'\0', 1)[0].decode()
            vm, vs, fo, fs = struct.unpack_from('<QQQQ', data, offset+24)
            if fo + fs > len(data):
                raise ValueError('Invalid file-backed segment')
            out[name] = dict(vmaddr=vm, vmsize=vs, fileoff=fo, filesize=fs)
        offset += size
    return out


def differences(a, b):
    if len(a) != len(b):
        raise ValueError('Input sizes differ')
    result = []
    for start in range(0, len(a), 4096):
        x, y = a[start:start+4096], b[start:start+4096]
        if x != y:
            result.extend(start+i for i, (u, v) in enumerate(zip(x, y)) if u != v)
    return result


def create(args):
    old, oi = read_input(args.old)
    tested, ti = read_input(args.tested)
    new, ni = read_input(args.new)
    if segments(old) != segments(new) or segments(old) != segments(tested):
        raise ValueError('Segment layouts differ')
    delta = differences(old, tested)
    conflicts = [i for i in delta if new[i] != old[i]]
    if len(delta) != 4045 or conflicts:
        raise ValueError(f'Unexpected baseline delta/preimages: {len(delta)}/{len(conflicts)}')
    result = bytearray(new)
    for i in delta:
        result[i] = tested[i]
    sec = segments(old)['__TEXT_EXEC']
    lo, hi = sec['fileoff'], sec['fileoff'] + sec['filesize']
    if result[lo:hi] != tested[lo:hi]:
        raise ValueError('Rebased executable segment differs from tested baseline')
    ranges = []
    for i in delta:
        if ranges and i == ranges[-1][1]:
            ranges[-1][1] = i + 1
        else:
            ranges.append([i, i+1])
    args.out.mkdir(parents=True, exist_ok=False)
    output = args.out / 'kernel.macho'
    with output.open('xb') as f:
        f.write(result)
    if output.read_bytes() != result:
        raise ValueError('Output read-back mismatch')
    report = dict(version=1, created_at=datetime.now(timezone.utc).isoformat(),
                  inputs=dict(old=oi, tested=ti, new=ni),
                  output=dict(path=str(output.resolve()), size=len(result), sha256=sha(result)),
                  migrated_bytes=len(delta), preimage_conflicts=0,
                  code_difference_bytes=0,
                  changes=[dict(file_offset=lo, size=hi-lo,
                                before_hex=old[lo:hi].hex(), after_hex=tested[lo:hi].hex())
                           for lo, hi in ranges],
                  segments=segments(new))
    save_json(args.out/'manifest.json', report)
    print(json.dumps({k: report[k] for k in ['migrated_bytes', 'preimage_conflicts', 'code_difference_bytes', 'output']}, ensure_ascii=False))


def verify(args):
    root = args.directory.resolve(strict=True)
    manifest = json.loads((root/'manifest.json').read_text())
    package = json.loads((root/'package.json').read_text())
    inputs = {k: Path(v['path']).read_bytes() for k, v in manifest['inputs'].items()}
    all_refs = list(manifest['inputs'].values()) + package['inputs']
    changed = sum(sha(Path(x['path']).read_bytes()) != x['sha256'] for x in all_refs)
    old, tested, new = (inputs[k] for k in ['old', 'tested', 'new'])
    actual = (root/'kernel.macho').read_bytes()
    delta = differences(old, tested)
    conflicts = sum(new[i] != old[i] for i in delta)
    expected = bytearray(new)
    for i in delta:
        expected[i] = tested[i]
    sec = segments(old)['__TEXT_EXEC']
    lo, hi = sec['fileoff'], sec['fileoff'] + sec['filesize']
    code_diff = len(differences(tested[lo:hi], actual[lo:hi]))
    extra = len(differences(expected, actual))
    fat_kernel = subprocess.run(['mtype', '-i', str(root/'payload.img'), '::/EFI/UniXNU/Payloads/kernel.macho'], check=True, capture_output=True).stdout
    spec = importlib.util.spec_from_file_location('boot_image', Path(__file__).resolve().parents[1]/'firmware/make-boot-image.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    image = root/'Mu-shennong-fi135.img'
    errors, info = module.build(image)
    boot = image.read_bytes()
    payload = (root/'payload.img').read_bytes()
    embedded = boot[info['payload_offset']:info['payload_offset']+info['ramdisk_size']]
    checks = [
        ('C1', changed == 0, dict(changed_inputs=changed, input_count=len(all_refs))),
        ('C2', len(delta) == 4045 and conflicts == 0, dict(migrated_bytes=len(delta), preimage_conflicts=conflicts)),
        ('C3', code_diff == 0, dict(code_difference_bytes=code_diff)),
        ('C4', extra == 0, dict(unexpected_difference_bytes=extra)),
        ('C5', fat_kernel == actual, dict(kernel_sha256_match=fat_kernel == actual, sha256=sha(fat_kernel))),
        ('C6', not errors, dict(boot_layout_errors=len(errors), errors=errors, **info)),
        ('C7', embedded == payload, dict(embedded_payload_sha256_match=embedded == payload, sha256=sha(embedded))),
    ]
    result = dict(version=1, summary=dict(total=len(checks), passed=sum(ok for _, ok, _ in checks), failed=sum(not ok for _, ok, _ in checks)),
                  checks=[dict(id=key, result='pass' if ok else 'fail', measured=value) for key, ok, value in checks],
                  image=dict(path=str(image), size=len(boot), sha256=sha(boot)))
    save_json(root/'acceptance.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if any(not ok for _, ok, _ in checks):
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='mode', required=True)
    make = sub.add_parser('create')
    for name in ['old', 'tested', 'new', 'out']:
        make.add_argument('--'+name, required=True, type=Path)
    check = sub.add_parser('verify')
    check.add_argument('directory', type=Path)
    check.add_argument('--all', action='store_true', required=True)
    args = ap.parse_args()
    (create if args.mode == 'create' else verify)(args)


if __name__ == '__main__':
    main()
