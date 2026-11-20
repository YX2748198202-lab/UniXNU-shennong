#!/usr/bin/env python3
"""Check the native 24A446 port's console pointers in an unstripped Mach-O.

Accept either the native executable or its symbol-bearing prelinked fileset.
XNU 12377's arm_vm_prot_init leaves __DATA_CONST writable until finalization,
but sets __KLDDATA read-only immediately. _PE_putc and _PE_kputc are written
during console startup: neither a move to __KLDDATA nor a move to permanently
writable __DATA preserves that lifecycle. This is a link-layout check, not a
measurement of live page tables or proof that the image boots.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

POINTERS = ("_PE_putc", "_PE_kputc")
EXPERIMENT_SYMBOLS = (*POINTERS, "_gPEKernelConfigurationBitmask", "_disable_serial_output",
                      "_disable_kprintf_output", "_disable_iolog_serial_output",
                      "_enable_dklog_serial_output")
EXPECTED = "__DATA_CONST"
EXPERIMENT_SECTION = "__pe_late"
DEFINED = re.compile(r"^\s*([0-9a-fA-F]+)\s+\(([^,()]+),([^,()]+)\)\s+.*\s(\S+)\s*$")


def check(symbol_table, *, experiment=False):
    found = {name: set() for name in EXPERIMENT_SYMBOLS if experiment or name in POINTERS}
    for line in symbol_table.splitlines():
        match = DEFINED.fullmatch(line)
        if match:
            va, segment, section, name = match.groups()
            if name in found:
                found[name].add((int(va, 16), segment, section))

    failures = 0
    for name, entries in found.items():
        if len(entries) != 1:
            message = "no section-backed definition" if not entries else "ambiguous section-backed definitions"
            print(f"FAIL {name}: {message}")
            failures += 1
            continue
        va, segment, section = next(iter(entries))
        location = f"{va:#018x} ({segment},{section})"
        if segment != EXPECTED or (experiment and section != EXPERIMENT_SECTION):
            expected = f"({EXPECTED},{EXPERIMENT_SECTION})" if experiment else EXPECTED
            print(f"FAIL {name}: {location}; expected {expected} (writable until VM finalization)")
            failures += 1
        else:
            print(f"OK   {name}: {location}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--nm", default="llvm-nm", help="path to a Mach-O nm (default: llvm-nm)")
    parser.add_argument("--experiment", action="store_true",
                        help="require all seven patched Platform Expert symbols in __DATA_CONST,__pe_late")
    args = parser.parse_args()
    try:
        result = subprocess.run([args.nm, "-m", str(args.kernel.resolve())],
                                capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"console layout: {getattr(error, 'stderr', '') or error}", file=sys.stderr)
        return 2
    return int(check(result.stdout, experiment=args.experiment) != 0)


if __name__ == "__main__":
    sys.exit(main())
