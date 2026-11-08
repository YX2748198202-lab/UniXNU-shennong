/* Freestanding EL1 fault dumper: paint ESR_EL1, FAR_EL1, ELR_EL1 and SPSR_EL1 as
 * hex on the physical frame buffer, then return to the caller. It is entered from
 * _sleh_synchronous, i.e. while the loader's page tables are still active, so the
 * splash frame buffer at its physical address is writable. */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

#define FB_BASE 0xFC400000UL   /* splash_region of the board ADT */
#define FB_ROW  5760u          /* 1440 px * 4 B */
#define SCALE   6

static const u8 font[16][7] = {
  {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E}, /* 0 */
  {0x04,0x0C,0x04,0x04,0x04,0x04,0x0E}, /* 1 */
  {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F}, /* 2 */
  {0x1F,0x02,0x04,0x02,0x01,0x11,0x0E}, /* 3 */
  {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02}, /* 4 */
  {0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E}, /* 5 */
  {0x06,0x08,0x10,0x1E,0x11,0x11,0x0E}, /* 6 */
  {0x1F,0x01,0x02,0x04,0x08,0x08,0x08}, /* 7 */
  {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E}, /* 8 */
  {0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C}, /* 9 */
  {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11}, /* A */
  {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E}, /* B */
  {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E}, /* C */
  {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E}, /* D */
  {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F}, /* E */
  {0x1F,0x10,0x10,0x1E,0x10,0x10,0x10}, /* F */
};

static inline void pix(u64 x, u64 y, u32 c)
{
  volatile u32 *p = (volatile u32 *)(FB_BASE + y * FB_ROW + x * 4);
  *p = c;
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
}
