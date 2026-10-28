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

| 版本 | 现象 | 根因 | 修复 |
|---|---|---|---|
| Mu-shennong-1 | 菜单 `no boot entry found` | 用了 header v4，`fastboot boot` 场景 ABL 无 vendor_boot DTB，initrd 传不进 | 改 header v0 + gzip + append_dtb（与参考设备一致）|
| Mu-shennong-2-v0 | 菜单出现 `1 shennong XNU first entry ... xnu`，DarwinBoot 输出 ID_AA64MMFR0/PFR0，画面静止 | XNU 输出走 serial，无显示驱动 | 加 panic screen + stage 探针 |
| Mu-shennong-3-v0-panic | 蓝色/绿色 stage 条 + `AMFI: No PMGR?` @ConfigurationSettings.cpp:235 + 内核栈 | AMFI 需要 provider-less ApplePMGRNub | 引入 ShengPlatformPower（provider-less nub）|
| Mu-shennong-5-pmgr | 三段 stage 条全出，仍 `No PMGR?` | `sheng-pmgr=2` 启动参数未传（本地手工 payload 遗漏）| 更新 unixnu.toml |
| Mu-shennong-6-pmgr2 | **`Failed to mount root device @IOKitBSDInit.cpp:984`，pages/free 正常** | 无根文件系统（预期）| — |

**阶段 C 里程碑**：XNU 完成入口、MMU、IOKit、Platform Expert、AMFI、bsd_init 全流程，停在 vfs_mountroot。
与 UniXNU 官方参考设备（sirius/sheng）的记录完全一致。

## 阶段 E：UFS 与根卷

- 采用 NativeUfs（UniXNU/ShengUfs，SM8550 起源）
- 寄存器核对：SM8650 与 SM8550 的 UFS GCC 偏移完全一致（GDSCR 0x77004 / MEM_PHY 0x9e000 / AXI 0x77018 / AHB 0x77024 / ICE 0x77074 / AGGRE 0x770e4 / UNIPRO 0x77068）
- SMMU：UFS stream ID 0x60（与 houji 实测一致）
- 根卷：`unixnu userdata` 从 iPadOS 17.7.11（21H461）IPSW 提取 OS + Cryptex1,SystemOS，生成 8.74 GiB 的 `SHNGROOT` 卷（本地生成，未写设备）

## 构建环境

- 内核：GitHub Actions macOS runner（Xcode 26.6），UniXNU main + device repo
- UEFI：本机 aarch64 Linux（PRoot Ubuntu 24.04），BaseTools 源码编译
- 已知 CI 注意点：
  - format1 的 `[kernel].archives` 只接受脚本名，`component:` 语法属于 format2
  - PMGR archive 需在正式 kernel pass 前预构建（bootstrap pass 就会引用 `sheng_pmgr_run`）
  - defconfig 必须含 `CONFIG_XNU_BUILD_ARCHIVES=y`
