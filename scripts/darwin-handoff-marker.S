// SPDX-License-Identifier: BSD-2-Clause-Patent
// fi102 diagnostic replacement for the 0x94-byte DarwinEnter from DarwinBoot
// 3c75734014cdab0acd9541e88057b7606ee7ae08. Keep both the cache sequence
// and the MMU-off/tail-branch sequence byte-for-byte unchanged.
.text
.global DarwinEnter
DarwinEnter:
  msr daifset, #15
  mov x11, x4                   // Save framebuffer address before x4 becomes cache cursor.
  lsr x9, x5, #4                // Same band height as the original green marker.
  bic x9, x9, #7

  add x5, x2, x3
  mrs x6, ctr_el0
  ubfx x6, x6, #16, #4
  mov x7, #4
  lsl x6, x7, x6
  sub x7, x6, #1
  bic x4, x2, x7
  dsb sy
1:
  dc civac, x4
  add x4, x4, x6
  cmp x4, x5
  b.lo 1b
  dsb sy
  ic iallu
  dsb sy
  isb

  // Prove the cache loop and barriers finished, while the framebuffer is
  // still addressable as before. The original marker was before the loop.
  cbz x11, 3f
  mov w10, #0xff00
  movk w10, #0xffff, lsl #16     // BGRA yellow (0xffffff00).
2:
  stp w10, w10, [x11], #8
  subs x9, x9, #8
  b.hi 2b
  dsb sy
3:
  mrs x4, sctlr_el1
  bic x4, x4, #1
  bic x4, x4, #4
  bic x4, x4, #0x1000
  msr sctlr_el1, x4
  isb
  tlbi vmalle1
  dsb sy
  isb
  br x1
