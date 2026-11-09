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

## 待办（按优先级）

1. 解决当前 rebase 冲突并推送，触发 CI 重建（带 storage archive 修复）
2. 新 payload 到手后打 T0SZ 补丁、组装镜像、真机验证
3. 若仍停在 NVRAM 之后，转向 UFS 驱动挂载路径排查

## 设备事实

- 设备 `9f72e95c`，无 Android 可启动（userdata 已是 iOS 根卷），只能长按电源 12 秒 → 音量下+电源进 fastboot
- panic 会画在屏幕上（`panic_screen` 生效），拍照即可读日志
