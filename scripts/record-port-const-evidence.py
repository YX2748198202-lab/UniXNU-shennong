#!/usr/bin/env python3
"""Collect only scoped build evidence, without environment or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--framework', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    framework = args.framework.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=False)
    trees = [framework] + sorted((framework/'out/shennong').glob('*/shennong/tree'))
    records = []
    for index, tree in enumerate(trees):
        paths = list((tree/'build/shennong-port-const').glob('*.json'))
        paths += [tree/'.cache/xnu-work/osfmk/arm64/arm_vm_init.c', tree/'.cache/xnu-work/makedefs/MakeInc.def']
        build = tree/'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
        paths += list(build.rglob('arm_vm_init.o')) if build.is_dir() else []
        paths += list(build.glob('mach.development.bcm2837.link/*.linkarguments'))
        for path in paths:
            if not path.is_file():
                continue
            relative = path.relative_to(tree)
            target = args.out/str(index)/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # A non-hidden copy is picked up by upload-artifact by default.
            if '.cache' in target.parts:
                target = args.out/str(index)/'compile-source'/Path(*relative.parts[2:])
                target.parent.mkdir(parents=True, exist_ok=True)
            with path.open('rb') as source, target.open('xb') as dest:
                shutil.copyfileobj(source, dest)
            content = target.read_bytes()
            records.append(dict(source=str(path), archived=str(target.relative_to(args.out)),
                                sha256=hashlib.sha256(content).hexdigest(), size=len(content)))
    with (args.out/'manifest.json').open('x') as f:
        json.dump(dict(version=1, files=records), f, indent=2)
        f.write('\n')
    print('port-const evidence files:', len(records))


if __name__ == '__main__':
    main()
