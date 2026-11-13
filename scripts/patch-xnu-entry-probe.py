#!/usr/bin/env python3
# Vendored from the UniXNU framework, pin c740efb5b23e94453bb179f7801eb592baafacf6,
# scripts/patch-xnu-entry-probe.py (bytes unchanged below this banner).
# The patch scripts in this directory import it by path for load_segments() /
# file_offset() / branch() / assemble() / kernel_symbols() / function_range() /
# find_call(); before 2026-11-10 it only existed in /tmp/probe, so a fresh
# checkout could not rebuild or re-verify a diagnostic image.
# The hard-coded VAs in main() belong to the framework's baseline kernel: use this
# file as a library and keep the board's addresses in the patch scripts.
# One local change: assemble() creates its work directory (the board patch scripts
# pass e.g. /tmp/probe/fault and relied on the tool to create it).
"""Put boot-progress probes into a COPY of the source XNU kernel (never the original).

There is no serial console on the device and the kernel cannot draw before its
own video console exists, so the early boot stages are reported by side
channels. The stage code lives in the zero padding after the kernel entry
(_start is one `b`) and displaced instructions are re-executed there:

  stage 1 (kernel entry, MMU off)       blue bar, then continues
  stage 2 (just before the MMU is on)   magenta bar, then continues
  stage 3 (right after the MMU is on)   waits --reset-delay seconds, then PSCI
                                        SYSTEM_RESET. A reboot by itself after
                                        that time shows the CPU got through the
                                        MMU enable; the frame buffer is not
                                        mapped by then, so time is the signal.
  panic screen (--panic-screen)         panic() and its common panic funnel draw
                                        their format string on the
                                        kernel's own frame buffer mapping and
                                        stops (scripts/xnu-panic-screen.c).
                                        --no-reset leaves out stages 3 and 4.
  stage 4 (--reset-after SYMBOL)        the same wait and reset, but placed after
                                        the call to SYMBOL in --in FUNCTION (the
                                        Nth call, --occurrence). It replaces
                                        stage 3, so one run asks one question:
                                        did the kernel get past that call?

The bars are the 1/16th bands of the frame buffer below the green one that
DarwinBoot paints (band index = stage). Each patch site is checked against its
expected original instruction first, and the tool refuses a kernel that does
not match. Offsets are specific to the kernel built by build-xnu-4k-baseline.sh.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ENTRY_VA = 0xFFFFFFF00B9D0488        # LC_UNIXTHREAD pc, `b start_first_cpu`
START_FIRST_CPU = 0xFFFFFFF00B9D205C
MMU_ENABLE_VA = 0xFFFFFFF00AD83418   # msr SCTLR_EL1, x0
AFTER_MMU_VA = 0xFFFFFFF00B9D2350    # mov x0, #0x300000
PANIC_VA = 0xFFFFFFF00BF69B04      # _panic
PANIC_DRY_RUN = False
VINFO_VA = 0xFFFFFFF00C0A2970      # _vinfo
PANIC_CAVE_END = 0xFFFFFFF00B9D0FF0
CAVE_SIZE = 0x60
CAVES = {1: 0xFFFFFFF00B9D0500, 2: 0xFFFFFFF00B9D0560, 3: 0xFFFFFFF00B9D05C0, 4: 0xFFFFFFF00B9D0620}
TIMEBASE = 19200000

PAINT = """
  ldr x1, [{args}, #0x28]
  ldr x2, [{args}, #0x38]
  ldr x3, [{args}, #0x48]
  mul x2, x2, x3
  lsr x2, x2, #4
  bic x2, x2, #7
  mov x4, #{band}
  mul x5, x2, x4
  add x1, x1, x5
  movz w6, #{lo}
  movk w6, #{hi}, lsl #16
1:
  stp w6, w6, [x1], #8
  subs x2, x2, #8
  b.hi 1b
  dsb sy
"""

SOURCES = {
    1: ".text\n.global _start\n_start:\n" + PAINT.format(args='x0', band=1, lo='0x00FF', hi='0xFF00') + "  b target\n",
    2: ".text\n.global _start\n_start:\n" + PAINT.format(args='x20', band=2, lo='0x00FF', hi='0xFFFF')
       + "  msr SCTLR_EL1, x0\n  b target\n",
    3: """.text
.global _start
_start:
  mov x0, #0x300000
  mrs x1, cntpct_el0
  ldr x2, ={ticks}
  add x2, x1, x2
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n",
    4: """.text
.global _start
_start:
  bl callee
  mrs x1, cntpct_el0
  ldr x2, ={ticks}
  add x2, x1, x2
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n",
}

# Stage 5 is the control experiment for the reset path itself: wait, then reset without
# ever returning to the kernel. A reboot after --reset-delay seconds proves PSCI
# SYSTEM_RESET reaches the platform's secure monitor; without that proof a silent stage 3
# cannot be told apart from a dead reset call. It paints nothing: the reboot is the signal,
# and a band would push the body past the 0x60 bytes a cave holds.
SOURCES[5] = (".text\n.global _start\n_start:\n"
              + """  mrs x1, cntpct_el0
  ldr x2, ={ticks}
  add x2, x1, x2
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n")

# Stage 5 borrows stage 1's cave: it replaces stage 1 instead of adding to it.
MONITOR_MSR = 0xD508831F         # msr s3_4_c8_c3_1, xzr inside ml_enable_monitor()
CAVE_OF = {5: 1, 6: 2}   # 6 = stage 2 with the frame buffer stash

# A silent death can be either a panic() with nowhere to print or a fault the exception
# handler ate. Panic reset answers that in one run: _panic() jumps here, waits, and asks
# the secure monitor for a reboot. A reboot therefore means "the kernel panicked", while
# a dark screen means the CPU never reached panic() at all.
PANIC_RESET = """.text
.global _start
_start:
  mrs x1, cntpct_el0
  ldr x2, ={ticks}
  add x2, x1, x2
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n"


# The fingerprint hook: a panic whose message cannot be printed still has to be named. panic()
# receives the format string in x0, so one slice of that address is turned into a measurable
# reset delay: the device reboots BASE + slice*STEP seconds after the panic, and the host
# recovers the slice from the clock. Two or three differently shifted slices reconstruct the
# whole pointer, which names the panic string exactly.
SLICE_RESET = """.text
.global _start
_start:
  lsr x9, {reg}, #{shift}
  and x9, x9, #{mask}
  movz x10, #{step}
  mul x9, x9, x10
  add x9, x9, #{base}
  movz x10, #{timebase_lo}
  movk x10, #{timebase_hi}, lsl 16
  mul x9, x9, x10
  mrs x1, cntpct_el0
  add x2, x1, x9
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl 16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n"


FAR_SLICE_RESET = """.text
.global _start
_start:
  mrs x0, far_el1
  lsr x9, {reg}, #{shift}
  and x9, x9, #{mask}
  movz x10, #{step}
  mul x9, x9, x10
  add x9, x9, #{base}
  movz x10, #{timebase_lo}
  movk x10, #{timebase_hi}, lsl 16
  mul x9, x9, x10
  mrs x1, cntpct_el0
  add x2, x1, x9
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl 16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n"

# The fingerprint hook, table form: when the possible format strings are known (they are, for
# the three panics reachable before vm_set_page_size), compare x0 against each of them and
# reboot at a delay that names the one that matched. The host subtracts a calibration round
# and the remaining seconds say which panic fired.
# Self-test for the display channel: at a site that is known to be reached, read back the frame
# buffer stage 6 saved and paint the low four bits of that value as four bands. If the bands show
# up, the stash and the frame buffer write both work and panic() can be made to talk.
# Same four bars, but with the frame buffer address given on the command line instead of read
# back from the stash: one boot then answers whether that address is writable after the MMU is on.
SELFTEST_CONST = """.text
.global _start
_start:
  ldr x1, ={fb}
  cbz x1, 9f
  ldr x11, ={fb_bytes}
  lsr x11, x11, #6
  mov x13, #0
1:
  lsr x14, x1, x13
  tbz w14, #0, 3f
  madd x15, x13, x11, x1
  movz w6, #0xFFFF
  movk w6, #0xFFFF, lsl 16
  mov x16, x11
2:
  stp w6, w6, [x15], #8
  subs x16, x16, #8
  b.hi 2b
3:
  add x13, x13, #1
  cmp x13, #4
  b.lo 1b
9:
{tail}
5:
  wfe
  b 5b
""" + ".ltorg\n"


SELFTEST = """.text
.global _start
_start:
  ldr x6, ={stash}
  ldr x1, [x6]
  cbz x1, 9f
  ldr x11, ={fb_bytes}
  lsr x11, x11, #6
  mov x13, #0
1:
  lsr x14, x1, x13
  tbz w14, #0, 3f
  madd x15, x13, x11, x1
  movz w6, #0xFFFF
  movk w6, #0xFFFF, lsl 16
  mov x16, x11
2:
  stp w6, w6, [x15], #8
  subs x16, x16, #8
  b.hi 2b
3:
  add x13, x13, #1
  cmp x13, #4
  b.lo 1b
9:
{tail}
5:
  wfe
  b 5b
""" + ".ltorg\n"


ASSERT_LINE_RESET = """.text
.global _start
_start:
  ldr x9, ={assert_fmt:#x}
  cmp x0, x9
  b.ne .Lnotassert
  lsr x9, x2, #{shift}
  and x9, x9, #0x3f
  add x9, x9, #{base}
  b .Lcommit
.Lnotassert:
  movz x9, #{unknown}
.Lcommit:
  movz x10, #{timebase_lo}
  movk x10, #{timebase_hi}, lsl 16
  mul x9, x9, x10
  mrs x1, cntpct_el0
  add x2, x1, x9
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl 16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n"

CANDIDATE_RESET = """.text
.global _start
_start:
{compare}
  movz x9, #{default_seconds}
  b .Lcommit
{slots}
.Lcommit:
  movz x10, #{timebase_lo}
  movk x10, #{timebase_hi}, lsl 16
  mul x9, x9, x10
  mrs x1, cntpct_el0
  add x2, x1, x9
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl 16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
2:
  wfe
  b 2b
""" + ".ltorg\n"

# Stage 1 and 2 run before the MMU turns the kernel's own page tables on, so they can still
# reach a kernel global by its PHYSICAL address; boot_args gives both bases. Saving the frame
# buffer there is what lets panic() draw later: _vinfo is empty this early, but the address the
# loader painted through is already known.
STASH_FB = """
  ldr x4, [x20, #0x08]
  ldr x5, [x20, #0x10]
  ldr x6, ={stash}
  sub x6, x6, x4
  add x6, x6, x5
  ldr x1, [x20, #0x28]      /* Boot_Video.v_baseAddr */
  str x1, [x6]
  stp x4, x5, [x6, #0x30]   /* VirtualBase, PhysicalBase: one instruction, keeps the cave in size */
  ldr x1, [x20, #0x38]      /* v_rowBytes */
  str x1, [x6, #0x10]
  ldr x1, [x20, #0x40]      /* v_width */
  str x1, [x6, #0x18]
  ldr x1, [x20, #0x48]      /* v_height */
  str x1, [x6, #0x20]
  ldr x1, [x20, #0x50]      /* v_depth */
  str x1, [x6, #0x28]
  add x1, x25, #0xf, lsl #12   /* bootstrap pool page 15, physical: a free L2 table */
  str x1, [x6, #0xff8]
"""

# The panic side: read the saved frame buffer, paint the low 32 bits of panic()'s format-string
# address as 32 bands (band i white when bit i is set), then stop. One photograph carries the
# whole pointer, which names the panic string exactly.
BANDS = """.text
.global _start
_start:
  ldr x6, ={stash}
  ldr x1, [x6]
  cbz x1, 9f
  ldr x11, ={framebuffer_bytes}
  lsr x11, x11, #6
  bic x11, x11, #7
  mov x13, #0
1:
  lsr x14, x0, x13
  tbz w14, #0, 3f
  madd x15, x13, x11, x1
  movz w6, #0xFFFF
  movk w6, #0xFFFF, lsl 16
  mov x16, x11
2:
  stp w6, w6, [x15], #8
  subs x16, x16, #8
  b.hi 2b
3:
  add x13, x13, #1
  cmp x13, #32
  b.lo 1b
9:
  wfe
  b 9b
""" + ".ltorg\n"


RESET_BEFORE = """.text
.global _start
_start:
  movz w0, #0x0009
  movk w0, #0x8400, lsl #16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
1:
  wfe
  b 1b
"""


def kernel_symbols(kernel):
    """Address -> name for the kernel's symbols, from llvm-nm."""
    nm = shutil.which('llvm-nm') or '/opt/homebrew/opt/llvm/bin/llvm-nm'
    table = {}
    # A fileset kernel makes llvm-nm emit lines that are not symbols at all
    # ("Symbols:", section headers), and its exit status is not a usable signal:
    # skip anything that does not parse instead of dying with
    # ValueError: invalid literal for int() with base 16: 'Symbols'
    result = subprocess.run([nm, '-n', kernel], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            address = int(parts[0], 16)
        except ValueError:
            continue
        table.setdefault(address, parts[2])
    if not table:
        print(f'kernel_symbols: nm rc={result.returncode} out={result.stdout[:300]!r} err={result.stderr[:300]!r}')
    return table


def function_range(symbols, name):
    """Start and end (next symbol) of a function by its symbol name."""
    starts = sorted(symbols)
    for start, symbol in symbols.items():
        if symbol == name:
            return start, next(address for address in starts if address > start)
    raise SystemExit(f'No symbol {name} in the kernel')


def find_call(data, symbols, function, name, occurrence):
    """The VA and target of the Nth `bl name` inside FUNCTION."""
    hits = []
    low, high = function_range(symbols, function)
    for va in range(low, high, 4):
        word = struct.unpack_from('<I', data, file_offset(va))[0]
        if word >> 26 == 0b100101:
            delta = word & 0x3FFFFFF
            delta -= (1 << 26) if delta & (1 << 25) else 0
            target = va + delta * 4
            if symbols.get(target) == name:
                hits.append((va, target))
    if len(hits) < occurrence:
        raise SystemExit(f'{function} has {len(hits)} call(s) to {name}, not {occurrence}')
    return hits[occurrence - 1]


def assemble_c(source, va, workdir, symbols):
    workdir.mkdir(parents=True, exist_ok=True)      # local change, see the banner
    """Build a freestanding C file for VA; returns (bytes, load address of the first byte, address of panic_screen).

    The linker may start .text a little after VA (it keeps the ELF headers in front), so the
    load address is read back from the ELF and is what the caller must write the bytes to."""
    clang = shutil.which('clang') or '/opt/homebrew/opt/llvm/bin/clang'
    lld = shutil.which('ld.lld') or '/opt/homebrew/opt/llvm/bin/ld.lld'
    objcopy = shutil.which('llvm-objcopy') or '/opt/homebrew/opt/llvm/bin/llvm-objcopy'
    nm = shutil.which('llvm-nm') or '/opt/homebrew/opt/llvm/bin/llvm-nm'
    # UNIXNU_UEFI is the Mu-Silicium checkout when the unixnu driver runs this script.
    font_dir = Path(os.environ.get('UNIXNU_UEFI') or ROOT / 'uefi-sheng') / 'Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib'
    if not (font_dir / 'Font.h').is_file():
        raise SystemExit('Panic screen requires Mu-Silicium FrameBufferSerialPortLib/Font.h; '
                         'set --uefi PATH or [build] uefi in unixnu.local.toml '
                         '(UNIXNU_UEFI for direct script calls)')
    obj, elf, binary = (workdir / name for name in ('panic.o', 'panic.elf', 'panic.bin'))
    definitions = []
    for macro, name, width in (('MAX_MEM', '_max_mem', 8),
                               ('PAGE_TOTAL', '_vm_page_pages', 4),
                               ('PAGE_FREE', '_vm_page_free_count', 4)):
        address = symbols.get(name)
        if address is None or address % width or not any(
                base <= address and address + width <= base + size
                for base, size, _, _ in SEGMENTS):
            raise SystemExit(f'Missing or invalid diagnostic symbol {name}')
        definitions.append(f'-D{macro}={address:#x}UL')
    # Optional: the board's banner buffer for the panic message (kits/sheng/BootProgress.c); kernels without it get 0 (no copy).
    text = symbols.get('_boot_progress_panic_text')
    if text is not None:
        if not any(base <= text and text + 256 <= base + size for base, size, _, _ in SEGMENTS):
            raise SystemExit('Invalid _boot_progress_panic_text')
        definitions.append(f'-DPANIC_TEXT={text:#x}UL')
        definitions.append(f'-DSTASH_VINFO={text:#x}UL')
        if PANIC_DRY_RUN:
            definitions.append('-DPANIC_DRY_RUN=1')
        pe_state = symbols.get('_PE_state')
        if pe_state is None:
            raise SystemExit('Missing _PE_state; the panic screen cannot read the frame buffer geometry')
        definitions.append(f'-DPE_STATE={pe_state:#x}UL')
        for macro, name in (('PHYS_BASE', '_gPhysBase'), ('VIRT_BASE', '_gVirtBase')):
            address = symbols.get(name)
            if address is None:
                raise SystemExit(f'Missing {name}; the panic screen cannot translate the frame buffer')
            definitions.append(f'-D{macro}={address:#x}UL')
    subprocess.run([clang, '--target=aarch64-none-elf', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                    '-mgeneral-regs-only', '-fno-pic', '-mcmodel=tiny', '-Oz', f'-DVINFO={VINFO_VA:#x}UL',
                    *definitions, f'-I{font_dir}', '-c', source, '-o', obj], check=True)
    script = workdir / 'panic.ld'
    script.write_text('SECTIONS { . = %#x; .text : { *(.text.a_entry) *(.text.a_common) *(.text*) *(.rodata*) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.*) } }\n' % va)
    size = shutil.which('llvm-size') or '/opt/homebrew/opt/llvm/bin/llvm-size'
    sizes = subprocess.run([size, '--format=berkeley', obj], capture_output=True, text=True, check=True).stdout.splitlines()[-1].split()
    if int(sizes[1]) or int(sizes[2]):
        # The code runs from the kernel's read-only text: a global would fault on its first store.
        raise SystemExit(f'{source.name} has writable data (data {sizes[1]}, bss {sizes[2]}); use the stack')
    subprocess.run([lld, '-T', script, '-e', 'panic_screen', obj, '-o', elf], check=True)
    # Only .text: a plain binary dump would start at the ELF headers kept in front of it.
    subprocess.run([objcopy, '-O', 'binary', '-j', '.text', elf, binary], check=True)
    readelf = shutil.which('llvm-readelf') or '/opt/homebrew/opt/llvm/bin/llvm-readelf'
    load = None
    for line in subprocess.run([readelf, '-S', elf], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.replace('[', ' ').replace(']', ' ').split()
        if len(parts) >= 4 and parts[1] == '.text':
            load = int(parts[3], 16)
    if load is None or load < va:
        raise SystemExit('Cannot find where the linker put .text')
    entry = None
    for line in subprocess.run([nm, elf], capture_output=True, text=True, check=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == 'panic_screen':
            entry = int(parts[0], 16)
    if entry != load:
        raise SystemExit(f'panic_screen at {entry:#x} is not the first byte {load:#x}')
    return binary.read_bytes(), load, entry


def panic_common_entry(workdir, code, load):
    """Resolve the real alternate entry and verify its distinct argument ABI."""
    nm = shutil.which('llvm-nm') or '/opt/homebrew/opt/llvm/bin/llvm-nm'
    names = {parts[2]: int(parts[0], 16)
             for line in subprocess.check_output([nm, workdir / 'panic.elf'], text=True).splitlines()
             if len(parts := line.split()) == 3}
    entry = names.get('panic_screen_common')
    main = names.get('panic_screen_main')
    if entry is None or main is None or not load <= entry <= load + len(code) - 8:
        raise SystemExit('Common panic renderer entry is missing or out of bounds')
    at = entry - load
    if code[at:at + 8] != struct.pack('<II', 0xf9400021, branch(entry + 4, main)):
        raise SystemExit('Common panic entry does not dereference the Darwin va_list pointer and branch to the renderer')
    return entry


ROOT = Path(__file__).resolve().parents[1]


SEGMENTS = []   # (vmaddr, vmsize, fileoff, filesize) of the kernel being patched


def load_segments(data):
    """Read the Mach-O segment table; the file layout differs between kernel builds."""
    magic, _, _, _, ncmds = struct.unpack_from('<IiiII', data, 0)
    if magic != 0xFEEDFACF:
        raise SystemExit('Not a 64-bit Mach-O')
    offset = 32
    SEGMENTS.clear()
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x19:
            _, vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<16sQQQQ', data, offset + 8)
            if filesize:
                SEGMENTS.append((vmaddr, vmsize, fileoff, filesize))
        offset += size


def function_extent(data, symbols, name):
    """Symbol start and the next symbol after it: good enough for a bounded byte scan."""
    start = symbols[name]
    after = [va for va in symbols.values() if va > start]
    return start, min(after) if after else start + 0x2000


def unixthread_pc(data):
    """LC_UNIXTHREAD entry pc (arm64 thread state: flavor, count, x0..x28, fp, lr, sp, pc)."""
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == 0x5:
            return struct.unpack_from('<Q', data, offset + 16 + 32 * 8)[0]
        offset += size
    raise SystemExit('No LC_UNIXTHREAD in kernel')


def rebase(kernel, data):
    """The probe sites are fixed offsets from the entry; shift them for another kernel build.

    _panic and _vinfo come from the symbol table when the kernel has one (the plain source
    kernel does); the retained candidate layout is the unshifted case.
    """
    global ENTRY_VA, START_FIRST_CPU, MMU_ENABLE_VA, AFTER_MMU_VA, PANIC_VA, VINFO_VA, PANIC_CAVE_END, CAVES
    delta = unixthread_pc(data) - ENTRY_VA
    if delta:
        ENTRY_VA += delta
        START_FIRST_CPU += delta
        MMU_ENABLE_VA += delta
        AFTER_MMU_VA += delta
        PANIC_CAVE_END += delta
        CAVES = {stage: va + delta for stage, va in CAVES.items()}
        PANIC_VA += delta
        VINFO_VA += delta
    names = {name: va for va, name in kernel_symbols(kernel).items()}
    if '_start_first_cpu' in names:
        START_FIRST_CPU = names['_start_first_cpu']
        # Native bootstrap table-capacity checks can grow before SCTLR setup.
        # Locate the unique instruction sequence in this bounded entry body;
        # do not assume a constant offset from the Mach-O entry point.
        matches = []
        for va in range(START_FIRST_CPU, START_FIRST_CPU + 0x1000, 4):
            def instruction(at):
                return struct.unpack_from('<I', data, file_offset(at))[0]
            if (instruction(va) == 0xD5181000 and
                    instruction(va + 4) == 0xD5033FDF and
                    instruction(va + 0x20) == 0xD2A00600 and
                    instruction(va + 0x24) == 0xD5181040):
                matches.append(va)
        if len(matches) != 1:
            raise SystemExit('Require one verified SCTLR/ISB/CPACR entry sequence')
        MMU_ENABLE_VA = matches[0]
        AFTER_MMU_VA = MMU_ENABLE_VA + 0x20
    if '_panic' in names and '_vinfo' in names:
        PANIC_VA = names['_panic']
        # Board diagnostics seed this ABI-compatible prefix from valid console
        # mappings, then pin it to their retained GOP mapping. Ordinary source
        # kernels without the observer retain the original vinfo path.
        VINFO_VA = names.get('_boot_progress_panic_vinfo', names['_vinfo'])
    return names


def file_offset(va):
    for vmaddr, vmsize, fileoff, filesize in SEGMENTS:
        if vmaddr <= va < vmaddr + min(vmsize, filesize):
            return fileoff + (va - vmaddr)
    raise SystemExit(f'{va:#x} is not in a file-backed segment of this kernel')


def branch(from_va, to_va):
    delta = (to_va - from_va) // 4
    if (to_va - from_va) % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise SystemExit('Branch out of range')
    return 0x14000000 | (delta & 0x3FFFFFF)


def assemble(source, va, symbols, workdir):
    workdir.mkdir(parents=True, exist_ok=True)      # local change, see the banner
    asm, obj, elf, binary = (workdir / name for name in ('cave.S', 'cave.o', 'cave.elf', 'cave.bin'))
    asm.write_text(source)
    clang = shutil.which('clang') or '/opt/homebrew/opt/llvm/bin/clang'
    lld = shutil.which('ld.lld') or '/opt/homebrew/opt/llvm/bin/ld.lld'
    objcopy = shutil.which('llvm-objcopy') or '/opt/homebrew/opt/llvm/bin/llvm-objcopy'
    subprocess.run([clang, '--target=aarch64-none-elf', '-c', asm, '-o', obj], check=True)
    subprocess.run([lld, f'-Ttext={va:#x}', *[f'--defsym={name}={value:#x}' for name, value in symbols.items()], '-e', '_start', obj, '-o', elf], check=True)
    subprocess.run([objcopy, '-O', 'binary', elf, binary], check=True)
    return binary.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('kernel', type=Path, help='the COPY of the kernel to patch in place')
    parser.add_argument('--reset-delay', type=int, default=6, help='seconds before the reset')
    parser.add_argument('--reset-after', metavar='SYMBOL', help='place the reset after this call in arm_init instead of stage 3')
    parser.add_argument('--reset-before', action='store_true', help='reset at the call site before invoking SYMBOL (requires --reset-after)')
    parser.add_argument('--panic-dry-run', action='store_true',
                        help='resolve the frame buffer geometry but never write to it')
    parser.add_argument('--panic-screen', action='store_true', help='draw panic() messages on the screen')
    parser.add_argument('--panic-reset', type=int, metavar='SECONDS',
                        help='reboot this many seconds after entering panic(): a reboot means the silent death is a panic, a dark screen means it is not')
    parser.add_argument('--panic-assert-line', type=int, metavar='SHIFT',
                        help='if panic() is an assert, encode (line >> SHIFT) & 0x3F into the reset '
                             'delay; a non-assert reads --assert-line-unknown seconds')
    parser.add_argument('--assert-line-base', type=int, default=10, metavar='SECONDS',
                        help='base seconds for --panic-assert-line (default 10)')
    parser.add_argument('--assert-line-unknown', type=int, default=90, metavar='SECONDS',
                        help='seconds for a non-assert panic under --panic-assert-line (default 90)')
    parser.add_argument('--panic-fingerprint', metavar='SHIFT:BITS:BASE:STEP[:REG]',
                        help='encode this slice of panic()\'s format-string address into the reset '
                             'delay: reboots BASE + slice*STEP seconds after the panic')
    parser.add_argument('--allow-cpu-topo', action='store_true',
                        help='treat AppleARMCPU::_validateConfiguration() as true, so a DT without '
                             'Apple CPU properties does not abort the boot')
    parser.add_argument('--allow-stack-chk', action='store_true',
                        help='make __stack_chk_fail a no-op, so a stack guard mismatch '
                             'does not abort the boot')
    parser.add_argument('--disable-monitor', action='store_true',
                        help='nop the inlined ml_enable_monitor() msr in _arm_vm_init: the Apple '
                             'monitor register does not exist on this SoC, and an msr to it traps')
    parser.add_argument('--zero-physmap-slide', action='store_true',
                        help='replace the _early_random call in _arm_vm_init with x0=0, i.e. '
                             'physmap_slide = 0: early_random needs the corecrypto DRBG, which this '
                             'port does not have this early, and the slide only randomizes the physmap')
    parser.add_argument('--selftest-fb', type=lambda text: int(text, 0), metavar='ADDRESS',
                        help='run the four-band self-test against this frame buffer address '
                             'instead of the stashed one')
    parser.add_argument('--fb-selftest', action='store_true',
                        help='paint four bands from the stashed frame buffer at a known-reached site, '
                             'then reset: answers whether the stash and the frame buffer write work')
    parser.add_argument('--stash-fb', action='store_true',
                        help='save the frame buffer from boot_args in stage 2, so panic() can draw')
    parser.add_argument('--panic-bands', action='store_true',
                        help='panic() paints the low 32 bits of its format-string address as bars')
    parser.add_argument('--panic-candidates', type=Path, metavar='FILE',
                        help='TSV of NAME<TAB>FMT_VA rows; panic() reboots at BASE+STEP*i seconds '
                             'for candidate i, and BASE+STEP*N for an unknown one')
    parser.add_argument('--candidate-step', type=int, default=6, metavar='SECONDS',
                        help='spacing between candidate delays (default 6 s)')
    parser.add_argument('--fault-fingerprint', metavar='SHIFT:BITS:BASE:STEP',
                        help='EL1 sync vector: wait BASE + STEP x bits SHIFT..SHIFT+BITS-1 of FAR_EL1, then reset')
    parser.add_argument('--fault-reset', type=int, metavar='SECONDS',
                        help='reboot this many seconds after an EL1/SPx synchronous exception: turns every silent fault into a timestamped reboot')
    parser.add_argument('--no-reset', action='store_true', help='no reset probe at all')
    parser.add_argument('--reset-at-entry', action='store_true',
                        help='control experiment: at the kernel entry, wait --reset-delay seconds, then PSCI SYSTEM_RESET without returning to the kernel (proves the reset path works on this platform)')
    parser.add_argument('--occurrence', type=int, default=1, help='which call to SYMBOL (1 = first)')
    parser.add_argument('--in', dest='function', default='_arm_init', help='function that makes the call (default _arm_init)')
    global PANIC_DRY_RUN
    args = parser.parse_args()
    PANIC_DRY_RUN = getattr(args, 'panic_dry_run', False)
    if args.reset_before and not args.reset_after:
        raise SystemExit('--reset-before requires --reset-after')
    data = bytearray(args.kernel.read_bytes())
    load_segments(data)
    kernel_names = rebase(args.kernel, data)

    def word(va):
        return struct.unpack_from('<I', data, file_offset(va))[0]

    expected = {ENTRY_VA: branch(ENTRY_VA, START_FIRST_CPU), MMU_ENABLE_VA: 0xD5181000, AFTER_MMU_VA: 0xD2A00600}
    for va, value in expected.items():
        if word(va) != value:
            raise SystemExit(f'{va:#x} holds {word(va):#010x}, expected {value:#010x}: not the kernel these probes are for')
    for va in CAVES.values():
        if any(data[file_offset(va):file_offset(va) + CAVE_SIZE]):
            raise SystemExit(f'Padding at {va:#x} is not empty')

    # (site, cave stage, symbols the cave is linked with)
    # --stash-fb swaps stage 2 for stage 6, which paints the same band and then saves the frame
    # buffer from boot_args, so panic() can draw even though _vinfo is still empty.
    sites = [(ENTRY_VA, 1, {'target': START_FIRST_CPU}),
             (MMU_ENABLE_VA, 2, {'target': MMU_ENABLE_VA + 4})]
    if args.reset_at_entry:
        # One question, one run: does PSCI SYSTEM_RESET reboot this platform at all?
        sites = [(ENTRY_VA, 5, {})]
        description = f'reset {args.reset_delay} s after the kernel entry, never returns'
    elif args.no_reset:
        description = 'no reset probe'
    elif args.reset_after:
        symbols = kernel_symbols(args.kernel)
        call_va, callee = find_call(data, symbols, args.function, args.reset_after, args.occurrence)
        sites.append((call_va, 4, {'callee': callee, 'target': call_va + 4}))
        description = f'stage 4 reset {"before" if args.reset_before else "after"} call #{args.occurrence} to {args.reset_after} in {args.function} (at {call_va:#x})'
    else:
        sites.append((AFTER_MMU_VA, 3, {'target': AFTER_MMU_VA + 4}))
        description = f'stage 3 reset {args.reset_delay} s after the MMU is on'

    if args.stash_fb:
        if 2 not in {stage for _, stage, _ in sites}:
            raise SystemExit('--stash-fb needs the stage 2 site, which --reset-at-entry does not use')
        if '_boot_progress_panic_text' not in kernel_names:
            raise SystemExit('no _boot_progress_panic_text: nowhere to keep the frame buffer')
        SOURCES[6] = (".text\n.global _start\n_start:\n"
                      + STASH_FB.format(stash=f"{kernel_names['_boot_progress_panic_text']:#x}")
                      + "  msr SCTLR_EL1, x0\n  b target\n")
        sites = [(site, 6 if stage == 2 else stage, extra) for site, stage, extra in sites]

    cave_lengths = {}
    with tempfile.TemporaryDirectory() as tmp:
        for site, stage, symbols in sites:
            source = RESET_BEFORE if (stage == 4 and args.reset_before) else SOURCES[stage].format(ticks=TIMEBASE * args.reset_delay)
            cave = CAVES[CAVE_OF.get(stage, stage)]
            code = assemble(source, cave, symbols, Path(tmp))
            if len(code) > CAVE_SIZE:
                raise SystemExit(f'Stage {stage} code is too large')
            data[file_offset(cave):file_offset(cave) + len(code)] = code
            cave_lengths[stage] = len(code)
    for site, stage, _ in sites:
        struct.pack_into('<I', data, file_offset(site), branch(site, CAVES[CAVE_OF.get(stage, stage)]))
    # Hooks that turn a silent death into a timestamped reboot: panic() and the EL1/SPx
    # synchronous exception entry. Two different delays answer "which one fired", and a
    # dark screen answers "neither".
    hooks = []
    if args.panic_reset is not None:
        hooks.append(('panic reset', args.panic_reset, 'panic()', PANIC_VA))
    if args.panic_fingerprint:
        if args.panic_reset is not None:
            raise SystemExit('--panic-reset and --panic-fingerprint both hook panic()')
        try:
            parts = args.panic_fingerprint.split(':')
            if len(parts) not in (4, 5):
                raise SystemExit('--panic-fingerprint wants SHIFT:BITS:BASE:STEP[:REG]')
            shift, bits, base, step = (int(part, 0) for part in parts[:4])
            slice_reg = parts[4] if len(parts) == 5 else 'x0'
        except ValueError:
            raise SystemExit('--panic-fingerprint: shift/bits/base/step must be integers')
        if not 0 <= shift < 64 or not 1 <= bits <= 16 or base < 0 or step < 1:
            raise SystemExit('--panic-fingerprint: shift 0..63, bits 1..16, base >= 0, step >= 1')
        hooks.append(('panic fingerprint %s' % args.panic_fingerprint, None, 'panic()', PANIC_VA))
    if args.fault_fingerprint:
        if args.fault_reset is not None:
            raise SystemExit('--fault-reset and --fault-fingerprint both hook the fault vector')
        if '_ExceptionVectorsBase' not in kernel_names:
            raise SystemExit('This kernel has no _ExceptionVectorsBase symbol; the fault hook is unavailable')
        try:
            shift, bits, base, step = (int(part, 0) for part in args.fault_fingerprint.split(':'))
        except ValueError:
            raise SystemExit('--fault-fingerprint wants SHIFT:BITS:BASE:STEP, all integers')
        if not 0 <= shift < 64 or not 1 <= bits <= 16 or base < 0 or step < 1:
            raise SystemExit('--fault-fingerprint: shift 0..63, bits 1..16, base >= 0, step >= 1')
        hooks.append(('fault fingerprint %s' % args.fault_fingerprint, None, 'el1 spx sync vector',
                      kernel_names['_ExceptionVectorsBase'] + 0x200))
    if args.fault_reset is not None:
        if '_ExceptionVectorsBase' not in kernel_names:
            raise SystemExit('This kernel has no _ExceptionVectorsBase symbol; the fault hook is unavailable')
        # Current EL with SPx, synchronous: the slot the kernel's own aborts land in.
        hooks.append(('fault reset', args.fault_reset, 'el1 spx sync vector',
                      kernel_names['_ExceptionVectorsBase'] + 0x200))
    if hooks:
        if args.panic_screen and args.panic_reset is not None:
            raise SystemExit('--panic-reset and --panic-screen both claim the byte after the caves')
        used = {CAVE_OF.get(stage, stage) for _, stage, _ in sites}
        free = [stage for stage in sorted(CAVES) if stage not in used]
        top = max(CAVES, key=lambda stage: CAVES[stage])
        extra = 0
        with tempfile.TemporaryDirectory() as tmp:
            for label, seconds, what, target in hooks:
                if free:
                    cave = CAVES[free.pop(0)]
                else:
                    # Every cave slot is taken: use the padding right after the last one.
                    extra += 1
                    cave = CAVES[top] + CAVE_SIZE * extra
                if any(data[file_offset(cave):file_offset(cave) + CAVE_SIZE]):
                    raise SystemExit(f'Padding at {cave:#x} is not empty')
                if word(target) in (0, 0xFFFFFFFF):
                    raise SystemExit(f'{what} is not where the {label} expects it ({target:#x})')
                if label.startswith('fault fingerprint'):
                    code = assemble(FAR_SLICE_RESET.format(shift=shift, mask=(1 << bits) - 1,
                                                           base=base, step=step,
                                                           timebase_lo=TIMEBASE & 0xFFFF,
                                                           timebase_hi=(TIMEBASE >> 16) & 0xFFFF),
                                    cave, {}, Path(tmp))
                    seconds = f'{base}+{step}s x FAR bits {shift}..{shift + bits - 1}'
                elif label.startswith('panic fingerprint'):
                    code = assemble(SLICE_RESET.format(reg=slice_reg, shift=shift, mask=(1 << bits) - 1,
                                                       base=base, step=step,
                                                       timebase_lo=TIMEBASE & 0xFFFF,
                                                       timebase_hi=(TIMEBASE >> 16) & 0xFFFF),
                                    cave, {}, Path(tmp))
                    seconds = f'{base}+{step}s x bits {shift}..{shift + bits - 1}'
                else:
                    code = assemble(PANIC_RESET.format(ticks=TIMEBASE * seconds), cave, {}, Path(tmp))
                if len(code) > CAVE_SIZE:
                    raise SystemExit(f'{label} code is too large')
                data[file_offset(cave):file_offset(cave) + len(code)] = code
                struct.pack_into('<I', data, file_offset(target), branch(target, cave))
                description += f', {label} {seconds} s at {what} (cave {cave:#x}, {len(code):#x} bytes)'
    if args.panic_assert_line is not None:
        # 本 binar 里 assert 用的格式串（另一份 0xfffffff0070460ac 是死副本，零引用）
        source = ASSERT_LINE_RESET.format(
            assert_fmt=0xFFFFFFF0071D942D, shift=args.panic_assert_line,
            base=args.assert_line_base, unknown=args.assert_line_unknown,
            timebase_lo=TIMEBASE & 0xFFFF, timebase_hi=(TIMEBASE >> 16) & 0xFFFF)
        top = max(CAVES, key=lambda stage: CAVES[stage])
        cave = CAVES[top] + CAVE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            code = assemble(source, cave, {}, Path(tmp))
        if word(PANIC_VA) in (0, 0xFFFFFFFF):
            raise SystemExit('panic() is not where the assert-line hook expects it')
        if cave + len(code) > PANIC_CAVE_END:
            raise SystemExit(f'assert-line hook is {len(code):#x} bytes at {cave:#x}, '
                             f'room ends at {PANIC_CAVE_END:#x}')
        if any(data[file_offset(cave):file_offset(cave) + len(code)]):
            raise SystemExit(f'Padding at {cave:#x} is not empty')
        data[file_offset(cave):file_offset(cave) + len(code)] = code
        struct.pack_into('<I', data, file_offset(PANIC_VA), branch(PANIC_VA, cave))
        description += (f', assert-line hook at {cave:#x} ({len(code):#x} bytes): delay'
                        f' {args.assert_line_base}+((line>>{args.panic_assert_line})&0x3F) s,'
                        f' non-assert {args.assert_line_unknown} s')

    if args.panic_candidates:
        if args.panic_reset is not None or args.panic_fingerprint or args.panic_assert_line is not None:
            raise SystemExit('wanted: one owner of panic()')
        rows = []
        for line in args.panic_candidates.read_text().splitlines():
            if not line.strip() or line.startswith('name\t'):
                continue
            name, fmt_va = line.split('\t')[:2]
            rows.append((name, int(fmt_va, 0)))
        if not rows:
            raise SystemExit(f'{args.panic_candidates} has no candidates')
        if len(rows) > 16:
            raise SystemExit('more than 12 candidates: split the question, the cave is finite')
        base, step = 10, args.candidate_step
        compare, slots = [], []
        for index, (name, fmt_va) in enumerate(rows):
            compare.append(f'  ldr x9, ={fmt_va:#x}\n  cmp x0, x9\n  b.eq .Lslot{index}')
            slots.append(f'.Lslot{index}:\n  movz x9, #{base + step * index}\n  b .Lcommit')
        source = CANDIDATE_RESET.format(compare='\n'.join(compare), slots='\n'.join(slots),
                                        default_seconds=base + step * len(rows),
                                        timebase_lo=TIMEBASE & 0xFFFF,
                                        timebase_hi=(TIMEBASE >> 16) & 0xFFFF)
        top = max(CAVES, key=lambda stage: CAVES[stage])
        cave = CAVES[top] + CAVE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            code = assemble(source, cave, {}, Path(tmp))
        if word(PANIC_VA) in (0, 0xFFFFFFFF):
            raise SystemExit('panic() is not where the candidate hook expects it')
        end = PANIC_CAVE_END
        if cave + len(code) > end:
            raise SystemExit(f'candidate hook is {len(code):#x} bytes at {cave:#x}, room ends at {end:#x}')
        if any(data[file_offset(cave):file_offset(cave) + len(code)]):
            raise SystemExit(f'Padding at {cave:#x} is not empty')
        data[file_offset(cave):file_offset(cave) + len(code)] = code
        struct.pack_into('<I', data, file_offset(PANIC_VA), branch(PANIC_VA, cave))
        description += (f', panic candidates {len(rows)} at {cave:#x} ({len(code):#x} bytes,'
                        f' delays {base}..{base + step * len(rows)} s)')
        for index, (name, fmt_va) in enumerate(rows):
            description += f' [{index}] {name} {fmt_va:#x} = {base + step * index} s'

    if args.panic_bands:
        if args.panic_reset is not None or args.panic_candidates or args.panic_fingerprint \
                or args.panic_screen:
            raise SystemExit('--panic-bands cannot be combined with the other panic hooks')
        if '_boot_progress_panic_text' not in kernel_names:
            raise SystemExit('no _boot_progress_panic_text: nowhere to keep the frame buffer')
        stash = kernel_names['_boot_progress_panic_text']
        # Stage 6 saves here; nothing else uses this buffer before the panic it is meant for.
        SOURCES[6] = (".text\n.global _start\n_start:\n"
                      + STASH_FB.format(stash=f'{stash:#x}')
                      + "  msr SCTLR_EL1, x0\n  b target\n")
        sites = [(site, 6 if stage == 2 else stage, extra) for site, stage, extra in sites]
        top = max(CAVES, key=lambda stage: CAVES[stage])
        cave = CAVES[top] + CAVE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            code = assemble(BANDS.format(stash=f'{stash:#x}', framebuffer_bytes=5760 * 3200), cave, {}, Path(tmp))
        if word(PANIC_VA) in (0, 0xFFFFFFFF):
            raise SystemExit('panic() is not where --panic-bands expects it')
        if cave + len(code) > PANIC_CAVE_END:
            raise SystemExit(f'--panic-bands is {len(code):#x} bytes at {cave:#x}, room ends at {PANIC_CAVE_END:#x}')
        if any(data[file_offset(cave):file_offset(cave) + len(code)]):
            raise SystemExit(f'Padding at {cave:#x} is not empty')
        data[file_offset(cave):file_offset(cave) + len(code)] = code
        struct.pack_into('<I', data, file_offset(PANIC_VA), branch(PANIC_VA, cave))
        description += (f', panic bands at {cave:#x} ({len(code):#x} bytes), frame buffer kept in '
                        f'_boot_progress_panic_text ({stash:#x})')

    if args.zero_physmap_slide:
        symbols = kernel_symbols(args.kernel)
        call_va, callee = find_call(data, symbols, '_arm_vm_init', '_early_random', 1)
        current = word(call_va)
        if (current & 0xFC000000) != 0x94000000:
            raise SystemExit(f'{call_va:#x} is not a bl: {current:#010x}, refusing to write')
        immediate = (current & 0x3FFFFFF) - (0x4000000 if current & 0x2000000 else 0)
        if call_va + immediate * 4 != callee:
            raise SystemExit(f'{call_va:#x} does not branch to _early_random ({callee:#x})')
        # mov x0, xzr: physmap_slide = 0 keeps the physmap where boot_args put it, and the
        # assertion that the slide is within range holds trivially.
        struct.pack_into('<I', data, file_offset(call_va), 0xD2800000)
        description += (f', physmap slide forced to 0 by replacing bl _early_random at '
                        f'{call_va:#x} (was {current:#010x}) with mov x0, xzr')

    if args.disable_monitor:
        symbols = kernel_symbols(args.kernel)
        names = {name: va for va, name in symbols.items()}
        start, end = function_extent(data, names, '_arm_vm_init')
        hits = [va for va in range(start, end, 4) if word(va) == MONITOR_MSR]
        if not hits:
            raise SystemExit(f'no ml_enable_monitor msr ({MONITOR_MSR:#010x}) in _arm_vm_init')
        # Followed by dsb sy / isb: those stay, they are harmless without the msr.
        for va in hits:
            struct.pack_into('<I', data, file_offset(va), 0xD503201F)   # nop
        description += (f', {len(hits)} Apple-monitor msr(s) replaced with nop at '
                        + ', '.join(f'{va:#x}' for va in hits))

    if args.selftest_fb is not None:
        top = max(CAVES, key=lambda stage: CAVES[stage])
        cave = CAVES[top] + CAVE_SIZE
        tail = "  b 5f" if args.reset_delay == 0 else (
            "  ldr x2, =%d\n  mrs x1, cntpct_el0\n  add x2, x1, x2\n"
            "4:\n  isb\n  mrs x1, cntpct_el0\n  cmp x1, x2\n  b.lo 4b\n"
            "  movz w0, #0x0009\n  movk w0, #0x8400, lsl 16\n"
            "  mov x1, xzr\n  mov x2, xzr\n  mov x3, xzr\n  smc #0"
            % (TIMEBASE * args.reset_delay))
        with tempfile.TemporaryDirectory() as tmp:
            code = assemble(SELFTEST_CONST.format(fb=f'{args.selftest_fb:#x}',
                                                  fb_bytes=5760 * 3200, tail=tail),
                            cave, {}, Path(tmp))
        if cave + len(code) > PANIC_CAVE_END or any(data[file_offset(cave):file_offset(cave) + len(code)]):
            raise SystemExit(f'no room for the constant self-test at {cave:#x}')
        data[file_offset(cave):file_offset(cave) + len(code)] = code
        struct.pack_into('<I', data, file_offset(AFTER_MMU_VA), branch(AFTER_MMU_VA, cave))
        description += (f', four-band self-test with frame buffer {args.selftest_fb:#x} at '
                        f'{cave:#x} ({len(code):#x} bytes)')

    if args.allow_stack_chk:
        target = None
        for name in ('___stack_chk_fail', '__stack_chk_fail'):
            if name in kernel_names:
                target = kernel_names[name]
                break
        if target is None:
            raise SystemExit('this kernel has no __stack_chk_fail symbol')
        first = word(target)
        if first in (0, 0xFFFFFFFF):
            raise SystemExit(f'{target:#x} does not look like the body of __stack_chk_fail')
        struct.pack_into('<I', data, file_offset(target), 0xD65F03C0)   # ret
        description += (f', __stack_chk_fail at 0x{target:x} turned into a no-op '
                        f'(was 0x{first:08x})')

    if args.allow_cpu_topo:
        # AppleARMCPU::_validateConfiguration() 要求每个 /cpus/cpu@N 带上 Apple 私有属性
        # （reg / cluster-type / interrupts / function-ipi_dispatch / function-enable_core …），
        # 这些值描述的是 Apple 自己的 IPI 与 idle 硬件，别家 SoC 无法伪造。做法与社区在
        # 别的板子上跑通的办法一致：让这次的校验调用直接「返回 true」，函数体本身不动。
        needle = b'bool AppleARMCPU::_validateConfiguration()\0'
        idx = data.find(needle)
        if idx < 0:
            raise SystemExit('this kernel carries no AppleARMCPU::_validateConfiguration() string')
        string_va = idx + 0xFFFFFFF007004000
        words = struct.unpack_from(f'<{len(data) // 4}I', data, 0)

        def word_va(index):
            return 0xFFFFFFF007004000 + index * 4

        # adrp 指向该字符串所在页，紧跟其后的 add 才是真正的取址
        page_want = string_va & ~0xFFF
        refs = []
        for i, ins in enumerate(words):
            if (ins & 0x9F000000) != 0x90000000:
                continue
            immlo = (ins >> 29) & 3
            immhi = (ins >> 5) & 0x7FFFF
            imm = (immhi << 2) | immlo
            if imm & 0x100000:
                imm -= 0x200000
            page = (word_va(i) & ~0xFFF) + (imm << 12)
            if page != page_want:
                continue
            reg = ins & 0x1F
            for step in (1, 2, 3):
                if i + step >= len(words):
                    break
                nxt = words[i + step]
                if (nxt & 0xFFC00000) != 0x91000000:
                    continue
                if (nxt & 0x1F) != reg or ((nxt >> 5) & 0x1F) != reg:
                    continue
                if page + ((nxt >> 10) & 0xFFF) == string_va:
                    refs.append(word_va(i + step))
        if not refs:
            raise SystemExit('no code references AppleARMCPU::_validateConfiguration()')

        # 函数入口：最近的一对 bti c / pacibsp
        ref = min(refs)
        entry = None
        for back in range(0, 0x600, 4):
            va = ref - back
            if va < 0xFFFFFFF007004000 + 8:
                break
            index = (va - 0xFFFFFFF007004000) // 4
            if words[index] == 0xD503245F and words[index + 1] == 0xD503237F:
                entry = va
                break
        if entry is None:
            raise SystemExit('could not find the entry of _validateConfiguration()')

        # 唯一的一处 bl 调用点
        calls = []
        for i, ins in enumerate(words):
            if (ins & 0xFC000000) != 0x94000000:
                continue
            imm = ins & 0x3FFFFFF
            if imm & 0x2000000:
                imm -= 0x4000000
            va = word_va(i)
            if ((va + imm * 4) & 0xFFFFFFFFFFFFFFFF) == entry:
                calls.append(va)
        if len(calls) != 1:
            raise SystemExit(f'expected one call to _validateConfiguration(), found {len(calls)}')
        call = calls[0]
        was = word(call)
        struct.pack_into('<I', data, file_offset(call), 0xD2800020)     # mov x0, #1
        note = (f'AppleARMCPU::_validateConfiguration() at 0x{entry:x} forced true '
                f'at its only call site 0x{call:x} (was 0x{was:08x})')
        # 调用之后紧跟的 `tbz w0, #0, <panic>` 也要拆掉：有些路径会先把返回值挪走再判，
        # 只改调用点不足以关死失败分支。
        follow = word(call + 4)
        if (follow & 0x7E000000) == 0x36000000 and (follow & 0x1F) == 0:
            struct.pack_into('<I', data, file_offset(call + 4), 0xD503201F)   # nop
            note += f'; the following tbz at 0x{call + 4:x} nop-ed (was 0x{follow:08x})'
        description += ', ' + note

    if args.selftest_fb is not None:
        if not args.stash_fb:
            raise SystemExit('--fb-selftest reads what --stash-fb saved; pass both')
        if '_boot_progress_panic_text' not in kernel_names:
            raise SystemExit('no _boot_progress_panic_text for the self-test stash')
        stash = kernel_names['_boot_progress_panic_text']
        # The self-test is not a cave-sized body and CAVES[3] already holds the stage 3 site, so it
        # lives in the zero padding right after the last cave, exactly like the panic hooks do.
        top = max(CAVES, key=lambda stage: CAVES[stage])
        cave = CAVES[top] + CAVE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            if args.reset_delay:
                tail = ("  ldr x2, =%d\n  mrs x1, cntpct_el0\n  add x2, x1, x2\n"
                        "4:\n  isb\n  mrs x1, cntpct_el0\n  cmp x1, x2\n  b.lo 4b\n"
                        "  movz w0, #0x0009\n  movk w0, #0x8400, lsl 16\n"
                        "  mov x1, xzr\n  mov x2, xzr\n  mov x3, xzr\n  smc #0"
                        % (TIMEBASE * args.reset_delay))
            else:
                # --reset-delay 0 keeps the picture on screen for the camera.
                tail = "  b 5f"
            code = assemble(SELFTEST.format(stash=f'{stash:#x}', fb_bytes=5760 * 3200,
                                            tail=tail), cave, {}, Path(tmp))
        if cave + len(code) > PANIC_CAVE_END:
            raise SystemExit(f'self-test is {len(code):#x} bytes at {cave:#x}, room ends at {PANIC_CAVE_END:#x}')
        if any(data[file_offset(cave):file_offset(cave) + len(code)]):
            raise SystemExit(f'Padding at {cave:#x} is not empty')
        data[file_offset(cave):file_offset(cave) + len(code)] = code
        struct.pack_into('<I', data, file_offset(AFTER_MMU_VA), branch(AFTER_MMU_VA, cave))
        description += (f', frame buffer self-test at {cave:#x} ({len(code):#x} bytes) hooked at '
                        f'0x{AFTER_MMU_VA:x}')

    if args.panic_screen:
        # Place the screen after the highest cave this build really uses, then scan forward for a
        # run of zero bytes big enough: --stash-fb makes the stage-2 cave longer than CAVE_SIZE,
        # so the old "cave + CAVE_SIZE" address is no longer guaranteed to be empty padding.
        last_stage = max((stage for _, stage, _ in sites if stage in CAVES), key=lambda stage: CAVES[stage])
        if word(PANIC_VA) in (0, 0xFFFFFFFF):
            raise SystemExit('panic() is not where the panic screen expects it')
        common = kernel_names.get('_panic_trap_to_debugger')
        if common is None or word(common) in (0, 0xFFFFFFFF):
            raise SystemExit('Common panic funnel is missing; refuse a partially covered panic screen')
        # Measure the screen once, then look for that many zero bytes anywhere in the kernel's
        # own text: the padding right after the caves is only ~0xa30 bytes and the screen is
        # bigger than that now, but the text segment carries other long zero runs.
        with tempfile.TemporaryDirectory() as tmp:
            code, load, entry = assemble_c(ROOT / 'scripts/xnu-panic-screen.c',
                                           CAVES[last_stage] + CAVE_SIZE, Path(tmp), kernel_names)
        size = len(code)
        chosen = None
        starts = [CAVES[last_stage] + CAVE_SIZE]
        starts += sorted({base + size for base, size_, _, _ in SEGMENTS} | {PANIC_CAVE_END},
                         reverse=True)
        for base, size_, fileoff, filesize in SEGMENTS:
            if fileoff:
                starts.append(base)
        tried = set()
        for start in starts:
            start = (start + 3) & ~3
            end_of_seg = None
            for base, size_, fileoff, filesize in SEGMENTS:
                if fileoff and base <= start < base + size_:
                    end_of_seg = base + size_
                    break
            if end_of_seg is None:
                continue
            while start + size <= end_of_seg:
                if abs(start - PANIC_VA) >= 0x7FFF000:
                    start += 0x1000
                    continue
                if start in tried:
                    break
                tried.add(start)
                if not any(data[file_offset(start):file_offset(start) + size]):
                    with tempfile.TemporaryDirectory() as tmp:
                        code, load, entry = assemble_c(ROOT / 'scripts/xnu-panic-screen.c',
                                                       start, Path(tmp), kernel_names)
                        common_entry = panic_common_entry(Path(tmp), code, load)
                    if not any(data[file_offset(load):file_offset(load) + len(code)]):
                        chosen = (load, code, entry, common_entry)
                        break
                start += 4
            if chosen is not None:
                break
        if chosen is None:
            raise SystemExit(f'no {len(code):#x}-byte run of empty padding after {start:#x} for the panic screen')
        load, code, entry, common_entry = chosen
        data[file_offset(load):file_offset(load) + len(code)] = code
        struct.pack_into('<I', data, file_offset(PANIC_VA), branch(PANIC_VA, entry))
        struct.pack_into('<I', data, file_offset(common), branch(common, common_entry))
        description += f', panic screen ({len(code):#x} bytes at {entry:#x}; common funnel at {common:#x})'
    args.kernel.write_bytes(data)
    # Only the stages that are really in this build get named: --reset-at-entry and --no-reset
    # have no blue/magenta bar at all, and claiming one sends the reader after a missing bar.
    stages = {stage for _, stage, _ in sites}
    bars = ', '.join(label for stage, label in ((1, 'stage 1 blue bar'), (2, 'stage 2 magenta bar'))
                     if stage in stages)
    print(f'patched {args.kernel.name}: ' + (f'{bars}, ' if bars else '') + description)

if __name__ == '__main__':
    main()
