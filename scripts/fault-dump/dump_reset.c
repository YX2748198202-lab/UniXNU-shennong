/* Like dump.c, but the image recovers on its own: after painting the EL1 fault
 * registers it waits PHOTO_SECONDS so the screen can be photographed, then asks
 * PSCI for SYSTEM_RESET. A fault therefore never leaves the phone hung.
 *
 * Two guards keep this from fighting the rest of the kernel:
 *  - a fault taken inside this cave (the frame buffer not being mapped any more)
 *    skips painting and resets immediately, so it cannot recurse;
 *  - a fault taken from EL0 is not ours at all, so it returns to the kernel. */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

#ifndef CAVE_LO
#define CAVE_LO 0xFFFFFFF00B4FA400UL
#endif
#ifndef CAVE_HI
#define CAVE_HI 0xFFFFFFF00B4FA700UL
#endif
#ifndef PHOTO_SECONDS
#define PHOTO_SECONDS 45
#endif

#define FB_BASE 0xFC400000UL
#define FB_ROW  5760u
#define SCALE   6

static const u8 font[16][7] = {
  {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E}, {0x04,0x0C,0x04,0x04,0x04,0x04,0x0E},
  {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F}, {0x1F,0x02,0x04,0x02,0x01,0x11,0x0E},
  {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02}, {0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E},
  {0x06,0x08,0x10,0x1E,0x11,0x11,0x0E}, {0x1F,0x01,0x02,0x04,0x08,0x08,0x08},
  {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E}, {0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C},
  {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11}, {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E},
  {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E}, {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E},
  {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F}, {0x1F,0x10,0x10,0x1E,0x10,0x10,0x10},
};

static inline void pix(u64 x, u64 y, u32 c)
{
  volatile u32 *p = (volatile u32 *)(FB_BASE + y * FB_ROW + x * 4);
  *p = c;
}

static void arm_reset(void)
{
  __asm__ volatile(
    "movz w0, #0x0009\n\t"
    "movk w0, #0x8400, lsl #16\n\t"
    "mov x1, xzr\n\t"
    "mov x2, xzr\n\t"
    "mov x3, xzr\n\t"
    "smc #0\n");
  for (;;)
    __asm__ volatile("wfe");
}

static void wait_seconds(u64 seconds)
{
  u64 freq, start, now, span;
  __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(freq));
  if (freq == 0 || freq > 100000000UL)
    freq = 19200000UL;               /* the board's timebase-frequency */
  __asm__ volatile("mrs %0, cntpct_el0" : "=r"(start));
  span = freq * seconds;
  do {
    __asm__ volatile("isb\n\tmrs %0, cntpct_el0" : "=r"(now));
  } while (now - start < span);
}

void fault_dump(void)
{
  u64 esr, far, elr, spsr, y, x;
  u32 l, i, r, c, sy, sx, d;
  u8 bits;
  u64 vals[4];
  const u32 colours[4] = { 0xFFFFFFFFu, 0xFFFF4040u, 0xFF40FF40u, 0xFF4090FFu };

  __asm__ volatile("mrs %0, esr_el1" : "=r"(esr));
  __asm__ volatile("mrs %0, far_el1" : "=r"(far));
  __asm__ volatile("mrs %0, elr_el1" : "=r"(elr));
  __asm__ volatile("mrs %0, spsr_el1" : "=r"(spsr));

  if (elr >= CAVE_LO && elr < CAVE_HI)     /* faulted inside this cave */
    arm_reset();
  if ((spsr & 0xFUL) == 0)                  /* fault came from EL0 */
    return;

  vals[0] = esr; vals[1] = far; vals[2] = elr; vals[3] = spsr;

  for (y = 30; y < 570; y++)
    for (x = 8; x < 1432; x++)
      pix(x, y, 0);

  for (l = 0; l < 4; l++) {
    u64 y0 = 50 + (u64)l * 130;
    for (i = 0; i < 16; i++) {
      d = (u32)((vals[l] >> ((15 - i) * 4)) & 0xF);
      u64 x0 = 24 + (u64)i * 86;
      for (r = 0; r < 7; r++) {
        bits = font[d][r];
        for (c = 0; c < 5; c++)
          if (bits & (0x10u >> c))
            for (sy = 0; sy < SCALE; sy++)
              for (sx = 0; sx < SCALE; sx++)
                pix(x0 + c * SCALE + sx, y0 + r * SCALE + sy, colours[l]);
      }
    }
  }

  wait_seconds(PHOTO_SECONDS);
  arm_reset();
}
