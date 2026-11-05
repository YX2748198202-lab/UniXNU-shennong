#!/usr/bin/env python3
"""Shift measured storage bindings by the prelink slide of this board.

scripts/scan-prelink-storage.py measures the IOStorageFamily dispatch table out of
the original kernelcache, where every kext sits at its original address. The prelink
places each component at `original + slide` (board.toml [kernel.prelink] slide), and
the built image confirms it: the IOStorageFamily text hashes identically at
0xfffffff00496c000, exactly 0x1000000 below the kernelcache address.

Binding without that shift makes the driver jump to zeros and the CPU takes an
undefined-instruction panic (`pc=...ed98 instr=0 @sleh.c:1045`), so this applies it
once, in the pipeline, instead of trusting a pin that is only valid for the IPSW.
"""
import argparse
import json
import re
from pathlib import Path

ADDRESS_KEYS = ('vtable', 'vtable_address_point', 'metaclass', 'metaclass_pointer',
                'protected_constructor', 'base_destructor')
EXTENT_KEYS = ('kext_text', 'kext_const')


def board_slide(board):
    match = re.search(r'^\s*"slide"\s*=\s*"(-?0x[0-9a-fA-F]+)"', board.read_text(), re.M)
    if not match:
        return 0
    return int(match.group(1), 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--board', type=Path, required=True)
    args = parser.parse_args()

    doc = json.loads(args.bindings.read_text())
    slide = board_slide(args.board)
    already = doc.get('slide_applied')
    if already == hex(slide):
        print(f'bindings already carry slide {hex(slide)}')
        return 0
    if already is not None:
        raise SystemExit(f'bindings carry slide {already}, board says {hex(slide)}')

    shifted = 0
    for key in ADDRESS_KEYS:
        if key in doc:
            doc[key] = hex(int(doc[key], 16) + slide)
            shifted += 1
    for key in EXTENT_KEYS:
        if key in doc and 'va' in doc[key]:
            doc[key]['va'] = hex(int(doc[key]['va'], 16) + slide)
            shifted += 1
    doc['slots'] = [hex(int(value, 16) + slide) for value in doc['slots']]
    doc['slide_applied'] = hex(slide)
    doc['slide_note'] = ('measured from the original kernelcache; shifted by the prelink '
                         'slide so the addresses match the built kernel image')
    args.bindings.write_text(json.dumps(doc, indent=2) + '\n')
    print(f'applied slide {hex(slide)} to {shifted} scalars and {len(doc["slots"])} slots; '
          f'constructor now {doc["protected_constructor"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
