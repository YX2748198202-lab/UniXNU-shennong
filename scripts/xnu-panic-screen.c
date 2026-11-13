/* Draw a kernel panic message, with its arguments, on the frame buffer, then stop.
 *
 * Built freestanding by patch-xnu-entry-probe.py and placed in unused padding
 * of a COPY of the kernel; panic() and its common panic funnel are redirected
 * here. It runs on the kernel's
 * own mapping of the frame buffer. With the board observer it uses the retained
 * GOP mapping prefix; otherwise it uses vinfo.v_baseaddr.
 *
 * panic(fmt, ...) is variadic and the Darwin arm64 ABI passes every variadic
 * argument in an 8-byte stack slot, starting at the stack pointer on entry.
 * A small printf walks the format string over those slots (%s %x %p, with
 * 0-flag, width, precision and l/ll/z). Kernel strings are checked with an
 * active hardware translation query before reading each byte;
 * unmapped/device/user pointers print as pointers. VINFO names that mapping prefix.
 */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

struct vc_info {
  u32 v_height, v_width, v_depth, v_rowbytes;
  u64 v_baseaddr;
};

#define SCALE   3

extern const u64 gFont[];

/* The kernel's own physical-to-physmap translation (osfmk/arm/pmap). DarwinBoot hands over
 * Video.v_baseaddr as a PHYSICAL address (0xFC400000 on this board); writing that value as a
 * virtual address faults, and the fault re-enters panic(), which draws again - a silent loop. */
#ifndef PHYS_BASE
#define PHYS_BASE 0UL
#endif
#ifndef VIRT_BASE
#define VIRT_BASE 0UL
#endif

/* All state lives on the stack: this code sits in the kernel's read-only text,
 * so a writable global would fault on its first store. */
struct ctx {
  u8  *base;
  u32 rb, w, h, x, y;
  u8  *log;   /* kernel buffer that also receives the formatted message (PANIC_TEXT), 0 = none */
  u32 logn;
};

#ifndef PANIC_TEXT
#define PANIC_TEXT 0UL
#endif
#define PANIC_TEXT_BYTES 2048
/* Stage 2 leaves the bootstrap pool's page 15 physical address in the last 8 bytes of PANIC_TEXT,
 * so the panic side can use that page as a fresh L2 table without guessing where it is. */
#define STASH_POOL  (PANIC_TEXT + 0xff8UL)
/* Set once the TTBR1 mapping exists, so later beacons never touch the pool page again: by then the
 * kernel may have handed that physical page out, and zeroing it would corrupt live data. */
#define STASH_FLAG  (PANIC_TEXT + 0xff0UL)
/* Stage 2 fills PANIC_TEXT before the MMU comes on, so these are valid from _arm_init onwards,
 * i.e. earlier than PE_state.video.  Layout: 0x00 v_baseAddr, 0x10 v_rowBytes, 0x18 v_width,
 * 0x20 v_height, 0x28 v_depth, 0x30 VirtualBase, 0x38 PhysicalBase. */
#define STASH_VIRT  (PANIC_TEXT + 0x30UL)
#define STASH_PHYS  (PANIC_TEXT + 0x38UL)
#define FB_MAGIC    0x4b41504d4f4f5246UL        /* "FROOMPAK" backwards, only for uniqueness */
/* v_baseaddr is the frame buffer's PHYSICAL address. The trampoline builds a V=P table and
 * installs it as TTBR0, so a physical address is directly addressable from the kernel - this is
 * exactly what upstream's panic screen relies on when it says it "uses vinfo.v_baseaddr". No
 * mapping of our own is needed or wanted. */
#define FB_KVA      0xFC400000UL
#define FB_BLOCKS   64   /* boot_progress_panic_text: a data abort's message with every register, then the frames */

/* Stop, but hand the device back: after `seconds` of parking, PSCI SYSTEM_RESET reboots the
 * phone, so it returns to the bootloader by itself instead of needing a 10 s power hold. */
__attribute__((noreturn)) static void park_for (unsigned long long seconds)
{
  unsigned long long start, now;
  __asm__ volatile ("mrs %0, cntpct_el0" : "=r"(start));
  for (;;) {
    __asm__ volatile ("mrs %0, cntpct_el0" : "=r"(now));
    if (now - start > 19200000ULL * seconds) {
      register unsigned long x0 __asm__("x0") = 0x84000009UL;
      register unsigned long x1 __asm__("x1") = 0;
      register unsigned long x2 __asm__("x2") = 0;
      register unsigned long x3 __asm__("x3") = 0;
      __asm__ volatile ("smc #0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3) : "memory");
    }
    __asm__ volatile ("wfe");
  }
}

/* 8 s means "no usable frame buffer": the renderer refused before drawing. 20 s means it drew
 * (or tried to) with a frame buffer, so one boot with a stopwatch already says which it was. */
#define PARK_RESET       20
#define PARK_RESET_SHORT  8

__attribute__((noreturn)) static void park (void)       { park_for (PARK_RESET); }
__attribute__((noreturn)) static void park_short (void) { park_for (PARK_RESET_SHORT); }
/* park_for() is declared before its uses below, so the geometry paths can name the delay. */


static u64 read_ttbr1 (void)
{
  u64 v;
  __asm__ volatile ("mrs %0, ttbr1_el1" : "=r"(v));
  return v;
}

static void flush_tlb (void)
{
  __asm__ volatile ("dsb ish\n\t tlbi vmalle1\n\t dsb ish\n\t isb" ::: "memory");
}

/* Resolve the frame buffer and install TTBR1 L1[1] -> FB_KVA. Returns 1 when g.base is usable. */
/* fatal != 0 parks with a timer code when the mapping cannot be built; a beacon passes 0 and simply
 * draws nothing, because sites before PE_init_platform have no geometry yet. */
static int fb_setup (struct ctx *g, int fatal, unsigned long ba_hint)
{
  u64 base, rb, width, height, depth;

  (void)fatal;
  (void)ba_hint;
  if (g->base != 0) {
    return 1;
  }
  /* Read the kernel's own vinfo structure, exactly as the version that was verified on this
   * device (fi58) did. The frame buffer geometry and, crucially, v_baseaddr live there:
   *
   *   0xFFFFFFF00B782350  v_height
   *   0xFFFFFFF00B782354  v_width
   *   0xFFFFFFF00B782358  v_depth
   *   0xFFFFFFF00B78235C  v_rowBytes
   *   0xFFFFFFF00B782360  v_baseaddr
   *
   * v_baseaddr is a VIRTUAL address the kernel has already mapped. boot_args->Video, which the
   * stash records, holds the PHYSICAL address (0xFC400000 on this board) - using that as a
   * pointer writes into unmapped space and silently vanishes. That mistake cost fi70..fi75. */
#define VINFO_H    0xFFFFFFF00B782350UL
  height = *(volatile const u32 *)VINFO_H;
  width  = *(volatile const u32 *)(VINFO_H + 4);
  depth  = *(volatile const u32 *)(VINFO_H + 8);
  rb     = *(volatile const u32 *)(VINFO_H + 12);
  base   = *(volatile const u64 *)(VINFO_H + 16);

  if (base == 0 || depth != 32 || rb == 0 || width == 0 || height == 0) {
    return 0;
  }
  g->base = (u8 *)base;
  g->rb = (u32)rb;
  g->w  = (u32)width;
  g->h  = (u32)height;
  return 1;
}

/* The frame buffer sits inside DRAM, so the kernel's TTBR0 maps it Normal cacheable: every store
 * lands in the cache and the display controller never sees it. Cleaning the drawn span back to
 * memory is what makes the text appear (the firmware could draw because it cleaned on exit, and
 * the old TTBR1 Device mapping needed no cleaning at all). */
static void clean_to_memory (struct ctx *g, u32 first_row, u32 rows)
{
  u64 a = (u64)(g->base + (u64)first_row * g->rb);
  u64 end = a + (u64)rows * g->rb;
  a &= ~63UL;
  for (; a < end; a += 64) {
    __asm__ volatile ("dc civac, %0" :: "r"(a) : "memory");
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}

static void put (struct ctx *g, u8 c)
{
  const u32 cell = 6 * SCALE, line = 14 * SCALE;
  u32 row, col, dy, dx;

  if (g->log && g->logn < PANIC_TEXT_BYTES - 1 && c >= 9 && c <= 126) {
    g->log[g->logn++] = (c < 32) ? ' ' : c;
    g->log[g->logn] = 0;
  }

  if (c == '\n') {
    g->x = 0;
    g->y += line;
    return;
  }
  if (c == '\t') {
    g->x += 4 * cell;
    return;
  }
  if (c < 32 || c > 126) {
    return;
  }
  if (g->x + cell > g->w) {
    g->x = 0;
    g->y += line;
  }
  if (g->y + line > g->h) {
    return;
  }
  u64 glyph = gFont[c - 32];
  u32 top = (u32)(glyph >> 32), bottom = (u32)glyph;
  for (row = 0; row < 12; row++) {
    u32 data = (row < 6) ? (top >> (row * 5)) : (bottom >> ((row - 6) * 5));
    for (col = 0; col < 5; col++) {
      if ((data >> col) & 1) {
        for (dy = 0; dy < SCALE; dy++) {
          for (dx = 0; dx < SCALE; dx++) {
            *(volatile u32 *)(g->base + (u64)(g->y + row * SCALE + dy) * g->rb + (u64)(g->x + col * SCALE + dx) * 4) = 0xFFFFFFFFu;
          }
        }
      }
    }
  }
  g->x += cell;
}

static void number (struct ctx *g, u64 value, u32 base, u32 width, int zero)
{
  u8  digits[24];
  u32 n = 0, i;

  do {
    u32 d = (u32)(value % base);
    digits[n++] = (u8)(d < 10 ? '0' + d : 'a' + d - 10);
    value /= base;
  } while (value && n < 24);
  for (i = n; i < width; i++) {
    put (g, zero ? '0' : ' ');
  }
  while (n) {
    put (g, digits[--n]);
  }
}

/* Probe each string byte before dereferencing it. Heap strings (process name
 * and exit reason) live outside the linked image. AT performs a hardware
 * translation query only: no table edits, mappings, or exception bypass.
 * Refuse user pointers, translation faults and device-memory attributes. */
static int readable (const char *s, const u64 *args)
{
  u64 a = (u64)s, par;
  (void)args;
  if (a < 0xffff000000000000UL) return 0;
  __asm__ volatile ("at s1e1r, %1; isb; mrs %0, par_el1" : "=r" (par) : "r" (a) : "memory");
  return !(par & 1) && ((par >> 60) != 0);
}

static void format (struct ctx *g, const char *fmt, const u64 *args)
{
  u32 i, used = 0;

  for (i = 0; i < 2000 && fmt[i]; i++) {
    u8 c = (u8)fmt[i];
    if (c != '%') {
      put (g, c);
      continue;
    }
    u32 width = 0;
    int zero = 0, longs = 0;
    c = (u8)fmt[++i];
    if (c == '0') {
      zero = 1;
      c = (u8)fmt[++i];
    }
    while (c >= '0' && c <= '9') {
      width = width * 10 + (c - '0');
      c = (u8)fmt[++i];
    }
    u32 precision = 4000;
    if (c == '.') {
      precision = 0;
      c = (u8)fmt[++i];
      if (c == '*') {
        precision = (u32)args[used++];
        c = (u8)fmt[++i];
      } else {
        while (c >= '0' && c <= '9') {
          if (precision < 4000) precision = precision * 10 + (c - '0');
          c = (u8)fmt[++i];
        }
      }
      if (precision > 4000) precision = 4000;
    }
    if (width > 256) width = 256;
    while (c == 'l' || c == 'z' || c == 'h') {
      longs += (c != 'h');
      c = (u8)fmt[++i];
    }
    if (c == '%') {
      put (g, '%');
      continue;
    }
    if (c == 0) {
      break;
    }
    u64 v = args[used++];
    if (c == 's') {
      const char *s = (const char *)v;
      u32 k;
      for (k = 0; k < precision; k++) {
        if (!readable (s + k, args)) {
          put (g, '<');
          number (g, (u64)(s + k), 16, 0, 0);
          put (g, '>');
          break;
        }
        u8 ch = (u8)s[k];
        if (!ch) break;
        put (g, ch);
      }
    } else if (c == 'x' || c == 'X') {
      number (g, longs ? v : (v & 0xFFFFFFFFu), 16, width, zero);
    } else if (c == 'u' || c == 'd') {
      number (g, longs ? v : (v & 0xFFFFFFFFu), 10, width, zero);
    } else if (c == 'p') {
      put (g, '0');
      put (g, 'x');
      number (g, v, 16, width, zero);
    }
  }
}

static void text (struct ctx *g, const char *s)
{
  while (*s) {
    put (g, (u8)*s++);
  }
}

static void hex (struct ctx *g, const char *label, u64 v)
{
  text (g, label);
  put (g, '0');
  put (g, 'x');
  number (g, v, 16, 16, 1);
}

/* x0 = fmt as for panic(); x1 is set by the stub to the entry stack pointer. */
__attribute__((noreturn, used, section(".text.b_main"))) void panic_screen_main (const char *fmt, const u64 *args)
{
  volatile struct vc_info *v = (volatile struct vc_info *)VINFO;
  struct ctx g;
  u32 row, col;

  __asm__ volatile ("msr daifset, #15");
  /* Record the panic in the same slot the beacons use, before touching the frame buffer. This is
   * the only way a panic becomes visible at all on this board: the kernel cannot write the frame
   * buffer (fi70/fi71), so the next boot's trampoline reads this word and paints it as bands.
   * 0xff sets every band, which is distinguishable from any beacon tag. */
  {
    volatile u64 *slot = (volatile u64 *)(PANIC_TEXT + 0x800UL);
    u64 a = (u64)slot & ~63UL;
#define PANIC_TAG 0xFFUL
    *slot = PANIC_TAG;
    __asm__ volatile ("dc civac, %0" :: "r"(a) : "memory");
    __asm__ volatile ("dsb sy" ::: "memory");
  }
  g.base = (u8 *)v->v_baseaddr;
  g.rb   = v->v_rowbytes;
  g.w    = v->v_width;
  g.h    = v->v_height;
  (void)fb_setup (&g, 1, 0);

#ifdef PANIC_DRY_RUN
  /* Diagnostic split for the frame buffer question: resolve the geometry exactly as the normal
   * path does, then stop without writing a single byte to video memory. 20 s here means the
   * mapping and the geometry are fine and only the writes are a problem; no reset means the
   * trampoline patch itself (scripts/patch-fb-map.py) breaks the boot. */
  park_for (20);
#endif

  if (fmt == 0) {
    park ();
  }

  /* First panic wins: a marker in the last row's first two pixels means a panic already drew
   * the screen; a later panic (another thread or exception) must not overwrite it. */
  volatile u32 *mark = (volatile u32 *)(g.base + (u64)(g.h - 1) * g.rb);
  if (mark[0] == 0xC0FFEE11u && mark[1] == 0x5CEEDA7Au) {
    park ();
  }
  g.x = 0;
  g.y = g.h / 8;
  g.log = 0;
  g.logn = 0;
  for (row = g.y; row < g.h; row++) {
    for (col = 0; col < g.w; col++) {
      *(volatile u32 *)(g.base + (u64)row * g.rb + (u64)col * 4) = 0;
    }
  }
  g.y += 8;
  /* The board's live banner keeps showing this text after the next swap paints over the screen (BootProgress.c,
   * boot_progress_panic_text). The first panic's text is kept: a buffer that already holds one is left alone. */
  if (PANIC_TEXT && *(volatile u8 *)PANIC_TEXT == 0) {
    g.log = (u8 *)PANIC_TEXT;
  }
  format (&g, fmt, args);
  /* The return addresses up the frame pointer chain: the exception entry links the panic's frames to the code that faulted, so this
   * names the callers the message leaves out. Stops at a pointer outside the kernel's range, a misaligned one or one that does not
   * move up the stack. */
  {
    const u64 *fp = (const u64 *)__builtin_frame_address (0);
    text (&g, "\nframes");
    for (unsigned i = 0; i < 24; i++) {
      const u64 at = (u64)fp;
      if (at < 0xfffffff000000000UL || (at & 15)) break;
      const u64 next = fp[0], lr = fp[1] & 0x0000007fffffffffUL;   /* the return address without its pointer authentication bits */
      put (&g, ' ');
      number (&g, lr | 0xffffff8000000000UL, 16, 16, 1);
      if (next <= at) break;
      fp = (const u64 *)next;
    }
  }
  g.log = 0;
  __asm__ volatile ("dsb sy");
  /* Resolved from this candidate's symbols by the patcher, never fixed addresses.
   * Values are sampled at panic time and need not form an atomic VM snapshot. */
  (void)MAX_MEM;
  hex (&g, "\npages=", *(volatile const u32 *)PAGE_TOTAL);
  hex (&g, "\nfree=", *(volatile const u32 *)PAGE_FREE);
  /* The raw argument slots are not dumped: the formatted message above already carries them (room for the PANIC_TEXT copy). */
  mark[0] = 0xC0FFEE11u;
  mark[1] = 0x5CEEDA7Au;
  __asm__ volatile ("dsb sy");
  clean_to_memory (&g, 0, g.h);   /* the whole span we touched: clear, message, frames, pages */
  park ();
}

/* Entry from panic(): keep the stack pointer, which addresses the variadic arguments. */
__attribute__((naked, noreturn, section(".text.a_entry"))) void panic_screen (const char *fmt)
{
  __asm__ volatile ("mov x1, sp\n\tb panic_screen_main");
}

/* The real panic_trap_to_debugger signature takes (fmt, va_list *, ...).
 * Darwin ARM64 va_list is a stack pointer; its address is passed in x1.
 * The wrapper has already established its frame, so SP is NOT the argument
 * list here. Follow exactly the one pointer supplied by the real wrapper.
 */
__attribute__((naked, noreturn, section(".text.a_common"))) void panic_screen_common (void)
{
  __asm__ volatile ("ldr x1, [x1]\n\tb panic_screen_main");
}

#include "Font.h"
__attribute__((section(".text.z_font"))) const u64 gFont[] = GLYPH_FONT;

/* The kernel cannot write the frame buffer: 0xFC400000 is inside DRAM, so the mapping exists and
 * the store does not fault, but the write is dropped (the display aperture is protected on this
 * SoC - the firmware and the pre-MMU trampoline can write it, an EL1 kernel cannot).
 * So a checkpoint writes its tag into kernel BSS instead, and the trampoline reads it back on the
 * next boot and paints it as bands, an operation already proven by the green and blue bars. */
/* The kernel cannot write the frame buffer: 0xFC400000 lies inside DRAM, so the mapping exists and
 * the store does not fault, but the write is dropped - the display aperture is protected on this
 * SoC. The firmware and the pre-MMU trampoline can write it (that is where the green and blue bars
 * come from); an EL1 kernel cannot. So a checkpoint records its tag in kernel BSS, and the
 * trampoline reads it back on the next boot and paints it as bands (scripts/patch-slot-bands.py).
 * PANIC_TEXT is ordinary kernel .data, so this store needs no mapping and cannot fault. */
void fb_beacon (unsigned long tag, unsigned long unused)
{
  volatile u64 *slot = (volatile u64 *)(PANIC_TEXT + 0x800UL);
  u64 a = (u64)slot & ~63UL;
  (void)unused;
  *slot = tag & 0x1ffUL;          /* keep bit 8: it marks a diagnostic site */
  __asm__ volatile ("dc civac, %0" :: "r"(a) : "memory");
  __asm__ volatile ("dsb sy" ::: "memory");
}

