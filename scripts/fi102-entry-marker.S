// SPDX-License-Identifier: BSD-2-Clause-Patent
// Prepend this to the existing fi102 stage-1 probe. Only the paired yellow
// DarwinEnter loader leaves x11 at the end of its first framebuffer band.
// Paint the last 192 KiB of that same band red; do not read x0 (boot_args).
// The original probe reloads x1, x2 and x3 before using them.
.text
.global fi102_entry_marker
fi102_entry_marker:
  cbz x11, 2f
  sub x1, x11, #0x30, lsl #12
  mov w2, #0x30000
  mov w3, #0xffff0000   // BGRA red.
1:
  stp w3, w3, [x1], #8
  subs w2, w2, #8
  b.hi 1b
  dsb sy
2:                      // Fall through to fi102's original blue probe.
