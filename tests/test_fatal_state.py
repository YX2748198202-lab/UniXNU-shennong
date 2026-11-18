"""Host negative cases plus real ARM64 observer under modeled system registers."""
import ctypes,importlib.util,json,os,struct,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/os.environ.get('FATAL_STATE_BUILD','out/diagnostics/fi138-fatal-state/build3')
s=importlib.util.spec_from_file_location('fixture',ROOT/'scripts/fatal-state-fixture.py');fx=importlib.util.module_from_spec(s);s.loader.exec_module(fx)
R=fx.R
class Pure(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name);c=p/'test.c'
  c.write_text('#include "fatal-record.h"\nint video(u64 *v){return fatal_video_valid(*(struct fatal_video*)v);}\nint state(void *p, unsigned long n,struct fatal_state *s){return fatal_state_decode(p,n,s);}\n')
  subprocess.run(['clang','-shared','-fPIC','-O2',f'-I{ROOT/"scripts"}',str(c),'-o',str(p/'test.so')],check=True)
  cls.lib=ctypes.CDLL(str(p/'test.so'));cls.lib.video.argtypes=[ctypes.POINTER(ctypes.c_uint64)];cls.lib.state.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_geometry_valid(self):self.assertEqual(self.lib.video((ctypes.c_uint64*5)(0xfc400000,5760,1440,3200,32)),1)
 def test_geometry_negative_matrix(self):
  for field,value in [(0,0),(0,0xfc400001),(1,4),(1,65537),(2,0),(2,4097),(3,0),(3,8193),(4,24),(0,0xfffffffffffffff0)]:
   v=[0xfc400000,5760,1440,3200,32];v[field]=value
   with self.subTest(field=field,value=value):self.assertEqual(self.lib.video((ctypes.c_uint64*5)(*v)),0)
 def test_state_short_null_unaligned_bad_flavor(self):
  b=(ctypes.c_uint64*40)();out=(ctypes.c_uint64*6)()
  for ptr,n in [(0,0x128),(ctypes.addressof(b),0x127),(ctypes.addressof(b)+1,0x128),(ctypes.addressof(b),0x128)]:
   with self.subTest(ptr=ptr,n=n):self.assertEqual(self.lib.state(ptr,n,out),0)
 def test_state_preserves_raw_fields(self):
  b=(ctypes.c_uint64*40)();b[0]=21
  for off,val in [(0xf8,0xaabbccdd00112233),(0x100,0x1234),(0x108,0xfffffff00abcdef0),(0x110,0x3c5),(0x118,0x123456789abcdef0),(0x120,0x9600004f)]:b[off//8]=val
  out=(ctypes.c_uint64*6)();self.assertEqual(self.lib.state(b,0x128,out),1);self.assertEqual(list(out),[b[0x108//8],b[0xf8//8],b[0x100//8],b[0x120//8],b[0x118//8],0x3c5])
class Machine(unittest.TestCase):
 def make(self,**kwargs):return fx.Fixture(BUILD,**kwargs)
 def test_panic_stack_slots(self):
  f=self.make();f.uc.mem_write(f.args,b'value=%u\0');f.uc.mem_write(f.args+4096,struct.pack('<Q',256));f.uc.reg_write(R.UC_ARM64_REG_SP,f.args+4096)
  r,t=f.run('fatal_panic',f.args);self.assertEqual(r[16],5);self.assertIn('value=256',t);self.assertIn('ELR may be stale',t);self.assertEqual(r[3],0xaabbccdd00112233)
 def test_common_va_list_pointer(self):
  f=self.make();f.uc.mem_write(f.args,b'common=%x\0');f.uc.mem_write(f.args+256,struct.pack('<Q',f.args+512));f.uc.mem_write(f.args+512,struct.pack('<Q',0x1234))
  r,t=f.run('fatal_common',f.args,f.args+256);self.assertEqual(r[8],2);self.assertIn('common=1234',t)
 def test_state_before_trace_outputs_original(self):
  f=self.make();state=bytearray(0x128);struct.pack_into('<I',state,0,21)
  for off,val in [(0xf8,0x8877665544332211),(0x100,0x81234560),(0x108,0xfffffff00ad55048),(0x110,0x3c5),(0x118,0xfc400000),(0x120,0x9600004f)]:struct.pack_into('<Q',state,off,val)
  f.uc.mem_write(f.args,bytes(state));f.uc.mem_write(f.args+4096,b'Kernel data abort.\0');r,t=f.run('fatal_state_entry',f.args+4096,f.args)
  self.assertEqual(r[16],5);self.assertIn('ORIGINAL saved_state',t);self.assertIn('PC=0xfffffff00ad55048',t);self.assertIn('LR=0x8877665544332211',t);self.assertIn('Kernel data abort.',t)
 def test_unmapped_saved_state(self):
  f=self.make();r,t=f.run('fatal_state_entry',0,0x70000000);self.assertIn('INVALID saved_state',t);self.assertEqual(r[16],5)
 def test_bad_flavor_saved_state(self):
  f=self.make();r,t=f.run('fatal_state_entry',0,f.args);self.assertIn('INVALID saved_state',t);self.assertEqual(r[17],0)
 def test_stale_pixels_do_not_claim(self):
  f=self.make();v=f.video;f.uc.mem_write(v[0]+v[1]*(v[3]-1),struct.pack('<II',0xc0ffee11,0x5ceeda7a));r,t=f.run('fatal_panic')
  self.assertEqual(r[16],5);self.assertIn('fi138',t)
 def test_nested_record_keeps_first(self):
  f=self.make();r,t=f.run('fatal_panic');first=bytes(f.uc.mem_read(f.symbols['FATAL_RECORD'],136));f.sim['elr_el1']=0x12345678;r2,t2=f.run('fatal_spill')
  self.assertEqual(r2[17],1);self.assertEqual(r2[20],0x12345678);self.assertEqual(bytes(f.uc.mem_read(f.symbols['FATAL_RECORD'],136)),first);self.assertEqual(t,t2)
 def test_bad_video_leaves_status(self):
  f=self.make(video=[0xfc400000,480*4,480,480,24]);r,t=f.run('fatal_panic');self.assertEqual(r[16],0xe1);self.assertEqual(t,'')
 def test_bad_device_attr_leaves_status(self):
  f=self.make();f.sim['mair_el1']|=0xff000000;r,t=f.run('fatal_panic');self.assertEqual(r[16],0xe1);self.assertFalse(any(w.startswith('ttbr0') for w in f.syswrites))
 def test_spill_captures_hardware(self):
  f=self.make();r,t=f.run('fatal_spill');self.assertEqual(r[8],4);self.assertIn('HARDWARE exception registers',t);self.assertIn('ESR=0x000000009600004f',t)
 def test_mmu_off_low_slots_with_physical_relocation(self):
  for slot in [0,4,8,15]:
   with self.subTest(slot=slot):
    f=self.make(mmu=0);v=f.video;boot=bytearray(0x80);struct.pack_into('<6Q',boot,0x28,v[0],1,v[1],v[2],v[3],v[4]);f.uc.mem_write(f.args,bytes(boot));f.uc.reg_write(R.UC_ARM64_REG_X20,f.args)
    r,t=f.run('fatal_low_'+str(slot));self.assertEqual(r[16],5);self.assertEqual(r[8],slot+16);self.assertIn('HARDWARE exception registers',t)
    self.assertEqual(r[2],0xdead0000 if slot==4 else f.sim['sp_el0']);self.assertFalse(any(w.startswith('ttbr0') for w in f.syswrites))
 def test_guarded_argument_pointer(self):
  f=self.make();f.uc.mem_write(f.args,b'%u\0');r,t=f.run('fatal_panic',f.args);self.assertIn('[bad args]',t);self.assertEqual(r[17],0)
 def test_full_log_preserves_claim(self):
  f=self.make();f.uc.mem_write(f.args,b'%s'*20+b'\0');f.uc.mem_write(f.args+1024,b'A'*256+b'\0');f.uc.mem_write(f.args+4096,struct.pack('<20Q',*([f.args+1024]*20)));f.uc.reg_write(R.UC_ARM64_REG_SP,f.args+4096)
  r,t=f.run('fatal_panic',f.args);self.assertEqual(len(t),2046);self.assertEqual(bytes(f.uc.mem_read(f.symbols['FATAL_CLAIM']-1,2)),b'\0\1')
if __name__=='__main__':unittest.main()
