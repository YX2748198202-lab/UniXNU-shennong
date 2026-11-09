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

## 待办（按优先级）

1. 解决当前 rebase 冲突并推送，触发 CI 重建（带 storage archive 修复）
2. 新 payload 到手后打 T0SZ 补丁、组装镜像、真机验证
3. 若仍停在 NVRAM 之后，转向 UFS 驱动挂载路径排查

## 设备事实

- 设备 `9f72e95c`，无 Android 可启动（userdata 已是 iOS 根卷），只能长按电源 12 秒 → 音量下+电源进 fastboot
- panic 会画在屏幕上（`panic_screen` 生效），拍照即可读日志
