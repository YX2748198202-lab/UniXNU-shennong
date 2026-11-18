/* Pure layout/geometry primitives shared by the fatal renderer and host fixtures. */
#ifndef UNIXNU_FATAL_RECORD_H
#define UNIXNU_FATAL_RECORD_H
#include <stdint.h>
#include <stddef.h>
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;
struct fatal_record {
  u64 arg0, arg1, sp, lr, esr, far, elr, spsr;
  u64 source, sctlr, tcr, ttbr0, ttbr1, mair, vbar, current_el;
  u64 status, nested, nested_esr, nested_far, nested_elr, nested_spsr;
};
_Static_assert(offsetof(struct fatal_record, source)==64,"assembly source ABI");
_Static_assert(offsetof(struct fatal_record, nested)==136,"assembly nesting ABI");
_Static_assert(sizeof(struct fatal_record)<=384,"reserved record bounds");
struct fatal_video {u64 base, rb, w, h, depth;};
struct fatal_state {u64 pc, lr, sp, esr, far; u32 cpsr;};
static int fatal_video_valid(struct fatal_video v) {
  return v.base && !(v.base&3) && v.depth==32 && v.w && v.w<=4096 &&
         v.h && v.h<=8192 && v.rb>=v.w*4 && v.rb<=65536 &&
         v.base+v.rb*v.h>=v.base;
}
static int fatal_state_decode(const void *p, size_t size, struct fatal_state *out) {
  if (!p || !out || ((uintptr_t)p&7) || size<0x128) return 0;
  const u8 *b=p;
  if (*(const u32 *)b!=0x15) return 0;
  out->lr=*(const u64 *)(b+0xf8); out->sp=*(const u64 *)(b+0x100);
  out->pc=*(const u64 *)(b+0x108); out->cpsr=*(const u32 *)(b+0x110);
  out->far=*(const u64 *)(b+0x118); out->esr=*(const u64 *)(b+0x120);
  return 1;
}
#endif
