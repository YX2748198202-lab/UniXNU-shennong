#!/usr/bin/env python3
"""Collect the panic() call sites reachable from a function, with their format strings.

The iOS 27 kernel dies inside `_arm_vm_init`'s first 2,324 bytes, but that region
contains **no** `bl _panic` at all: the panic comes from one of the ten functions
it calls there (or from something those call). Since the kernel cannot print at
that point, the message has to be identified by other means — and the first step
is knowing which format strings are even possible.

For each requested function this tool:

1. takes the function's range from the symbol table (start = symbol address,
   end = the next symbol, which is how the linker lays out a text segment),
2. finds every `bl _panic` / `bl _panic_trap_to_debugger` / `bl _panic_with_data`
   inside it,
3. walks back a few instructions to recover the value of `x0` (`adrp`/`add`, or
   `adrp` into a scratch register then `add x0, scratch, #imm`),
4. reads the format string at that address out of the kernel file, and
5. prints one TSV row per site:  name \t fmt_va \t call_site_va \t text

`--depth 1` also scans the functions the target calls, which is what the walk's
bracket needs: the panicking callee is one of the calls in the window.

Usage:
  scripts/collect-panic-sites.py --kernel KERNEL.macho --function _arm_vm_init --depth 1
  scripts/collect-panic-sites.py --kernel KERNEL.macho --window 0xVA:0xVA --depth 1

The output is what `patch-xnu-entry-probe.py --panic-fingerprint` consumes.
"""
import argparse
import importlib.util
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PANIC_FUNCTIONS = ('_panic', '_panic_trap_to_debugger', '_panic_with_data',
                   '_panic_unimplemented', '_panic_with_options')

# A12.2.4 data processing (immediate): add/sub, 64-bit, no shift.
ADD_X_MASK, ADD_X_VALUE = 0xFF800000, 0x91000000
ADRP_MASK, ADRP_VALUE = 0x9F000000, 0x90000000
BL_MASK, BL_VALUE = 0xFC000000, 0x94000000
B_MASK, B_VALUE = 0xFC000000, 0x14000000
MOVZ_X_MASK, MOVZ_X_VALUE = 0x7F800000, 0xD2800000 >> 0   # checked per-instruction below


def load_probe():
    spec = importlib.util.spec_from_file_location('probe', HERE / 'patch-xnu-entry-probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sext(value, bits):
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def decode_adrp(word, pc):
    rd = word & 0x1F
    imm = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 3)
    return rd, ((pc & ~0xFFF) + (sext(imm, 21) << 12)) & 0xFFFFFFFFFFFFFFFF


def decode_bl(word, pc):
    imm = sext(word & 0x03FFFFFF, 26)
    return (pc + imm * 4) & 0xFFFFFFFFFFFFFFFF


def is_call(word):
    """bl or b — the compiler reaches panic() both ways (cold parts often tail-branch)."""
    return (word & BL_MASK) in (BL_VALUE, B_VALUE)


def decode_add_imm(word):
    """(rd, rn, imm) for a 64-bit ADD (immediate), else None."""
    if (word & ADD_X_MASK) != ADD_X_VALUE:
        return None
    return word & 0x1F, (word >> 5) & 0x1F, (word >> 10) & 0xFFF


def decode_movz(word):
    """(rd, imm) for a 64-bit MOVZ, else None."""
    if (word & 0x7F800000) != (0xD2800000 & 0x7F800000) or not word & 0x80000000:
        return None
    return word & 0x1F, (word >> 5) & 0xFFFF


def format_string_at(data, probe, va):
    """Read a C string at va, or None when the address is not a readable string."""
    try:
        offset = probe.file_offset(va)
    except SystemExit:
        return None
    chunk = data[offset:offset + 96]
    for end, byte in enumerate(chunk):
        if byte == 0:
            break
    else:
        return None
    if end < 4:
        return None
    text = chunk[:end]
    if any(byte < 0x20 or byte > 0x7E for byte in text):
        return None
    return text.decode('ascii')


def find_format(blob, index, base, data, probe):
    """Recover x0 at blob[index] from the instructions that set it up.

    Two shapes matter and both appear in this kernel's cold sections:
      adrp x0, page / add x0, x0, #imm        (format string in __cstring)
      ldr x0, #imm19                          (format string from a literal pool)
    The nearest definition of x0 wins, so the window is read backwards, with the
    page map collected first — the `add` always comes before the `adrp` in a
    backwards walk.
    """
    window = list(range(max(index - 12, 0), index))
    pages, immediate = {}, {}
    for at in window:
        word = struct.unpack_from('<I', blob, at * 4)[0]
        if (word & ADRP_MASK) == ADRP_VALUE:
            rd, page = decode_adrp(word, base + at * 4)
            pages.setdefault(rd, page)
        else:
            movz = decode_movz(word)
            if movz:
                immediate.setdefault(movz[0], movz[1])
    for at in reversed(window):
        pc = base + at * 4
        word = struct.unpack_from('<I', blob, at * 4)[0]
        if (word & 0xFF000000) == 0x58000000:            # ldr x0, #imm19 (literal pool)
            rt = word & 0x1F
            if rt == 0:
                literal = (pc + (sext((word >> 5) & 0x7FFFF, 19) << 2)) & 0xFFFFFFFFFFFFFFFF
                try:
                    offset = probe.file_offset(literal)
                except SystemExit:
                    return None
                return struct.unpack_from('<Q', data, offset)[0]
        if (word & ADD_X_MASK) == ADD_X_VALUE:
            rd, rn, imm = decode_add_imm(word)
            if rd == 0:
                if rn in pages:
                    return (pages[rn] + imm) & 0xFFFFFFFFFFFFFFFF
                if rn == 0 and 0 in immediate:
                    return (immediate[0] + imm) & 0xFFFFFFFFFFFFFFFF
        movz = decode_movz(word)
        if movz and movz[0] == 0:
            return movz[1]
    return None


def function_range(symbols, name):
    """[start, end) of a function: its symbol address up to the next symbol."""
    starts = sorted(va for va in symbols if va >= 0xFFFFFFF000000000)
    va = next((value for value, symbol in symbols.items() if symbol == name), None)
    if va is None:
        raise SystemExit(f'{name} is not in the symbol table')
    index = starts.index(va)
    end = starts[index + 1] if index + 1 < len(starts) else va + 0x4000
    return va, end


def scan(blob, base, probe, symbols, data, depth, seen, rows):
    start, end = base
    length = (end - start) // 4
    if length <= 0 or length > 0x20000:
        return
    callees, cold = [], []
    owner = symbols.get(start, '')
    for index in range(length):
        word = struct.unpack_from('<I', blob, index * 4)[0]
        if not is_call(word):
            continue
        target = decode_bl(word, start + index * 4)
        symbol = symbols.get(target)
        site = start + index * 4
        if symbol in PANIC_FUNCTIONS:
            fmt = find_format(blob, index, start, data, probe)
            text = format_string_at(data, probe, fmt) if fmt else None
            rows.append({'kind': 'panic',
                         'function': symbols.get(start, f'0x{start:x}'),
                         'call_site': site,
                         'panic_fn': symbol,
                         'fmt_va': fmt,
                         'text': text})
        elif symbol and symbol not in seen:
            if symbol.startswith(owner + '.cold') or symbol.startswith('_OUTLINED_FUNCTION'):
                cold.append(symbol)
            elif depth:
                callees.append(symbol)
    for symbol in cold + callees:
        if symbol in seen:
            continue
        seen.add(symbol)
        callee_start, callee_end = function_range(symbols, symbol)
        try:
            offset = probe.file_offset(callee_start)
        except SystemExit:
            continue
        scan(data[offset:offset + (callee_end - callee_start)],
             (callee_start, callee_end), probe, symbols, data,
             depth - 1 if symbol in callees else depth, seen, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--kernel', required=True, type=Path, help='kernel.macho to scan')
    parser.add_argument('--function', action='append', default=[],
                        help='function to scan (repeatable)')
    parser.add_argument('--window', help='0xVA:0xVA — scan a raw address window instead')
    parser.add_argument('--depth', type=int, default=0,
                        help='also scan functions called by the target, this many levels deep')
    parser.add_argument('--min-text', type=int, default=4,
                        help='shortest format string worth reporting')
    parser.add_argument('--table', type=Path, help='write the TSV here instead of stdout')
    args = parser.parse_args()

    probe = load_probe()
    data = args.kernel.read_bytes()
    probe.load_segments(data)
    symbols = probe.kernel_symbols(str(args.kernel))

    if not args.function and not args.window:
        parser.error('give at least one --function or a --window')

    rows, seen = [], set()
    for name in args.function:
        start, end = function_range(symbols, name)
        offset = probe.file_offset(start)
        scan(data[offset:offset + (end - start)], (start, end), probe, symbols, data,
             args.depth, seen, rows)
    if args.window:
        low, _, high = args.window.partition(':')
        start, end = int(low, 0), int(high, 0)
        offset = probe.file_offset(start)
        scan(data[offset:offset + (end - start)], (start, end), probe, symbols, data,
             args.depth, seen, rows)

    rows = [row for row in rows if row['fmt_va'] and row['text']
            and len(row['text']) >= args.min_text]
    rows.sort(key=lambda row: (row['function'], row['call_site']))

    lines = ['name\tfmt_va\tcall_site_va\ttext']
    for row in rows:
        name = f"{row['function']}+0x{row['call_site'] - next(va for va, s in symbols.items() if s == row['function']):x}"
        lines.append(f"{name}\t0x{row['fmt_va']:x}\t0x{row['call_site']:x}\t{row['text']}")
    body = '\n'.join(lines) + '\n'
    if args.table:
        args.table.write_text(body)
        print(f'{len(rows)} panic call site(s) -> {args.table}')
    else:
        sys.stdout.write(body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
