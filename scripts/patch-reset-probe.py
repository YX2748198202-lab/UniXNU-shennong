#!/usr/bin/env python3
"""Probe a boot stage by resetting the SoC a fixed delay after a marker.

A band on screen only helps while somebody is looking at the phone.  This probe
turns "did the kernel reach marker X" into a USB-observable event instead: the
cave spins on the generic counter for --delay-seconds and then issues PSCI
SYSTEM_RESET.  A device that shows up on USB again ~delay later reached the
marker; a device that stays dark did not.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

CAVE_BASE = 0xFFFFFFF00B4FB800
DEFAULT_SITE = 0xFFFFFFF00B4768D0   # _arm_init entry

ASM = """.text
.global _start
_start:
  stp  x0, x1, [sp, #-0x10]!
  stp  x2, x3, [sp, #-0x10]!
  stp  x4, x5, [sp, #-0x10]!
  stp  x29, x30, [sp, #-0x10]!
  mrs  x9, cntfrq_el0
  movz x10, #0x{dsec}
  mul  x10, x9, x10
  mrs  x11, cntpct_el0
  add  x10, x11, x10
1:
  mrs  x11, cntpct_el0
  cmp  x11, x10
  b.lo 1b
  movz x0, #0x8400, lsl #16
  movk x0, #0x9
  smc  #0
  b    .
.ltorg
"""


def load_probe(path):
    spec = importlib.util.spec_from_file_location('probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--site', default=hex(DEFAULT_SITE))
    parser.add_argument('--delay-seconds', type=int, default=8)
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-reset'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    probe.kernel_symbols(args.kernel)

    site = int(args.site, 0)
    args.workdir.mkdir(parents=True, exist_ok=True)
    asm = ASM.format(dsec=args.delay_seconds)
    blob = probe.assemble(asm, CAVE_BASE, {}, args.workdir)
    off = probe.file_offset(CAVE_BASE)
    data[off:off + len(blob)] = blob
    site_off = probe.file_offset(site)
    old = struct.unpack_from('<I', data, site_off)[0]
    struct.pack_into('<I', data, site_off, probe.branch(site, CAVE_BASE))
    args.kernel.write_bytes(bytes(data))
    print(f'reset probe: cave {len(blob)} bytes at {CAVE_BASE:#x},'
          f' site {site:#x} was {old:#010x}, delay {args.delay_seconds}s')


if __name__ == '__main__':
    main()
