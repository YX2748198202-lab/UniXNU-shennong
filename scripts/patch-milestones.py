#!/usr/bin/env python3
"""Paint one 1/16 colour band per early-boot milestone into a copy of the kernel.

Why this exists
---------------
The board has no serial console and XNU cannot draw before its own video console
is up, so an early stop leaves the panel frozen with only the entry bands. A
reset probe answers one question per boot *and* leaves the phone hung when the
probe is not reached, which needs a physical power cycle. This tool instead
paints a cumulative ladder: every listed call site in `_arm_init` is replaced by
a call to a cave that (1) paints one full 1/16 band of the frame buffer in its
own colour, (2) re-executes the displaced call, (3) branches back. The screen
therefore keeps the highest band the CPU reached, and a photo taken at any later
moment reads the answer. Nothing is blocked: if the kernel survives all of the
bands it keeps booting normally.

The frame buffer address, row bytes and height are the values DarwinBoot prints
(base 0xFC400000, 1440x3200, row 5760, 32 bpp); every band is height/16 rows.
All listed sites run before `arm_vm_init` replaces the loader's page tables, so
the physical frame buffer is still mapped and writable there.

The band indices start at 3 because the entry probe already paints band 1
(blue) at the kernel entry and band 2 (magenta) just before the MMU is enabled.
"""
import argparse
import importlib.util
import struct
from pathlib import Path

FB_BASE = 0xFC400000  # splash_region from the board ADT (DarwinBoot prints the same)
FB_ROW = 5760
FB_HEIGHT = 3200
BAND_BYTES = (FB_ROW * FB_HEIGHT // 16) & ~7

# (symbol called from _arm_init, band index, colour word, label)
MILESTONES = [
    ('_OSRuntimeSignStructors', 3, 0xFFFFFFFF, 'white        fileset signatories'),
    ('_PE_init_platform', 4, 0xFFFF0000, 'red          PE_init_platform'),
    ('_configure_timer_apple_regs', 5, 0xFFFF8000, 'orange       timer regs configured'),
    ('_SecureDTGetProperty', 6, 0xFFFFFF00, 'yellow       DT properties read'),
    ('_check_for_failure_injection', 7, 0xFF80FF00, 'yellow-green failure injection checked'),
    ('_ml_parse_cpu_topology', 8, 0xFF00FF00, 'green        cpu topology parsed'),
    ('_thread_bootstrap', 9, 0xFF00FF80, 'spring green thread_bootstrap'),
    ('_cpu_bootstrap', 10, 0xFF00FFFF, 'cyan         cpu_bootstrap'),
    ('_kernel_startup_bootstrap', 11, 0xFF0080FF, 'sky blue     kernel_startup_bootstrap'),
    ('_timer_call_init', 12, 0xFF0000FF, 'blue         timer_call_init'),
    ('_cpu_init', 13, 0xFF8000FF, 'violet       cpu_init'),
    ('_processor_bootstrap', 14, 0xFFFF00FF, 'magenta      processor_bootstrap'),
    ('_arm_vm_init', 15, 0xFF32CD32, 'lime         reached arm_vm_init'),
]

CAVE_BASE = 0xFFFFFFF00B4F9700  # all-zero tail padding of __TEXT_EXEC in the 24A446 kernel
CAVE_STRIDE = 0xE0

ASM = """.text
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
  bl target
  b back

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
    parser.add_argument('--workdir', type=Path, default=Path('/tmp/probe/caves'))
    args = parser.parse_args()

    probe = load_probe(args.probe_tool)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    symbols = probe.kernel_symbols(args.kernel)

    args.workdir.mkdir(parents=True, exist_ok=True)
    patched = []
    for index, (symbol, band, colour, label) in enumerate(MILESTONES):
        site, target = probe.find_call(bytes(data), symbols, '_arm_init', symbol, 1)
        cave = CAVE_BASE + index * CAVE_STRIDE
        source = ASM.format(
            base_lo=f'{FB_BASE & 0xFFFF:#x}',
            base_hi=f'{(FB_BASE >> 16) & 0xFFFF:#x}',
            size_lo=f'{BAND_BYTES & 0xFFFF:#x}',
            size_hi=f'{(BAND_BYTES >> 16) & 0xFFFF:#x}',
            band=band,
            colour_lo=f'{colour & 0xFFFF:#x}',
            colour_hi=f'{(colour >> 16) & 0xFFFF:#x}',
        )
        code = probe.assemble(source, cave, {'target': target, 'back': site + 4}, args.workdir)
        if len(code) > CAVE_STRIDE:
            raise SystemExit(f'cave {band} needs {len(code)} bytes, stride {CAVE_STRIDE}')
        cave_off = probe.file_offset(cave)
        site_off = probe.file_offset(site)
        data[cave_off:cave_off + len(code)] = code
        if struct.unpack_from('<I', data, site_off)[0] >> 26 != 0b100101:
            raise SystemExit(f'site {site:#x} is not a bl')
        struct.pack_into('<I', data, site_off, probe.branch(site, cave))
        patched.append((band, label, site, cave, len(code)))

    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel}')
    for band, label, site, cave, size in patched:
        print(f'  band {band}: {label:34s} site {site:#x} -> cave {cave:#x} ({size} bytes)')


if __name__ == '__main__':
    main()
