/* All entry points are terminal: no normal-path probe or recovery bypass. */
.section .fatal_entries,"ax",@progbits
.balign 4
.global fatal_panic, fatal_common, fatal_state_entry, fatal_spill
fatal_panic:
  mov x1, sp
  mov x2, #1
  b fatal_capture
fatal_common:
  mov x2, #2
  b fatal_capture
fatal_state_entry:
  mov x2, #3
  b fatal_capture
fatal_spill:
  mov x2, #4
  b fatal_capture
/* Low-vector slots were all B self. x20 holds physical boot_args on this path. */
.macro LOW_SLOT n
.global fatal_low_\n
fatal_low_\n:
  mov x0, x20
  mov x2, #(16+\n)
  b fatal_capture
.endm
LOW_SLOT 0
LOW_SLOT 1
LOW_SLOT 2
LOW_SLOT 3
LOW_SLOT 4
LOW_SLOT 5
LOW_SLOT 6
LOW_SLOT 7
LOW_SLOT 8
LOW_SLOT 9
LOW_SLOT 10
LOW_SLOT 11
LOW_SLOT 12
LOW_SLOT 13
LOW_SLOT 14
LOW_SLOT 15

fatal_capture:
  msr daifset, #15
  /* Capture exception registers before any data access; never use incoming SP. */
  mov x10, sp
  mov x11, x30
  mrs x12, esr_el1
  mrs x13, far_el1
  mrs x14, elr_el1
  mrs x15, spsr_el1
  /* Low slots 0..3 and 8..15 interrupted SP_EL0; SP_EL1 is the vector stack. */
  cmp x2, #16
  b.lo .Lhave_sp
  cmp x2, #20
  b.lo .Lsp0
  cmp x2, #24
  b.lo .Lhave_sp
.Lsp0:
  mrs x10, sp_el0
.Lhave_sp:
  adrp x16, FATAL_RECORD
  add x16, x16, :lo12:FATAL_RECORD
  adrp x17, FATAL_CLAIM
  add x17, x17, :lo12:FATAL_CLAIM
  mrs x3, sctlr_el1
  tbz x3, #0, .Lphysical_claim
.Lclaim:
  ldaxrb w18, [x17]
  cbnz w18, .Lnested
  mov w4, #1
  stxrb w5, w4, [x17]
  cbnz w5, .Lclaim
  b .Lclaimed
.Lphysical_claim:
  /* Cold CPU only; don't issue exclusives to MMU-off device-typed memory. */
  ldrb w18, [x17]
  cbnz w18, .Lnested
  mov w4, #1
  strb w4, [x17]
.Lclaimed:
  stp x0, x1, [x16]
  stp x10, x11, [x16, #16]
  stp x12, x13, [x16, #32]
  stp x14, x15, [x16, #48]
  stp x2, x3, [x16, #64]
  mrs x3, tcr_el1
  mrs x4, ttbr0_el1
  stp x3, x4, [x16, #80]
  mrs x3, ttbr1_el1
  mrs x4, mair_el1
  stp x3, x4, [x16, #96]
  mrs x3, vbar_el1
  mrs x4, CurrentEL
  stp x3, x4, [x16, #112]
  mov x3, #1
  stp x3, xzr, [x16, #128]
  dsb sy
  adrp x3, FATAL_STACK_TOP
  add x3, x3, :lo12:FATAL_STACK_TOP
  mov sp, x3
  mov x0, x16
  b fatal_main
.Lnested:
  /* Preserve the first record and stack. Record second exception, then park. */
  mov x3, #1
  str x3, [x16, #136]
  stp x12, x13, [x16, #144]
  stp x14, x15, [x16, #160]
  dsb sy
.Lpark:
  wfe
  b .Lpark
