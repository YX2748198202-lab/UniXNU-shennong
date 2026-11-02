# UniXNU-shennong

Xiaomi 14 Pro（`shennong` / 23116PN5BC / SM8650 "pineapple"）的 UniXNU 移植工作树。

目标：在真实硬件上启动 Apple XNU 内核并运行 iOS 用户态，逐步恢复显示、触控、GPU 等硬件功能。
非模拟器、非主题仿制；全程 `fastboot boot` 临时启动，不写系统分区。

## 当前状态（2026-11-02）

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链与加载器（BootShim / FD / boot.img 打包）| ✅ 完成（CI 最近 run #87 成功）|
| B | UEFI 实机（UniXNU 菜单稳定显示）| ✅ 完成（v6）|
| C | XNU 早期启动（AMFI / bsd_init / 内核栈）| ✅ **完成**：内核实际运行，曾到过 `IOKitBSDInit.cpp:984` |
| D | 中断 / CPU / 内存 | 🟡 stage 探针与 CPU0 已通过；`/cpus` 被原厂 `AppleARMCPU` 抢走（`AppleARMCPU.cpp:111`）|
| D2 | 修法 B：改写 `AppleARMCPU` personality 的 `IONameMatch` | 🟡 工具已实现并离线自检，**等真机确认** |
| E | UFS 驱动 + iOS 根卷 | 🟡 NativeUfs 接入 CI；静态符号表路线已证伪 |
| F | 用户态（launchd / SpringBoard）| ⬜ 待开始 |
| G | 硬件功能（显示 / 触控 / GPU / Wi-Fi / 音频）| ⬜ 待开始 |

关键里程碑证据见 [docs/bringup.md](docs/bringup.md)。

**下一步（需要真机，当前会话没有设备）**：

```bash
adb pull /sdcard/Download/Mu-shennong-smp.img .
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img --check
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img \
    --out Mu-shennong-xpu.img --report Mu-shennong-xpu.json
fastboot boot Mu-shennong-xpu.img          # 只启动，不写任何分区
```

背景见 [BRINGUP-STATUS.md 第 3 节](docs/handoff/BRINGUP-STATUS.md)：
`sheng-smp=1` 在单 CPU 的 ADT 上不可能改变 `cpu0` 的驱动归属，所以改用上游
rmx1971/sirius 验证过的 `IONameMatch cpu -> xpu`。

> **接手 / 继续移植请先读这三份**：
> - [docs/handoff/BRINGUP-STATUS.md](docs/handoff/BRINGUP-STATUS.md) —— 当前真实进度、panic 根因、**已证伪的路线**（别再走）、剩余步骤
> - [docs/handoff/ARTIFACTS.md](docs/handoff/ARTIFACTS.md) —— 产物清单与 sha256、二进制为何不入库、本地重建产物与打补丁的方法
> - [docs/handoff/VERIFICATION-2026-11-02.md](docs/handoff/VERIFICATION-2026-11-02.md) —— 最近一轮的实测命令、输出与哈希（区分已实测/推断/未验证）

## 本仓库包含

```
board.toml                    # 设备配置（schema_version 2）
configs/shennong_defconfig    # XNU 内核配置（MOCKFS 已开）
.github/workflows/kernel.yml  # CI：macOS 构建 kernel + payload + AppleARMCPU 补丁
dts/shennong.dts              # 板级设备树源（真实 DTB 转出）
feeds.toml                    # SoC feed（UniXNU-sm8550-common 固定 commit）
package/                      # 板级 C/C++ 组件（PMGR、BootProgress、FatVolume…）
patches/xnu/series            # 板级 XNU patch 序列（当前为空）
scripts/                      # 打包、改参、抽 payload、AppleARMCPU 补丁、静态探针
docs/                         # 进度、实机记录、硬件清单、恢复方案、验证记录
```

> UEFI 固件（Mu-Silicium shennongPkg）**不在本仓库**，也不在 `uefi-sheng@sheng`：
> 该 checkout 的 `Resources/Configs/` 有 87 个机型但没有 `shennong.toml`。
> 这也是 CI 里暂时无法自动产出 boot image 的原因（详见 ARTIFACTS.md 4.3）。

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
