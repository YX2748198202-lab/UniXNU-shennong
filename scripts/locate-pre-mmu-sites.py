#!/usr/bin/env python3
"""Locate the pre-MMU trampoline sites in a built kernel.macho.

The diagnostic patches in this directory contain hard-coded virtual addresses
(``0xFFFFFFF00AD83xxx``) that were read off one specific payload build.  A
different OS profile, patch series or prelink layout moves them, and a stale
address silently corrupts unrelated code instead of failing.  This tool
re-derives the addresses from the binary itself, so an image can be built from
whatever kernel is in hand and the address table can be checked before a
boot.

It recognises the trampoline by instruction, not by address:

* ``_start_first_cpu`` (or failing that, the function holding
  ``msr OSLAR_EL1, xzr``) with the Mach-O header guard
  ``ldr w1,[x0,#0x18]; tbz w1,#0x1f`` + ``cmp w1,#0x19; b.ne .``,
* ``common_start`` (or the function holding ``msr SCTLR_EL1, x0``) with TCR,
  TTBR0 helper call, TTBR1, MAIR, the TLB/cache maintenance, VBAR, the
  pointer-auth key writes and the SCTLR install plus its read-back self loop.

Usage:
    scripts/locate-pre-mmu-sites.py kernel.macho [--json out.json]
Exit status is 1 when a site every image depends on is missing.
"""
import argparse
import importlib.util
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / 'patch-xnu-entry-probe.py'

# opcode -> label.  These are single instructions, so they are stable across
# builds even when the surrounding code is laid out differently.
WORDS = {
    0xD510109F: 'msr OSLAR_EL1, xzr',
    0xD5182040: 'msr TCR_EL1, x0',
    0xD5182041: 'msr TCR_EL1, x1',
    0xD5182020: 'msr TTBR1_EL1, x0',
    0xD518A200: 'msr MAIR_EL1, x0',
    0xD508871F: 'tlbi vmalle1',
    0xD508751F: 'ic iallu',
    0xD518C000: 'msr VBAR_EL1, x0',
    0xD5181000: 'msr SCTLR_EL1, x0',
    0xD5181040: 'msr CPACR_EL1, x0',
    0xD518D09F: 'msr TPIDR_EL1, xzr',
    0xD5033FDF: 'isb',
    0xD5033B9F: 'dsb ish',
}
# Pointer-auth key registers (APIAKeyLo..APGAKeyHi) are 0xd518a0xx..0xd518a5xx.
PAC_KEY_RANGE = (0xD518A000, 0xD518A600)
PAC_KEY_NAMES = {
    0xD518A020: 'msr APIAKeyLo_EL1', 0xD518A021: 'msr APIAKeyHi_EL1',
    0xD518A022: 'msr APIBKeyLo_EL1', 0xD518A023: 'msr APIBKeyHi_EL1',
    0xD518A024: 'msr APDAKeyLo_EL1', 0xD518A025: 'msr APDAKeyHi_EL1',
    0xD518A026: 'msr APDBKeyLo_EL1', 0xD518A027: 'msr APDBKeyHi_EL1',
    0xD518A028: 'msr APGAKeyLo_EL1', 0xD518A029: 'msr APGAKeyHi_EL1',
}


def load_probe():
    spec = importlib.util.spec_from_file_location('probe', PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_backed_ranges(probe):
    """(start_va, end_va) of every file-backed segment of the loaded kernel."""
    return [(vmaddr, vmaddr + min(vmsize, filesize))
            for vmaddr, vmsize, _fileoff, filesize in probe.SEGMENTS]


def decode_branch(word, at_va):
    """Local b/bl decoder: the vendored probe only encodes, it does not decode."""
    if word & 0x7C000000 != 0x14000000:
        return None
    delta = word & 0x03FFFFFF
    if delta & (1 << 25):
        delta -= (1 << 26)
    return ('bl' if word & 0x80000000 else 'b', at_va + delta * 4)


def enclosing_function(probe, symbols, va):
    """Symbol whose address is the greatest one at or below ``va``."""
    candidates = [symbol for symbol in symbols if symbol <= va]
    if not candidates:
        return None, va
    start = max(candidates)
    end = None
    following = sorted(symbol for symbol in symbols if symbol > va)
    if following:
        end = following[0]
    return symbols[start], (start, end or start + 0x4000)


def scan(probe, data, start, end, wanted):
    """Addresses inside [start, end) whose first word is one of ``wanted``."""
    hits = []
    for va in range(start, end, 4):
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        label = WORDS.get(word) or PAC_KEY_NAMES.get(word)
        if word in wanted:
            hits.append((va, label))
        elif PAC_KEY_RANGE[0] <= word <= PAC_KEY_RANGE[1]:
            hits.append((va, label or f'msr PAC key ({word:#010x})'))
    return hits


def self_loop(probe, data, start, end):
    """Conditional branches whose target is the branch itself."""
    loops = []
    for va in range(start, end, 4):
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        if word & 0xFF000010 != 0x54000000:      # B.cond
            continue
        delta = (word >> 5) & 0x7FFFF
        if delta & 0x40000:
            delta -= 0x80000
        if va + delta * 4 == va:
            loops.append((va, f'b.<cond> . ({word:#010x})'))
    return loops


def sctlr_constant(probe, data, sctlr_va):
    """Rebuild the movz/movk chain that loads the SCTLR value into x0.

    XNU writes the constant with four ``movk`` halfwords, so composing the
    lanes is enough even though the first instruction is not a ``movz``.
    """
    lanes = {}
    lanes_started = False
    for va in range(sctlr_va - 4 * 8, sctlr_va, 4):
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        if (word >> 23) & 0x3F != 0x25 or (word & 0x1F) != 0:
            continue
        opc = (word >> 29) & 0x3
        hw = (word >> 21) & 0x3
        imm = (word >> 5) & 0xFFFF
        if opc == 2:                    # MOVZ: the chain starts here
            lanes = {hw: imm}
            lanes_started = True
        elif opc == 3:                  # MOVK: patch one halfword
            if not lanes_started:
                lanes = {}
                lanes_started = True
            lanes[hw] = imm
    if not lanes_started:
        return None
    value = 0
    for hw, imm in lanes.items():
        value |= imm << (16 * hw)
    return value


def analyse(probe, path):
    data = path.read_bytes()
    probe.load_segments(data)
    symbols = probe.kernel_symbols(path)
    report = {'kernel': str(path), 'symbols': {}, 'sites': {}, 'missing': []}

    # 1. prologue
    prologue_va = None
    for name in ('_start_first_cpu', 'start_first_cpu'):
        if name in symbols.values():
            prologue_va = next(va for va, symbol in symbols.items() if symbol == name)
            break
    if prologue_va is None:
        # No symbol table entry: find the entry by its first instruction instead.
        for start, end in file_backed_ranges(probe):
            for va in range(start, end, 4):
                if struct.unpack_from('<I', data, probe.file_offset(va))[0] == 0xD510109F:
                    prologue_va = va
                    break
            if prologue_va is not None:
                break
    if prologue_va is None:
        report['missing'].append('prologue (msr OSLAR_EL1, xzr not found)')
        prologue_range = (0, 0)
        report['symbols']['start_first_cpu'] = None
    else:
        name, prologue_range = enclosing_function(probe, symbols, prologue_va)
        report['symbols']['start_first_cpu'] = {'name': name, 'range': [hex(prologue_range[0]), hex(prologue_range[1])]}
        guard = [(va, 'cmp w1,#0x19') for va in range(prologue_range[0], prologue_range[1], 4)
                 if struct.unpack_from('<I', data, probe.file_offset(va))[0] == 0x7100643F]
        for va, label in guard:
            word = struct.unpack_from('<I', data, probe.file_offset(va + 4))[0]
            report['sites'][f'guard: first load command must be LC_SEGMENT_64 ({va:#x})'] = {
                'va': f'{va:#x}', 'next': f'{word:#010x}',
                'self_loop_after': any(lva == va + 4 for lva, _ in self_loop(probe, data, va, va + 8)),
            }

    # 2. common_start
    common_va = None
    for name in ('common_start', '_common_start'):
        if name in symbols.values():
            common_va = next(va for va, symbol in symbols.items() if symbol == name)
            break
    if common_va is None:
        report['missing'].append('common_start symbol')
        return report
    name, common_range = enclosing_function(probe, symbols, common_va)
    report['symbols']['common_start'] = {'name': name, 'range': [hex(common_range[0]), hex(common_range[1])]}

    wanted = {0xD5182040, 0xD5182041, 0xD518A200, 0xD508871F, 0xD508751F, 0xD518C000, 0xD5181000,
              0xD5181040, 0xD518D09F, 0xD5182020}
    for va, label in scan(probe, data, common_range[0], common_range[1], wanted):
        report['sites'].setdefault(label, {'va': f'{va:#x}'})

    # the TTBR0 helper call: the only `bl` in range that lands on a 12-byte
    # function whose single instruction is "msr TTBR0_EL1"
    for va in range(common_range[0], common_range[1], 4):
        word = struct.unpack_from('<I', data, probe.file_offset(va))[0]
        decoded = decode_branch(word, va)
        if not decoded or decoded[0] != 'bl':
            continue
        target = decoded[1]
        try:
            target_word = struct.unpack_from('<I', data, probe.file_offset(target + 4))[0]
        except SystemExit:
            continue
        if target_word == 0xD5182000:
            report['sites']['bl set_mmu_ttb'] = {'va': f'{va:#x}', 'target': f'{target:#x}'}

    for va, label in self_loop(probe, data, common_range[0], common_range[1]):
        report['sites'][f'self loop: {label}'] = {'va': f'{va:#x}'}

    # Every "msr SCTLR_EL1, x0" in the image. A payload build moves this
    # instruction into an injected band-painting cave, so the trampoline's own
    # site can be a plain "b" there; listing all sites makes that visible
    # instead of reporting a bare "missing".
    everywhere = []
    for start, end in file_backed_ranges(probe):
        for va in range(start, end, 4):
            if struct.unpack_from('<I', data, probe.file_offset(va))[0] == 0xD5181000:
                everywhere.append(va)
    report['sctlr_sites'] = [f'{va:#x}' for va in everywhere]
    sctlr_site = report['sites'].get('msr SCTLR_EL1, x0')
    if sctlr_site is None and everywhere:
        # The trampoline redirects to a cave: report where the real switch lives.
        inside = [va for va in everywhere if common_range[0] <= va < common_range[1]]
        outside = [va for va in everywhere if va not in inside]
        if outside:
            report['sites']['msr SCTLR_EL1, x0 (injected cave)'] = {'va': f'{outside[0]:#x}',
                                                                   'trampoline_site_redirected': True}

    sctlr = report['sites'].get('msr SCTLR_EL1, x0')
    if sctlr:
        value = sctlr_constant(probe, data, int(sctlr['va'], 16))
        sctlr['constant'] = f'{value:#x}' if value else None
        sctlr['enabled'] = sorted(name for bit, name in
                                  ((31, 'EnIA'), (30, 'EnIB'), (27, 'EnDA'), (13, 'EnDB'))
                                  if value and value & (1 << bit))
    else:
        report['missing'].append('msr SCTLR_EL1, x0')

    for required in ('msr TCR_EL1, x0', 'msr TCR_EL1, x1', 'msr MAIR_EL1, x0', 'msr VBAR_EL1, x0',
                     'bl set_mmu_ttb', 'msr SCTLR_EL1, x0'):
        if required not in report['sites']:
            report['missing'].append(required)
    satisfied_aliases = {
        'msr TCR_EL1, x0': ('msr TCR_EL1, x1',),
        'msr SCTLR_EL1, x0': ('msr SCTLR_EL1, x0 (injected cave)',),
    }
    report['missing'] = [name for name in report['missing']
                         if not any(alias in report['sites']
                                    for alias in satisfied_aliases.get(name, ()))]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--json', type=Path, help='write the full report here')
    args = parser.parse_args()
    probe = load_probe()
    report = analyse(probe, args.kernel)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
    print(f'kernel: {report["kernel"]}')
    for key, value in report['symbols'].items():
        print(f'  {key:<18} {value}')
    print('  sites:')
    for label, value in report['sites'].items():
        extra = {k: v for k, v in value.items() if k not in ('va',)}
        print(f'    {value["va"]:>16}  {label}' + (f'  {extra}' if extra else ''))
    if report['missing']:
        print('  missing: ' + ', '.join(report['missing']))
        return 1
    print('  every pre-MMU site the diagnostic patches need is present')
    return 0


if __name__ == '__main__':
    sys.exit(main())
