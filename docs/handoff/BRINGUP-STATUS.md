# 移植状态报告

最后更新：2026-11-08
设备：Xiaomi 14 Pro / `shennong` / `23116PN5BC` / SM8650 (pineapple) / 12 GB RAM
仓库：https://github.com/Y2748198202-lab/UniXNU-shennong

> 本文件是**状态索引与历史结论**。阶段 E 的逐轮设备证据、根策略机制和产物哈希在
> [UFS-E3-2026-11-05.md](UFS-E3-2026-11-05.md)，各阶段实机记录在
> [../bringup.md](../bringup.md)。
>
> **供体说明**：A–E 的验收发生在 **iPadOS 17.7.11（21H461，arm64）** 供体上；
> 2026-11-07 起供体改为 **iPhone17,1 iOS 27.0.1（24A446，arm64e，XNU 12377.121.6）**。
> 下表的 ✅ 若没有注明 iOS 27，就只代表 iPadOS 供体。

## 当前位置

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链与加载器 | ✅ 2026-11-08 复验（iOS 27 payload：`drivers 1 loaded / 0 failed` + handoff）|
| B | UEFI 实机（菜单稳定）| ✅ v6 |
| C | XNU 早期启动到 `vfs_mountroot` | 🟡 iPadOS 供体 2026-11-05 已验收；iOS 27 供体卡在 `_arm_init` 早期（探针定位，待梯级色带照片判读）|
| D | 中断 / CPU / 内存 | 🟡 iPadOS 供体验收；iOS 27 待同条件复核 |
| E | UFS 驱动 + iOS 根卷 | 🟡 存储栈已通，剩根窗口发布（iPadOS 根卷语义，iOS 27 需重做根卷/策略）|
| F | 用户态（launchd / SpringBoard）| ⬜ |
| G | 硬件功能（显示 / 触控 / GPU / 网络 / 音频）| ⬜ |

阶段 C 的验收判据：屏幕出现 `Failed to mount root device @IOKitBSDInit.cpp:984`，
即 XNU 走完 AMFI / bsd_init / IOKit / Platform Expert，停在 `vfs_mountroot`。

## 2026-11-08 本轮记录（iOS 27 供体）

| 项 | 结果 | 依据 |
|---|---|---|
| 阶段 A（loader）| ✅ 通过 | 照片：`drivers 1 loaded / 0 failed`、`hand-off to the kernel`；修复提交 `4484825`（卸载旧协议实例再安装）|
| 交接后内核输出 | ⬜ 无输出，原因已定位 | 构建日志 `42462550406`：`XNU_BOOT_PROGRESS env: unset`，`boot_progress_*` 全是空操作 |
| 诊断内核 | 🔄 run `42468975624` 构建中 | 提交 `4f12b68` 设 `XNU_BOOT_PROGRESS: '1'` |
| 后续判读 | 红方块=到了 `initialize_screen`；无红方块=更早的 `arm_vm_init` 段 | [../bringup.md](../bringup.md) A.3 |
| 持久日志（pstore 等价物）| 📋 方案已定，未接线 | houji 实测 pstore 不可用；走 NativeUfs 日志窗口 + 重启后读回（[../bringup.md](../bringup.md) A.4）|

> 结论：现在**没有证据**说明 iOS 27 的 XNU 能走到阶段 C；iPadOS 时期的阶段 C/D 记录
> 只作历史参考。2026-11-08 的入口探针把卡点缩小到 `_arm_init` 早期
> （`_machine_startup` 之前，且 stage-3 证明入口代码已执行），
> 下一张 `Mu-ladder.img` 的照片会读出具体停在哪个里程碑，判读表见
> [../bringup.md](../bringup.md) A.5。


## 历史结论（仍然成立，值得先读）

### 1. `AppleARMCPU` 会前缀匹配 `cpu0`

`AppleARMPlatform.kext` 里 `AppleARMCPU` 的 `IONameMatch = "cpu"` 是前缀匹配，会认领
设备树里任何 `cpu` 节点；一旦它拿到 `/cpus`，就会在 `AppleARMCPU.cpp:111` panic。

**最终解法**：把 payload 的 ADT 换成板级自建树（`scripts/make-shennong-adt.py`，
只有 `cpu0` 与必要属性），而不是改 personality。这条修法在 2026-11-05 真机验收通过。

### 2. 静态符号表查找路线彻底证伪

内核里的 IOStorageFamily 绑定符号是**绝对地址**，不是 import；正确做法是从原厂
kernelcache 量出 190 个槽位，再按 `[kernel.prelink] slide` 平移后落到库里
（`scripts/scan-prelink-storage.py` + `scripts/apply-prelink-slide.py`）。

**陷阱**：构建出的 `kernel.macho` 符号表里仍然是**未重定位的原厂地址**，用它核对会
得出「pin 正确」的错误结论。要核对就去找字节：IOStorageFamily 的代码段在构建镜像里
位于 `0xfffffff00496c000`（原厂 kernelcache 是 `0xfffffff00596c000`，正好 slide 16 MiB）。

### 3. `sheng-smp=1` 改变不了 `cpu0` 的归属

它只影响副核心。历史交接里把它当成 `AppleARMCPU.cpp:111` 的修法是错的。

### 4. `gdb-stop.json` 不是地址来源

它记录的是断点现场，不是内核符号布局；用它推地址会错。

## 已废弃的路线（别再走）

| 路线 | 为什么废弃 |
|---|---|
| `xpu` 单字节补丁（`cpu`→`xpu`）| 只是掩盖 `AppleARMCPU` panic；ADT 修好后再也不需要，且会让 `cpu0` 无人认领 |
| 用 `NATIVE_VERIFIED_BLOCK=0` 或改源码绕过根策略 | 驱动被设计成必须 owner 签名；绕过只会卡在 `validate()`，`prepared=2` 后仍然 `published=0` |
| 只改编译宏不删归档 | 归档按源码时间戳重编，宏改了但 `libShengUfs.a` 不变，等于没改 |
| 相对路径跑绑定扫描 | 扫描器需要 tree 内的绝对路径 |
| Windows `fastboot.exe` 直接刷 | 本机没有 WinUSB 绑定，看不到设备；走 WSL + usbip |

## 文档索引

| 文档 | 内容 |
|---|---|
| [UFS-E3-2026-11-05.md](UFS-E3-2026-11-05.md) | 阶段 E 现状、根策略、逐轮证据、产物、复现、判读表 |
| [ARTIFACTS.md](ARTIFACTS.md) | 产物清单、哈希、本地必须保留的东西、重建步骤 |
| [STAGE-C-2026-11-04.md](STAGE-C-2026-11-04.md) | 阶段 C 验收记录（历史）|
| [VERIFICATION-2026-11-02.md](VERIFICATION-2026-11-02.md) | 2026-11-02 的实测记录（历史）|
| [../bringup.md](../bringup.md) | 各阶段实机记录 |
| [../hardware.md](../hardware.md) | 实测硬件清单 |
| [../recovery.md](../recovery.md) | 设备现状与恢复 Android 的路径 |
