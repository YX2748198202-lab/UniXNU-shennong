#!/usr/bin/env python3
"""Compile/execute the installed ledger checks; preserve the flag-off upstream path.
The C ABI shim only supplies types, linker ranges, and assertion capture; it is
not a complete XNU build. Optional integration uses the actual external source.
"""
import ctypes,importlib.util,json,os,random,re,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('pc',ROOT/'scripts/apply-port-const.py');pc=importlib.util.module_from_spec(s);s.loader.exec_module(pc)
PREFIX='''#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
typedef struct ledger_entry_template { unsigned char bytes[120]; } *ledger_entry_template_t;
typedef struct ledger_template {
 const char *name; void *zone; ledger_entry_template_t lt_entries;
 uint16_t lt_cnt, size, counters; void *tabs; uint32_t lut[64];
} *ledger_template_t;
'''
HOST=PREFIX+'''#include <setjmp.h>
static jmp_buf failed;
static int checks;
#define assert(c) do { checks++; if (!(c)) longjmp(failed,checks); } while(0)
#define __SEGMENT_START_SYM(s)
#define __SEGMENT_END_SYM(s)
unsigned char arena[16384] __attribute__((aligned(4096)));
__asm__(".global data_const_start\\n.set data_const_start,arena\\n"
        ".global data_const_end\\n.set data_const_end,arena+4096\\n"
        ".global port_const_start\\n.set port_const_start,arena+12288\\n"
        ".global port_const_end\\n.set port_const_end,arena+16384\\n");
'''
SUFFIX='''uintptr_t base_addr(void) { return (uintptr_t)arena; }
size_t template_bytes(void) {return sizeof(struct ledger_template);}
size_t entry_bytes(void) {return sizeof(struct ledger_entry_template);}
int validate_at(uintptr_t p, uintptr_t entries, uint16_t count) {
 if (p >= (uintptr_t)arena && p <= (uintptr_t)arena+sizeof(arena)-sizeof(struct ledger_template)) {
   ledger_template_t t=(ledger_template_t)p; t->lt_entries=(ledger_entry_template_t)entries; t->lt_cnt=count;
 }
 checks=0; int failure=setjmp(failed); if (failure) return failure;
 lt_require_data_const((ledger_template_t)p); return 0;
}
'''
ARM=PREFIX+'''#define __SEGMENT_START_SYM(s) asm("segment$start$" s)
#define __SEGMENT_END_SYM(s) asm("segment$end$" s)
extern void fixture_assert_failed(void) __attribute__((noreturn));
#define assert(c) ((c) ? (void)0 : fixture_assert_failed())
'''
class Transform(unittest.TestCase):
 def test_idempotent_exact_single_edit(self):
  before='/* before */\n'+pc.LEDGER_OLD+'\n/* after */';after=pc.patch_ledger(before)
  self.assertEqual(after,pc.patch_ledger(after));self.assertEqual(after.replace(pc.LEDGER_NEW,pc.LEDGER_OLD),before)
 def test_missing_ambiguous_partial_context_fails(self):
  for text in ['changed upstream',pc.LEDGER_OLD*2,pc.LEDGER_NEW+'\n'+pc.LEDGER_OLD,pc.LEDGER_SPAN_HELPER+pc.LEDGER_OLD]:
   with self.subTest(case=text[:30]),self.assertRaises(ValueError):pc.patch_ledger(text)
 def test_existing_assertions_and_entry_guard_retained(self):
  self.assertIn('if (lt->lt_cnt)',pc.LEDGER_NEW);self.assertEqual(pc.LEDGER_NEW.count('assert('),4)
  self.assertIn('sizeof(*lt)',pc.LEDGER_NEW);self.assertIn('sizeof(*lt->lt_entries)',pc.LEDGER_NEW)
 def test_real_source_install_twice_and_no_other_changes(self):
  tree=os.environ.get('LEDGER_CONST_XNU')
  if not tree:self.skipTest('Set LEDGER_CONST_XNU for external source integration')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sources={};paths=['osfmk/arm64/arm_vm_init.c','osfmk/kern/ledger.c','makedefs/MakeInc.def']
   for rel in paths:
    original=(Path(tree)/rel).read_bytes();sources[rel]=original;p=root/'.cache/xnu-work'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(original)
   first=pc.run('prepare',root);once={rel:(root/'.cache/xnu-work'/rel).read_bytes() for rel in paths};second=pc.run('prepare',root)
   self.assertEqual([r['changed'] for r in first['files']],[True,True,True]);self.assertTrue(all(not r['changed'] for r in second['files']))
   for rel in paths:self.assertEqual((Path(tree)/rel).read_bytes(),sources[rel]);self.assertEqual((root/'.cache/xnu-work'/rel).read_bytes(),once[rel])
   self.assertEqual(once['osfmk/kern/ledger.c'].decode().replace(pc.LEDGER_NEW,pc.LEDGER_OLD),sources['osfmk/kern/ledger.c'].decode())
 def test_ledger_failure_never_partially_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);work=root/'.cache/xnu-work';paths={'osfmk/arm64/arm_vm_init.c':'\n'.join(x[1] for x in pc.ARM_REPLACEMENTS),'osfmk/kern/ledger.c':'upstream changed','makedefs/MakeInc.def':pc.MAKEDEF_OLD}
   for rel,text in paths.items():p=work/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
   with self.assertRaises(ValueError):pc.run('prepare',root)
   for rel,text in paths.items():self.assertEqual((work/rel).read_text(),text)
 def test_ledger_symlink_escape_fails_before_write(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);work=root/'.cache/xnu-work';arm=work/'osfmk/arm64/arm_vm_init.c';arm.parent.mkdir(parents=True);before='\n'.join(x[1] for x in pc.ARM_REPLACEMENTS);arm.write_text(before)
   external=root/'reference.c';external.write_text(pc.LEDGER_OLD);ledger=work/'osfmk/kern/ledger.c';ledger.parent.mkdir(parents=True);ledger.symlink_to(external)
   with self.assertRaisesRegex(ValueError,'escaped'):pc.run('prepare',root)
   self.assertEqual(arm.read_text(),before);self.assertEqual(external.read_text(),pc.LEDGER_OLD)
class Compiled(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name);cls.libs={}
  # With an integration tree, compile the function extracted AFTER patching the
  # actual ledger.c, rather than silently using the replacement text directly.
  tree=os.environ.get('LEDGER_CONST_XNU');cls.block=pc.LEDGER_NEW
  if tree:
   original=(Path(tree)/'osfmk/kern/ledger.c').read_text();patched=pc.patch_ledger(original);cls.block=patched[patched.index(pc.LEDGER_SPAN_HELPER):patched.index(pc.LEDGER_SPAN_HELPER)+len(pc.LEDGER_NEW)]
   assert cls.block==pc.LEDGER_NEW
  for enabled in [False,True]:
   c=cls.path/f'{enabled}.c';so=cls.path/f'{enabled}.so';extra='\nint span(uintptr_t p,size_t n,size_t w){return lt_span_in_const_segment((void *)p,n,w);}\n' if enabled else ''
   c.write_text(HOST+cls.block+SUFFIX+extra);flags=['-DUNIXNU_SHENNONG_PORT_CONST=1'] if enabled else []
   subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',*flags,str(c),'-o',str(so)],check=True)
   lib=ctypes.CDLL(str(so));lib.base_addr.restype=ctypes.c_size_t;lib.template_bytes.restype=ctypes.c_size_t;lib.entry_bytes.restype=ctypes.c_size_t
   lib.validate_at.argtypes=[ctypes.c_size_t,ctypes.c_size_t,ctypes.c_uint16]
   if enabled:lib.span.argtypes=[ctypes.c_size_t]*3
   cls.libs[enabled]=lib
  cls.lib=cls.libs[True];cls.base=cls.lib.base_addr();cls.size=cls.lib.template_bytes();cls.entry=cls.lib.entry_bytes()
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_original_and_new_regions_accepted(self):
  for region in [0,12288]:
   for offset in [0,4096-self.size]:
    with self.subTest(region=region,offset=offset):self.assertEqual(self.lib.validate_at(self.base+region+offset,0,0),0)
 def test_template_and_entries_can_use_either_region(self):
  for obj in [self.base,self.base+12288]:
   for entries in [self.base+1024,self.base+12288+1024]:self.assertEqual(self.lib.validate_at(obj,entries,2),0)
 def test_template_gap_cross_end_null_and_wrap_fail(self):
  for address in [0,self.base-1,self.base+4096,self.base+8192,self.base+16384,self.base+4096-self.size+8,self.base+16384-self.size+8,(1<<64)-8]:
   with self.subTest(address=address):self.assertEqual(self.lib.validate_at(address,0,0),1)
 def test_entries_cross_end_gap_null_and_wrap_fail(self):
  for entries,count in [(0,1),(self.base+4096-self.entry,2),(self.base+8192,1),(self.base+16384-self.entry,2),((1<<64)-8,2)]:
   with self.subTest(entries=entries,count=count):self.assertEqual(self.lib.validate_at(self.base,entries,count),2)
 def test_zero_entries_preserves_original_semantics(self):self.assertEqual(self.lib.validate_at(self.base,(1<<64)-1,0),0)
 def test_span_multiply_add_wrap_and_zero_width_fail(self):
  for p,n,w in [(self.base,1<<63,2),(self.base,1,1<<63),((1<<64)-8,2,16),(self.base,0,1),(self.base,1,0)]:
   with self.subTest(p=p,n=n,w=w):self.assertEqual(self.lib.span(p,n,w),0)
 def test_exhaustive_boundary_matrix(self):
  checked=0
  for p in [self.base+i for i in range(-16,16401,8)]:
   for n in [0,1,2,31,4096,(1<<64)-1]:
    for w in [0,1,8,120,1<<63]:
     size=n*w;expected=n>0 and w>0 and size<(1<<64) and any(start<=p<end and size<=end-p for start,end in [(self.base,self.base+4096),(self.base+12288,self.base+16384)])
     self.assertEqual(bool(self.lib.span(p,n,w)),expected,(p,n,w));checked+=1
  self.assertEqual(checked,61590)
 def test_flag_off_remains_upstream_data_const_only(self):
  lib=self.libs[False];b=lib.base_addr();self.assertEqual(lib.validate_at(b,0,0),0);self.assertEqual(lib.validate_at(b+12288,0,0),1)
  # Compare actual preprocessor output, not just a substring assertion.
  files=[]
  for name,block in [('old',pc.LEDGER_OLD),('new',self.block)]:
   p=self.path/(name+'-off.c');p.write_text(HOST+block+SUFFIX);files.append(subprocess.check_output(['clang','-E','-P',str(p)]))
  self.assertEqual(files[0],files[1])
 def test_arm64e_object_has_both_real_segment_bounds_and_assertion(self):
  p=self.path/'arm.c';obj=self.path/'arm.o';p.write_text(ARM+self.block+'\nvoid check(ledger_template_t t){lt_require_data_const(t);}\n')
  subprocess.run(['clang','--target=arm64e-apple-darwin','-ffreestanding','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-DUNIXNU_SHENNONG_PORT_CONST=1','-c',str(p),'-o',str(obj)],check=True)
  symbols=subprocess.check_output(['llvm-nm','-u',str(obj)],text=True)
  for name in ['segment$start$__DATA_CONST','segment$end$__DATA_CONST','segment$start$__PORT_CONST','segment$end$__PORT_CONST','_fixture_assert_failed']:self.assertIn(name,symbols)
  cpu,subtype=struct.unpack_from('<II',obj.read_bytes(),4)
  self.assertEqual(cpu,0x0100000c);self.assertEqual(subtype&0x00ffffff,2)
if __name__=='__main__':unittest.main(verbosity=2)
