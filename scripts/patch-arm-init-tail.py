#!/usr/bin/env python3
"""nop 掉 arm_init 尾部 Apple 专有调用（脚手架补丁，可复用）

--keep-early-random leaves `bl _early_random` (0xB477534) alone.  The DRBG behind
read_erandom() is only set up by early_random_init(), which early_random() calls lazily
(osfmk/prng/prng_random.c:267-280), so stubbing the call leaves ccdrbg_info full of zeros and
the first random_bool_init() from zone_bootstrap dies on a null callback at
_ccdrbg_generate+0x3c (blraa x9).  The call can only be restored together with a boot seed:
bootseed_init_bootloader() panics unless /chosen/random-seed holds 4*SHA512_DIGEST_LENGTH =
256 bytes on arm64 (prng_random.c:52-55), see scripts/patch-adt-randseed.py.
"""
import importlib.util, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('probe', os.path.join(HERE, 'patch-xnu-entry-probe.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

path = sys.argv[1]
keep_early = '--keep-early-random' in sys.argv
# _PE_init_platform is the only thing that fills PE_state.video (pexpert/arm/pe_init.c:449), and
# the panic screen reads exactly that.  Leaving it off makes every later "no text" reading
# meaningless, so it gets its own switch.
keep_platform = '--keep-pe-init-platform' in sys.argv
KEEP_NAMES = {
    'serial':   0xFFFFFFF00B4774C0,   # _switch_to_serial_console
    'console':  0xFFFFFFF00B4774D0,   # _PE_create_console
    'printf':   0xFFFFFFF00B4774D8,   # _PE_init_printf
    'pio':      0xFFFFFFF00B477510,   # _ml_map_cpu_pio
    'timebase': 0xFFFFFFF00B477518,   # _cpu_timebase_init
    'kptimer':  0xFFFFFFF00B47751C,   # _kptimer_curcpu_up
    'cpu':      0xFFFFFFF00B477520,   # _PE_init_cpu
    'fiq':      0xFFFFFFF00B477530,   # _fiq_context_init
}
extra_keep = set()
for flag in sys.argv[1:]:
    if flag.startswith('--keep='):
        for name in flag.split('=', 1)[1].split(','):
            name = name.strip()
            if name not in KEEP_NAMES:
                raise SystemExit(f'unknown --keep name {name!r}; known: {", ".join(KEEP_NAMES)}')
            extra_keep.add(KEEP_NAMES[name])
data = bytearray(open(path, 'rb').read()); p.load_segments(bytes(data))
NOP = 0xD503201F
CALLS = [0xFFFFFFF00B4774C0, 0xFFFFFFF00B4774D0, 0xFFFFFFF00B4774D8,
         0xFFFFFFF00B4774F4, 0xFFFFFFF00B4774FC, 0xFFFFFFF00B477510,
         0xFFFFFFF00B477518, 0xFFFFFFF00B47751C, 0xFFFFFFF00B477520,
         0xFFFFFFF00B477524, 0xFFFFFFF00B477528, 0xFFFFFFF00B477530]
PE_INIT_PLATFORM = 0xFFFFFFF00B4774F4
for va in CALLS:
    if va in extra_keep:
        continue
    if keep_platform and va == PE_INIT_PLATFORM:
        continue
    struct.pack_into('<I', data, p.file_offset(va), NOP)
if keep_early:
    print('保留 bl _early_random（由 ADT 提供 256 字节熵）')
else:
    struct.pack_into('<I', data, p.file_offset(0xFFFFFFF00B477534), 0xD2800000)  # early_random -> mov x0,xzr
open(path, 'wb').write(bytes(data))
noped = len(CALLS) - (1 if keep_platform else 0) - len(extra_keep)
print(f'arm_init 尾部补丁完成：nop {noped} 个调用 + early_random '
      + ('保留' if keep_early else '置 0')
      + (' + PE_init_platform 保留' if keep_platform else '')
      + (f' + 额外保留 {len(extra_keep)} 个' if extra_keep else ''))
