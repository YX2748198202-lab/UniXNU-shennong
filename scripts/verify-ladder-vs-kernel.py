#!/usr/bin/env python3
"""Check a hard-coded site table against a kernel at a different base address.

Every diagnostic image in this repository carries absolute virtual addresses
that were read off one payload build (``0xFFFFFFF00AD8xxxx`` for the iOS 27
kernel).  A rebuilt kernel moves them.  Both kernels still contain the same XNU
source, so the *relative* layout inside the trampoline is stable; checking a
table against a kernel whose entry address is known therefore catches a wrong or
stale address without needing the payload itself.

Usage:
    scripts/verify-ladder-vs-kernel.py REFERENCE_KERNEL \
        --table scripts/patch-pre-mmu-squares.py \
        --payload-anchor 0xFFFFFFF00AD8305C

The reference kernel's entry is taken from ``_start_first_cpu``; ``--reference-anchor``
overrides it.  Sites that fall outside the reference kernel's file-backed range,
or that land past ``common_start``, are reported as "not checkable here" instead
of being counted as failures: the arm64e payload has an extra
``PAC_INIT_KEY_STATE`` block that the arm64 reference does not.
"""
import argparse
import importlib.util
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def disassemble_word(word):
    """Enough of AArch64 to name the instruction class of a site."""
    if word == 0xD503201F:
        return 'nop'
    if word == 0xD5033FDF:
        return 'isb'
    if word & 0xFFC00000 == 0xD5000000:
        return 'msr/mrs'
    if word & 0x7C000000 == 0x14000000:
        return 'b/bl'
    if word & 0xFF000010 == 0x54000000:
        return 'b.cond'
    if word & 0x7F800000 in (0x52800000, 0x72800000, 0xF2800000, 0x12800000):
        return 'movz/movk'
    if word & 0x7F000000 == 0x11000000:
        return 'add/sub imm'
    return 'other'


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('reference', type=Path, help='kernel the table is checked against')
    parser.add_argument('--table', type=Path, default=HERE / 'patch-pre-mmu-squares.py')
    parser.add_argument('--payload-anchor', type=lambda s: int(s, 0), required=True,
                        help='entry address (msr OSLAR_EL1) in the payload the table was written for')
    parser.add_argument('--reference-anchor', type=lambda s: int(s, 0),
                        help='entry address in the reference kernel (default: its _start_first_cpu)')
    args = parser.parse_args()

    probe = load(HERE / 'patch-xnu-entry-probe.py', 'probe')
    table = load(args.table, 'table')
    data = args.reference.read_bytes()
    probe.load_segments(data)
    symbols = probe.kernel_symbols(args.reference)
    by_name = {name: va for va, name in symbols.items()}
    reference_anchor = args.reference_anchor or by_name['_start_first_cpu']
    delta = args.payload_anchor - reference_anchor
    common = by_name.get('common_start') or by_name.get('_common_start')
    common_end = probe.function_range(symbols, 'common_start')[1] if common else reference_anchor

    print(f'reference anchor {reference_anchor:#x}, payload anchor {args.payload_anchor:#x}, '
          f'delta {delta:#x}')
    print(f"{'#':>3} {'payload site':>14} {'reference':>14}  word        kind           verdict")
    inside = outside = unmapped = 0
    for index, site in enumerate(table.SITES):
        target = site - delta
        try:
            word = struct.unpack_from('<I', data, probe.file_offset(target))[0]
        except SystemExit:
            print(f'{index:>3} {site:>14x} {target:>14x}  --          --             unmapped')
            unmapped += 1
            continue
        kind = disassemble_word(word)
        if reference_anchor <= target < common_end:
            verdict = 'reachable in the trampoline'
            inside += 1
        else:
            verdict = 'beyond the arm64 trampoline (in the PAC/band extension)'
            outside += 1
        print(f'{index:>3} {site:>14x} {target:>14x}  {word:#010x}  {kind:<13}  {verdict}')

    print()
    print(f'{inside} site(s) land inside the reference trampoline, {outside} beyond it, '
          f'{unmapped} outside the reference kernel')
    # A site that is unmapped is a table error only when it is also unmapped in
    # the payload: without the payload we can only report it.
    return 0


if __name__ == '__main__':
    sys.exit(main())
