# `_arm_init` call map (shennong payload, XNU 12377, `0xfffffff00b4768d0`)

Every `bl` between the `_arm_init` entry and its `retab`, in program order, with the
band that the matching ladder image paints immediately *before* the call runs.
Bands are numbered from 0 at the top of the screen; the loader paints green, the
kernel entry stub paints blue then magenta, so ladder bands 0-2 overwrite those.

| # | site | callee | image band |
|---|------|--------|------------|
| 1 | `0xfffffff00b476a60` | `_OSRuntimeSignStructors` | band 1 (ladder3) |
| 2 | `0xfffffff00b476f54` | `_PE_set_kc_header` | band 2 |
| 3 | `0xfffffff00b476f8c` | `_kernel_collection_adjust_mh_addrs` | band 3 |
| 4 | `0xfffffff00b476f94` | `_OSRuntimeSignStructorsInFileset` | band 4 |
| 5 | `0xfffffff00b476fa8` | `_static_if_init` | band 5 |
| 6 | `0xfffffff00b476fc0` | `_memmove` | band 6 |
| 7 | `0xfffffff00b476fd8` | `_cpu_data_init` | band 7 |
| 8 | `0xfffffff00b476fdc` | `_ml_default_rop_pid` | band 8 |
| 9 | `0xfffffff00b476fe4` | `_ml_default_jop_pid` | band 9 |
| 10 | `0xfffffff00b476ff4` | `_PE_init_platform` | band 10 |
| 11 | `0xfffffff00b476ff8` | `_boot_progress_init` | band 11 |
| 12 | `0xfffffff00b476ffc` | `_configure_timer_apple_regs` | band 12 |
| 13 | `0xfffffff00b477000` | `_wfe_timeout_configure` | band 13 |
| 14 | `0xfffffff00b477004` | `_wfe_timeout_init` | band 14 |
| 15 | `0xfffffff00b477008` | `_configure_misc_apple_boot_args` | band 15 |
| 16 | `0xfffffff00b477010` | `_configure_misc_apple_regs` | ladder2c band 0 |
| 17 | `0xfffffff00b477028` | `_SecureDTLookupEntry` | ladder2c band 1 |
| 18 | `0xfffffff00b477048` | `_SecureDTGetProperty (root)` | ladder2c band 2 |
| 19 | `0xfffffff00b477090` | `_SecureDTGetProperty (2nd)` | ladder2c band 3 |
| 20 | `0xfffffff00b4770c8` | `_check_for_failure_injection` | ladder2c band 4 |
| 21 | `0xfffffff00b4770ec` | `_ml_parse_cpu_topology` | ladder2c band 5 |
| 22 | `0xfffffff00b4770f0` | `_ml_get_boot_cpu_number` | ladder2c band 6 |
| 23 | `0xfffffff00b47718c` | `_thread_bootstrap` | ladder2c band 7 |
| 24 | `0xfffffff00b4771a0` | `_machine_set_current_thread` | ladder2c band 8 |
| 25 | `0xfffffff00b4771a8` | `_cpu_bootstrap` | ladder2c band 9 |
| 26 | `0xfffffff00b4771ac` | `_rtclock_early_init` | ladder2c band 10 |
| 27 | `0xfffffff00b4771b8` | `_kernel_debug_string_early` | ladder2c band 11 |
| 28 | `0xfffffff00b4771bc` | `_kernel_startup_bootstrap` | ladder2c band 12 |
| 29 | `0xfffffff00b4771c0` | `_timer_call_init` | ladder2c band 13 |
| 30 | `0xfffffff00b4771c4` | `_cpu_init` | ladder2c band 14 |
| 31 | `0xfffffff00b4771c8` | `_processor_bootstrap` | ladder3c band 0 |
| 32 | `0xfffffff00b4771dc` | `_PE_parse_boot_argn` | band 1 |
| 33 | `0xfffffff00b477200` | `_PE_get_default` | band 2 |
| 34 | `0xfffffff00b477228` | `_PE_parse_boot_argn` | band 3 |
| 35 | `0xfffffff00b47724c` | `_kern_feature_override` | band 4 |
| 36 | `0xfffffff00b477260` | `_kern_feature_override` | band 5 |
| 37 | `0xfffffff00b477288` | `_nanoseconds_to_absolutetime` | band 6 |
| 38 | `0xfffffff00b4772a0` | `_PE_parse_boot_argn` | band 7 |
| 39 | `0xfffffff00b4772bc` | `_SecureDTLookupEntry` | band 8 |
| 40 | `0xfffffff00b4772dc` | `_SecureDTGetProperty` | band 9 |
| 41 | `0xfffffff00b4772fc` | `_SecureDTGetProperty` | band 10 |
| 42 | `0xfffffff00b477340` | `_boot_progress_stage (pre arm_vm_init)` | band 11 |
| 43 | `0xfffffff00b477350` | `_arm_vm_init` | band 12 |
| 44 | `0xfffffff00b47735c` | `_boot_progress_stage (post arm_vm_init)` | band 13 |
| 45 | `0xfffffff00b477370` | `_patch_low_glo` | band 14 |
| 46 | `0xfffffff00b477374` | `_PE_consistent_debug_inherit` | band 15 |
| 47 | `0xfffffff00b477378` | `_serial_init` |  |
| 48 | `0xfffffff00b477384` | `_kernel_startup_initialize_upto` |  |
| 49 | `0xfffffff00b477390` | `_kprintf` |  |
| 57 | `0xfffffff00b4774a0` | `_switch_to_serial_console` |  |
| 58 | `0xfffffff00b4774b0` | `_PE_create_console` |  |
| 59 | `0xfffffff00b4774b8` | `_PE_init_printf` |  |
| 60 | `0xfffffff00b4774c0` | `_cpu_machine_idle_init` |  |
| 64 | `0xfffffff00b4774f8` | `_cpu_timebase_init` |  |
| 71 | `0xfffffff00b477530` | `_machine_startup` |  |

Ladder images built from the 2026-11-08 payload kernel:

| image | markers | sha256 (first 16) |
|-------|---------|-------------------|
| `Mu-ladder3.img` | `_arm_init` entry + calls 1-15 | `6c91093c2ef6904e` |
| `Mu-ladder2c.img` | calls 16-30 | `310cda4502ab7b15` |

