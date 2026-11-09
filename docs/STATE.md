# 项目状态（唯一事实源）

> 本文件在任何上下文压缩/会话丢失后都应先读。最后更新：2026-11-09 08:30

## 当前阶段

阶段 C **已打通**，内核能完整启动到一个点。已验证的两步：

1. **TCR 的 T0SZ 26→27**（payload 内常量 `0x22A51A251A`→`0x22A51A251B`，payload.img 偏移 `0x2428a8`，整镜像偏移 +2400256）—— 修好后内核第一次打印 panic，说明穿过了 MMU / `_arm_init` / `bsd_init`。
2. **去掉 `cs_enforcement_disable=1`**，只留 `amfi_get_out_of_my_way=1` —— AMFI panic 消失，内核跑完整 boot log 到 IONVRAM。

## 最新进展停在

内核启动日志停在 `IONVRAM` 之后（`NVRAM size is 8192 bytes`、`bankSize=0x2000`），之后没有输出。屏幕同时出现显示测试图案。

## 已做但未验证的两项配置对齐（提交 6fd201c、eff89c9）

- `CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"`（原 `source`）
- `CONFIG_XNU_EXTRA_LD_ARCHIVES` 强制链接 `libStorageBindings.a` + `libVerifiedRoot.a`（原为空）
- payload `kernel_args` 增加 `native-ufs-root=1`、`offline-apfs-load=1`、`-apfs_shared_datavolume`

依据是同 SoC 手机 nx769j 与 sheng 的配置对照；这两项直接影响 root volume 挂载。

## 镜像与工具

- `C:\Users\yoox\AppData\Local\Temp\Mu-t0sz-root.img`（sha256 `3561ff60a675b9ea`）—— 含 T0SZ 修复 + AMFI 参数修正 + root 挂载参数，但 **不含** storage archive 修复（那需要 CI 重新构建 payload）
- 组装方法：`Mu-*.img = 2400256 字节 ANDROID! 头 + payload.img`；改参数用 mcopy 取 `::/EFI/UniXNU/unixnu.toml`
- 自动引导：`/tmp/cycle-t0sz.sh`（日志 `/tmp/cycle-slot.log`），手机进入 fastboot 即自动 `fastboot boot`

## CI 构建（进行中）

- 分支 `stage-c-verified`（基于 origin/main，含本次全部改动），推送提交 `2b56b29`
- 构建触发方式：**workflow_dispatch 手动触发**（推送不会自动构建）
- workflow id `398420499`，本轮 run `42540875453`，监视日志 `/tmp/ci-watch.log`


## 2026-11-09 关键发现（MH_FILESET）

**加载器拒绝 kernels 的直接证据**：启动时菜单返回 `'shennong XNU native UFS' returned: Unsupported`。
比对 Mach-O 头：

| | 11-05 内核（能加载） | 11-08 内核（被拒） |
|---|---|---|
| cpusubtype | 0x0 | 0xc0000002 |
| filetype | 2 = MH_EXECUTE | 12 = MH_FILESET |
| 大小 | 52,068,352 | 94,552,064 |

根因链：`profiles/os/ios-27.0.1-24A446-iphone16pro/profile.toml` 里 `"arch" = "arm64e"`
→ arm64e 构建产出 MH_FILESET → UniXNU xnu 加载器只认 MH_EXECUTE → `Unsupported`。
11-05 能跑是因为那时用旧的 iPadOS 17.7.11 profile（arm64）。

**已做的改动（未验证）**：提交 `c88d25d` 把该 profile 的 `arch` 改为 `arm64`，
触发构建 run `42560655968`，期望拿回 MH_EXECUTE 内核。

## 尚未定论的事

昨晚日志停在 `IONVRAMCHRPHandler.cpp:unserializeImage:479`。**注意不要当成定论**：
同一份日志里有两条 `debug_log_init: Error: gPanicBase is still not initialized`，
说明日志系统本身没完全起来 —— 所以「没有后续输出」既可能是内核停住，
也可能只是**日志出不来了**。要等新内核上机后对比才知道。

## 2026-11-09 踩过的坑（避免重犯）

1. 照抄 11-08 payload 自带的 `unixnu.toml` 做镜像，丢了 `rd=md0-shennong`、多了四条调试参数
   → 复现 AMFI panic。**正确参数见上「最新镜像」一节的 good args。**
2. 早上改的两行 defconfig（`prelinked` 加密、nx769j 的两个 archive）让内核**链接失败**，
   未定义符号 `_source_corecrypto14_*` 与 `_native_verified_block_*`。已回退（提交 `c5c8422`）。
3. 组装脚本已加 `--args` 显式覆盖，不要再信任 payload 自带 toml。


## 2026-11-09 下午：加载器拒收的完整追查（重要，避免重复踩坑）

### 已证实的事实

1. 启动菜单对 11-08 内核的原文报错：`'shennong XNU native UFS' returned: Unsupported`。
2. 11-08 内核 Mach-O：`filetype=12`（MH_FILESET）、`cpusubtype=0xc0000002`（arm64e）、94,552,064 B。
   11-05 能正常加载的内核：`filetype=2`（MH_EXECUTE）、`cpusubtype=0x0`（arm64）、52,068,352 B。
3. `SEPARATE_KEXT_FILESET=0` 传给 XNU 构建 **无效**：产出的内核仍是 filetype=12（run 42563552297 已验证）。
4. 该构建里 `Build kernel` 步骤其实是 **成功** 的，内核产物（`shennong-kernel-1`）已上传；
   失败发生在之后的 `Build payload` 步骤，工具只认普通 ARM64，
   报 `ValueError: Only ordinary little-endian ARM64 is supported`。
5. 切 `arch = "arm64"` 后会卡在补丁：`architectural-timer-entry.patch` 针对 arm64e 的
   `osfmk/arm64/start.s` 上下文，arm64 下 `patch does not apply`。
6. **补丁系列的真实位置**（构建日志原文）：
   `unixnu/profiles/arch/arm64/patches/xnu/series:2` 引用 `unixnu/patches/xnu/...`。
   之前三轮改的 `patches/xnu/series`、`unixnu/patches/xnu/series` 都不是它。

### 当前做法（run 42570856051，提交 7a0864e）

工作流在构建前用 `find "$GITHUB_WORKSPACE" -path '*patches/xnu/series'` 把所有系列文件里的
`architectural-timer-entry` 行删掉（绝对路径，避免工作目录差异导致漏改）。
本地守护 `/tmp/auto3.sh` 会在构建结束后：
下载 `shennong-kernel-*` 产物 → 检查 `filetype==2` → 用 11-05 的 payload 换内核
→ 组装 192 MiB 镜像（2400256 字节头 + payload）→ `fastboot boot`。
失败或 filetype≠2 则 **不推机器**。

### 教训（写下来别再犯）

- 改 CI 前先看构建日志里 **原样打印的路径**，不要按目录结构猜。
- 相对路径在工作流各步骤里含义可能不同；用 `$GITHUB_WORKSPACE` 绝对路径。
- payload 打包工具只支持普通 arm64，arm64e 内核必须绕开它，本地自行打包。
- 内核能编出来 ≠ 能打包 ≠ 能被加载器接受，这三个环节要分别验证。

## 待办（按优先级）

1. 解决当前 rebase 冲突并推送，触发 CI 重建（带 storage archive 修复）
2. 新 payload 到手后打 T0SZ 补丁、组装镜像、真机验证
3. 若仍停在 NVRAM 之后，转向 UFS 驱动挂载路径排查

## 设备事实

- 设备 `9f72e95c`，无 Android 可启动（userdata 已是 iOS 根卷），只能长按电源 12 秒 → 音量下+电源进 fastboot
- panic 会画在屏幕上（`panic_screen` 生效），拍照即可读日志

## 2026-11-09 20:30 — 根因定案（有外部参考佐证）

### 结论
payload 里的 `Payloads/DarwinBoot.efi` **不会被固件派发**，因此实际运行的是**固件内置的旧 DarwinBoot**。
旧版不支持 arm64e fileset 内核（94 MB / filetype 12），对 11-08 内核返回 `EFI_UNSUPPORTED`；
11-05 的 donor kernelcache 是原厂 arm64 MH_EXECUTE（52 MB），旧版能接受，所以能跑到 IONVRAM。
这一条同时解释了今天所有现象（A–H），并解释了「改了 DarwinBoot.c 却没有反应」。

### 外部证据
- https://github.com/lee-kenneth/unixnu-nabu  HANDOVER.md「坑 6」：
  `LocateProtocol(gUniXNULoaderProtocolGuid)` 返回 Not Found，`Boot()` 一行都不执行，
  「所有 DarwinBoot 补丁『加了没反应』的元凶」。
- https://github.com/lee-kenneth/unixnu-nabu/blob/main/docs/firmware-patches.md：
  必须把 `INF DarwinBootPkg/Driver/DarwinBoot.inf` 并入**第一个** `APRIORI DXE {}` 块；
  单独新开块会 `GenFv ERROR 2000`。fdf 里不要内嵌 `unixnu.toml`（`Config->Volume` 恒 NULL）。

### 排除项（今日已用实测/编译验证）
- `ParseKernel` 接受两个内核（本机 gcc 编译真实源码，均返回 SUCCESS）
- `AdtNode` 在两个 ADT 上均成功，`ramdisk = 无节点`，窗口 256 MB
- 两镜像 payload 的非内核文件 md5 全一致；内核大小不是因素（补零到 94 MB 仍可启动）
- `CRYPTO_BOOTSTRAP="prelinked"` 在本树无法链接（缺 `_source_corecrypto14_original` /
  `_source_corecrypto14_start_once`，由 `OSKext::start` 引用），已回退为 `"source"`

### 待办（按顺序）
1. 从设备 `uefi_a` 分区导出原厂 UEFI 二进制（需要一次进 Android + adb root）
2. 以 `uefi-sheng/Platforms/Xiaomi/nuwaPkg` 为模板建 `shennongPkg`
3. APRIORI 第一块加入 DarwinBoot；fdf 保留 DarwinBoot、不内嵌 toml
4. `Resources/Configs/shennong.toml` 定 FD base/size（3 MB，勿放大）
5. CI 增加固件构建步骤，产出 `SILICIUM_UEFI.fd` → 打包 boot image → fastboot boot

## 2026-11-09 20:34 — 原厂 UEFI 分区已导出（TWRP 只读，未写分区）

用 TWRP 3.7.1_16-Xiaomi_14_Pro-A15 临时启动（`fastboot reboot recovery`，不写任何分区）读出：

```
adb shell dd if=/dev/block/sde1 of=/tmp/uefi_a.img bs=1M
adb pull /tmp/uefi_a.img
```

产物：`.work/uefi_a/uefi_a.img`，5,242,880 字节，md5 `237b02b052137cea7c75ec57c8a9625e`

结构（实测）：
- 头部是 ELF（`7f454c46`，ABL 引导程序）
- 偏移 0x1000 处是一个 FV，长度 0x2cd000（2.80 MB），HeaderLength 0x48
- FV 内含 `QcomPkg` / `UFS` / `Display` / `Usb` 等 ASCII 字样
- `UniXNU`、`DarwinBoot`、`BootShim` 均 0 次（原厂固件不含这些）

用途：这是 Mu-Silicium `Binaries/shennong`（高通底层 UEFI 驱动）的来源，
也是自己编 `shennongPkg` 固件的前置输入。

### 对照：现在用的 Mu-amfi.img 里的固件卷
- `kernel` 区（page 4096，offset 4096，size 2,393,623）是 gzip 流，解开得 3,145,920 字节
- 其中 FV 起始于解压后 0xc0，长度 0x300000（正好 3 MB）
- 该固件卷内 `DarwinBoot` 0 次 → 加载内核走的是 UniXNU 内置的 `RunXnu`

## 2026-11-09 21:40 — 固件加载器模块本地编译成功

不再依赖整平台编译：`UniXNUPkg` 与 `DarwinBootPkg` 都是平台无关的 EFI 模块，
用 EDK2 单独编即可。已实测通过。

### 环境
- EDK2：`microsoft/mu_basecore` @ cfb9372（`uefi-sheng` 的子模块，release/202608）
- 本机：`aarch64-linux-gnu-gcc` 13.3.0
- 依赖子模块：`BaseFdtLib/libfdt`、`MipiSysTLib/mipisyst`、`BaseTools/Source/C/BrotliCompress/brotli`
- BaseTools C 工具已编出：`GenFfs GenFv GenFw GenSec GenCrc32 EfiRom VfrCompile`

### 编译命令（UniXNU 包）
```
cd /home/yoox/UniXNU-framework/package
UNIXNU_EDK2=<edk2> UNIXNU_BUILD_DIR=<out> ./build.sh -b DEBUG -t GCC
```
产物（8 秒）：
```
Build/Out/AARCH64-DEBUG/UniXNU.efi            102,400
Build/Out/AARCH64-DEBUG/UniXNUDxe.efi          20,480   ← gUniXNULoaderProtocolGuid 提供者
Build/Out/AARCH64-DEBUG/UniXNURamDiskDxe.efi   24,576
```

### 模块 FILE_GUID（用于在固件卷里定位/替换）
```
DarwinBoot            1B64AF87-8415-4B57-9B16-680D70913B9F
UniXNU                9B665204-A133-47A2-9396-9E2B370A4E25
UniXNUDxe             29B950CF-586D-49EA-9D71-F88645CCDAF6
UniXNURamDiskDxe      75CA63AD-FBAE-4A06-92A0-F937C671251D
```

### 已确认的事实
- 整个 `uefi-sheng` 里只有 `Platforms/Xiaomi/shengPkg` 接了 DarwinBoot 与 UniXNU
  （`sheng.dsc:112-122`、`Include/DXE.inc:47-50`）；没有 SM8650（Pineapple）SoC 包，
  所以不可能从零编一整套 shennong 固件。
- `Mu-amfi.img` 的固件卷（3 MB）顶层只有 2 个 FFS：一个 PEI 核（65,464 B）和一个
  嵌套 FV 镜像（1,122,917 B，GUID-defined LZMA 段，data_off=24, attr=0x1）。
  四个 UniXNU 模块的 GUID 在该 3 MB 里**不出现**，说明它们在 LZMA 压缩段内部。

### 21:55 — DarwinBoot.efi 也编出来了
```
build/build/DarwinBoot/DEBUG_CLANGPDB/AARCH64/DarwinBoot.efi
```
关键：Mu 的 EDK2 用 **CLANGPDB** 工具链，不是 GCC5（`tools_def.template` 里没有 GCC5_AARCH64）。
`GCC5` 只适用于 `package/build.sh`（它内部自己设了 `GCC_AARCH64_PREFIX`）。

### 22:10 — 剩下的唯一障碍：固件卷里的 DXE 段解不开
顶层 FV 的第 2 个 FFS 是嵌套 FV 镜像，节类型 0x02，GUID =
`ee4e5898-3914-4259-9d6e-dc7bd79403cf`（**EFI_LZMA_CUSTOM_DECOMPRESS**），
DataOffset=24，Attributes=0x1。段数据 1,122,865 字节。

试过且失败的解码方式：
- `lzma.FORMAT_ALONE`（按 5+8 头）
- `lzma.FORMAT_RAW` + 从 payload[0]/[1]/[5] 取 props，skip 13/5
- 按 BigEndian 解读长度

段内前 24 字节：`01 08 20 6c 00 00 00 00 00 00 02 00 32 73 03 2a 98 84 36 fd fb ec ff db`

下一步（下次继续时从这里做）：
1. 用 EDK2 自己的解压实现（`Mu_Basecore/BaseTools/Source/C/Common/Decompress.c` +
   LZMA-SDK）编一个小 CLI，让它来解这段 —— 这是权威实现，格式细节以它为准。
2. 解开后应得到 DXE FV，再用四个 GUID 定位模块（见上表），替换成刚编出来的 .efi，
   重新压缩 + 修 section/FV 校验和。
3. 打包回 boot image（`scripts/repack-v0-bootimg.py`），`fastboot boot` 验证。

### 当前设备状态
- 手机在 fastboot（序列号 9f72e95c），可随时长按电源 12 秒关机
- TWRP 3.7.1 已刷在 recovery 分区，需要时 `fastboot reboot recovery` 进入
- userdata 里仍是 iPadOS 17.7.11 根卷（用户已确认可格式化重做）

### 22:30 — DXE 段解码仍无解，记录已排除的方式
试过并失败：`lzma.FORMAT_ALONE`、`lzma.FORMAT_RAW`（props 取自 payload[0]/[1]/[5]，skip 5/13）、
`xz -d --format=lzma`（skip 0/5/13）、EDK2 `LzmaCompress -d -e`（只做了编码）。
段内结构（1,122,865 字节）：
```
01 08 20 6c 00 00 00 00 00 00 02 00 32 73 03 2a 98 84 36 fd fb ec ff db
```
既不是标准 LZMA_ALONE 头，也不是 (size+props) 或 (props+size) 的常见排布。

### 关于时间线的实话
阶段 C→F（用户态）在同设备参考移植里用了数周。今晚/明天能达成的**最有价值的里程碑**是：
**让 arm64e 内核第一次真正被加载并跑起来（越过 Unsupported）**，然后才有 bsd_init / 根卷 / launchd。
不应该承诺 1-2 天内到 SpringBoard。

### 22:58 — 新线索：prelink 可能本来就支持 arm64e
`UniXNU-framework/docs/drivers/xnu-prelink.md` 第 11-14 行原文：

> For arm64e fileset kernel collections, `emit_prelink.py` selects the fileset
> emitter and generates a function/data map.

也就是说 **`emit_prelink.py` 明确支持 arm64e fileset**。那么工作流里那句
“its XnuPrelink reader rejects arm64e kernels” 指的应该是**另一个组件**
（很可能是 regression policy 的 reader / check_prelink_regressions），而不是 prelink 本身。

如果这一条成立，路径会比改固件短得多：
1. 让 `./unixnu build prelink` 在 arm64e 上真正跑通，产出 MH_EXECUTE 形态的 kernelcache
2. 现有固件的加载器**接受 MH_EXECUTE**（11-05 的 52 MB 原厂内核已实测能启动到 IONVRAM）
3. 完全不需要碰固件、不需要改加载器

下一步：读 `<unixnu>/kits/XnuPrelink/emit_prelink.py` 与 workflow 里 “Build prelink” 的真实失败输出，
确认拒绝到底发生在哪一步。（`kits/XnuPrelink/*.py` 不在 framework 仓库，在 CI 检出的 unixnu 目录里。）
