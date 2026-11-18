#!/usr/bin/env python3
"""Compile the installed ledger range contract into an allowlisted fi138 derivative.
This is a native binary derivative, not a full XNU rebuild. Native finalization,
feature checks, failure BRKs and outer PAC frame remain the original machine code.
"""
import argparse,hashlib,hmac,importlib.util,json,shutil,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE_SHA='955ae86dc07a3f24b76d22e2cacf0279ab2d7823e3d77920aaee6f7f733e0fbe'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def branch(pc,target):
 d=target-pc;assert not d%4 and -(1<<27)<=d<(1<<27);return struct.pack('<I',0x14000000|((d>>2)&0x3ffffff))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',required=True,type=Path);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);args=p.parse_args()
 raw=args.kernel.read_bytes();assert sha(raw)==BASE_SHA,'Requires the exact fi138 booted kernel'
 pc=load('pc',ROOT/'scripts/apply-port-const.py');source=args.source.read_text();patched=pc.patch_ledger(source);assert patched.count(pc.LEDGER_NEW)==1
 block=patched[patched.index(pc.LEDGER_SPAN_HELPER):patched.index(pc.LEDGER_SPAN_HELPER)+len(pc.LEDGER_NEW)];assert block==pc.LEDGER_NEW
 a=load('audit',ROOT/'scripts/audit-port-const-kernel.py');r=a.MachO(raw);m=a.MachO(raw,r.entries['com.apple.kernel']);syms=m.symbols();data=bytearray(raw)
 def at(va,n):
  seg=next(s for s in m.segments.values() if s['va']<=va and va+n<=s['va']+s['filesize']);return seg['fileoff']+va-seg['va']
 fn=syms['_ledger_template_finalize'];size=min(v for v in syms.values() if v>fn)-fn;assert size==492
 # Exact ABI evidence from the frozen function, not guessed offsets.
 assert raw[at(fn,4):at(fn,4)+4]==struct.pack('<I',0xd503237f)
 hook=fn+0x194;resume=fn+0x30;fail1=fn+0x1b4;fail2=fn+0x1e8
 # Use an independent fixed digest of the full function in the report as well;
 # opcode/operand validation below pins every original range-check boundary.
 from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
 cs=Cs(CS_ARCH_ARM64,CS_MODE_ARM);ins={i.address:(i.mnemonic,i.op_str) for i in cs.disasm(raw[at(fn,size):at(fn,size)+size],fn)}
 assert ins[hook]==('adrp','x8, #0xfffffff007dd0000')
 assert ins[fn+0x19c]==('add','x9, x19, #0x128')
 assert ins[fn+0x1b8]==('ldr','x9, [x19, #0x10]') and ins[fn+0x1cc]==('ldrh','w8, [x19, #0x18]')
 assert ins[fn+0x1d0]==('mov','w10, #0x78')
 assert ins[fail1]==('bl',hex(syms['_ledger_template_finalize.cold.2']).replace('0x','#0x'))
 assert ins[fail2][0]=='bl' and ins[resume]==('ldrh','w8, [x19, #0x18]')
 copy=syms['_ledger_template_copy'];copy_size=min(v for v in syms.values() if v>copy)-copy;assert copy_size==496
 copy_ins={i.address:(i.mnemonic,i.op_str) for i in cs.disasm(raw[at(copy,copy_size):at(copy,copy_size)+copy_size],copy)}
 guards=[dict(name='finalize',entry='ledger_entry',input_reg='x19',hook=hook,resume=resume,fail_template=fail1,fail_entries=fail2),
         dict(name='copy_destination',entry='ledger_copy_destination',input_reg='x19',hook=copy+0x140,resume=copy+0x164,fail_template=copy+0x160,fail_entries=copy+0x1b8),
         dict(name='copy_source',entry='ledger_copy_source',input_reg='x20',hook=copy+0x164,resume=copy+0x44,fail_template=copy+0x184,fail_entries=copy+0x1ec)]
 for g in guards[1:]:
  assert copy_ins[g['hook']]==('adrp','x8, #0xfffffff007dd0000')
  assert copy_ins[g['hook']+8]==('add','x9, '+g['input_reg']+', #0x128')
  for field in ['fail_template','fail_entries']:
   mnemonic,operand=copy_ins[g[field]];assert mnemonic=='bl'
   target=int(operand[1:],16);assert any(i.mnemonic=='brk' and i.op_str=='#0xbffc' for i in cs.disasm(raw[at(target,16):at(target,16)+16],target))
 # The source helper has exactly three non-unit-test invocations: finalize, dst, src.
 assert source.count('\tlt_require_data_const(')==3
 low=syms['_LowExceptionVectorBase'];cave=low+0xa00;limit=low+0x1000;assert not any(raw[at(cave,limit-cave):at(cave,limit-cave)+limit-cave])
 dc=m.segments['__DATA_CONST'];port=m.port_segment()
 # Mach-O segment$end$ is the unrounded last-section end, NOT vmsize padding.
 dc_end=max(s['va']+s['size'] for s in dc['sections'].values());port_end=max(s['va']+s['size'] for s in port['sections'].values())
 assert dc['va']==0xfffffff007dd0000 and dc_end==0xfffffff007e31958
 out=args.out.resolve();assert ROOT in out.parents;out.mkdir(parents=True,exist_ok=False)
 # ABI shim only supplies the fields touched by the actual installed function.
 # All sizes/offsets are cross-checked against the original native instructions.
 prefix='''#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
struct ledger_entry_template { unsigned char opaque[0x78]; };
typedef struct ledger_template {
 unsigned char prefix[0x10]; struct ledger_entry_template *lt_entries;
 uint16_t lt_cnt; unsigned char suffix[0x128-0x1a];
} *ledger_template_t;
_Static_assert(sizeof(struct ledger_template)==0x128,"native template size");
_Static_assert(offsetof(struct ledger_template,lt_entries)==0x10,"native pointer offset");
_Static_assert(offsetof(struct ledger_template,lt_cnt)==0x18,"native count offset");
#define __SEGMENT_START_SYM(s) __asm__("SEGSTART" s)
#define __SEGMENT_END_SYM(s) __asm__("SEGEND" s)
enum { ASSERT_COUNTER_BASE = __COUNTER__ };
#define assert(c) do { if (!(c)) return __COUNTER__-ASSERT_COUNTER_BASE; } while (0)
'''
 # Only failure reporting is adapted: 1 -> original template BRK, 2 -> entry BRK.
 adapter=block.replace('static void\nlt_require_data_const','static unsigned\nlt_require_data_const',1);left,right=adapter.rsplit('\n}',1);adapter=left+'\n\treturn 0;\n}'+right
 c=out/'ledger-check.c';c.write_text(prefix+adapter+'\nunsigned ledger_check(ledger_template_t p){return lt_require_data_const(p);}\n')
 asm=out/'ledger-entry.S';assembly=['.section .ledger_entry,"ax",@progbits']
 for g in guards:
  name=g['entry'];assembly.append(f'''.global {name}
{name}:
 stp x0,x1,[sp,#-32]!
 str x30,[sp,#16]
 mov x0,{g['input_reg']}
 bl ledger_check
 mov w8,w0
 ldr x30,[sp,#16]
 ldp x0,x1,[sp],#32
 cmp w8,#1
 b.eq .Lfail_template_{name}
 cmp w8,#2
 b.eq .Lfail_entries_{name}
 cbnz w8,.Lfail_template_{name}
 b RESUME_{name}
.Lfail_template_{name}:
 b FAIL_TEMPLATE_{name}
.Lfail_entries_{name}:
 b FAIL_ENTRIES_{name}
''')
 asm.write_text('\n'.join(assembly))
 bindings='\n'.join(f"FAIL_TEMPLATE_{g['entry']} = {g['fail_template']:#x}; FAIL_ENTRIES_{g['entry']} = {g['fail_entries']:#x}; RESUME_{g['entry']} = {g['resume']:#x};" for g in guards)
 ld=out/'ledger.ld';ld.write_text(f'''SEGSTART__DATA_CONST = {dc['va']:#x};
SEGEND__DATA_CONST = {dc_end:#x};
SEGSTART__PORT_CONST = {port['va']:#x};
SEGEND__PORT_CONST = {port_end:#x};
{bindings}
SECTIONS {{ . = {cave:#x}; .text : {{ *(.ledger_entry) *(.text*) *(.rodata*) }} /DISCARD/ : {{ *(.eh_frame*) *(.note*) *(.comment) }} }}
''')
 flags=['--target=aarch64-none-elf','-march=armv8.3-a','-mbranch-protection=pac-ret+leaf+b-key+bti','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-mcmodel=small','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror','-DUNIXNU_SHENNONG_PORT_CONST=1']
 commands=[]
 def run(cmd):
  commands.append([str(x) for x in cmd]);p=subprocess.run([str(x) for x in cmd],capture_output=True)
  (out/f'command-{len(commands)}.stdout').write_bytes(p.stdout);(out/f'command-{len(commands)}.stderr').write_bytes(p.stderr)
  if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
  return p.stdout
 run(['clang',*flags,'-c',c,'-o',out/'check.o']);run(['clang',*flags,'-c',asm,'-o',out/'entry.o']);run(['ld.lld','-T',ld,'-e','ledger_entry',out/'entry.o',out/'check.o','-o',out/'ledger.elf']);run(['llvm-objcopy','-O','binary','-j','.text',out/'ledger.elf',out/'ledger.bin'])
 assert not run(['llvm-nm','--undefined-only',out/'ledger.elf']).strip()
 symbols={}
 for line in run(['llvm-nm',out/'ledger.elf']).decode().splitlines():
  f=line.split()
  if len(f)==3:symbols[f[2]]=int(f[0],16)
 blob=(out/'ledger.bin').read_bytes();assert cave+len(blob)<=limit
 decoded=list(cs.disasm(blob,cave));assert any(i.mnemonic=='pacibsp' for i in decoded) and any(i.mnemonic=='retab' for i in decoded),'New checker must use B-key PAC return'
 changes=[]
 def put(va,b,label):
  off=at(va,len(b));assert not any(max(off,x['file_offset'])<min(off+len(b),x['file_offset']+x['size']) for x in changes)
  changes.append(dict(label=label,va=hex(va),file_offset=off,size=len(b),before_sha256=sha(raw[off:off+len(b)]),after_sha256=sha(b)));data[off:off+len(b)]=b
 put(cave,blob,'compiled original predicates: two resident constant domains with full spans')
 for g in guards:
  put(g['hook'],branch(g['hook'],symbols[g['entry']]),'replace constant-range contract: '+g['name'])
 title=b'fi138 / full checks / fatal record';assert raw.count(title)==1;title_off=raw.index(title)
 title_seg=next(s for s in m.segments.values() if s['fileoff']<=title_off<title_off+len(title)<=s['fileoff']+s['filesize']);title_va=title_seg['va']+title_off-title_seg['fileoff'];put(title_va,b'fi139 / full checks / fatal record','diagnostic build label only')
 seals=[s for seg in m.segments.values() for n,s in seg['sections'].items() if n=='__fips_hmacs'];assert len(seals)==1;text=m.segments['__TEXT_EXEC']['sections']['__text'];start=at(text['va'],text['size']);seal=seals[0];assert raw[at(seal['va'],32):at(seal['va'],32)+32]==hmac.new(b'\0',raw[start:start+text['size']],hashlib.sha256).digest()
 put(seal['va'],hmac.new(b'\0',data[start:start+text['size']],hashlib.sha256).digest(),'genuine native text HMAC recomputed')
 # Exact complement proof. All original BRKs, PAC, stack frame, loop and epilogue stay.
 allowed=bytearray(len(raw))
 for x in changes:allowed[x['file_offset']:x['file_offset']+x['size']]=b'\1'*x['size']
 changed_bytes=sum(x!=y for x,y in zip(raw,data));assert all(allowed[i] for i,(x,y) in enumerate(zip(raw,data)) if x!=y)
 oldfn=raw[at(fn,size):at(fn,size)+size];newfn=data[at(fn,size):at(fn,size)+size];assert oldfn[:0x194]==newfn[:0x194] and oldfn[0x198:]==newfn[0x198:]
 functions=[]
 for label,va,n in [('finalize',fn,size),('copy',copy,copy_size)]:
  before=raw[at(va,n):at(va,n)+n];after=data[at(va,n):at(va,n)+n];sites={g['hook'] for g in guards if va<=g['hook']<va+n}
  assert all(any(site-va<=i<site-va+4 for site in sites) for i,(x,y) in enumerate(zip(before,after)) if x!=y)
  functions.append(dict(name=label,va=hex(va),bytes=n,hooks=[hex(x) for x in sorted(sites)],before_sha256=sha(before),after_sha256=sha(after)))
 (out/'kernel.macho').write_bytes(data);(out/'ledger.asm').write_text('\n'.join(f'{i.address:#x}: {i.mnemonic} {i.op_str}' for i in decoded)+'\n')
 report=dict(guards=[{k:(hex(v) if isinstance(v,int) else v) for k,v in g.items()} for g in guards],functions=functions,input_sha256=sha(raw),output_sha256=sha(data),changes=changes,changed_bytes=changed_bytes,blob_bytes=len(blob),symbols={k:hex(v) for k,v in symbols.items()},function=dict(va=hex(fn),bytes=size,hook=hex(hook),resume=hex(resume),fail_template=hex(fail1),fail_entries=hex(fail2),before_sha256=sha(oldfn),after_sha256=sha(newfn)),ranges=dict(DATA_CONST=[hex(dc['va']),hex(dc_end)],PORT_CONST=[hex(port['va']),hex(port_end)]),source_sha256=sha(source.encode()),patched_ledger_sha256=sha(patched.encode()),contract_sha256=sha(pc.LEDGER_NEW.encode()),adapter='Only void assertion reporting adapted to statuses 1/2; exact installed span predicates retained',commands=commands,scope='native binary derivative, not full XNU rebuild; hardware unverified')
 (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['changes','symbols','commands']},indent=2))
if __name__=='__main__':main()
