# Boot latency trace

`BootLatencyTrace.c` and its headers (`BootLatencyStore.h`, `BootLatencyUnwind.h`) come unchanged
from the sibling reference port **UniXNU/UniXNU-sheng** (`package/`).

The iOS 27 branch of `scripts/build-sheng-source-storage.py` adds this file to the source-storage
archive only when it is present next to `BootLog.c`, and `BootLog.c`/`BootUiTraceProbe.c` call its
`boot_latency_*` entry points, so it is a required input of the kernel link on this profile rather
than an optional diagnostic.

## Weak data sources

`BootLog.c` repeats seven weak imports on their own lines at the end of the file. The framework
derives `BootLogDefaults.c` — zero definitions for weak imports that this board does not build in —
from every `extern ... __attribute__((weak_import));` line of `BootLog.c`, and that generator is
line-based. The original declarations of `sheng_idle_*`, `native_gop_virtual`,
`native_gpu_role_thread` and `sheng_pmu_fixup` are spread over multi-declarator lines in this
package and its headers, so the generator could not see them and the kernel link failed with them
undefined. Repeating them one per line is the fix; the definitions still come from the platform
drivers when those are built in.
