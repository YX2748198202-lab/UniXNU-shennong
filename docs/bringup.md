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

下一步判读用 `Mu-ladder.img`：同一批调用点上各画一条 1/16 高的色带
（白=fileset 签名、红=PE_init_platform、黄=CPU 拓扑、青=cpu_init、橙=processor_bootstrap、
柠檬绿=到达 arm_vm_init）。照片上最高的那条色带就是内核走到的地方；这条路线不阻塞，
拍一张照片即可，不需要实时观察。

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
