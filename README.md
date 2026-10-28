# UniXNU-shennong

Xiaomi 14 Pro（`shennong` / 23116PN5BC / SM8650 "pineapple"）的 UniXNU 移植工作树。

目标：在真实硬件上启动 Apple XNU 内核并运行 iOS 用户态，逐步恢复显示、触控、GPU 等硬件功能。
非模拟器、非主题仿制；全程 `fastboot boot` 临时启动，不写系统分区。

## 当前状态（2026-10-28）

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链与加载器（BootShim / FD / boot.img 打包）| ✅ 完成 |
| B | UEFI 实机（UniXNU 菜单稳定显示）| ✅ 完成（v6）|
| C | XNU 早期启动（AMFI / bsd_init / 内核栈）| ✅ **完成**：到达 `Failed to mount root device @IOKitBSDInit.cpp:984` |
| D | 中断 / CPU / 内存 | 🟡 stage 探针与 CPU0 已通过，8 核拓扑待验证 |
| E | UFS 驱动 + iOS 根卷 | 🟡 进行中：NativeUfs 接入 CI 构建，根卷镜像已生成 |
| F | 用户态（launchd / SpringBoard）| ⬜ 待开始 |
| G | 硬件功能（显示 / 触控 / GPU / Wi-Fi / 音频）| ⬜ 待开始 |

关键里程碑证据见 [docs/bringup.md](docs/bringup.md)。

## 本仓库包含

```
board.toml                 # 设备配置（format1，UniXNU CLI 直接可用）
configs/shennong_defconfig # XNU 内核配置
.github/workflows/kernel.yml # CI：macOS 构建 kernel + payload
dtb/                       # 合并后的板级设备树（base + overlay）
uefi/Platforms/Xiaomi/shennongPkg/ # UEFI 固件包（基于 LanaiPkg SM8650 层）
tools/                     # 二进制补丁、打包与验证脚本
docs/                      # 进度、实机记录、硬件清单、恢复方案
```

## 构建

内核与 payload 在 GitHub Actions 上构建（macOS runner，Xcode 26.6）：

```
Actions → "shennong kernel" → Run workflow
```

产物包含 `kernel.macho`（prelink 后的 XNU，含 kext）与 `payload.img`（ADT + kernel + unixnu.toml FAT 卷）。
boot.img 组装方式与参考设备一致：**header v0 + gzip(BootShim+FD) + append_dtb**，`fastboot boot` 直接启动。

UEFI 固件在本机（aarch64 Linux）构建：

```
bash tools/build_shennong_uefi.sh DEBUG
```

## 使用前提

- Bootloader 已解锁（本机检测显示的上锁状态为伪上锁模块所致，实际可用 fastboot）
- 只用 `fastboot boot` 临时启动，**不刷写任何分区**
- 测试前确认设备可随时长按电源 10 秒强制重启回 Android

## 参考与致谢

- [UniXNU](https://github.com/UniXNU/UniXNU) — 移植框架、XNU 补丁、DarwinBoot、ADT 生成
- [UniXNU-houji](https://github.com/lonzzi/UniXNU-houji) — 同 SoC（SM8650）参考设备，已验证 UFS/HFSX 根卷与 iOS 桌面
- [Project Silicium / Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium) — UEFI 驱动框架
- Apple 开源的 XNU 与相关组件

## 版权与合规

本仓库不包含 Apple 固件（IPSW）、OEM 二进制或设备唯一数据。所有 Apple 组件需用户自行从 Apple 官方渠道获取并在本机使用。
