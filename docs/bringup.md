# 实机记录（bring-up log）

按时间顺序记录每一个镜像版本、屏幕现象与对应修复。全部通过 `fastboot boot` 临时启动，无分区写入。

## 硬件身份（实测）

| 项 | 值 |
|---|---|
| 型号 | 23116PN5BC / shennong |
| SoC | SM8650（qcom,msm-id 0x22d），board-id 0x08 |
| 系统 | HyperOS 3.0.309.0.WNBCNXM / Android 16 / slot _a |
| 内存 | 12 GB |
| UFS | `ufshc@1d84000`，逻辑块 4096 B |

## 阶段 B：UEFI 固件迭代

| 版本 | 现象 | 根因 | 修复 |
|---|---|---|---|
| v1 | 卡在 PmicDxe | SPMI 外部中止 | 摘除 PmicDxe 验证 |
| v2 | 卡在 UFSDxe（Sense Key 0x02 NOT READY）| 初始化期调用了 UFS Sleep | 反汇编定位 `0xb008`，`bl sleep` → `bl wakeup` |
| v3 | 首次显示 UniXNU 菜单，1 秒后崩溃 | SPMIDxe 补丁打偏（0x144c）| 改为按参考设备 patched 反汇编精确 stub 0x14ac/0x154c 两处为 `mov w0,wzr; ret` |
| v4 | PmicDxe 完整跑完但黑屏 | PmicDxe 下游电源链连带崩溃 | 整体摘除电源链（PmicDxe/PmicGlink/UsbPwrCtrl/QcomCharger/ChargerEx）|
| v5 | 菜单 <1 秒后崩溃（FAR=0x221CB500）| UniXNU 菜单第二次重绘访问失效指针 | `Menu.c` 强制 `HasInput=FALSE` + `gBS->Stall()` 单帧路径 |
| v6 | **菜单稳定 10 秒，logo 清晰** | — | `Ui.c` logo 上限 160px |

## 阶段 C：XNU 启动

> **供体变更提醒（2026-11-08 补记）**：下面 2026-11-05 的验收用的是 **iPadOS 17.7.11
> （21H461，arm64）** 供体。供体在此之后改为 **iPhone17,1 iOS 27.0.1（24A446，arm64e，
> XNU 12377.121.6）**（目标是手机用户态，不是平板）。**iOS 27 供体还没有重复这条验收**，
> 现状见 [handoff/BRINGUP-STATUS.md](handoff/BRINGUP-STATUS.md)。
> 表里的 `Mu-shennong-*` 镜像都属于 iPadOS 供体时代，不能当作 iOS 27 的证据。

| 版本 | 现象 | 根因 | 修复 |
|---|---|---|---|
| Mu-shennong-1 | 菜单 `no boot entry found` | 用了 header v4，`fastboot boot` 场景 ABL 无 vendor_boot DTB，initrd 传不进 | 改 header v0 + gzip + append_dtb（与参考设备一致）|
| Mu-shennong-2-v0 | 菜单出现 `1 shennong XNU first entry ... xnu`，DarwinBoot 输出 ID_AA64MMFR0/PFR0，画面静止 | XNU 输出走 serial，无显示驱动 | 加 panic screen + stage 探针 |
| Mu-shennong-3-v0-panic | 蓝色/绿色 stage 条 + `AMFI: No PMGR?` @ConfigurationSettings.cpp:235 + 内核栈 | AMFI 需要 provider-less ApplePMGRNub | 引入 ShengPlatformPower（provider-less nub）|
| Mu-shennong-5-pmgr | 三段 stage 条全出，仍 `No PMGR?` | `sheng-pmgr=2` 启动参数未传（本地手工 payload 遗漏）| 更新 unixnu.toml |
| Mu-shennong-6-pmgr2 | **`Failed to mount root device @IOKitBSDInit.cpp:984`，pages/free 正常** | 无根文件系统（预期）| — |

**阶段 C 里程碑**：XNU 完成入口、MMU、IOKit、Platform Expert、AMFI、bsd_init 全流程，停在 vfs_mountroot。
与 UniXNU 官方参考设备（sirius/sheng）的记录完全一致。

## 2026-11-08：阶段 A 复验与 iOS 27 早期启动诊断

### A.1 阶段 A 复验通过（loader）

- 现象：`drivers 0 loaded / 1 failed`、`\A: start failed`、entry `returned: Unsupported`。
- 根因：出厂固件里已经存在一个旧 `DarwinBoot`，它先安装了 `gUniXNULoaderProtocolGuid`；
  新的 `DarwinBoot` 入口发现协议已存在就返回 `EFI_ALREADY_STARTED`，所以根本没跑到加载。
- 修复：CI 提交 `4484825` —— 先 `LocateHandleBuffer` 卸载所有既有实例，再安装自己的协议。
- 真机复验（照片）：`drivers 1 loaded / 0 failed`，随后
  `DARWINBOOT: inputs validated: exiting boot services`、`DARWINBOOT: hand-off to the kernel`。

### A.2 交接后屏幕无输出：不是内核挂死，是进度屏没编进去

- 现象：DarwinBoot 打完寄存器诊断（kernel va/pa、entry、video、SCTLR/TCR、MMFR0/PFR0）
  后画面静止，没有任何 XNU 输出。
- 查证依据（构建日志，不是猜）：run `42462550406` 的日志里是
  `XNU_BOOT_PROGRESS env: unset`；`scripts/build-xnu-4k-baseline.sh` 取
  `BOOT_PROGRESS=${XNU_BOOT_PROGRESS:-0}`，于是所有 `boot_progress_*` 调用编译成空操作。
- **陷阱**：`strings kernel.macho | grep 'STAGE '` 命中 7 次**不能**证明进度屏可用 ——
  归档被强制链接进去了，但调用点没有生成，屏幕自然不动。
- 修复：提交 `4f12b68` 在 `Build kernel` 步骤的 `env` 加 `XNU_BOOT_PROGRESS: '1'`，
  run `42468975624` 重编诊断内核。

### A.3 诊断屏怎么读（之后每张照片按这个规则判读）

- 帧缓冲绑定成功（`vcattach` / `initialize_screen` 路径）时，左上角会画 **48×48 红色方块**（8,8）。
- 高度 60%：8 位二进制计数 = `boot_progress_stage()` 事件个数；68%：`bsd_init:` 打印次数。
- 高度 76% / 84%：两条里程碑 lane（固定颜色与槽位）。
- 高度 54%：`STAGE <n> <名字>` 大字行，名字按阶段表顺序单调递增。
- **没有红方块 ⇒ 内核没到 `initialize_screen`**（它在 `kernel_bootstrap_thread` 里、`spllo()` 之后），
  问题在更早的 `arm_vm_init` / `machine_startup` 段。

### A.4 持久日志通道（“内核转储 / pstore 等价物”）

- 同 SoC（SM8650）参考 houji 的实测结论：ramoops/pstore 区 `A7000000–A73FFFFF` 与启动固件
  保留区重叠，重启后为空，**不能作为本平台的转储通道**。
- 可用路线：NativeUfs 固定日志窗口（`package/BootLog.c`，4096 B 块：头部 / 内核消息缓冲 /
  文本环）写入 userdata 尾部，重启后经 ADB 或恢复环境读回；houji 已跨重启核验过 CRC。
- 本仓库现状：内核已导出 `native_ufs_log_open/write/sync/export_blocks/log_panic`，也解析
  `sheng-log` 与 `sheng-log-reserve`；但 `kernel_args` 尚未传 `sheng-log=1`，仓库里也还没有
  读取脚本 → 待补。

### A.7 故障寄存器转储（2026-11-08）

`arm_vm_init` 之前 panic 屏画不出来（内核还没映射帧缓冲），但 **loader 的页表仍在**，
所以物理地址 `0xFC400000` 可写。`Mu-fault.img` 把 `_sleh_synchronous` 的入口改成跳到
一段 600 字节的 cave：读 `ESR_EL1 / FAR_EL1 / ELR_EL1 / SPSR_EL1`，用自带 5×7 点阵
把四个 64 位值画成十六进制（黑底、四行四色：白=ESR、红=FAR、绿=ELR、蓝=SPSR），
然后跳回原处理流程。配合 13 条里程碑色带，一张照片就能读出“停在哪一步 + 是不是
同步异常、异常类型/访问地址/出错 PC”。

注意：若停点是**死循环**而不是异常，这段代码不会触发（屏幕只显示色带），
这本身也是判读依据。

### A.8 供体内核缓存核对与 `early_security_init` 实测范围（2026-11-08）

用 HTTP range 直接取 profile 里那条 IPSW URL 的成员，不下载 12.3 GB 整包：

```
scripts/donor/fetch-ipsw-member.py KernelCache <IPSW URL>
```

取到的 `kernelcache.release.iphone17` 解 IM4P → LZFSE → 0x0100000c 切片后
sha256 = `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`，
与线上下载的构建产物 `kernel.json` 里 `inputs.kernelcache_sha256` **完全一致**，
说明本机复现的就是 CI 实际用的那个供体。

**早期安全初始化地址已测出并启用**（2026-11-08）：AMFI 的 `__TEXT_EXEC` 内
`0xfffffff00921000c` 处正是补丁要求的 `void(void)` 契约：

```
bti c; pacibsp; stp x29, x30, [sp, #-0x10]!; mov x29, sp
bl 0xfffffff00920f854        ; initializeAppleMobileFileIntegrity
mov w0, #0; ldp x29, x30, [sp], #0x10; retab
```

校验链（三层独立证据）：
1. 在**下载的供体内核缓存**里该地址字节如上；
2. 在**线上构建产物** `kernel.macho` 里搜索这 40 字节签名，唯一命中位置反推正好是
   `0xfffffff00921000c`（AMFI `__TEXT_EXEC` 起点 `0xfffffff009201820` 起算）；
3. 产物里 AMFI 的 `__TEXT_EXEC` 段与供体完全一致（`va=0xfffffff009201820`、
   `size=0x2b808`、`initprot=5`、`maxprot=5`），且 AMFI 在供体元数据里
   `AppleSecurityExtension = true`，满足 `emit_prelink` 的全部前置条件。

同一份缓存里量出 AMFI 的代码段（`scripts/donor/parse-donor.py`）：

| 项 | 值 |
|---|---|
| kext 装载地址 | `0xfffffff00764ece0` |
| `__TEXT_EXEC` | `0xfffffff009201820 .. 0xfffffff00922d028`（`initprot=5`、`maxprot=5`，unslid）|

profile 里遗留的 `0xfffffe00092551ac` 属于 iPadOS 内核的地址空间（内核基址
`0xfffffe0007004000`），落在本供体模块之外，`emit_prelink` 会直接拒绝；因此
这一项仍保持**不启用**（线上产物 `kernel.json` 的 `early_security_init` 就是 `{}`）。
下一件要做的就是把 AMFI 里那个「调用 `_initializeAppleMobileFileIntegrity` 并返回 0」
的 `void(void)` 包装函数在这段范围内定位出来，再写成
`"early_security_init" = "com.apple.driver.AppleMobileFileIntegrity=<VA>"`。

顺带修正了 profile 里过期的 `kernel.prelink.kernelcache_sha256`（原来是另一份供体的值）。

### A.6 内核里 `cluster-type` 的真实语义（反汇编核实，2026-11-08）

用 capstone 反汇编 `_ml_parse_cpu_topology`（`0xfffffff00ad85fa0`）核实：

- 它先读启动参数 `cpus` / `cpumask`（默认 CPU 数 8），再对 `/cpus` 做 `SecureDTLookupEntry`
  和 `SecureDTInitEntryIterator`，逐个 CPU 节点读：`state`（与字符串 `running` 比较）、
  `die-id`、`reg`（走 `_ml_readprop`）、`l2-cache-size/id`、`l3-cache-size/id`、
  `coresight-reg`、`cluster-type`、`cluster-power-down`、`cpu-impl-reg`、`cpm-impl-reg`、
  `die-cluster-id`、`cluster-core-id`、`acc-impl-reg`、`kernPOST`、`enable_skstb`、
  `enable_skstsct`、`cluster_power`。
- `cluster-type` 的取值语义（`0xad86544` 起）：先写默认值 **0**，然后按属性长度读 1/2/4/8
  字节；`'P'(0x50)` → 2、`'M'(0x4d)` → 3、`'E'(0x45)` → 1；属性缺失时保持 0，**这个函数
  本身不会因为缺失而 panic**。
- 我们在 ADT 里给 cpu0 加 `cluster-type='E'`（u32 0x45，小端字节 `45 00 00 00`）就是让它
  走 1（E 核）这条分支；对照组 `Mu-ct-ms.img` 用来验证后续调度器是否接受该值。

结论：fuxi 记录里"簇数超过 `MAX_CPU_CLUSTERS` 触发 assert"的路径不在这个函数里（本版内核
该函数对未知/缺失类型是静默降级到 0）。因此 `cluster-type` 是**待验证的可疑项**，不是已证实的根因；
真正的停点仍要由 `Mu-probe-*` 序列或色带照片判定。

### A.5 早期卡点定位（入口探针二分，2026-11-08 深夜）

工具：`scripts/patch-xnu-entry-probe.py`。它只改 payload 里那份 kernel 的几条指令，
不需要重编内核，所以每轮几分钟就能上机：

- stage 3：MMU 打开后等 `--reset-delay` 秒再 PSCI `SYSTEM_RESET`，**不继续执行**；
  用于证明“入口代码跑到了”。
- stage 4：在 `_arm_init` 里指定符号的调用处等待/立即复位（`--reset-before` 立即复位），
  用于二分“有没有走到这个调用”。

实测记录：

| 轮 | 探针 | 结果 | 判读 |
|---|---|---|---|
| 1 | stage 3，6 秒 | 推镜像约 2 分钟后手机自行重启进 recovery（`/proc/uptime`=1248 s 吻合）| 内核入口代码执行、PSCI 复位可用；但该模式**停在 MMU 打开处不继续** |
| 2 | stage 4 `--reset-before _machine_startup` | 5 分钟无复位，设备停在镜像里且无 USB | 内核**没有走到** `_machine_startup` 调用点 |

结论：iOS 27 内核的卡点在 `_arm_init` 的**早期**（`_OSRuntimeSignStructors` …
`_arm_vm_init` 之间），而不是 `vfs_mountroot`。

注意：stage 4 探针“没走到”时设备会停住且无 USB（没有 serial、没有显示驱动），
只能强制重启（长按电源 ~12 秒；音量下 + 电源进 fastboot）。

> **同 SoC 参考（fuxi，SM8550，同一套 XNU 12377）**：同类现象的设备记录把停点定在
> `ml_parse_cpu_topology`——ADT 的簇数/cluster-type 与内核的 `MAX_CPU_CLUSTERS` 不匹配，
> 在内核有一条 assert，控制台出现之前就 panic。修法是让 ADT 的 cluster-type 与内核
> 的簇配置一致（fuxi 用 AMP 补丁把 `MAX_CPU_CLUSTERS` 提到 2）。我们的 ADT 里 cpu0
> **没有** `cluster-type`，因此准备了两份镜像做对照。

下一步判读用 **13 色带**镜像 `Mu-ladder2.img`（`scripts/patch-milestones.py` 生成）。
它在 `_arm_init` 的 13 个关键调用点各画一条 1/16 高的色带，位置固定、颜色固定：

| 带 | 颜色 | 含义（画带时说明上一个调用已返回）|
|---|---|---|
| 3 | 白 | `_OSRuntimeSignStructors` 返回（fileset 签名完成）|
| 4 | 红 | `_PE_init_platform` 返回 |
| 5 | 橙 | `_configure_timer_apple_regs` 返回 |
| 6 | 黄 | 第二次 `_SecureDTGetProperty` 返回（DT 读取完成）|
| 7 | 黄绿 | `_check_for_failure_injection` 返回 |
| 8 | 绿 | `_ml_parse_cpu_topology` 返回 |
| 9 | 春绿 | `_thread_bootstrap` 返回 |
| 10 | 青 | `_cpu_bootstrap` 返回 |
| 11 | 天蓝 | `_kernel_startup_bootstrap` 返回 |
| 12 | 蓝 | `_timer_call_init` 返回 |
| 13 | 紫 | `_cpu_init` 返回 |
| 14 | 品红 | `_processor_bootstrap` 返回 |
| 15 | 柠檬绿 | 到达 `_arm_vm_init` 调用点 |

照片上**最高的那条色带**就是内核走到的地方；它不阻塞、不需要实时观察，
之后任意时间拍一张照片即可。

另一点已核实：CI payload 内核本来就把 `_panic` 改成了跳转（跳到 `0xfffffff00b4f6ea8`
的 panic 屏代码），但真机上 panic 屏从没出现过。结合 fuxi 的记录，这说明卡住的位置
在内核映射帧缓冲之前（`arm_vm_init` 之前），panic 屏同样画不出来，因此只能靠
直接写物理地址的色带。最终镜像 `Mu-ladder2b.img` 就是“CI 补丁 + 13 色带”的叠加。`Mu-ladder2-ct.img` 是同一套色带外加 ADT
`cluster-type='E'` 的对照组，用来验证 fuxi 记录里的簇配置假设。

## 阶段 E：UFS 与根卷

- 采用 NativeUfs（UniXNU/ShengUfs，SM8550 起源）
- 寄存器核对：SM8650 与 SM8550 的 UFS GCC 偏移完全一致（GDSCR 0x77004 / MEM_PHY 0x9e000 / AXI 0x77018 / AHB 0x77024 / ICE 0x77074 / AGGRE 0x770e4 / UNIPRO 0x77068）
- SMMU：UFS stream ID 0x60（与 houji 实测一致）
- 根卷：`unixnu userdata` 从 iPadOS 17.7.11（21H461）IPSW 提取 OS + Cryptex1,SystemOS，
  生成 `SHNGROOT` 卷，2026-11-05 经授权写入 `userdata`（写入后 Android 数据不再存在，
  见 [recovery.md](recovery.md)）

### E3：真机逐轮记录（2026-11-05）

| 轮 | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | `smmu: conflicting UFS stream mapping slot=2 smr=80000060 s2cr=2` | 固件给 UFS stream 留了独占 SMR，且 translation 开着，规划器只接受空闲或 bypass bank | `patches/ufs-smmu-takeover.patch` 接管该 bank |
| 2 | `magic=474e4853 544f4f52`、`manifest status=0 windows=2` | — | SMMU 通后 UFS 与根卷全部可读 |
| 3 | `Undefined kernel instruction: pc=0xfffffff00596ed98 instr=0` | 绑定表取自原厂 kernelcache，而 prelink 把每个组件平移了 `[kernel.prelink] slide` | `scripts/apply-prelink-slide.py` 平移后**提交** pin |
| 4 | `Failed to mount root device @IOKitBSDInit.cpp:984` | 绑定修好，驱动跑起来但没有根设备 | 进入策略问题 |
| 5 | `stage=policy count invalid`、`policies=0` | 驱动要求 owner 签名根策略 | 生成本板策略（见下）|
| 6 | `stage=signed window identities`、`prepared=2` | 无签名构建里 `validate()` 恒 false | 放弃绕过，走真策略 |
| 7 | 策略版内核已启动，等待屏幕确认 | — | — |

策略包：`scripts/make-root-policy.py` 从根卷解析 APFS 卷 UUID、逐 4096 块算 SHA-256、
签 160B 头；544B 头与 395B 公钥存 `policies/`，哈希表作为根卷对象 `OS.vroot` /
`SystemOS.vroot` 存在。完整说明见 [handoff/UFS-E3-2026-11-05.md](handoff/UFS-E3-2026-11-05.md)。

## 构建环境

- 内核：GitHub Actions macOS runner（Xcode 26.6），UniXNU main + device repo
- UEFI：本机 aarch64 Linux（PRoot Ubuntu 24.04），BaseTools 源码编译
- 已知 CI 注意点：
  - format1 的 `[kernel].archives` 只接受脚本名，`component:` 语法属于 format2
  - PMGR archive 需在正式 kernel pass 前预构建（bootstrap pass 就会引用 `sheng_pmgr_run`）
  - defconfig 必须含 `CONFIG_XNU_BUILD_ARCHIVES=y`

## 早期色带的盲区：引导页表不含 framebuffer（2026-11-08 定位）

### 现象

把 `_arm_init` 及其前 15 个调用点全部替换成"画一条色带"的探针后，真机屏幕上**只有
loader 自己画的三条带**（绿=交接、蓝=进入内核、品红=开 MMU 前一刻），之后无论探针放在
哪里都没有任何输出，容易被读成"内核停在这里"。

### 根因

内核在 `0xAD832A8` 写 `TCR_EL1` 之后、开 MMU 之前，用自己建的页表接管了两套翻译：

| 寄存器 | 值 | 来源 |
|---|---|---|
| `TTBR0` | `pool & ~1` | `_set_mmu_ttb`（VA `0xFFFFFFF00AD88930`，内含 `msr ttbr0_el1, x0`）在 `0xAD832B4` 被调用 |
| `TTBR1` | `(pool + 0x1000) & ~1` | `0xAD832C4` |
| `TCR_EL1` | `0x00080022A51A251A`（T0SZ=T1SZ=26，TG0=TG1=4 KiB，IPS=2） | `0xAD832A8` |

两套表只覆盖 `boot_args` 给的窗口：`[PhysicalBase, PhysicalBase + MemorySize)`
（本机 `0x0DB0004000 + 0x10000000`）。**framebuffer 在 `0xFC400000`，落在窗口外**，
所以开 MMU 之后任何写 framebuffer 的指令都会触发数据中止；而异常向量在 KVA
（`VBAR=0xAD7C000+slide`，属 TTBR1），向量里的画带同样写 framebuffer，于是双重故障、
静默死锁。屏幕就永远停在 loader 的三条带上。

这也解释了 `docs/devices/elden.md` 里那句"MMU 打开后内核只映射 VirtualBase + (PA - PhysicalBase)
的 256 MiB 窗口，framebuffer 在窗口外，之后的 console 输出需要显式映射或者必须在切换前完成"。

### 修法

`scripts/patch-fb-map.py`：在 `0xAD832C8`（`mov x0, xzr`，此时 TTBR0 已装好、MMU 未开、
`tlbi vmalle1` 未做）注入一个 148 字节的 cave，借引导表池里空闲的第 4/5 页建两张 L2 表，
把 `0xFC400000` 起 30 个、`0x100000000` 起 8 个 2 MiB 块（`0x40D` = 有效块 + AttrIdx 3
= Device-nGnRnE）填进 V=P 表的 L1 槽位 3/4。

池布局（`pool` 是在 V=P 下 `adrp` 算出的**物理**地址 `0x0DB58B4000`）：

| 偏移 | 用途 | 谁用 |
|---|---|---|
| `+0x0000` | V=P 表根（TTBR0） | 内核建表循环 |
| `+0x1000` | KVA 表根（TTBR1） | 内核建表循环 |
| `+0x2000` | V=P 窗口 L2 | 内核建表循环 |
| `+0x3000` | KVA 窗口 L2 | 内核建表循环 |
| `+0x4000` | framebuffer L1[3] 的 L2 | `patch-fb-map.py` |
| `+0x5000` | framebuffer L1[4] 的 L2 | `patch-fb-map.py` |

### 验证

用按同一算法写的走表模拟器（以真机打印的 `VB/PB/MemorySize` 为输入）核对：

- `VA 0xDB3D8341C`（开 MMU 时的 PC）→ 有效块、AF=1、AttrIdx=0（Normal WB）
- `VA 0xFFFFFFF00B4768D0`（`_arm_init`）→ `PA 0x0DB44768D0`
- `VA 0xFC400000` → `PA 0xFC400000`、AttrIdx=3（Device），补丁生效
- `VA 0x100000000` / `0x100A4E000`（后 16 条色带所在）→ 已覆盖

结论：**此后任何"开 MMU 后没有输出"的判断，都必须先确认 `patch-fb-map.py` 在同一张镜像里**，
否则结论无效（本仓库 2026-11-08 之前基于色带得到的"停点"结论都需要按这个前提重读）。


## 进度槽：把早期进度写进内存、下一轮在开 MMU 前读出（2026-11-08 实证）

framebuffer 在引导窗口之外，开 MMU 之后的任何色带都不可信；但**开 MMU 之前**画屏是可靠的。两次真机实验确认：

| 实验 | 镜像 | 结果 |
| --- | --- | --- |
| cave 在 `0xAD832C8` 画白带（MMU 关闭、PA 直写） | `Mu-vis3.img` `6e9bc8f00565f799` | **白带出现**，替换了 loader 的绿带 → 注入点确实被执行 |
| 同一镜像再在 `_arm_init` 入口用 KVA 别名画红带 | 同上 | 无红带 → 开 MMU 后的可见性仍不可用 |

因此诊断通道改成「写内存 + 下轮启动读出」：

1. 进度槽放在内核自己的引导表池第 15 页：`VA 0xFFFFFFF00C8BF000`（`x25 + 0xF000`）。trampoline 在 `0xAD830E4` 才把池清零，读点必须在清零之前。
2. 读点注入 `0xAD83088`（`ldr x26,[x20,#0x470]`，此时 `x25` 已就绪、MMU 仍关、栈不可用）。cave 用 `add x9,x25,#0xf,lsl #12; ldr w19,[x9]; str wzr,[x9]` 读并清零，只碰 `x9-x17/x19`，`x20`/`x22-x26` 一律不碰。
3. 画法：band 0 恒白（证明读出 cave 执行），band 1..8 依次是记录值的 bit0..bit7（白=1、黑=0），逐带前进 `0x119400` 字节。
4. 标记点用开 MMU 后的普通 store 写槽（只写内存），一次启动记录、下一次启动显示，天然形成「一轮一格」的对照实验。
5. `scripts/patch-progress-slot.py --sites "value@target,..."` 支持任意符号/地址作为标记点；当前链路覆盖 MMU 后第一指令、自检、`_arm_init` 入口与若干调用点、`arm_vm_init`、`early_random`、`device_service_create`、`phys_carveout_init`、`kdp_init`、`cpu_init`、`timer_call_init`、`rtclock_early_init`、`PE_init_printf`、`PE_init_iokit`、`machine_startup`、`kernel_bootstrap`、`bsd_init`、`bsd_autoconf`、`vfs_mountroot` 共 26 个点。

读表：band 1..8 的二进制值就是「最后一格到达的标记编号」，0 表示一个都没到。


## 开 MMU 之后的第一道静默死循环：SCTLR 自检（2026-11-08 反汇编确认）

trampoline 在装好 SCTLR 之后的代码是这样的：

```
0xAD83408-0xAD83414   x0 = 0xFC54793D        ; 内核期望的 SCTLR_EL1 值
0xAD83418             b   0xAD81560          ; 画第 3 条带、写 SCTLR、开 MMU、返回
0xAD8341C             isb                     ; ← 开 MMU 之后的第一条指令
0xAD83420-0xAD8342C   x1 = 0xFC54793D
0xAD83430             cmp x0, x1
0xAD83434             b.ne 0xAD83434          ; ← 回读不匹配就原地永久自旋，无输出、无复位
0xAD83438             mov x0, #0x300000       ; cpacr_el1
```

`b.ne` 的目标就是自己，所以只要回读值与这个 ARMv8 时代的常量有一位不同（ARMv9.x 核心的 RES1/RAZ 位可能不同），内核就在这里**静默卡死**——症状与我们看到的完全一致：屏幕停在 loader 界面、USB 消失、永不复位。

`scripts/patch-mmu-guard.py` 把这条自检改成：保留比较 → 不相等时把 `0x81` 写进进度槽第二字 → **继续走正常路径**。这样守卫失败既可观测、又不再致命，配合进度槽的读出（band 9 专画这个标志）就能一次启动定位。

### 进度槽读出条带布局（`Mu-guard.img` 起）

| 条带 | 含义 |
| --- | --- |
| 0 | 恒白：读出 cave 在开 MMU 前执行了 |
| 1..8 | 上一轮记录值的 bit0..bit7（白=1，黑=0） |
| 9 | SCTLR 自检失败标志（白=失败过） |

记录值含义：`0`=loader 没跑到 cave，`0x80`=跑到 cave 但开 MMU 后第一条指令没执行，`1`=开 MMU 后第一条指令执行了（若 band 9 也白则卡在自检死循环），`2`=过了自检，`3`=`_arm_init` 入口，`4..11`=`_arm_init` 的调用点，`12..26` 见 `scripts/patch-progress-slot.py` 的链路表。


## 0xAD81560 写的是白色，但屏幕上是品红：卡点在开 MMU 之前（2026-11-08）

`0xAD83418` 的 `b 0xAD81560` 是开 MMU 前的最后一步。`0xAD81560` 的代码：

```
0xAD81560  ldr x1, [x20, #0x28]   ; boot_args.Video.v_baseAddr
0xAD81564-0xAD81570  x2 = rowBytes * height / 16 & ~7   ; 一条带的字节数
0xAD81570-0xAD81580  x1 = base + 2 * band_bytes
0xAD81584-0xAD8158C  w6 = 0xFFFFFFFF          ; 白色
0xAD8158C            stp w6, w6, [x1], #8      ; 画第 3 条带
0xAD81598            dsb sy
0xAD8159C            msr sctlr_el1, x0         ; 开 MMU
0xAD815A0            b   0xAD8341C
```

也就是说：**只要内核走到这里，第 3 条带就会变成白色**。而真机照片里第 3 条带始终是品红（loader 画的），所以内核**从来没有走到 `0xAD83418`**——阶段 C 的停点在这之前，而不是在 `_arm_init` 里。

窗口 `0xAD832CC…0xAD83418` 全程 MMU 关闭：MAIR 组装 → `msr mair_el1` → `tlbi vmalle1` / `ic iallu` → （热启动分支里从 `0xC8B2000+0x208` 重装 TTBR1）→ VBAR ← `0xAD7C000+slide` → PAC 密钥生成（用 `cntpct_el0` 做种子写入 `0xB6B8000+0x120`）→ `msr apiakey/apibkey/apdakey/apdbkey/apgakey_*_el1` → 最后才 `b 0xAD81560`。

其中 `msr apiakey*_el1` 一族在**不支持指针认证的核心上是未定义指令**（会触发同步异常，而此时异常向量刚装好但没有可用处理器）。骁龙 8 Gen 3 的 Cortex-X4/A720 支持 PAC，理论上不会在这里炸，但这正是 `Mu-pre.img` 阶梯要逐段验证的内容。


## 内核自己的画带代码确认了停点在开 MMU 之前（2026-11-08 反汇编）

| 位置 | 颜色 | 落点 |
| --- | --- | --- |
| loader `Entry.S` | green `0xFF00FF00` | band 0 |
| 内核入口 `0xAD81500`（`0xAD81488` 的 `b` 目标） | blue `0xFF0000FF` | band 1 |
| `0xAD81560`（`0xAD83418` 的 `b` 目标，紧接着 `msr sctlr_el1`） | white `0xFFFFFFFF` | band 2 |

真机照片里 band 0 白（我们的 cave）、band 1 蓝、band 2 **品红**。蓝带出现说明内核入口执行了；band 2 没变白说明**内核从未执行到 `0xAD83418`**。因此阶段 C 的停点不在 `_arm_init`，而在开 MMU 之前那段 `0xAD830D4…0xAD83418` 的窗口里：清池 → 建 V=P/KVA 两级表 → `msr tcr_el1` → `bl _set_mmu_ttb`（装 TTBR0）→ MAIR → `tlbi vmalle1` / `ic iallu` → 重装 VBAR → 生成并写入 PAC 密钥（`msr apiakey/apibkey/apdakey/apdbkey/apgakey_*_el1`）。

`scripts/patch-pre-mmu-squares.py` 在这段窗口里放了 24 个检查点，每个检查点画一个 60×60 方块（不是整条带，所以不受 16 条带限制），并且**只用 x7/x8/x16/x17、不碰栈**（此时 SP 仍是未映射的内核虚拟地址）。第一个没出现的方块就是死掉的位置。


## 39 点阶梯的解码表与对应修法（`Mu-sq3.img`，2026-11-08）

方块网格：列 `x = 16 + (i % 20) * 70`，行 `y = 20 + (i // 20) * 70`，尺寸 60×60。第一行 17 个白色（内核入口序言），第二行 22 个红色（建表到 PAC 密钥）。**第一个缺失的方块就是停点**。

| # | 方块坐标 | 颜色 | 注入地址 |
| --- | --- | --- | --- |
| #00 | (16, 20) | 白 | `0x00AD8305C` |
| #01 | (86, 20) | 白 | `0x00AD83060` |
| #02 | (156, 20) | 白 | `0x00AD83064` |
| #03 | (226, 20) | 白 | `0x00AD8306C` |
| #04 | (296, 20) | 白 | `0x00AD83074` |
| #05 | (366, 20) | 白 | `0x00AD83078` |
| #06 | (436, 20) | 白 | `0x00AD83080` |
| #07 | (506, 20) | 白 | `0x00AD83084` |
| #08 | (576, 20) | 白 | `0x00AD83088` |
| #09 | (646, 20) | 白 | `0x00AD83094` |
| #10 | (716, 20) | 白 | `0x00AD830A4` |
| #11 | (786, 20) | 白 | `0x00AD830AC` |
| #12 | (856, 20) | 白 | `0x00AD830BC` |
| #13 | (926, 20) | 白 | `0x00AD830C4` |
| #14 | (996, 20) | 白 | `0x00AD830D4` |
| #15 | (1066, 20) | 白 | `0x00AD830E4` |
| #16 | (1136, 20) | 白 | `0x00AD830F0` |
| #17 | (1206, 20) | 红 | `0x00AD83128` |
| #18 | (1276, 20) | 红 | `0x00AD83144` |
| #19 | (1346, 20) | 红 | `0x00AD83164` |
| #20 | (16, 90) | 红 | `0x00AD831C4` |
| #21 | (86, 90) | 红 | `0x00AD831EC` |
| #22 | (156, 90) | 红 | `0x00AD83238` |
| #23 | (226, 90) | 红 | `0x00AD83290` |
| #24 | (296, 90) | 红 | `0x00AD832A4` |
| #25 | (366, 90) | 红 | `0x00AD832A8` |
| #26 | (436, 90) | 红 | `0x00AD832B4` |
| #27 | (506, 90) | 红 | `0x00AD832BC` |
| #28 | (576, 90) | 红 | `0x00AD832CC` |
| #29 | (646, 90) | 红 | `0x00AD8330C` |
| #30 | (716, 90) | 红 | `0x00AD83314` |
| #31 | (786, 90) | 红 | `0x00AD83320` |
| #32 | (856, 90) | 红 | `0x00AD8332C` |
| #33 | (926, 90) | 红 | `0x00AD83348` |
| #34 | (996, 90) | 红 | `0x00AD8335C` |
| #35 | (1066, 90) | 红 | `0x00AD833C8` |
| #36 | (1136, 90) | 红 | `0x00AD833CC` |
| #37 | (1206, 90) | 红 | `0x00AD83404` |
| #38 | (1276, 90) | 红 | `0x00AD83418` |

| 现象 | 结论 | 下一步 |
| --- | --- | --- |
| 一个方块都没有 | trampoline 第一条指令之前就死了（loader 跳转或 `msr oslar_el1` 处异常） | 检查 loader `DarwinEnter` 的 `br x1` 目标与 `boot_args` 指针；在 `0xAD8305C` 之前加 cave（例如入口 `0xAD81488`）验证 |
| 白行部分出现 | 序言有问题：`daifset` / 读 boot_args（x20 不是物理地址就会取指中止）/ SPSel 切栈 / 清池 | 按缺失位置定位；若是读 boot_args 处，怀疑 loader 传的 `Args` 不是物理地址 |
| 白行全有、红行一个都没有 | 清池之后立刻死（`adrp x0, 0x7184000` 读 `[x0+0x18]` 的 `tbz w1,#0x1f` 分支、或 `cmp w1,#0x19; b.ne 0xAD83108` 自旋） | `0xAD83108` 也是一个静默自旋点：`b.ne` 到自身；若 `[0x7184018]` 的 bit31 未置位就会走到那里 |
| 红行到 `0xAD8328C` 之前断开 | 建表循环耗尽（`b.hs 0xAD8328C` → `b .` 自旋） | 说明引导表池不够或窗口超界：检查 `MemorySize`、`VirtualBase-PhysicalBase` 与 `x25` 池地址是否合理 |
| 红行到 `0xAD832B4`（`bl _set_mmu_ttb`）断开 | TTBR0 安装路径异常 | 读 `_set_mmu_ttb`（`0xAD88930`）实现，确认 x0 的 ASID/属性位 |
| 红行到 PAC 段断开 | `msr apiakey*_el1` 一类未定义（核心不支持指针认证） | 用 `scripts/patch-mmu-guard.py` 的同类手法把 PAC 写入改成可跳过，或用 `SCTLR_EL1.EnIA` 控制 |
| 39 个全出现 | 死在 `0xAD81560` 内部（画 band 2 白 或 `msr sctlr_el1`），即开 MMU 瞬间 | 下一步查引导表的恒等映射是否覆盖当前 PC 与 `_arm_init` 的 KVA |


## Cave 必须放进已验证的零填充区（2026-11-08 自查发现的工具缺陷）

早期几版探针把 cave 写在了 `0xB4F5000 / 0xB4F6000 / 0xB4F8000 / 0xB4F9000`，事后按符号表核对，这些地址**落在真实函数里**：

| 地址 | 实际落在 |
| --- | --- |
| `0xB4F5000` | `NativeUfs::start` 的 `.cold.4`（+0x14） |
| `0xB4F6000` | `_ccdigest_update`（+0x11C） |
| `0xB4F8000` | `OSRuntimeSignStructorsInSegment` 函数开头 |
| `0xB4F9000` | `KLDBootstrap::readBuiltinPersonalities`（+0x214） |

这些函数大多在 kext 加载阶段才跑，所以不一定是本次挂死的原因，但**补丁污染内核代码本身不可接受**，也会让后续阶段的结论不可信。

正确做法：先扫 `__TEXT_EXEC` 里连续 ≥0x400 字节的零填充，再往里面放 cave。当前内核（iOS 27.0.1 24A446 / XNU 12377）的可用填充段：

| 起始 VA | 长度 |
| --- | --- |
| `0xFFFFFFF00B4F9688` | `0x2978` |
| `0xFFFFFFF00AD80090` | `0xF70` |
| `0xFFFFFFF00AD815A4` | `0xA5C` |
| `0xFFFFFFF00AD82784` | `0x87C` |
| `0xFFFFFFF00B4F78F0` | `0x710` |
| `0xFFFFFFF00AD7BA50` | `0x5B0` |

现在 `patch-pre-mmu-squares.py` 用 `0xB4F9700`（39 个 cave × 0x100 = 0x2700，正好落在 `0xB4F9688+0x2978 = 0xB4FC000` 之前，并带断言），`patch-progress-slot.py` 的读出 cave 用 `0xAD815A4`、标记 cave 用 `0xB4F9700`。

---

## 2026-11-10 20:09–20:20：fastboot boot 破局（append_dtb）+ 第一个真机 UEFI 异常

### 事实（设备侧，逐条可复核）

| 时间 | 动作 | 结果 |
|---|---|---|
| 20:09:39 | `fastboot boot Mu-shennong-fd1.img`（无 DTB） | `Booting OKAY`，但 USB 0.32 s 后回到 fastboot |
| 20:09:44–20:17 | 反复重试 fd1 / fd3 | 全部 `FAILED (remote: 'Failed to load/authenticate boot image: Load Error')` |
| 20:09:39 起 | 屏幕 | 全黑（多次 `fastboot reboot-bootloader` 才恢复 fastboot 界面） |
| 20:16:06 | `fastboot boot` **append_dtb 变体**（`gzip(shim+FD)+shennong.dtb`） | `Booting OKAY`，**USB 不再回来**，持续 5 分钟以上 |
| 20:17 | 屏幕 | **UEFI 异常转储**（见下） |

判别手段：0.3 s 粒度的 `fastboot devices` 轮询。不带 DTB 的镜像 0.3 s 内回到 fastboot；带 DTB 的镜像永远不回来 —— 说明 ABL 真的把控制权交出去了。

### 关键发现 1：ABL 要求内核流末尾带 DTB

`ASSERT` 之前的失败信息是 `Failed to load/authenticate boot image: Load Error`，与 Mu-Silicium
`Resources/Configs/*.toml` 的 `[boot_image_kernel] append_dtb = true` 完全对应。我们的
`firmware/make-boot-image.py` 之前只压 `shim+FD`，没带 DTB，所以每次都被拒。

已落地修复：
- `firmware/make-boot-image.py` 新增 `--append-dtb PATH`（`build()` 用 `zlib.decompressobj(31)`
  判 `unused_data`，缺 DTB 直接判失败，除非显式 `--allow-missing-dtb`）；
- `board.toml ["bootimg"] append_dtb = "Resources/DTBs/shennong.dtb"`；
- `scripts/verify-boot-package.py` 新增 `image append_dtb` 检查（旧 fd1/fd2/fd3 现在会 FAIL）。

### 关键发现 2：固件跑起来了，但死在 AOP cmd-db 的翻译错误上

屏幕原文（照片 `device-runs/2026-11-10/uefi-exception-2016.jpg`）：

```
ASSERT [ArmCpuDxe] CpuExceptionHandlerLib.c(438): ((BOOLEAN)(0==1))
X0 = 0x0000000081C60000            FAR  = 0x0000000081C60000
ESR : EC 0x25 IL 0x1 ISS 0x00000007
Data abort: Translation fault, third level
```

（`ArmCpuDxe` 是异常向量表的所有者，不是肇事模块。）

`0x81C60000` 在设备树里是 `aop_cmd_db_region`（`compatible = "qcom,cmd-db"`, size 0x20000）。
`MemoryMapLib.c` 之前只描述 xbl_config 的粗粒度区间，`0x81C00000–0x81CF4000` 整段没有映射，
所以 `CmdDbDxe`（继承自 giulia 的 `Binaries/giulia/QcomPkg/Drivers/CmdDbDxe`）一写就缺页。

修复：`scripts/make-shennong-uefi-pkg.py` 现在同时读 `dts/shennong.dts` 的 `reserved-memory`，
把 xbl 区间未覆盖的节点补进 `MemoryMapLib`（`AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN`），
本次补 17 条（gunyah_hyp / cpusys_vm / xbl_aop_image / **aop_cmd_db** / aop_tme_uefi / chipinfo /
adsp_mhi / global_sync / tz_stat / qdss / mpss_dsm / xbl_ramdump / tz_merged / hwfence-shmem /
trust_ui_vm / llcc_lpi…）。ramoops 因已被 UEFI_FD 三行并集覆盖而跳过。

新固件：`SILICIUM_UEFI-shennong-DEBUG.fd` sha256 `646bcfc39f429b9241977c5351f120c88f285d4299f670a8471d8ecdc1fcfc8f`，
新镜像：`boot/Mu-shennong-fd4.img` 2,523,136 B sha256 `7ba626e299ca0d52172c54b5e0d2271d720aee4fc9382a1f8f0c2922dea1e4ba`，
预检 15 项全过（含 `image append_dtb` 1,238,463 B）。

### 关键发现 3：fd4 时代码跑到 MMU 初始化，屏幕自己打出内存映射错误

照片 `device-runs/2026-11-10/fd4-console-2026.jpg`：

```
Project Silicium for Xiaomi Xiaomi 14 Pro
Firmware Version 4.0 Build at 12:20:27 Nov 10 2026
MMU: 53 regions
"aop_tme_uefi_merged_region" (0x81C80000) and "UEFI_Log" (0x81CE4000) Overlap!
```

两件事同时被证明：

1. **显示链是通的**——这是第一次在屏幕上看到我们自己固件的文字（SimpleFbDxe + 控制台都正常），
   `MemoryMapLib` 的 53 条描述也确实是新固件（fd3 时代是 36 条）。
2. **厂商数据自己就重叠**：设备树 `aop_tme_uefi_merged_region` = 0x81C80000+0x74000
   一直盖到 0x81CF4000，而 xbl 的 `UEFI_Log` 是 0x81CE4000+0x10000，两者重叠 64 KB。
   ArmCpuDxe 拒绝重叠描述符，所以停在 MMU 初始化。

修复：生成器不再「整块加入」，而是**按已占用区间裁剪**——DTB 保留区先被 xbl 行裁剪
（aop_tme 变成 0x81C80000+0x64000），最后再对整个描述符表做一次去重（xbl 自己的
`IMEM` 与 `IMEM_Cookie_Base` 也重叠 8 KB，`IMEM` 裁到 0x2A000）。自检：53 行、**零重叠**。

### 关键发现 4：fd6 的新异常（0x088E2000，二级翻译故障）

照片 `device-runs/2026-11-10/fd6-exception-2028.jpg`（20:28 拍摄）：

```
ASSERT [ArmCpuDxe] CpuExceptionHandlerLib.c(438)
ELR 0xCF8B6E60   LR 0xCF8B2568   SP 0xA764BAB0
ESR 0x96000006   FAR 0x088E2000
ESR : EC 0x25  IL 0x1  ISS 0x00000006
Data abort: Translation fault, second level
```

结论（已核实）：

1. `FAR = 0x088E2000` 在我们的 53 条描述符里**没有任何一条覆盖**（用生成后的
   `MemoryMapLib.c` 逐条比对得出），所以这是又一处未映射地址。
2. 但**没有任何模块的机器码里有指向 0x088E2000 页的 `adrp`**（新写的
   `scripts/find-mmio-reference.py` 扫完 FD 解压后的 106 个 PE 得到的结论），
   说明它不是编译进代码的寄存器基址，而是**算出来的指针**——继续猜基址没有意义。
3. `X20 = X23 = 0xCF8B0000` 与 `ELR = 0xCF8B6E60` 说明故障模块的加载基址是
   0xCF8B0000、故障点在该模块 +0x6E60 处；`ArmCpuDxe` 只是异常向量表的拥有者。

因此下一步不再改地址表，而是**把"哪个模块在跑"变成屏幕上的文字**：
新增 `UniXNUPkg/Driver/BootTraceDxe`，它做两件事——

- 每加载一个镜像就打印 `BT img <base> +<size> <文件名>`，崩溃前最后一行即肇事模块；
- 启动时直接回答几个"故障地址是否已映射"：`BT probe 0x088E2000 mapped/UNMAPPED`。

## 2026-11-10 21:00–21:20：从"USB 组崩溃"到"没有谁去启动菜单"（fd10–fd14）

这一段把 UEFI 阶段从"驱动崩溃"推进到"驱动全部装完、BDS 空转"，并定位了
真正卡住阶段 A 的那一环。

### fd10：把转储压成一行，暴露出第一个真凶
- 改动：`SiliciumPkg.dsc.inc` 里 `PcdDebugPrintErrorLevel` 从 `0x8007EE0F` 改为
  `0x0007EE0F`（清掉 bit31 == `DEBUG_ERROR`）。控制台只有约 40 行，原来
  `CpuExceptionHandlerLib` 的 60 行转储会把之前的 `Loading driver ...` 全部冲掉。
- 结果：屏幕只剩一行 `Synchronous Exception at 0x00000000CF8A6E60`，上面完整的
  装载记录第一次被保住。
- 归属判定：崩溃前最后一条装载记录是
  `Loading driver at 0x000CF89C000 EntryPoint=0x000CF89D000 UsbConfigDxe.efi`，
  `0xCF8A6E60` 落在 `[0xCF89C000, 0xCF89C000+0x16000)` 内，偏移 `+0xAE60`；
  且它紧跟在 `UsbConfigLib_pmic_npa_create_sync_client` 的几条消息后面。

### fd11：整组移除 USB 驱动后，装载一路走到底
- 改动：`Platforms/Xiaomi/shennongPkg/Include/APRIORI.inc` / `DXE.inc` 里注释掉
  11 个 USB 模块（`UsbPwrCtrlDxe`、`UsbfnDwc3Dxe`、`XhciPciEmulationDxe`、
  `XhciDxe`、`UsbBusDxe`、`UsbKbDxe`、`UsbMassStorageDxe`、`UsbMsdDxe`、
  `UsbDeviceDxe`、`UsbConfigDxe`、`UsbInitDxe`），模块数 107 → 96。
- 结果：`UsbConfigDxe` 那处崩溃不再出现，装载穿过 `ChargerExDxe`、`ButtonsDxe`、
  `TsensDxe`、`SimpleFbDxe`、`LimitsDxe`、`GpioDxe`、`UCDxe`、`RngDxe`、
  `SimpleTextInOutSerial`、`ConPlatformDxe`、`ConSplitterDxe` —— **BDS 已经在跑**。
- 备注：USB 对这条启动路径不是必需品（payload 来自 appended image，由
  `UniXNURamDiskDxe` 提供），所以移除它没有副作用。

### fd12：`gRT->SetVariable` 在本机会 fault
- `BootTraceDxe` 加了 NVRAM 探针后，屏幕上**没有** `BT nvram set` 那一行，
  紧随 `BT hook` 的就是 `BT SYNC … esr 0000000020000000 far …0 ec 0 iss 0`。
- 结论（推断，但证据链完整）：这台机器的变量写入路径不可用，而
  `UniXNUDxe` 当年的 Depex 是
  `gEfiVariableArchProtocolGuid AND gEfiVariableWriteArchProtocolGuid`，
  变量服务不可用 ⇒ 驱动永远不被 dispatch ⇒ 没有任何启动项 ⇒ BDS 空转。

### fd13：ReadyToBoot 是错的钩子（源码已证）
- 设计：`UniXNUDxe` 的 Depex 改 `TRUE`，在 **ReadyToBoot** 事件里
  `LoadImage` + `StartImage` 起 app。
- 结果：屏幕与 fd11 完全一样，没有 `UX entry`、没有 `UX startimage`。
- 源码核对：本树里 `EfiSignalEventReadyToBoot()` 全树只有一处调用——
  `Mu_Basecore/MdeModulePkg/Library/UefiBootManagerLib/BmLoadOption.c:1490`，
  而且被 `LoadOption->OptionType == LoadOptionTypePlatformRecovery` 包着。
  也就是说 **BootOrder 为空时 ReadyToBoot 根本不会触发**，这个钩子在 shennong
  上从设计上就不可能命中。

### fd14：改成"GOP 出现就启动应用"
- `UniXNUDxe` 入口先 `LocateProtocol(gEfiGraphicsOutputProtocolGuid)`：
  - 已有 GOP → 直接 `LoadImage` + `StartImage`；
  - 没有 → `CreateEvent(EVT_NOTIFY_SIGNAL)` + `RegisterProtocolNotify`，等
    `SimpleFbDxe` 装上 GOP 时在同一轮 dispatch 里启动。
- 注意（已修正的一个坑）：`CreateEventEx(..., &gEfiGraphicsOutputProtocolGuid, ...)`
  是**事件组**语义，对协议 GUID 永远不触发；协议通知必须用 `RegisterProtocolNotify`。
- 启动前把 `LoadedImage->LoadOptions` 显式设成 `L"unixnu:firmware"`，让应用知道
  自己是被固件拉起的，和当年 Boot#### 的 optional data 行为一致。
- 全过程直写屏状态：`UX entry` → `UX found app` → `UX gop hook <st>` →
  `UX image <st>` → `UX startimage <st> exit <code>`。

### fd15：应用终于被拉起来了，然后它自己踩空
- 改动：启动逻辑从 `UniXNUDxe` 整个搬进 `BootTraceDxe`（后者在 fd10–fd14 五次启动里
  每次都有 `BT START`，前者一次都没有）；删掉 VBAR 钩子；恢复
  `PcdDebugPrintErrorLevel = 0x8007EE0F` 让 DxeCore 的错误重新可见。
- 结果：屏幕第一次给出**完整原生异常转储**，内容与之前的"静默停住"完全不同：
  - `Synchronous Exception at 0x00000000D208B1E4`
  - `ESR 0x96000046` → EC `0x25`（同 EL 数据访问中止），ISS `0x46`：WnR=1、DFSC=0x06
    ⇒ **对 0x0880402C 的写操作触发二级翻译错误**
  - `FAR 0x0880402C`，`SP 0x00000000A764B910`
  - 结尾 `ASSERT [ArmCpuDxe] CpuExceptionHandlerLib.c(438)`
- 归属判断（**推断**）：`0xD208B1E4` 不在任何已知驱动基址区
  （`0xCF9xxxxx/0xCFAxxxxx/0xCFBxxxxx`），而 LoadImage 会把应用装到高地址，
  因此这一条很可能就是 `UniXNU.efi` 自身；即 fd15 的 "FV 探针 → LoadImage →
  GOP 通知 → StartImage" 链路真的跑通了。

### 「屏幕只有 40 行」这个天花板是可以拆的（源码已证）
- `FrameBufferSerialPortLib` 的行数 = `FB_HEIGHT / ((FONT_HEIGHT-4) * FontScale)`，
  `FontScale` 取自 `gSiliciumPkgTokenSpaceGuid.PcdFrameBufferFontScale`，`0` 表示
  自动（`shorterDim / 426`）。
- `shengPkg/sheng.dsc:82` 显式设成 `3`；**shennongPkg 之前没有设**，所以是自动值
  （约 3，一行字模放大三倍 ⇒ 约 40 行）。
- 结论：改一个 PCD 就能把可见行数放大三倍，转储与我们自己的日志首次可以同屏——
  这比继续盲改代码有价值得多。fd16 已按 `PcdFrameBufferFontScale|1` +
  `PcdFrameBufferDelay|30000` 构建下发。

### fd16：真凶浮出水面——`SdccDxe.dll`（证据：真机照片 ×4）
- 改动：`PcdFrameBufferFontScale|1` + `PcdFrameBufferDelay|30000`，
  `BootTraceDxe` 增加 `BT app image <base> size` 与 `BT gop fb <addr> res WxH` 打印。
- 结果：控制台行数放大三倍后，转储**第一次带上了模块归属表**，直接点名：

  ```
  Synchronous Exception at 0x00000000D208C1E4
  PC 0x0000D208C1E4 (0x0000D2084000+0x000081E4) [0] SdccDxe.dll
  PC 0x0000D2090A98 (0x0000D2084000+0x0000C9B8) [0] SdccDxe.dll
  PC 0x0000D208D05C (0x0000D2084000+0x0000905C) [0] SdccDxe.dll
  ...
  ESR : EC 0x25 IL 0x1 ISS 0x00000046 -> Data abort: Translation fault, second level
  FAR 0x00000000880402C
  ```

  即崩溃发生在这个厂商 SD 卡控制器驱动的 `+0x81E4`，对 `0x0880402C` 做**写**，
  该地址没有二级页表映射。与我们的 `UniXNU.efi` 无关；此前把 `0xD208B1E4`
  当成应用自身，是被"驱动基址都在 0xCF9/0xCFA 段"的旧假设带偏了——**SdccDxe
  就装在 0xD2084000**，说明 giulia 那批二进制驱动被装载到另一段地址。
- 结论（已验证）：从 fd10 起挡住 BDS 的"无名写异常"就是 SdccDxe；它也是最可能
  让 `UniXNUDxe` 一直没被 dispatch 的原因（同步异常把 CPU 停在了 CpuDeadLoop）。

### fd17：摘掉 SDCC 整条卡栈
- `APRIORI.inc:47`、`DXE.inc:71` 的 `SdccDxe.inf` 注释掉（我们从这个 boot image
  自带的 payload 起，不需要 SD 卡）。
- 预检 0 failure，`Mu-shennong-fd17.img` sha256 前缀 `67eb4f44`，22:16 下发。

### fd18：给应用装行级进度打印（黑屏可见化）
- 现象（用户口述，fd17）：出现小米 logo 后**整屏黑**，连异常转储都没有。
- 判断（推断）：不是死机，而是有人把帧缓冲清空后什么都没画上去——
  `Ui.c:719` 文本路径会 `ConOut->ClearScreen()`，图形路径会 `FillRect(0,0,W,H)`，
  两者都在"绘制前"把屏幕刷掉；若随后卡住，看到的就是纯黑。
- 改动：
  1. `UniXNULib` 新增 `UniXNUStage()`，用 **`SerialPortWrite()`**（= 帧缓冲控制台）
     直接写 `APP <阶段>`，绕开 `DebugLib` 掩码与尚未就绪的 `SerialIo`；
     `UniXNURun()` 沿途打 `enter/connect all/connected/config load/config done/
     inject drivers/acpi done/ui probe/ui ready`，`Ui.c` 在清屏与填充后各打一行。
  2. `FrameBufferSerialPortLib.GetFbPositions()` 增加游标纠偏：游标存在帧缓冲最后
     8 字节里，任何一次清屏/改模式都会把它变成噪声，**此后所有输出都画到屏幕外**，
     表面就是"黑屏但机器还活着"。现在越界即整屏清空并从左上角重来。
  3. `BootTraceDxe` 增加 `BT app start begin`，区分"没启动"与"启动了但没画"。
- 构建 fd18：预检 0 failure，`Mu-shennong-fd18.img` sha256 前缀 `8460f710`，22:55 下发
  （下发前确认设备在 fastboot，`fastboot devices` 有 `9f72e95c`，未变砖）。
