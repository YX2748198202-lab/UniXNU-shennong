#!/usr/bin/env python3
"""Self-test a square-ladder kernel: every site must branch into its cave and
every cave must decode to the paint block plus the displaced instruction."""
import argparse
import importlib.util
import struct
from pathlib import Path


def load(path, name='m'):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path('/tmp/probe/patch-xnu-entry-probe.py'))
    parser.add_argument('--ladder', type=Path,
                        default=Path('scripts/patch-pre-mmu-squares.py'))
    args = parser.parse_args()
    probe = load(args.probe_tool, 'probe')
    ladder = load(args.ladder, 'ladder')
    data = args.kernel.read_bytes()
    probe.load_segments(data)
    failures = 0
    for index, site in enumerate(ladder.SITES):
        cave = ladder.CAVE_BASE + index * 0x100
        word = struct.unpack_from('<I', data, probe.file_offset(site))[0]
        expected = probe.branch(site, cave)
        if word != expected:
            print(f'FAIL #{index:02d} site {site:#x}: {word:#010x} != {expected:#010x}')
            failures += 1
            continue
        # the cave must end with a branch back to site+4
        blob = data[probe.file_offset(cave):probe.file_offset(cave) + 0x100]
        for offset in range(0, 0xF8, 4):
            word = struct.unpack_from('<I', blob, offset)[0]
            if word & 0xFC000000 == 0x14000000:
                delta = word & 0x3FFFFFF
                delta -= (1 << 26) if delta & (1 << 25) else 0
                target = cave + offset + delta * 4
                if target == site + 4:
                    break
        else:
            print(f'FAIL #{index:02d} cave {cave:#x}: no branch back to {site + 4:#x}')
            failures += 1
    print(f'{len(ladder.SITES)} checkpoints, {failures} failure(s)')
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
