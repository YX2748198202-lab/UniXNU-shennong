#!/usr/bin/env python3
"""Build the board's minimal diagnostic screen against this kernel's real ABI.

Why this replaces the full BootProgress.c build
-----------------------------------------------
`package/BootProgress.c` is the complete diagnostic page: stages, kernel console
rows, panic log, touch overlay, UFS/virtio/cpufreq counters. It links against the
same subsystems those counters come from, so with this board's configuration
(NATIVE_UFS, virtio, cpufreq and touch all off) the archive leaves the kernel link
with undefined symbols (`_native_virtio_ready`, `_native_ufs_verify_ticks`,
`_sheng_cpufreq_poll`, ...).

The bring-up needs one thing from the screen first: how far the kernel got. So this
build compiles `package/BootProgressMini.c` — the same boot_progress_* entry points,
implemented as stage markers painted into the framebuffer — and keeps the
`char boot_progress_panic_text[2048]` symbol the panic-screen patcher resolves.

The archive path is the one `build-xnu-4k-baseline.sh` force-loads when
XNU_BOOT_PROGRESS=1.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/boot-progress'
OUT.mkdir(parents=True, exist_ok=True)
record = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/startup.o.json')
                    .read_text().strip().rstrip(','))
source = ROOT / 'kits/shennong/BootProgressMini.c'
obj = OUT / 'BootProgressMini.o'
command = []
args = record['arguments']
index = 0
while index < len(args):
    arg = args[index]
    if arg == record['file']:
        command.append(str(source))
    elif arg == '-o':
        command += ['-o', str(obj)]
        index += 1
    elif arg in ('-MF', '-MT', '-MJ'):
        index += 1
    elif arg == '-Xclang' and args[index + 1].startswith('-W'):
        index += 1
    elif arg == '-D' and args[index + 1].startswith('XNU_BOOT_PROGRESS='):
        index += 1
    elif not arg.startswith(('-W', '-DXNU_BOOT_PROGRESS=')):
        command.append(arg)
    index += 1
command += ['-DXNU_BOOT_PROGRESS=1', '-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror']
subprocess.run(command, cwd=record['directory'], check=True, timeout=90)
(OUT / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')

archive = OUT / 'libBootProgress.a'
archive.unlink(missing_ok=True)
subprocess.run(['xcrun', 'ar', 'rcs', str(archive), str(obj)], check=True, timeout=30)
(OUT / 'build-report.json').write_text(json.dumps({
    'source': str(source.relative_to(ROOT)),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'full_screen_skipped': 'BootProgress.c needs the UFS/virtio/cpufreq/touch subsystems this board does not build',
    'hardware_execution': False,
}, indent=2) + '\n')
print('PASS: minimal stage-marker diagnostic built against the source kernel ABI')
