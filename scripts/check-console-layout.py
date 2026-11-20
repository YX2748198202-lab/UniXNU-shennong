#!/usr/bin/env python3
"""Check the native 24A446 port's console pointers in an unstripped Mach-O.

Accept either the native executable or its symbol-bearing prelinked fileset.
XNU 12377's arm_vm_prot_init leaves __DATA_CONST writable until finalization,
but sets __KLDDATA read-only immediately. _PE_putc and _PE_kputc are written
during console startup: neither a move to __KLDDATA nor a move to permanently
writable __DATA preserves that lifecycle. This is a link-layout check, not a
measurement of live page tables or proof that the image boots. Optionally
check retained C++ metaclass pointer slots for bootstrap lifetime violations.
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
# 24A446 kext GOT entries dereference these slots, not gMetaClass objects.
RETAINED_METACLASS_SLOTS = frozenset({
    "__ZN18IOMemoryDescriptor9metaClassE", "__ZN12IOUserClient9metaClassE",
    "__ZN8OSObject9metaClassE", "__ZN12OSCollection9metaClassE",
})
EXPERIMENT_SECTION = "__pe_late"
DEFINED = re.compile(r"^\s*([0-9a-fA-F]+)\s+\(([^,()]+),([^,()]+)\)\s+.*\s(\S+)\s*$")


def definitions(symbol_table):
    for line in symbol_table.splitlines():
        match = DEFINED.fullmatch(line)
        if match:
            va, segment, section, name = match.groups()
            yield name, (int(va, 16), segment, section)


def check(symbol_table, *, experiment=False):
    found = {name: set() for name in EXPERIMENT_SYMBOLS if experiment or name in POINTERS}
    for name, location in definitions(symbol_table):
        if name in found:
            found[name].add(location)

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


def check_metaclass_lifetime(symbol_table):
    """Reject runtime OSMetaClass slots in the jettisoned kernel bootstrap data."""
    found = {}
    for name, location in definitions(symbol_table):
        if name.startswith("__ZN") and name.endswith("9metaClassE"):
            found.setdefault(name, set()).add(location)

    invalid = set()
    for name in sorted(found.keys() | RETAINED_METACLASS_SLOTS):
        entries = found.get(name, set())
        if len(entries) != 1 or any(segment != EXPECTED for _, segment, _ in entries):
            invalid.add(name)
            if name in RETAINED_METACLASS_SLOTS:
                slots = ", ".join(f"{va:#018x} ({segment},{section})"
                                  for va, segment, section in sorted(entries))
                print(f"FAIL {name}: {slots or 'no section-backed definition'}; expected resident {EXPECTED}")
    if invalid:
        print(f"FAIL metaclass lifetime: {len(invalid)} of "
              f"{len(found.keys() | RETAINED_METACLASS_SLOTS)} slots missing, ambiguous or outside {EXPECTED}")
    else:
        print(f"OK   metaclass lifetime: {len(found)} slots in resident {EXPECTED}")
    return len(invalid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("--nm", default="llvm-nm", help="path to a Mach-O nm (default: llvm-nm)")
    parser.add_argument("--experiment", action="store_true",
                        help="require all seven patched Platform Expert symbols in __DATA_CONST,__pe_late")
    parser.add_argument("--check-metaclass-lifetime", action="store_true",
                        help="require retained and other kernel metaclass slots to remain resident")
    args = parser.parse_args()
    try:
        result = subprocess.run([args.nm, "-m", str(args.kernel.resolve())],
                                capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"console layout: {getattr(error, 'stderr', '') or error}", file=sys.stderr)
        return 2
    failures = check(result.stdout, experiment=args.experiment)
    if args.check_metaclass_lifetime:
        failures += check_metaclass_lifetime(result.stdout)
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
