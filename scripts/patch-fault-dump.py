#!/usr/bin/env python3
"""Draw the EL1 fault registers on the frame buffer from _sleh_synchronous.

Entered before the kernel has any console, so the four values (ESR, FAR, ELR,
SPSR) are painted at the physical frame buffer address of the splash region and
then execution returns to the original handler.
"""
import argparse, importlib.util, struct, subprocess, tempfile
from pathlib import Path

CAVE_VA = 0xFFFFFFF00B4FA400   # free zero padding tail of __TEXT_EXEC

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel', type=Path)
    ap.add_argument('--probe-tool', type=Path, default=Path(__file__).with_name('patch-xnu-entry-probe.py'))
    ap.add_argument('--src', type=Path, default=Path('/tmp/probe/fault'))
    ap.add_argument('--va', type=lambda s: int(s, 0), default=CAVE_VA)
    ap.add_argument('--mode', choices=('paint', 'reset'), default='paint',
                    help='paint only, or paint then wait --photo-seconds and reset')
    ap.add_argument('--photo-seconds', type=int, default=45)
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location('probe', args.probe_tool)
    probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
    data = bytearray(args.kernel.read_bytes())
    probe.load_segments(bytes(data))
    syms = {name: va for va, name in probe.kernel_symbols(args.kernel).items()}

    handler = syms['_sleh_synchronous']
    first = struct.unpack_from('<I', data, probe.file_offset(handler))[0]
    work = Path(tempfile.mkdtemp())
    size_hint = 0x300
    asm = (args.src / 'cave.S').read_text().replace('.inst 0x00000000', f'.inst {first:#010x}')
    (work / 'cave.S').write_text(asm)
    clang = 'clang'; lld = 'ld.lld'; objcopy = 'llvm-objcopy'; nm = 'llvm-nm'
    subprocess.run([clang, '--target=aarch64-none-elf', '-c', work / 'cave.S', '-o', work / 'cave.o'], check=True)
    subprocess.run([clang, '--target=aarch64-none-elf', '-ffreestanding', '-fno-builtin',
                    '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-mgeneral-regs-only',
                    '-fno-pic', '-mcmodel=tiny', '-Oz',
                    f'-DCAVE_LO={args.va:#x}', f'-DCAVE_HI={args.va + size_hint:#x}',
                    f'-DPHOTO_SECONDS={args.photo_seconds}',
                    '-c', args.src / ('dump_reset.c' if args.mode == 'reset' else 'dump.c'),
                    '-o', work / 'dump.o'], check=True)
    # .rodata (the font) must sit right after .text: the default placement jumps a
    # page and would land in the hole between __TEXT_EXEC and __DATA.
    (work / 'fault.ld').write_text(
        'SECTIONS {\n'
        f'  . = {args.va:#x};\n'
        '  .text : { *(.text*) }\n'
        '  .rodata : { *(.rodata*) }\n'
        '  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }\n'
        '}\n')
    subprocess.run([lld, '-T', work / 'fault.ld', f'--defsym=back={handler + 4:#x}',
                    '-e', '_start', work / 'cave.o', work / 'dump.o', '-o', work / 'fault.elf'], check=True)
    load = None
    for line in subprocess.check_output([nm, work / 'fault.elf'], text=True).splitlines():
        p = line.split()
        if len(p) == 3 and p[2] == '_start':
            load = int(p[0], 16)
    if load is None:
        raise SystemExit('no _start in the linked image')
    subprocess.run([objcopy, '-O', 'binary', work / 'fault.elf', work / 'fault.bin'], check=True)
    code = (work / 'fault.bin').read_bytes()
    off = probe.file_offset(load)
    region = bytes(data[off:off + len(code)])
    if any(region):
        raise SystemExit(f'the cave at {load:#x} is not empty')
    data[off:off + len(code)] = code
    struct.pack_into('<I', data, probe.file_offset(handler), probe.branch(handler, load))
    args.kernel.write_bytes(bytes(data))
    print(f'patched {args.kernel.name}: fault dump {len(code)} bytes at {load:#x}, '
          f'_sleh_synchronous {handler:#x} -> b {load:#x}')

if __name__ == '__main__':
    main()
