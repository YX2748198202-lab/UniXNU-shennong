#!/usr/bin/env python3
"""Wire non-stopping checkpoints ("beacons") into kernel functions.

A beacon draws its tag on the frame buffer and returns, so one boot shows the whole trajectory
of functions entered instead of a single stop.  The drawing code is the one in
scripts/xnu-panic-screen.c (fb_beacon), which builds its own TTBR1 mapping for the frame buffer;
the panic screen keeps working in the same build because both go through fb_setup().

Each site gets its own stub because the tag is an immediate:

    sub  sp, sp, #0x60
    stp  x0, x1, [sp, #0x00]      ... x0..x17, plus x18/x30 in the last pair
    mov  x0, #TAG
    bl   <fb_beacon>
    ldp  ... restore
    add  sp, sp, #0x60
    b    <site+4>          (or the original instruction, see --insn)

Only x0..x18 and x30 are saved: fb_beacon obeys AAPCS64 and preserves x19..x29, and the sites are
function entries where the argument registers are the only live state.
"""
import argparse
import importlib.util
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('probe', HERE / 'patch-xnu-entry-probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

STUB = """.text
.global _start
_start:
  {first}
  sub  sp, sp, #0xa0
  stp  x0, x1, [sp, #0x00]
  stp  x2, x3, [sp, #0x10]
  stp  x4, x5, [sp, #0x20]
  stp  x6, x7, [sp, #0x30]
  stp  x8, x9, [sp, #0x40]
  stp  x10, x11, [sp, #0x50]
  stp  x12, x13, [sp, #0x60]
  stp  x14, x15, [sp, #0x70]
  stp  x16, x17, [sp, #0x80]
  stp  x18, x30, [sp, #0x90]
  ldr  x1, [sp, #0x00]        /* the caller's x0: boot_args at the arm_init end */
  mov  x0, #{tag}
  bl   beacon
  ldp  x18, x30, [sp, #0x90]
  ldp  x16, x17, [sp, #0x80]
  ldp  x14, x15, [sp, #0x70]
  ldp  x12, x13, [sp, #0x60]
  ldp  x10, x11, [sp, #0x50]
  ldp  x8, x9, [sp, #0x40]
  ldp  x6, x7, [sp, #0x30]
  ldp  x4, x5, [sp, #0x20]
  ldp  x2, x3, [sp, #0x10]
  ldp  x0, x1, [sp, #0x00]
  add  sp, sp, #0xa0
  b back
"""



def find_zero_run(data, base, size, need, prefer, limit=0x4000000):
    """Find `need` zero bytes inside a segment, closest to `prefer`."""
    best = None
    start = base
    end = base + size
    while start < end:
        off = probe.file_offset(start)
        chunk = data[off:off + need]
        if len(chunk) == need and not any(chunk):
            distance = abs(start - prefer)
            if best is None or distance < best[0]:
                best = (distance, start)
            start += need
            continue
        start += 4
    if best is None or best[0] > limit:
        raise SystemExit(f'no {need:#x}-byte zero run within {limit:#x} of {prefer:#x}')
    return best[1]


def segment_of(addr):
    for base, size, _, _ in probe.SEGMENTS:
        if base <= addr < base + size:
            return base, size
    raise SystemExit(f'{addr:#x} is not inside a mapped segment')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('kernel', type=Path)
    ap.add_argument('--beacon', action='append', default=[], metavar='SYMBOL:TAG',
                    help='function entry to beacon, e.g. _zone_bootstrap:3')
    ap.add_argument('--screen-va', type=lambda v: int(v, 0), default=None,
                    help='where the panic screen blob already sits (default: find a run for it)')
    args = ap.parse_args()
    if not args.beacon:
        raise SystemExit('nothing to do without --beacon')

    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    names = {v: k for k, v in probe.kernel_symbols(args.kernel).items()
             if isinstance(k, int) and k > 0xFFFFFF0000000000}

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        # The blob is placed by --panic-screen normally; when the caller already put one down we
        # need its address, so assemble once to learn the size and then look for the run.
        code, load, _entry = probe.assemble_c(ROOT / 'scripts/xnu-panic-screen.c',
                                              0xFFFFFFF00B4F6EE8, work, names)
        blob_va = args.screen_va
        if blob_va is None:
            base, size = segment_of(0xFFFFFFF00B4F6EE8)
            blob_va = find_zero_run(data, base, size, len(code), 0xFFFFFFF00B4F6EE8)
        shutil.rmtree(work / 'panic.o', ignore_errors=True)
        code, load, _entry = probe.assemble_c(ROOT / 'scripts/xnu-panic-screen.c', blob_va, work, names)
        off = probe.file_offset(blob_va)
        there = bytes(data[off:off + len(code)])
        if there != code:
            if any(there):
                raise SystemExit(f'{blob_va:#x} holds something other than this blob; '
                                 'pass --screen-va for the address --panic-screen used')
            data[off:off + len(code)] = code

        nm = shutil.which('llvm-nm') or '/opt/homebrew/opt/llvm/bin/llvm-nm'
        beacon_va = None
        for line in subprocess.run([nm, str(work / 'panic.elf')], capture_output=True,
                                   text=True, check=True).stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2] == 'fb_beacon':
                beacon_va = int(parts[0], 16)
        if beacon_va is None:
            raise SystemExit('fb_beacon is missing from the assembled blob')
        print(f'panic screen + beacon at {blob_va:#x} ({len(code):#x} bytes), fb_beacon {beacon_va:#x}')

        for spec_ in args.beacon:
            symbol, _, tag = spec_.partition(':')
            if not tag:
                raise SystemExit(f'{spec_}: expected SYMBOL:TAG')
            site = names.get(symbol)
            if site is None:
                raise SystemExit(f'{symbol} is not in the symbol table')
            insn = struct.unpack_from('<I', data, probe.file_offset(site))[0]
            if insn in (0, 0xFFFFFFFF):
                raise SystemExit(f'{site:#x}: no instruction at the {symbol} entry')
            # Every arm64e function starts with pacibsp or bti c.  It has to run again inside the
            # stub: skipping pacibsp leaves the return address unsigned and the function's own
            # retab then fails the check, which is fatal long after the beacon returned.
            if insn in (0xD503237F, 0xD503245F):
                first = f'.inst {insn:#010x}'
            elif (insn & 0xD503201F) == 0xD503201F:
                first = f'.inst {insn:#010x}'      # some other hint/nop: harmless to replay
            else:
                raise SystemExit(f'{symbol} starts with {insn:#010x}, which this stub cannot replay; '
                                 'pick a site that begins with pacibsp or bti')
            base, size = segment_of(site)
            stub_va = find_zero_run(data, base, size, 0x100, site)
            asm = STUB.format(tag=int(tag, 0), first=first)
            with tempfile.TemporaryDirectory() as tmp2:
                stub = probe.assemble(asm, stub_va, {'beacon': beacon_va, 'back': site + 4}, Path(tmp2))
            if any(data[probe.file_offset(stub_va):probe.file_offset(stub_va) + len(stub)]):
                raise SystemExit(f'stub run at {stub_va:#x} is not empty')
            data[probe.file_offset(stub_va):probe.file_offset(stub_va) + len(stub)] = stub
            struct.pack_into('<I', data, probe.file_offset(site), probe.branch(site, stub_va))
            print(f'  {symbol} @ {site:#x} -> tag {tag}: stub {stub_va:#x} ({len(stub):#x} bytes, replays {first})')

    args.kernel.write_bytes(bytes(data))
    print(f'{args.kernel}: beacons wired')


if __name__ == '__main__':
    main()
