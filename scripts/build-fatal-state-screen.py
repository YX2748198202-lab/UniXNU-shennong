#!/usr/bin/env python3
"""Build an immutable fatal-state observer; preserve all normal execution paths."""
import argparse,hashlib,hmac,importlib.util,json,os,shutil,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def off(m,va,n=1):
 for s in m.segments.values():
  if s['va']<=va and va+n<=s['va']+s['filesize']:return s['fileoff']+va-s['va']
 raise ValueError(f'No file backing: {va:#x}+{n}')
def branch(pc,target):
 delta=target-pc
 if delta%4 or not -(1<<27)<=delta<(1<<27):raise ValueError('Branch range')
 return struct.pack('<I',0x14000000|((delta>>2)&0x3ffffff))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--uefi',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
 raw=args.kernel.read_bytes();a=load('audit',ROOT/'scripts/audit-port-const-kernel.py');r=a.MachO(raw);m=a.MachO(raw,r.entries['com.apple.kernel']);names=m.symbols()
 if sha(raw)!='c5cbf10864845a1cb30fe0bb5048a12d40c41c3f948c998eea936f8befa17571':raise ValueError('Requires frozen raw full-check CI kernel')
 out=args.out.resolve();assert ROOT in out.parents;out.mkdir(parents=True,exist_ok=False)
 font=args.uefi.resolve(strict=True)/'Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib';assert (font/'Font.h').is_file()
 text=m.segments['__TEXT_EXEC'];sections_end=max(s['va']+s['size'] for s in text['sections'].values());cave=(sections_end+4095)&~4095
 low=names['_LowExceptionVectorBase'];entries=low+0x800;entries_end=low+0x1000
 assert raw[off(m,entries,entries_end-entries):off(m,entries,entries_end-entries)+entries_end-entries]==bytes(entries_end-entries)
 ds=m.segments['__DATA'];last=max(s['va']+s['size'] for s in ds['sections'].values());record=(last+63)&~63;stack_top=ds['va']+ds['size'];stack_bottom=record+384
 assert stack_top%16==0 and stack_top-stack_bottom>=1536
 # Reserve only linker padding after all native DATA sections; loader zeroes vmsize.
 assert record>=ds['va']+ds['filesize'] and stack_top==ds['va']+ds['size']
 log=names['_boot_progress_panic_text'];assert raw[off(m,log,2048):off(m,log,2048)+2048]==bytes(2048)
 port=m.port_segment();table_va=port['va']+port['size']-4096;assert max(x['va']+x['size'] for x in port['sections'].values())<=table_va
 script=out/'fatal.ld';script.write_text(f'''FATAL_RECORD = {record:#x};
FATAL_STACK_TOP = {stack_top:#x};
FATAL_CLAIM = {log+2047:#x};
fatal_log = {log:#x};
fatal_video_state = {names['_PE_state']+8:#x};
fatal_fb_root = {table_va:#x};
SECTIONS {{
 . = {entries:#x}; .fatal_entries : {{ *(.fatal_entries) }}
 . = {cave:#x}; .text : {{ *(.text*) *(.rodata*) }}
 /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) }}
}}
''')
 flags=['--target=aarch64-none-elf','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-mcmodel=small','-mgeneral-regs-only','-Oz','-fstack-usage','-Wall','-Wextra','-Werror',f'-I{font}',f'-I{ROOT/"scripts"}']
 clang=shutil.which('clang');lld=shutil.which('ld.lld');objcopy=shutil.which('llvm-objcopy');nm=shutil.which('llvm-nm')
 for src,name in [('fatal-state-screen.c','screen'),('fatal-state-entry.S','entry')]:
  subprocess.run([clang,*flags,'-c',str(ROOT/'scripts'/src),'-o',str(out/(name+'.o'))],check=True)
 elf=out/'fatal.elf';subprocess.run([lld,'-T',str(script),'-e','fatal_panic',str(out/'entry.o'),str(out/'screen.o'),'-o',str(elf)],check=True)
 syms={}
 for line in subprocess.check_output([nm,str(elf)],text=True).splitlines():
  fields=line.split()
  if len(fields)==3:syms[fields[2]]=int(fields[0],16)
 assert not subprocess.check_output([nm,'--undefined-only',str(elf)],text=True).strip()
 binaries={}
 for section in ['.text','.fatal_entries']:
  binary=out/(section[1:]+'.bin');subprocess.run([objcopy,'-O','binary','-j',section,str(elf),str(binary)],check=True);binaries[section]=binary.read_bytes()
 assert cave+len(binaries['.text'])<=text['va']+text['filesize'],f'Renderer exceeds text padding: {len(binaries[".text"])}'
 assert entries+len(binaries['.fatal_entries'])<=entries_end
 usage=[]
 for line in (out/'screen.su').read_text().splitlines():
  fields=line.split('\t');assert len(fields)==3 and fields[2]=='static',line;usage.append(dict(function=fields[0],bytes=int(fields[1])))
 # No recursion or indirect calls in this freestanding renderer; sum is conservative.
 sum_stack=sum(x['bytes'] for x in usage);assert sum_stack+256<=stack_top-stack_bottom
 data=bytearray(raw);changes=[]
 def put(va,b,label,empty=False):
  at=off(m,va,len(b));old=raw[at:at+len(b)];assert not empty or not any(old)
  assert all(max(at,c['file_offset'])>=min(at+len(b),c['file_offset']+c['size']) for c in changes)
  data[at:at+len(b)]=b;changes.append(dict(label=label,va=hex(va),file_offset=at,size=len(b),before_sha256=sha(old),after_sha256=sha(b)))
 put(cave,binaries['.text'],'fatal renderer in executable linker padding',True)
 put(entries,binaries['.fatal_entries'],'stackless terminal fault capture in low-vector padding',True)
 for name,target in [('_panic','fatal_panic'),('_panic_trap_to_debugger','fatal_common'),('_panic_with_thread_kernel_state','fatal_state_entry')]:
  va=names[name];assert raw[off(m,va,4):off(m,va,4)+4]==struct.pack('<I',0xd503237f)
  put(va+4,branch(va+4,syms[target]),'fatal branch after PACIBSP: '+name)
 for slot in range(16):
  va=low+slot*128;assert raw[off(m,va,4):off(m,va,4)+4]==struct.pack('<I',0x14000000)
  put(va,branch(va,syms[f'fatal_low_{slot}']),f'terminal low vector slot {slot}')
 spill=names['_el1_sp1_synchronous_vector_long_spill_failed'];assert raw[off(m,spill,8):off(m,spill,8)+8]==struct.pack('<II',0xd503205f,0x17ffffff)
 put(spill,branch(spill,syms['fatal_spill']),'terminal SP1 spill-failed branch')
 table=bytearray(4096);struct.pack_into('<Q',table,24,(1<<54)|(1<<53)|0xc0000000|0x40d)
 put(table_va,table,'fatal-only constant TTBR0 view',True)
 seals=[s for seg in m.segments.values() for n,s in seg['sections'].items() if n=='__fips_hmacs'];assert len(seals)==1
 sec=text['sections']['__text'];start=off(m,sec['va'],sec['size']);seal=seals[0];seal_at=off(m,seal['va'],32)
 assert raw[seal_at:seal_at+32]==hmac.new(b'\0',raw[start:start+sec['size']],hashlib.sha256).digest()
 put(seal['va'],hmac.new(b'\0',data[start:start+sec['size']],hashlib.sha256).digest(),'recomputed genuine native HMAC')
 preserved={}
 for name in ['__start','_start_first_cpu','common_start','_arm_init','_arm_vm_init','_arm_vm_prot_init','_arm_vm_prot_finalize','_early_random','_early_random_init','___stack_chk_fail','_kalloc_type_view_parse','_fleh_synchronous','_sleh_synchronous','_sleh_synchronous_sp1']:
  va=names[name];end=min(v for v in names.values() if v>va);at=off(m,va,end-va);assert raw[at:at+end-va]==data[at:at+end-va],name
  preserved[name]=dict(va=hex(va),bytes=end-va,sha256=sha(raw[at:at+end-va]))
 # Exact allowlist: every changed byte belongs to an explicit terminal hook/padding/HMAC.
 allowed=bytearray(len(raw))
 for c in changes:allowed[c['file_offset']:c['file_offset']+c['size']]=b'\1'*c['size']
 assert all(allowed[i] for i,(x,y) in enumerate(zip(raw,data)) if x!=y)
 (out/'kernel.macho').write_bytes(data)
 report=dict(input_sha256=sha(raw),output_sha256=sha(data),renderer_bytes=len(binaries['.text']),entry_bytes=len(binaries['.fatal_entries']),
   record=dict(va=hex(record),bytes=384,stack_bottom=hex(stack_bottom),stack_top=hex(stack_top),stack_bytes=stack_top-stack_bottom,conservative_stack_sum=sum_stack),
   claim=hex(log+2047),symbols={k:hex(v) for k,v in syms.items()},changes=changes,preserved_functions=preserved,stack_usage=usage,
   sources={n:sha((ROOT/'scripts'/n).read_bytes()) for n in ['fatal-state-screen.c','fatal-state-entry.S','fatal-record.h']},
   runtime='Unverified: no hardware inference from offline construction; no pstore persistence asserted')
 (out/'diagnostic-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['symbols','changes','preserved_functions','stack_usage']},indent=2))
if __name__=='__main__':main()
