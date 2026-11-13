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
import shutil
import struct
import subprocess
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

    # 6. The silent-death hooks: each one must land in its own cave, and the cave must
    #    really contain the wait-then-SYSTEM_RESET body. A hook that branches into a
    #    cave holding something else looks exactly like a probe that never fired.
    delta = symbol_va('_start_first_cpu') - probe.START_FIRST_CPU
    caves = {stage: va + delta for stage, va in probe.CAVES.items()}
    entry_va = probe.ENTRY_VA + delta
    panic_va = symbol_va('_panic')
    vector_va = symbol_va('_ExceptionVectorsBase') + 0x200
    smc = 0xD4000003                     # smc #0, the PSCI SYSTEM_RESET call
    wait_first = 0xD53BE021              # mrs x1, cntpct_el0

    def walk(blob, cave, size=0x60):
        return [struct.unpack_from('<I', blob, probe.file_offset(cave + offset))[0]
                for offset in range(0, size, 4)]

    def run_patch(*flags):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'kernel.macho'
            shutil.copyfile(args.kernel, target)
            result = subprocess.run([sys.executable, str(PROBE), str(target), *flags],
                                    capture_output=True, text=True)
            if result.returncode:
                failures.append(f'patch {flags} failed: {result.stderr.strip()[-200:]}')
                print(f'FAIL patch {flags}: {result.stderr.strip()[-200:]}')
                return None
            return target.read_bytes()

    patched = run_patch('--reset-at-entry')
    if patched is not None:
        branch = decode_branch(struct.unpack_from('<I', patched, probe.file_offset(entry_va))[0], entry_va)
        check('--reset-at-entry branches to cave 1', branch, ('b', caves[1]))
        body = walk(patched, caves[1])
        check('--reset-at-entry cave waits on cntpct', f'{body[0]:#010x}', f'{wait_first:#010x}')
        check('--reset-at-entry cave resets', smc in body, True)
        check('--reset-at-entry cave never returns to the kernel',
              any(decode_branch(word, caves[1] + index * 4) == ('b', symbol_va('_start_first_cpu'))
                  for index, word in enumerate(body)), False)

    patched = run_patch('--no-reset', '--panic-reset', '20', '--fault-reset', '60')
    if patched is not None:
        panic_hook = decode_branch(struct.unpack_from('<I', patched, probe.file_offset(panic_va))[0], panic_va)
        fault_hook = decode_branch(struct.unpack_from('<I', patched, probe.file_offset(vector_va))[0], vector_va)
        check('--panic-reset hooks panic()', panic_hook is not None and panic_hook[0] == 'b', True)
        check('--fault-reset hooks the EL1/SPx sync vector', fault_hook is not None and fault_hook[0] == 'b', True)
        check('--panic-reset target is one of the caves', panic_hook[1] in caves.values(), True)
        check('--fault-reset target is one of the caves', fault_hook[1] in caves.values(), True)
        check('the two hooks use different caves', panic_hook[1] != fault_hook[1], True)
        for label, cave in (('panic', panic_hook[1]), ('fault', fault_hook[1])):
            body = walk(patched, cave)
            check(f'{label} hook cave waits on cntpct', f'{body[0]:#010x}', f'{wait_first:#010x}')
            check(f'{label} hook cave resets', smc in body, True)

    # 7. The fingerprint hook: panic() cannot print this early, so the cave turns a slice of the
    #    format-string address into a reset delay. The body must really shift, mask and scale
    #    that slice — a cave that always waits the same time would decode as one slice forever.
    patched = run_patch('--no-reset', '--panic-fingerprint', '4:6:10:3')
    if patched is not None:
        hook = decode_branch(struct.unpack_from('<I', patched, probe.file_offset(panic_va))[0], panic_va)
        check('--panic-fingerprint hooks panic()', hook is not None and hook[0] == 'b', True)
        if hook is not None:
            body = walk(patched, hook[1])
            # lsr x9, x0, #4   = UBFM x9, x0, #4, #63   -> immr=4, imms=63
            check('fingerprint cave shifts the slice by 4', body[0], 0xD344FC09)
            # and x9, x9, #0x3f = AND (immediate), 64-bit, N=1, immr=0, imms=5
            check('fingerprint cave masks the slice to 6 bits', body[1], 0x92401529)
            check('fingerprint cave scales by the step', body[2], 0xD280006A)  # movz x10, #3
            check('fingerprint cave adds the base', body[4], 0x91002929)       # add x9, x9, #0xA
            check('fingerprint cave resets', smc in body, True)

    print()
    if failures:
        print(f'{len(failures)} failure(s)')
        return 1
    print('entry-probe contract: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
