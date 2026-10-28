# 备份与恢复方案

## 安全边界

- 只使用 `fastboot boot` 临时启动，**不刷写 boot/系统分区**
- 唯一计划内的分区写入是 **userdata**（阶段 E：写入 iOS 根卷），执行前需明确授权
- 不修改 GPT、不写 calibration、不改变活动槽位

## 已备份内容（2026-10-28）

87 个分区，共约 2.0 GB，位于 `backups/partitions/`（不随仓库上传，只在本机/外部介质保留）：

| 类别 | 分区 |
|---|---|
| 引导 | boot_a/b、init_boot_a/b、vendor_boot_a/b、dtbo_a/b、recovery_a/b |
| 校验 | vbmeta_a/b、vbmeta_system_a/b |
| 设备唯一 | persist、misc、fsg、fsc、modemst1、modemst2、devinfo、cdt、connsec、secdata、bk01–bk07、bk51 |
| 通信 | modem_a/b、modemfirmware_a/b、dsp_a/b、bluetooth_a/b |
| 固件链 | xbl_a/b、xbl_config_a/b、xbl_ramdump_a/b、abl_a/b、aop_a/b、aop_config_a/b、devcfg_a/b、hyp_a/b、tz_a/b、keymaster_a/b、qupfw_a/b、cpucp_a/b、cpucp_dtb_a/b、shrm_a/b、multiimgoem_a/b、multiimgqti_a/b、qweslicstore_a/b、spuservice_a/b、uefi_a/b、uefisecapp_a/b、uefivarstore |
| 其它 | imagefv_a/b、storsec、toolsfv、vm-bootsys_a/b、vm-persist、mdcompress |

另含：6 个 LUN（sda–sdf）的 GPT 头备份、`partitions.sha256` 校验清单、`partitions-backup.tar.gz`（打包 + SHA256）。

## 备份前提

- `/sdcard` 属于 userdata 分区，**写入 userdata 前必须把备份转出**（HTTP 拉取到第二台设备或 U 盘）

## 恢复 Android

1. 从备份恢复关键分区（示例，正常应在 fastboot 下）：

```
fastboot flash boot_a boot_a.img
```

2. 恢复 userdata：线刷官方 HyperOS 包（会重建 /data）：

```
fastboot flash super super.img
```

3. 若仅恢复引导链，至少恢复 boot_a、init_boot_a、vendor_boot_a、dtbo_a、vbmeta_a。

## 测试恢复

任意镜像测试后：

- 长按电源 10 秒强制重启 → 直接回 Android
- 或 `fastboot reboot`

以上路径在全部阶段 B/C 测试中已验证 10 次以上。