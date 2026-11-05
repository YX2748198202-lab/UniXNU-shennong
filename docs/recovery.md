# 恢复方案

## 现在的设备状态（2026-11-05）

- **这台机器已经不再运行 Android。** `userdata` 分区被写成了 iOS 根卷（SHNGROOT，
  约 9.46 GB），原来的 236 GB 用户数据（含 `/sdcard`）随写入被覆盖。
- 设备上不存在「随时回 Android」的路径了：panic 屏后只能长按电源重启进 fastboot，
  没有可启动的 Android 系统。

## 恢复 Android 的唯一路径

线刷官方 HyperOS 完整包（会重建 super / userdata）：

```
fastboot flash super super.img          # 官方包里的大分区
fastboot flash userdata userdata.img    # 或让官方脚本处理
# 官方 flash 脚本会把 boot/init_boot/vendor_boot/dtbo/vbmeta 等一并写回
```

注意两点：

1. 线刷会**再次覆盖 iOS 根卷**，即恢复 Android 就丢掉当前阶段 E 的进展
   （根卷可以从 IPSW 重新生成，见下）；
2. 恢复完成后若要继续 iOS 移植，需要重新执行 `fastboot flash userdata <根卷镜像>`。

## 根卷可以重建

根卷不是唯一副本：`unixnu userdata` 能从本机的 iPadOS 17.7.11 (21H461) IPSW 重新生成，
再用 `scripts/add-root-policy-objects.py` 追加两个策略对象。流程见
[handoff/UFS-E3-2026-11-05.md](handoff/UFS-E3-2026-11-05.md)。

## 分区备份（2026-10-28 采集）

87 个分区的只读备份保存在本机 `backups/partitions/`（约 2.0 GB，不入仓库）：

| 类别 | 分区 |
|---|---|
| 引导 | boot_a/b、init_boot_a/b、vendor_boot_a/b、dtbo_a/b、recovery_a/b |
| 校验 | vbmeta_a/b、vbmeta_system_a/b |
| 设备唯一 | persist、misc、fsg、fsc、modemst1、modemst2、devinfo、cdt、connsec、secdata、bk01–bk07、bk51 |
| 通信 | modem_a/b、modemfirmware_a/b、dsp_a/b、bluetooth_a/b |
| 固件链 | xbl_a/b、xbl_config_a/b、xbl_ramdump_a/b、abl_a/b、aop_a/b、aop_config_a/b、devcfg_a/b、hyp_a/b、tz_a/b、keymaster_a/b、qupfw_a/b、cpucp_a/b、cpucp_dtb_a/b、shrm_a/b、multiimgoem_a/b、multiimgqti_a/b、qweslicstore_a/b、spuservice_a/b、uefi_a/b、uefisecapp_a/b、uefivarstore |
| 其它 | imagefv_a/b、storsec、toolsfv、vm-bootsys_a/b、vm-persist、mdcompress |

另含 6 个 LUN（sda–sdf）的 GPT 头备份与 `partitions.sha256` 校验清单。
这些备份在本机，不在设备上，因此不受 `userdata` 覆盖影响。

## 安全边界（本项目一直在守的规则）

- 日常验证只用 `fastboot boot` 临时启动，不写引导分区
- 唯一允许的分区写入是经明确授权的 **userdata**（2026-11-05 已执行两次）
- 不修改 GPT、不写 calibration、不改变活动槽位
- 测试后长按电源 10 秒即可回到 fastboot
