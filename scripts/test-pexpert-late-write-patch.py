#!/usr/bin/env python3
"""Link the exact XNU Platform Expert declarations before and after the patch.

Pass a directory with the unmodified ac9718f source files, or a complete checkout.
Use --kernel-link with the cctools linker to exercise the two CI renames
in a static arm64e link. This does not build the kernel or fileset.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/experiments/pexpert-late-write-section.patch"
HEADER = "libkern/libkern/section_keywords.h"
FILES = ("pexpert/gen/pe_gen.c", "pexpert/arm/pe_kprintf.c")
SYMBOLS = ("gPEKernelConfigurationBitmask", "PE_putc", "PE_kputc", "disable_serial_output",
           "disable_kprintf_output", "disable_iolog_serial_output", "enable_dklog_serial_output")


def declarations(source, names):
    lines = source.read_text().splitlines()
    for name in names:
        definition = re.compile(rf"\b{re.escape(name)}(?: = (?:true|false))?;$")
        found = [i for i, line in enumerate(lines)
                 if definition.search(line) and (line.startswith("SECURITY_READ_ONLY_LATE(")
                                                 or (i and lines[i-1].startswith("__attribute__")))]
        if len(found) != 1:
            raise ValueError(f"expected one annotated definition of {name} in {source}")
        i = found[0]
        if not lines[i].startswith("SECURITY_READ_ONLY_LATE("):
            yield lines[i-1]
        yield lines[i]


def build_and_check(tree, work, mode, tools, *, kernel_link):
    clang, linker, nm = tools
    source = work / f"{mode}.c"
    source.write_text('#include "section_keywords.h"\n'
                      'typedef unsigned int uint32_t;\n'
                      'typedef void (*PE_putc_t)(char), (*PE_kputc_t)(char);\n'
                      '#define bool _Bool\n#define true 1\n#define false 0\n'
                      + '\n'.join((*declarations(tree / FILES[0], SYMBOLS[:2]),
                                   *declarations(tree / FILES[1], SYMBOLS[2:])))
                      + '\n__attribute__((used, section("__DATA_CONST,__const")))\n'
                        'const unsigned long immutable_fixture = 42;\n'
                        'void entry(void) {}\n')
    obj = source.with_suffix('.o')
    image = source.with_suffix('.macho')
    compile_mode = ['-mkernel'] if kernel_link else []
    subprocess.run([clang, '--target=arm64e-apple-ios27.0', '-ffreestanding', *compile_mode, '-I',
                    str(tree / HEADER.rsplit('/', 1)[0]), '-c', str(source), '-o', str(obj)], check=True)
    # XNU first maps __DATA,__const into __DATA_CONST,__const. CI then
    # maps that output into __KLDDATA,__const. ld64.lld fixtures express
    # the first move directly, while cctools can run the actual sequence.
    link_mode = ['-static', '-kernel', '-Z'] if kernel_link else []
    first_segment = '__DATA_CONST' if kernel_link else '__KLDDATA'
    subprocess.run([linker, *link_mode, '-arch', 'arm64e', '-platform_version', 'ios', '27.0', '27.0',
                    '-e', '_entry', '-rename_section', '__DATA', '__const', first_segment, '__const',
                    '-rename_section', '__DATA_CONST', '__const', '__KLDDATA', '__const',
                    '-segprot', '__DATA_CONST', 'r--', 'r--', '-o', str(image), str(obj)], check=True)
    table = subprocess.check_output([nm, '-m', str(image)], text=True)
    wanted = '(__DATA_CONST,__pe_late)' if mode == 'patched' else '(__KLDDATA,__const)'
    for name in SYMBOLS + ('immutable_fixture',):
        expected = '(__KLDDATA,__const)' if name == 'immutable_fixture' else wanted
        defs = [line for line in table.splitlines() if line.endswith(' _' + name)]
        if len(defs) != 1 or expected not in defs[0]:
            raise AssertionError(f'{mode}: {name} expected {expected}, got {defs}')
        print(f'{mode}: {name}: {expected}')
    for qualification in ([], ['--experiment']):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/check-console-layout.py'),
                                 '--nm', nm, *qualification, str(image)], check=False)
        if result.returncode != int(mode == 'original'):
            raise AssertionError(f'{mode}: layout checker {qualification} returned {result.returncode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--clang', default='clang-18')
    parser.add_argument('--linker', default='ld64.lld-18')
    parser.add_argument('--kernel-link', action='store_true',
                        help='use static kernel-mode flags and chained section renames (requires cctools ld)')
    parser.add_argument('--nm', default='llvm-nm-18')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pexpert-late-write-') as directory:
        work = Path(directory)
        tree = work / 'src'
        for rel in (*FILES, HEADER):
            dest = tree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.source / rel, dest)
        tools = args.clang, args.linker, args.nm
        build_and_check(tree, work, 'original', tools, kernel_link=args.kernel_link)
        subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=tree, check=True)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=tree, check=True)
        build_and_check(tree, work, 'patched', tools, kernel_link=args.kernel_link)
    print('pexpert late write: fixture regression passed')


if __name__ == '__main__':
    main()
