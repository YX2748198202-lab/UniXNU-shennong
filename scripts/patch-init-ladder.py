#!/usr/bin/env python3
"""Paint a band ladder along _arm_init, marking each call *before* it runs.

patch-milestones.py marks a call after it returns, so a call that never returns
paints nothing.  This tool instead paints immediately before the call, so a
photo shows the last call that started even when the kernel dies inside it.

Markers are numbered from 0 and painted into band 0, 1, 2, ...  With the default
--from-call 1 the ladder is the _arm_init entry plus calls 1..15; with
--no-entry --from-call 16 it is calls 16..31, and so on, which lets one image
cover any window of the function.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

FB_BASE = 0xFC400000
FB_ROW = 5760
FB_HEIGHT = 3200
BAND_BYTES = (FB_ROW * FB_HEIGHT // 16) & ~7

COLOURS = [
    0xFFFFFFFF, 0xFFFF0000, 0xFFFF8000, 0xFFFFFF00,
    0xFF80FF00, 0xFF00FF00, 0xFF00FF80, 0xFF00FFFF,
    0xFF0080FF, 0xFF0000FF, 0xFF8000FF, 0xFFFF00FF,
    0xFFFF80C0, 0xFF804000, 0xFF808080, 0xFF32CD32,
]

CAVE_BASE = 0xFFFFFFF00B4F9700
CAVE_STRIDE = 0xE0

PAINT = """.text
.global _start
_start:
  stp x29, x30, [sp, #-16]!
  stp x0, x1, [sp, #-16]!
  stp x2, x3, [sp, #-16]!
  stp x4, x5, [sp, #-16]!
  movz x1, #{base_lo}
  movk x1, #{base_hi}, lsl 16
  movz w2, #{size_lo}
  movk w2, #{size_hi}, lsl 16
  mov x4, #{band}
  mul x5, x2, x4
  add x1, x1, x5
  movz w6, #{colour_lo}
  movk w6, #{colour_hi}, lsl 16
1:
  stp w6, w6, [x1], #8
  subs x2, x2, #8
  b.hi 1b
  dsb sy
  ldp x4, x5, [sp], #16
  ldp x2, x3, [sp], #16
  ldp x0, x1, [sp], #16
  ldp x29, x30, [sp], #16
"""

ENTRY_TAIL = """  pacibsp
  b tail
.ltorg
"""

CALL_TAIL = """  bl target
  b tail
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
    parser.add_argument('--probe-tool', type=Path,
                        default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves-ladder'))
    parser.add_argument('--from-call', type=int, default=1, help='1-based first call')
    parser.add_argument('--calls', type=int, default=15, help='how many calls to mark')
    parser.add_argument('--no-entry', action='store_true', help='omit the entry marker')
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    symbols = probe.kernel_symbols(args.kernel)
    entry = {name: va for va, name in symbols.items()}['_arm_init']

    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    code = bytes(data[probe.file_offset(entry):probe.file_offset(entry) + 0x2000])
    calls = []
    for ins in md.disasm(code, entry):
        if ins.mnemonic == 'bl':
            calls.append((ins.address, int(ins.op_str.lstrip('#'), 0)))
        if ins.mnemonic in ('ret', 'retab'):
            break
    first = args.from_call - 1
    window = calls[first:first + args.calls]
    if len(window) != args.calls:
        raise SystemExit(f'only {len(window)} calls available from {args.from_call}')

    markers = []
    if not args.no_entry:
        markers.append((entry, None))
    markers += window
    if len(markers) > 16:
        raise SystemExit(f'{len(markers)} markers exceed the 16 bands')

    args.workdir.mkdir(parents=True, exist_ok=True)
    for index, (site, target) in enumerate(markers):
        cave = CAVE_BASE + index * CAVE_STRIDE
        source = PAINT.format(
            base_lo=f'{FB_BASE & 0xFFFF:#x}', base_hi=f'{(FB_BASE >> 16) & 0xFFFF:#x}',
            size_lo=f'{BAND_BYTES & 0xFFFF:#x}', size_hi=f'{(BAND_BYTES >> 16) & 0xFFFF:#x}',
            band=index, colour_lo=f'{COLOURS[index] & 0xFFFF:#x}',
            colour_hi=f'{(COLOURS[index] >> 16) & 0xFFFF:#x}')
        source += ENTRY_TAIL if target is None else CALL_TAIL
        binds = {'tail': site + 4}
        if target is not None:
            binds['target'] = target
        blob = probe.assemble(source, cave, binds, args.workdir)
        if len(blob) > CAVE_STRIDE:
            raise SystemExit(f'cave {index} needs {len(blob)} bytes')
        data[probe.file_offset(cave):probe.file_offset(cave) + len(blob)] = blob
        site_off = probe.file_offset(site)
        word = struct.unpack_from('<I', data, site_off)[0]
        if target is not None and word >> 26 != 0b100101:
            raise SystemExit(f'site {site:#x} is not a bl')
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        if target is None:
            label = 'entry'
        elif args.no_entry:
            label = f'call {args.from_call + index}'
        else:
            label = f'call {args.from_call + index - 1}'
        print(f'  band {index:2d}  {label:8s} site {site:#x} -> cave {cave:#x}')

    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel} with {len(markers)} markers')


if __name__ == '__main__':
    main()
