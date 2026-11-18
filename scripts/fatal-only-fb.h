/* Fatal-only framebuffer view. No mapping changes during normal kernel flow.
 * FB_ROOT_VA names a read-only, offline-built 4 KiB L1 table in reserved
 * PORT_CONST padding. Only its 3..4 GiB Device/RW/NX block is populated.
 * Source ABI: pinned pexpert.h PE_state.video starts at +8; first five u64s
 * are base, stride, width, height, depth. Existing usable mappings win.
 */
static u64 fatal_par(u64 va, int write)
{
  u64 par;
  if (write) __asm__ volatile("at s1e1w, %0" :: "r"(va) : "memory");
  else __asm__ volatile("at s1e1r, %0" :: "r"(va) : "memory");
  __asm__ volatile("isb\n\tmrs %0, par_el1" : "=r"(par) :: "memory");
  return par;
}
static int fatal_readable(u64 va, u64 bytes)
{
  return va + bytes >= va && !(fatal_par(va, 0) & 1) &&
         !(fatal_par(va + bytes - 1, 0) & 1);
}
static int fb_setup(struct ctx *g, int fatal, unsigned long hint)
{
  (void)fatal; (void)hint;
  const volatile u64 *video = (const volatile u64 *)(PE_STATE + 8UL);
  if (!fatal_readable((u64)video, 40)) return 0;
  u64 base=video[0]&~3UL, rb=video[1], width=video[2], height=video[3], depth=video[4];
  if (!base || depth!=32 || !width || width>4096 || !height || height>8192 ||
      rb<width*4 || rb>65536 || base+rb*height<base) return 0;
  if ((fatal_par(base,1)&1) || (fatal_par(base+rb*height-1,1)&1)) {
    /* The only fallback is the observed board framebuffer's physical block. */
    if ((base>>30)!=3 || ((base+rb*height-1)>>30)!=3) return 0;
    u64 mair, tcr;
    __asm__ volatile("mrs %0, mair_el1\n\tmrs %1, tcr_el1" : "=r"(mair),"=r"(tcr));
    u64 attr=(mair>>24)&255;
    if (attr & ~0x0dUL) return 0; /* Device only, including the FEAT_XS encodings. */
    u64 par=fatal_par(FB_ROOT_VA,0);
    if (par&1) return 0;
    u64 pa=par&0x0000fffffffff000UL;
    /* TTBR0 alone: 39-bit/4 KiB/L1 root, normal WB table walks, enabled.
     * Preserve TTBR1, IPS, MAIR, PAC controls and all kernel mappings. */
    tcr=(tcr&~0xffffUL)|25UL|(1UL<<8)|(1UL<<10)|(3UL<<12);
    __asm__ volatile("dsb ish\n\tmsr ttbr0_el1, %0\n\tmsr tcr_el1, %1\n\tisb\n\ttlbi vmalle1is\n\tdsb ish\n\tisb"
                     :: "r"(pa),"r"(tcr) : "memory");
    if ((fatal_par(base,1)&1) || (fatal_par(base+rb*height-1,1)&1)) return 0;
  }
  g->base=(u8 *)base; g->rb=(u32)rb; g->w=(u32)width; g->h=(u32)height;
  return 1;
}
