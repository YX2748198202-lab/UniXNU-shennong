#!/usr/bin/env python3
"""Install shennong's separate, resident late-constant segment support.

Only the actual .cache/xnu-work source is patched at prepare time. Text changes
are count-checked and calculated for all files before any file is written.
No KLDDATA permission, unmap, destructor or reclamation path is changed.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FLAG = 'UNIXNU_SHENNONG_PORT_CONST'
SEGMENT = '__PORT_CONST'

# Each new block includes its original anchor, allowing strict idempotence.
ARM_REPLACEMENTS = [
    ('globals',
     'SECURITY_READ_ONLY_LATE(static unsigned long) segSizeKLDDATA;',
     'SECURITY_READ_ONLY_LATE(static unsigned long) segSizeKLDDATA;\n\n'
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '/* Resident late constants: distinct from reclaimable __KLDDATA. */\n'
     'SECURITY_READ_ONLY_LATE(static vm_offset_t) segPORTCONSTB;\n'
     'SECURITY_READ_ONLY_LATE(static unsigned long) segSizePORTCONST;\n'
     '#endif'),
    ('initial-mapping',
     '\tarm_vm_page_granular_RWNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);',
     '\tarm_vm_page_granular_RWNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);\n'
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\tarm_vm_page_granular_RWNX(segPORTCONSTB, segSizePORTCONST, 0);\n'
     '#endif'),
    ('physmap-readonly-alias',
     '\tarm_vm_physmap_slide(temp_ptov_table, segKLDDATAB, segSizeKLDDATA, AP_RONA, 0);',
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\t/* Match DATA_CONST: never create a writable physmap alias. */\n'
     '\tarm_vm_physmap_slide(temp_ptov_table, segPORTCONSTB, segSizePORTCONST, AP_RONA, 0);\n'
     '#endif\n'
     '\tarm_vm_physmap_slide(temp_ptov_table, segKLDDATAB, segSizeKLDDATA, AP_RONA, 0);'),
    ('final-readonly',
     '\tarm_vm_page_granular_RNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);\n\n'
     '\t__builtin_arm_dsb(DSB_ISH);',
     '\tarm_vm_page_granular_RNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);\n'
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\t/* Static page tables may reside here; tighten this region last. */\n'
     '\tarm_vm_page_granular_RNX(segPORTCONSTB, segSizePORTCONST, 0);\n'
     '#endif\n\n'
     '\t__builtin_arm_dsb(DSB_ISH);'),
    ('segment-discovery',
     '\tsegKLDDATAB      = (vm_offset_t) getsegdatafromheader(&_mh_execute_header, "__KLDDATA", &segSizeKLDDATA);',
     '\tsegKLDDATAB      = (vm_offset_t) getsegdatafromheader(&_mh_execute_header, "__KLDDATA", &segSizeKLDDATA);\n'
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\tsegPORTCONSTB = (vm_offset_t) getsegdatafromheader(&_mh_execute_header, "__PORT_CONST", &segSizePORTCONST);\n'
     '\tassert(segPORTCONSTB != 0 && segSizePORTCONST != 0);\n'
     '\tassert((segPORTCONSTB & (ARM_PGBYTES - 1)) == 0);\n'
     '\tassert((segSizePORTCONST & (ARM_PGBYTES - 1)) == 0);\n'
     '\tassert(segPORTCONSTB + segSizePORTCONST > segPORTCONSTB);\n'
     '#endif'),
    ('kernel-reservation-bounds',
     '\tend_kern = round_page(segHIGHESTKC ? segHIGHESTKC : getlastkerneladdr()); /* Force end to next page */',
     '\tend_kern = round_page(segHIGHESTKC ? segHIGHESTKC : getlastkerneladdr()); /* Force end to next page */\n'
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\tassert(segPORTCONSTB >= gVirtBase);\n'
     '\tassert(segPORTCONSTB + segSizePORTCONST <= end_kern);\n'
     '#endif'),
    ('ro-range-classifier',
     '\treturn segDATACONSTB <= addr && addr < (segDATACONSTB + segSizeDATACONST);',
     '#if defined(UNIXNU_SHENNONG_PORT_CONST)\n'
     '\tif (segPORTCONSTB <= addr && addr < (segPORTCONSTB + segSizePORTCONST)) {\n'
     '\t\treturn true;\n'
     '\t}\n'
     '#endif\n'
     '\treturn segDATACONSTB <= addr && addr < (segDATACONSTB + segSizeDATACONST);'),
]

# Keep native DATA_CONST valid; accept the separate resident segment as a second
# whole-span domain, never the interval spanning the gap between both segments.
LEDGER_OLD = '''static void
lt_require_data_const(ledger_template_t lt)
{
	extern const char data_const_start[] __SEGMENT_START_SYM("__DATA_CONST");
	extern const char data_const_end[] __SEGMENT_END_SYM("__DATA_CONST");

	assert(data_const_start <= (const char *)lt &&
	    (const char *)(lt + 1) <= data_const_end);
	if (lt->lt_cnt) {
		assert(data_const_start <= (const char *)lt->lt_entries &&
		    (const char *)(lt->lt_entries + lt->lt_cnt) <= data_const_end);
	}
}'''
LEDGER_SPAN_HELPER = '''#if defined(UNIXNU_SHENNONG_PORT_CONST)
/* Complete object/array must fit in ONE resident constant segment. */
static bool
lt_span_in_const_segment(const void *object, size_t count, size_t width)
{
	extern const char data_const_start[] __SEGMENT_START_SYM("__DATA_CONST");
	extern const char data_const_end[] __SEGMENT_END_SYM("__DATA_CONST");
	extern const char port_const_start[] __SEGMENT_START_SYM("__PORT_CONST");
	extern const char port_const_end[] __SEGMENT_END_SYM("__PORT_CONST");
	uintptr_t first = (uintptr_t)object;
	uintptr_t dc_start = (uintptr_t)data_const_start;
	uintptr_t dc_end = (uintptr_t)data_const_end;
	uintptr_t pc_start = (uintptr_t)port_const_start;
	uintptr_t pc_end = (uintptr_t)port_const_end;

	/* Check multiplication first, then subtract bounds instead of adding size. */
	if (count == 0 || width == 0 || count > (size_t)-1 / width) {
		return false;
	}
	size_t bytes = count * width;
	return (dc_start <= first && first < dc_end && bytes <= dc_end - first) ||
	       (pc_start <= first && first < pc_end && bytes <= pc_end - first);
}
#endif
'''
LEDGER_NEW = LEDGER_SPAN_HELPER + '''static void
lt_require_data_const(ledger_template_t lt)
{
#if defined(UNIXNU_SHENNONG_PORT_CONST)
	assert(lt_span_in_const_segment(lt, 1, sizeof(*lt)));
	if (lt->lt_cnt) {
		assert(lt_span_in_const_segment(lt->lt_entries,
		    lt->lt_cnt, sizeof(*lt->lt_entries)));
	}
#else
''' + LEDGER_OLD.split('{\n', 1)[1].rsplit('\n}', 1)[0] + '''
#endif
}'''
LEDGER_REPLACEMENTS = [('ledger-constant-span-contract', LEDGER_OLD, LEDGER_NEW)]

MAKEDEF_OLD = '\t__TEXT:__DATA_CONST:__DATA_SPTM:__LINKEDIT:__TEXT_EXEC:__TEXT_BOOT_EXEC:__KLD:__PPLTEXT:__PPLTRAMP:__PPLDATA_CONST:__LASTDATA_CONST:__LAST:__PPLDATA:__KLDDATA:__DATA:__HIBDATA:__BOOTDATA'
MAKEDEF_NEW = '\t__TEXT:__DATA_CONST:__DATA_SPTM:__LINKEDIT:__TEXT_EXEC:__TEXT_BOOT_EXEC:__KLD:__PPLTEXT:__PPLTRAMP:__PPLDATA_CONST:__LASTDATA_CONST:__LAST:__PPLDATA:__KLDDATA:__PORT_CONST:__DATA:__HIBDATA:__BOOTDATA'
LAYOUT_OLD = "        for name in ('__KLDDATA', '__BOOTDATA'):"
LAYOUT_NEW = (
    "        # shennong: resident late constants must not share reclaimable KLDDATA.\n"
    "        late = ('__PORT_CONST',) if any(s['name'] == '__PORT_CONST' for s in native.segments) else ()\n"
    "        for name in late + ('__KLDDATA', '__BOOTDATA'):"
)
BUILD_OLD = 'EXTRA_CFLAGS="$EXTRA_CFLAGS -DXNU_BOOT_PROGRESS=$BOOT_PROGRESS"'
BUILD_NEW = BUILD_OLD + '\nEXTRA_CFLAGS="$EXTRA_CFLAGS -DUNIXNU_SHENNONG_PORT_CONST=1"'
HOOK = '''
# shennong-port-const-v1: invoked after headers, against the actual compile tree.
if __name__ == '__main__':
    import os as _pc_os
    import subprocess as _pc_subprocess
    import sys as _pc_sys
    from pathlib import Path as _pc_Path
    _pc_device = _pc_Path(_pc_os.environ['UNIXNU_DEVICE']).resolve(strict=True)
    _pc_subprocess.run([
        _pc_sys.executable, str(_pc_device / 'scripts/apply-port-const.py'),
        'prepare', '--tree', str(_pc_Path(__file__).resolve().parents[1]),
    ], check=True)
'''


def transform(text, replacements):
    """Fail on absent/ambiguous/partially duplicated context, including re-runs."""
    for label, old, new in replacements:
        if text.count(new) == 1 and text.count(old) == new.count(old):
            continue
        if text.count(new) or text.count(old) != 1:
            raise ValueError(f'{label}: expected exactly one pristine or complete patched block')
        text = text.replace(old, new, 1)
    return text


def patch_ledger(text):
    if 'lt_span_in_const_segment' in text and text.count(LEDGER_NEW) != 1:
        raise ValueError('ledger-constant-span-contract: partial or duplicate helper')
    return transform(text, LEDGER_REPLACEMENTS)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stage_file(path, transform_fn):
    before = path.read_bytes()
    text = before.decode('utf-8')
    after = transform_fn(text).encode('utf-8')
    return path, before, after


def install_hook(text):
    if 'shennong_kld_writable' in text:
        raise ValueError('Obsolete KLDDATA hook still installed; use a clean framework tree')
    if 'shennong-port-const-v1' in text:
        if text.count(HOOK) != 1:
            raise ValueError('Incomplete or duplicated port-const hook')
        return text
    return text + HOOK


def run(mode, tree):
    tree = tree.resolve(strict=True)
    if mode == 'install':
        changes = [
            stage_file(tree/'kits/XnuPrelink/fileset_layout.py', lambda t: transform(t, [('layout', LAYOUT_OLD, LAYOUT_NEW)])),
            stage_file(tree/'scripts/build-xnu-4k-baseline.sh', lambda t: transform(t, [('build-flag', BUILD_OLD, BUILD_NEW)])),
            stage_file(tree/'scripts/prepare-xnu-source.py', install_hook),
        ]
    else:
        work = tree/'.cache/xnu-work'
        if work.is_symlink() or not work.is_dir():
            raise ValueError(f'Expected a real compile source directory: {work}')
        path = work/'osfmk/arm64/arm_vm_init.c'
        ledger = work/'osfmk/kern/ledger.c'
        make = work/'makedefs/MakeInc.def'
        for source in (path, ledger, make):
            if not source.resolve(strict=True).is_relative_to(work.resolve(strict=True)):
                raise ValueError('Compile source escaped .cache/xnu-work')
        changes = [
            stage_file(path, lambda t: transform(t, ARM_REPLACEMENTS)),
            stage_file(ledger, patch_ledger),
            stage_file(make, lambda t: transform(t, [('segment-order', MAKEDEF_OLD, MAKEDEF_NEW)])),
        ]
    # All transformations and preimage checks succeeded before the first write.
    entries = []
    for path, before, after in changes:
        if path.read_bytes() != before:
            raise ValueError(f'Concurrent input modification: {path}')
        if before != after:
            path.write_bytes(after)
        if path.read_bytes() != after:
            raise ValueError(f'Write read-back mismatch: {path}')
        entries.append(dict(path=str(path), resolved_path=str(path.resolve()), changed=before != after,
                            before_sha256=sha(before), after_sha256=sha(after)))
    evidence = dict(version=1, stage=mode, tree=str(tree), segment=SEGMENT, flag=FLAG,
                    created_at=datetime.now(timezone.utc).isoformat(), files=entries)
    audit = tree/'build/shennong-port-const'
    audit.mkdir(parents=True, exist_ok=True)
    # Every invocation gets its own immutable receipt, including idempotent passes.
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json', prefix=mode+'-', dir=audit, delete=False) as f:
        json.dump(evidence, f, indent=2)
        f.write('\n')
    print(json.dumps(evidence, indent=2))
    return evidence


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['install', 'prepare'])
    ap.add_argument('--tree', type=Path, required=True)
    args = ap.parse_args()
    run(args.mode, args.tree)


if __name__ == '__main__':
    main()
