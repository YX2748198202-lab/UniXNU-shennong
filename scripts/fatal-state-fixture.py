#!/usr/bin/env python3
"""Execute real linked fatal observer in Unicorn, modeling privileged translations.
This is a fixture, not proof of Qualcomm MMU/display behavior.
"""
from pathlib import Path
import json,struct
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_ALL
import unicorn.arm64_const as R
MASK=(1<<64)-1
class Fixture:
 def __init__(self,build,mmu=1,video=None):
  self.build=Path(build);self.report=json.loads((self.build/'diagnostic-manifest.json').read_text());self.delta=(0x80000000-0xfffffff000000000) if not mmu else 0
  self.move=lambda v:v+self.delta if v>=0xffff000000000000 else v
  self.symbols={k:self.move(int(v,16)) for k,v in self.report['symbols'].items()};self.uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);self.regions=[];self.log=[];self.syswrites=[];self.parked=False
  self.sim={'sctlr_el1':mmu,'tcr_el1':0x80022a51a251a,'ttbr0_el1':0x1234000,'ttbr1_el1':0x2345000,'mair_el1':0x0c0804ff00bb44ff,'vbar_el1':0xfffffff00ad7c000,'currentel':4,'esr_el1':0x9600004f,'far_el1':0xfffffff012345678,'elr_el1':0xfffffff00abcdef0,'spsr_el1':0x3c5,'sp_el0':0x81234560,'par_el1':0}
  for section in ['text','fatal_entries']:
   change=next(c for c in self.report['changes'] if (c['label'].startswith('fatal renderer') if section=='text' else c['label'].startswith('stackless terminal')));base=self.move(int(change['va'],16));blob=(self.build/(section+'.bin')).read_bytes();self.map(base,len(blob));self.uc.mem_write(base,blob)
   cs=Cs(CS_ARCH_ARM64,CS_MODE_ARM);cs.skipdata=True
   for ins in cs.disasm(blob,base):
    if ins.mnemonic in ['mrs','msr','at','dc','tlbi','ic','wfe']:
     self.uc.hook_add(UC_HOOK_CODE,self.special,ins,ins.address,ins.address)
  record=self.symbols['FATAL_RECORD'];self.map(record,0x780);claim=self.symbols['FATAL_CLAIM'];self.map(claim-2047,2048)
  self.map(self.symbols['fatal_video_state'],40);self.map(self.symbols['fatal_fb_root'],4096)
  v=video or [0xfc400000,480*4,480,480,32];self.video=v
  self.uc.mem_write(self.symbols['fatal_video_state'],struct.pack('<5Q',*v));self.map(v[0],max(v[1]*v[3],4096))
  self.args=0x81000000;self.map(self.args,8192)
  self.uc.reg_write(R.UC_ARM64_REG_SP,0xdead0000);self.uc.reg_write(R.UC_ARM64_REG_X30,0xaabbccdd00112233)
 def map(self,addr,n):
  low=addr&~4095;high=(addr+n+4095)&~4095
  for page in range(low,high,4096):
   if not any(a<=page<b for a,b in self.regions):self.uc.mem_map(page,4096,UC_PROT_ALL);self.regions.append((page,page+4096))
 def mapped(self,addr):return any(a<=addr<b for a,b in self.regions)
 def reg(self,name):
  if name=='xzr':return 0
  return self.uc.reg_read(getattr(R,'UC_ARM64_REG_'+name.upper()))
 def special(self,uc,address,size,ins):
  op=ins.mnemonic;parts=[p.strip() for p in ins.op_str.split(',')]
  if op=='mrs':uc.reg_write(getattr(R,'UC_ARM64_REG_'+parts[0].upper()),self.sim[parts[1]])
  elif op=='msr':
   self.syswrites.append(ins.op_str)
   if parts[0] not in ['daifset']:self.sim[parts[0]]=self.reg(parts[1])
  elif op=='at':
   va=self.reg(parts[1]);self.sim['par_el1']=(va&0x0000fffffffff000) if self.mapped(va) else 1
  elif op=='wfe':self.parked=True;uc.emu_stop();return
  uc.reg_write(R.UC_ARM64_REG_PC,address+4)
 def run(self,entry,arg0=0,arg1=0,count=30000000):
  self.uc.reg_write(R.UC_ARM64_REG_X0,arg0);self.uc.reg_write(R.UC_ARM64_REG_X1,arg1);self.parked=False
  self.uc.emu_start(self.symbols[entry],0,count=count)
  if not self.parked:raise AssertionError('Did not reach terminal WFE')
  record=self.symbols['FATAL_RECORD'];fields=struct.unpack('<22Q',bytes(self.uc.mem_read(record,176)))
  text=bytes(self.uc.mem_read(self.symbols['fatal_log'],2047)).split(b'\0',1)[0].decode('ascii')
  return fields,text
if __name__=='__main__':
 import sys
 f=Fixture(sys.argv[1]);f.uc.mem_write(f.args,b'fixture panic value=%u\0');f.uc.mem_write(f.args+4096,struct.pack('<Q',256));f.uc.reg_write(R.UC_ARM64_REG_SP,f.args+4096)
 r,t=f.run('fatal_panic',f.args);print(json.dumps({'record':list(r),'text':t,'syswrites':f.syswrites},indent=2))
