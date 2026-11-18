# UniXNU-shennong

Xiaomi 14 Pro（`shennong` / 23116PN5BC / SM8650 "pineapple"）的 UniXNU 移植工作树。

目标：在真实硬件上启动 Apple XNU 内核并运行 iOS 用户态，逐步恢复显示、触控、GPU 等硬件功能。
非模拟器、非主题仿制。

## 当前状态（2026-11-18，基线 fi139）

> 供体：A–E 的验收在 **iPadOS 17.7.11（21H461，arm64）** 上完成；2026-11-07 起供体改为
> **iPhone17,1 iOS 27.0.1（24A446，arm64e，XNU 12377.121.6）**。表格里没写 iOS 27 的 ✅
> 只代表 iPadOS 供体，不代表当前目标。
>
> 权威状态以 [docs/STATE.md](docs/STATE.md) 为准，本文只做门面摘要。

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链与加载器（BootShim / FD / boot.img 打包）| ✅ 2026-11-08 复验（iOS 27 payload：`drivers 1 loaded / 0 failed` + handoff）|
| B | UEFI 实机（UniXNU 菜单稳定显示）| ✅ 完成（v6）|
| C | XNU 早期启动（AMFI / bsd_init）| 🟡 **iOS 27 供体已越过 `_early_random`（`0xb477534`）与 `_machine_startup`（`0xb477550`）调用点**，当前停在后续内核初始化的 `_ledger_template_finalize` 常量段断言（fi138 暴露、fi139 已修，fi139 停点待画面判读）。历史 iPadOS 供体停在 `vfs_mountroot`（`IOKitBSDInit.cpp:984`）——这条是另一条线的成绩，与当前进度分开记。**阶段 C 仍未通过** |
| D | 中断 / CPU / 内存 | 🟡 iPadOS 供体验收（ADT 板级树后 `/cpus` 正常）；iOS 27 待复核 |
| E | UFS 驱动 + iOS 根卷 | 🟢 iPadOS 供体根窗口已发布（`published=2`）；iOS 27 需重做根卷与策略 |
| F | 用户态（launchd / SpringBoard）| ⬜ 待开始 |
| G | 硬件功能（显示 / 触控 / GPU / Wi-Fi / 音频）| ⬜ 待开始 |

### 最新进展（fi136–fi139，2026-11-18）

1. **启动种子契约**（fi137）：ADT 的 `chosen/random-seed` 原来是 64 字节，ARM XNU 要 256 字节，
   fi136 因此停在 `early_random`。生成器改用系统 CSPRNG 直接给 256 字节，扩展脚本改为严格节点解析
   加只读 `--check`，CI 在 ADT 生成后和 FAT 回读后各加一处守卫——原来是「生成件与回读件一致就算过」，
   两边同为 64 也能通过。
2. **fatal 观察器**（fi136b/fi138）：异常向量与 panic 两条通路都挂上钩子，把
   `PC/ESR/FAR/SPSR` 和来源标签画到屏幕。此前只看颜色，「屏幕没变」分不清「没进内核」和
   「进了但走了别的通路」。
3. **ledger 常量段契约**（fi139）：常驻段改造把三个 ledger 模板搬进 `__PORT_CONST`，而
   `ledger.c` 的段归属检查只认 `__DATA_CONST`，fi138 停在
   `_ledger_template_finalize.cold.2+0xc` 的 `BRK #0xbffc`。修的是契约不是删检查：源码里
   三处内联调用点（`finalize`、`copy` 的目标与源）全部覆盖，原有三条断言、原 PAC 栈帧、
   原失败调用点一律保留，只改 3 条入口分支共 12 字节。

fi139 镜像 SHA256 `33b9ba83e1b6f2d640226e4d76ba329c9da0d385bb204a4a8025faf80b649727`，
内核 `c09c4b0970d364dfe38b838389d47b29eeb83347cfea0f6cec5b037af4cac8c5`，
相对已启动的 fi138 内核只动了 359 字节。已于 2026-11-18 17:36:53 对 `9f72e95c` 执行唯一一次临时 boot，返回 0。
**但本次屏幕证据尚未取得，据此不判断是否越过 ledger，也不把阶段 C 记为通过。**

2026-11-08 那轮的结论（阶段 A 的 `start failed` 根因是出厂固件占用 loader 协议；进度屏本来就是开的，
真因是内核没走到 `_machine_startup`；pstore 不可用、可用 NativeUfs 日志窗口）作为历史保留，
判读规则与 13 色带镜像见 [docs/bringup.md](docs/bringup.md) A.5。

### 阶段 E 目前的位置（iPadOS 供体，历史记录）

真机已验证：UFS 控制器 / GCC / PHY 起来、SMMU 独占 bank 被接管、GPT 解析正确、
写进 `userdata` 的 SHNGROOT 卷读回（`magic=474e4853 544f4f52`、`manifest=0`、`windows=2`）、
两个根窗口通过 owner 签名策略校验并发布为 IOMedia：

```
NATIVE_UFS media report: published=2 reads=142 failures=0 media=7
disk1s1 uuid=8846FE78-2910-42…   ← 与 SystemOS 策略 UUID 一致
disk3s1 uuid=04769D26-2CA0-4…    ← 与 OS 策略 UUID 一致
disk2  GUID_partition_scheme / disk2s1 7C3457EF-… (APFS)
```

下一步：`native-ufs-root=1` 让 XNU 真正挂载根卷。

**完整过程、判读表与产物哈希见 [docs/handoff/UFS-E3-2026-11-05.md](docs/handoff/UFS-E3-2026-11-05.md)。**

## 设备现状（重要）

- 这台机器已**不再运行 Android**：`userdata` 分区现在是 iOS 根卷（约 9.46 GB），
  `/sdcard` 与全部用户数据已随写入被覆盖。这是 2026-11-05 写入时的状态；此后只做
  `fastboot boot` 临时启动，未再写任何分区，该结论仍成立。
- 想恢复 Android 只能线刷官方 HyperOS 包，而那会再次覆盖这个根卷。
  细节与分区备份说明见 [docs/recovery.md](docs/recovery.md)。
- 日常验证：`fastboot boot <镜像>` 临时启动，不写引导分区。分区写入只有经明确授权的
  `userdata` 写入这一项。
- 每个镜像配一份新的 256 字节种子，同一镜像不重复启动；`fastboot` 返回 0 只表示交接完成，
  不表示内核前进。

## 接手请读

按顺序：

- [docs/STATE.md](docs/STATE.md) —— **权威状态**，随阶段推进更新：现在停在哪、已验证事实、两条 PAC 硬规则、下一步
- [docs/research/fi139-ledger-2026-11-18/](docs/research/fi139-ledger-2026-11-18/EVIDENCE.md) —— 最近一轮的证据（分「已命令确认 / 只能看图 / 不知道」三类）、[验收 14 项](docs/research/fi139-ledger-2026-11-18/P0-EXEC.yml)、[结论与下一步](docs/research/fi139-ledger-2026-11-18/RESULTS-AND-NEXT.md)
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
