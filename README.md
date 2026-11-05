# UniXNU-shennong

Xiaomi 14 Pro（`shennong` / 23116PN5BC / SM8650 "pineapple"）的 UniXNU 移植工作树。

目标：在真实硬件上启动 Apple XNU 内核并运行 iOS 用户态，逐步恢复显示、触控、GPU 等硬件功能。
非模拟器、非主题仿制。

## 当前状态（2026-11-05）

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链与加载器（BootShim / FD / boot.img 打包）| ✅ 完成 |
| B | UEFI 实机（UniXNU 菜单稳定显示）| ✅ 完成（v6）|
| C | XNU 早期启动（AMFI / bsd_init / 内核栈）| ✅ **完成**：停在 `vfs_mountroot`（`IOKitBSDInit.cpp:984`）|
| D | 中断 / CPU / 内存 | ✅ 完成：ADT 换成板级树后 `/cpus` 正常认领，`AppleARMCPU` 不再 panic |
| E | UFS 驱动 + iOS 根卷 | 🟡 **存储栈已打通**，剩根窗口发布（见下）|
| F | 用户态（launchd / SpringBoard）| ⬜ 待开始 |
| G | 硬件功能（显示 / 触控 / GPU / Wi-Fi / 音频）| ⬜ 待开始 |

### 阶段 E 目前的位置

真机上已验证：UFS 控制器 / GCC / PHY 起来、SMMU 独占 bank 被接管、GPT 解析正确、
写进 `userdata` 的 SHNGROOT 卷读回（`magic=474e4853 544f4f52`、`manifest=0`、`windows=2`）、
两个根窗口 `prepared=2`。

唯一剩余门：驱动的 `configureVerification` / `validate` 要求 **owner 签名的根策略**才发布窗口。
已用本板自己的 RSA-3072 密钥生成策略（`policies/`），根卷内含匹配的哈希表对象；策略版内核
`Mu-policy12.img` 已启动，等待屏幕确认是否 `published=2`。

**完整过程、判读表与产物哈希见 [docs/handoff/UFS-E3-2026-11-05.md](docs/handoff/UFS-E3-2026-11-05.md)。**

## 设备现状（重要）

- 这台机器已**不再运行 Android**：`userdata` 分区现在是 iOS 根卷（约 9.46 GB），
  `/sdcard` 与全部用户数据已随写入被覆盖。
- 想恢复 Android 只能线刷官方 HyperOS 包，而那会再次覆盖这个根卷。
  细节与分区备份说明见 [docs/recovery.md](docs/recovery.md)。
- 日常验证：`fastboot boot <镜像>` 临时启动，不写引导分区。分区写入只有经明确授权的
  `userdata` 写入这一项。

## 接手请读

- [docs/handoff/UFS-E3-2026-11-05.md](docs/handoff/UFS-E3-2026-11-05.md) —— 阶段 E 现状、根策略机制、逐轮设备证据、产物哈希、复现命令、下一步判读
- [docs/bringup.md](docs/bringup.md) —— 各阶段的实机记录（UEFI 迭代、XNU 启动、UFS）
- [docs/handoff/ARTIFACTS.md](docs/handoff/ARTIFACTS.md) —— 产物清单与 sha256、为何二进制不入库、如何重建
- [docs/hardware.md](docs/hardware.md) —— 实测硬件清单（地址、时钟、UFS/SMMU 事实）
- [docs/handoff/BRINGUP-STATUS.md](docs/handoff/BRINGUP-STATUS.md) —— 历史结论与已废弃路线（别再走）

## 本仓库包含

```
board.toml                    # 设备配置（schema_version 2）
configs/shennong_defconfig    # XNU 内核配置
.github/workflows/kernel.yml  # CI：macOS 构建 kernel + payload、量取绑定、构建根策略
dts/shennong.dts              # 板级设备树源
feeds.toml                    # SoC feed（UniXNU-sm8550-common 固定 commit）
package/                      # 板级 C/C++ 组件（PMGR、BootProgress、FatVolume…）
patches/xnu/series            # 板级 XNU patch 序列
patches/ufs-*.patch           # 打进 tree 的 UFS 驱动补丁（SMMU 接管）
policies/                     # 本板的根策略签名头与公钥（私钥不入库）
scripts/                      # 打包、改参、绑定测量、策略生成、根卷对象追加
docs/                         # 进度、实机记录、硬件清单、恢复方案
```

> UEFI 固件（Mu-Silicium shennongPkg）**不在本仓库**。CI 也不产出 boot image：
> 它只产出 `kernel.macho` 与 `payload.img`，boot image 由 `scripts/repack-v0-bootimg.py`
> 用固定模板重打包。

## 构建

内核与 payload 在 GitHub Actions 上构建（macOS runner）：

```
Actions → "kernel" → Run workflow
```

产物包含 `kernel.macho`（prelink 后的 XNU，含 kext）、`payload.img`（ADT + kernel +
unixnu.toml 的 192 MiB FAT 卷），以及 `storage-bindings`（从原厂 kernelcache 量出的
IOStorageFamily 槽位表）。

## 版权与合规

本仓库不包含 Apple 固件（IPSW）、OEM 二进制或设备唯一数据，也不包含签名私钥。
所有 Apple 组件需用户自行从 Apple 官方渠道获取并在本机使用。

## 参考与致谢

- [UniXNU](https://github.com/UniXNU/UniXNU) — 移植框架、XNU 补丁、DarwinBoot、ADT 生成
- [UniXNU-houji](https://github.com/lonzzi/UniXNU-houji) — 同 SoC（SM8650）参考设备
- [Project Silicium / Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium) — UEFI 驱动框架
- Apple 开源的 XNU 与相关组件
