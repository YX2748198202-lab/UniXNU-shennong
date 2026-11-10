#!/usr/bin/env python3
"""Contract test for scripts/patch-xnu-entry-probe.py against a real kernel.

Every diagnostic image (Mu-sq3, Mu-guard, Mu-fault, the framebuffer cave) is
built through that module, so its API has to be pinned by something executable.
The expectations below are read out of a built kernel with ``llvm-objdump``:
the words and symbols are the ones the disassembly actually shows, not values
copied from the documentation.

Usage:
    scripts/test-entry-probe.py <kernel.macho>
"""
import argparse
import importlib.util
import struct
import sys
import tempfile
from pathlib import Path

PROBE = Path(__file__).with_name('patch-xnu-entry-probe.py')


def load(path, name='probe'):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode_branch(word, at_va):
    """Local b/bl decoder: the vendored probe only encodes, it does not decode."""
    if word & 0x7C000000 != 0x14000000:
        return None
    delta = word & 0x03FFFFFF
    if delta & (1 << 25):
        delta -= (1 << 26)
    return ('bl' if word & 0x80000000 else 'b', at_va + delta * 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    probe = load(PROBE)
    data = args.kernel.read_bytes()
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f'{name}: {got!r} != {want!r}')
            print(f'FAIL {name}: got {got!r}, want {want!r}')
        else:
            print(f'ok   {name}')

    probe.load_segments(data)
    segments = probe.SEGMENTS
    check('segments parsed', len(segments) > 0, True)
    check('segment tuples are (vmaddr, vmsize, fileoff, filesize)',
          all(len(segment) == 4 for segment in segments), True)

    symbols = probe.kernel_symbols(args.kernel)
    check('symbols parsed', len(symbols) > 100, True)

    # 1. VA -> file offset: this word is the trampoline's "msr SCTLR_EL1, x0".
    def symbol_va(name):
        return next(va for va, symbol in symbols.items() if symbol == name)

    sctlr = symbol_va('_set_mmu_ttb')
    check('_set_mmu_ttb resolved', sctlr > 0, True)
    for name, expected_word in (('_set_mmu_ttb', 0xD5033B9F), ):
        va = symbol_va(name)
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        check(f'{name} first word', f'{word:#010x}', f'{expected_word:#010x}')

    # 2. A word whose address the docs quote: the MMU switch itself lives a few
    #    dozen bytes after common_start; find it by decoding, not by hardcoding.
    start, end = probe.function_range(symbols, 'common_start')
    check('common_start start', start > 0, True)
    sctlr_site = None
    for va in range(start, end, 4):
        if struct.unpack_from('<I', data, probe.file_offset(va))[0] == 0xD5181000:
            sctlr_site = va
            break
    if sctlr_site is None:
        # A payload build replaces this instruction with a branch into the band
        # cave that paints the pre-MMU band, runs the msr and comes back. Both
        # forms are correct; what must hold is that the msr still runs.
        cave_site = None
        for va in range(start, end, 4):
            word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
            decoded = decode_branch(word, va)
            if decoded and decoded[0] == 'b' and not start <= decoded[1] < end:
                candidate = decoded[1]
                for walk in range(candidate, candidate + 0x200, 4):
                    if struct.unpack_from('<I', data, probe.file_offset(walk))[0] == 0xD5181000:
                        cave_site, sctlr_site = va, walk
                        break
            if cave_site is not None:
                break
        check('msr SCTLR_EL1 reachable (direct or through the band cave)',
              sctlr_site is not None, True)
        if cave_site is not None:
            print(f'     instrumented: {cave_site:#x} branches to the cave at {sctlr_site:#x}')
    else:
        check('msr SCTLR_EL1 inside common_start', True, True)

    # 3. find_call: common_start calls the TTBR0 installer through `bl`.
    try:
        site, target = probe.find_call(data, symbols, 'common_start', '_set_mmu_ttb', 0)
        check('find_call site target', target, symbol_va('_set_mmu_ttb'))
        check('find_call site decodes to bl', decode_branch(
            struct.unpack_from('<I', data, probe.file_offset(site))[0], site)[0], 'bl')
    except Exception as error:      # noqa: BLE001 - report, do not abort the suite
        failures.append(f'find_call: {error}')
        print(f'FAIL find_call: {error}')

    # 4. branch encoding round-trips through the arm64 immediate rules.
    encoded = probe.branch(0x1000, 0x2000)
    check('branch immediate', f'{encoded:#010x}', f'{0x14000000 | (0x1000 >> 2):#010x}')
    check('branch round-trip', decode_branch(encoded, 0x1000), ('b', 0x2000))
    backwards = probe.branch(0x2000, 0x1000)
    check('backwards branch round-trip', decode_branch(backwards, 0x2000), ('b', 0x1000))
    try:
        probe.branch(0x0, 0x20000000)
        failures.append('branch out of range was accepted')
        print('FAIL branch out of range was accepted')
    except SystemExit:
        print('ok   branch out of range rejected')

    # 5. assemble(): a cave with a relative branch is byte-exact once linked at
    #    its virtual address, which is what the patch scripts rely on.
    source = """.text
.global _start
_start:
  movz w17, #0x1234
  b    back
.ltorg
"""
    with tempfile.TemporaryDirectory() as tmp:
        blob = probe.assemble(source, 0xFFFFFFF00B4F9700, {'back': 0xFFFFFFF00B4F9800},
                              Path(tmp))
    check('assemble size', len(blob) >= 8, True)
    first = struct.unpack_from('<I', blob, 0)[0]
    check('assemble movz', f'{first:#010x}', f'{0x52800000 | (0x1234 << 5) | 17:#010x}')
    branch_word = struct.unpack_from('<I', blob, 4)[0]
    check('assemble branch target', decode_branch(branch_word, 0xFFFFFFF00B4F9704),
          ('b', 0xFFFFFFF00B4F9800))

    print()
    if failures:
        print(f'{len(failures)} failure(s)')
        return 1
    print('entry-probe contract: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
