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
