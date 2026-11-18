#!/usr/bin/env python3
"""Add fatal-only display, preserving every normal-flow instruction and PAC prologue."""
import argparse, hashlib, hmac, importlib.util, json, os, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def offset(image, va, size=1):
    for s in image.segments.values():
        if s['va']<=va and va+size<=s['va']+s['filesize']:
            return s['fileoff']+va-s['va']
    raise ValueError(f'Unbacked address {va:#x}')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--uefi',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    raw=args.kernel.read_bytes(); audit=load('port_audit',ROOT/'scripts/audit-port-const-kernel.py')
    root=audit.MachO(raw); native=audit.MachO(raw,root.entries['com.apple.kernel'])
    names=native.symbols(); data=bytearray(raw); changes=[]
    args.out.mkdir(parents=True,exist_ok=False)
    def put(va, blob, label, empty=False):
        at=offset(native,va,len(blob)); old=bytes(data[at:at+len(blob)])
        if empty and any(old):raise ValueError(f'Nonempty reserved padding: {label}')
        for c in changes:
            if max(at,c['file_offset'])<min(at+len(blob),c['file_offset']+c['size']):
                raise ValueError('Overlapping diagnostic writes')
        data[at:at+len(blob)]=blob
        changes.append(dict(label=label,va=hex(va),file_offset=at,size=len(blob),before_sha256=hashlib.sha256(old).hexdigest(),after_sha256=hashlib.sha256(blob).hexdigest()))
    port=native.port_segment(); table_va=port['va']+port['size']-4096
    assert table_va%4096==0
    assert max(s['va']+s['size'] for s in port['sections'].values())<=table_va
    table=bytearray(4096); pte=(1<<54)|(1<<53)|0xc0000000|0x40d
    struct.pack_into('<Q',table,3*8,pte)
    put(table_va,table,'constant fatal TTBR0 table; EL1 RW, EL0 inaccessible, NX',True)
    source=(ROOT/'scripts/xnu-panic-screen.c').read_text()
    begin=source.index('static int fb_setup ('); end=source.index('\n/* The frame buffer sits inside DRAM',begin)
    source=source[:begin]+(ROOT/'scripts/fatal-only-fb.h').read_text()+source[end:]
    begin=source.index('  unsigned long long start, now;'); end=source.index('\n}\n',begin)
    source=source[:begin]+'  (void)seconds;\n  for (;;) __asm__ volatile("wfe");'+source[end:]
    begin=source.index('  /* Record the panic in the same slot');end=source.index('\n#ifdef PANIC_DRY_RUN',begin)
    source=source[:begin]+'  (void)v;\n  g.base=0;\n  if (!fb_setup(&g,1,0)) park_short();\n'+source[end:]
    source=source.replace('if (at < 0xfffffff000000000UL || (at & 15)) break;',
                          'if (at < 0xfffffff000000000UL || (at & 15) || !fatal_readable(at,16)) break;')
    # Beacons are not included in this build, and their old out-of-bounds stash is omitted.
    source=source[:source.index('\n/* The kernel cannot write the frame buffer:',source.index('#include "Font.h"'))]
    source=source.replace('  format (&g, fmt, args);', '  text(&g,"fi136 / full checks\\n");\n  format (&g, fmt, args);')
    source=source.replace('  (void)MAX_MEM;', '  (void)MAX_MEM;\n  hex(&g,"\\nresetWpar=",fatal_par(RESET_HANDLER_VA,1));')
    # A previous boot's framebuffer pixels must never suppress this boot's panic.
    source=source.replace('mark[0] == 0xC0FFEE11u && mark[1] == 0x5CEEDA7Au',
                          '__atomic_exchange_n((volatile u8 *)(PANIC_TEXT + PANIC_TEXT_BYTES - 1), (u8)1, __ATOMIC_RELAXED) != 0')
    source=source.replace('g->logn < PANIC_TEXT_BYTES - 1', 'g->logn < PANIC_TEXT_BYTES - 2')
    source=source.replace('/* First panic wins: a marker in the last row\'s first two pixels means a panic already drew\n   * the screen; a later panic (another thread or exception) must not overwrite it. */',
                          '/* First panic claim lives in this kernel\'s fresh native buffer, not retained pixels. */')
    assert names.get('_boot_progress_panic_text'), 'Per-boot claim needs a native buffer'
    source='#define FB_ROOT_VA '+hex(table_va)+'UL\n#define RESET_HANDLER_VA '+hex(names['_ResetHandlerData'])+'UL\n'+source
    generated=args.out/'fatal-screen.c'; generated.write_text(source)
    probe=load('panic_probe',ROOT/'scripts/patch-xnu-entry-probe.py')
    probe.load_segments(raw);probe.VINFO_VA=names['_vinfo']
    os.environ['UNIXNU_UEFI']=str(args.uefi.resolve(strict=True))
    text=native.segments['__TEXT_EXEC']; end_of_sections=max(s['va']+s['size'] for s in text['sections'].values())
    cave=(end_of_sections+4095)&~4095
    code,load_va,entry=probe.assemble_c(generated,cave,args.out/'renderer',names)
    assert load_va+len(code)<=text['va']+text['filesize'], 'Renderer exceeds native executable padding'
    put(load_va,code,'fatal-only renderer in unused executable padding',True)
    common=probe.panic_common_entry(args.out/'renderer',code,load_va)
    for name,target in [('_panic',entry),('_panic_trap_to_debugger',common)]:
        va=names[name]; at=offset(native,va,8)
        assert struct.unpack_from('<I',raw,at)[0]==0xd503237f, 'Expected intact PACIBSP prologue'
        assert raw[at+4:at+8]!=b'\0'*4
        put(va+4,struct.pack('<I',probe.branch(va+4,target)),'fatal dispatch after preserved PACIBSP: '+name)
        assert bytes(data[at:at+4])==raw[at:at+4]
    seals=[s for seg in native.segments.values() for n,s in seg['sections'].items() if n=='__fips_hmacs']
    assert len(seals)==1 and seals[0]['size']==32
    native_text=text['sections']['__text']; start=offset(native,native_text['va'],native_text['size'])
    seal_at=offset(native,seals[0]['va'],32)
    assert raw[seal_at:seal_at+32]==hmac.new(b'\0',raw[start:start+native_text['size']],hashlib.sha256).digest(), 'Original native HMAC mismatch'
    digest=hmac.new(b'\0',data[start:start+native_text['size']],hashlib.sha256).digest()
    put(seals[0]['va'],digest,'recomputed native corecrypto HMAC')
    preserved={}
    for name in ['___stack_chk_fail','_kalloc_type_view_parse','_arm_vm_init','_arm_vm_prot_init','_arm_vm_prot_finalize','_arm_init','_PE_init_printf']:
        va=names[name]; end=min(v for v in names.values() if v>va);at=offset(native,va,end-va)
        assert raw[at:at+end-va]==bytes(data[at:at+end-va]),name+' was modified'
        preserved[name]=dict(va=hex(va),bytes=end-va,sha256=hashlib.sha256(raw[at:at+end-va]).hexdigest())
    allowed=set()
    for c in changes:allowed.update(range(c['file_offset'],c['file_offset']+c['size']))
    assert all(i in allowed for i,(x,y) in enumerate(zip(raw,data)) if x!=y)
    output=args.out/'kernel.macho'
    with output.open('xb') as f:f.write(data)
    report=dict(input_sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(data).hexdigest(),output=str(output),renderer_bytes=len(code),
                preserved_functions=preserved,changes=changes,normal_flow_changes=0,old_masking_patches_inherited=0,
                runtime_permissions='Unverified; this diagnostic only uses a private TTBR0 view after fatal dispatch')
    with (args.out/'diagnostic-manifest.json').open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
