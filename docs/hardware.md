# 板级硬件清单（全部实测）

数据来源：本机只读采集（DTBO/boot/vendor_boot 解包、合并 DTS、GPT、getprop、/proc/iomem），
不引用参考设备数值。

## 内存与地址空间

| 项 | 值 |
|---|---|
| DRAM | 12 GiB，起始 0x80000000 |
| splash_region | 0xFC400000，大小 0x2B00000 |
| FD_BASE（UEFI 加载地址）| 0xA7100000，FD_SIZE 0x300000 |
| 原厂 uefi_a 入口 | 0xA7000000（ARM64 ELF）|

## 中断 / 时钟

| 项 | 值 |
|---|---|
| GICv3 distributor | 0x17100000 |
| GICv3 redistributor | 0x17180000，stride 0x40000 |
| 架构 timer 频率 | 19.2 MHz |
| PSCI method | SMC |

## CPU 拓扑

8 核 big.LITTLE：2×Cortex-A520（~2.27 GHz）+ 5×Cortex-A720 + 1×Cortex-X4（~3.30 GHz）。

## UFS

| 项 | 值 |
|---|---|
| 控制器 | `ufshc@1d84000`（reg 0x1d84000 / 0x3000）|
| MCQ SQD | 0x1da5000 / 0x2000 |
| VS | 0x1da4000 / 0x10 |
| SMMU stream ID | 0x60 |
| 逻辑块 | 4096 B（GPT 头在 4K-LBA1）|
| userdata 窗口 | LBA 2260480 – 64049146（253.2 GiB）|

GCC（0x100000）UFS 相关偏移，与 SM8550 完全一致：

```
UFS_PHY_GDSCR              0x77004
UFS_MEM_PHY_GDSCR          0x9e000
UFS_PHY_AXI_ENABLE         0x77018
UFS_PHY_AHB_ENABLE         0x77024
UFS_PHY_UNIPRO_CORE_ENABLE 0x77068
UFS_PHY_ICE_CORE_ENABLE    0x77074
UFS_PHY_PHY_AUX_ENABLE     0x770b0
GCC_AGGRE_UFS_PHY_AXI      0x770e4
```

## GPU

Adreno 750（rev 2770）。

## 显示

1440×3200 DSC cmd 面板，`msm_drm.dsi_display0=qcom,mdss_dsi_n2_42_02_0a_p2_dsc_cmd`。
与所有参考设备时序不同，显示阶段优先使用 ABL/UEFI GOP  framebuffer。

## 触控

Synaptics TCM over SPI。

## 分区

6 个物理 LUN（sda–sdf），GPT 双备份。关键分区：boot_a/b、init_boot_a/b、vendor_boot_a/b、
dtbo_a/b、recovery_a/b、vbmeta*、persist、uefi_a/b、xbl*/abl*/tz*/hyp* 等（完整备份见 recovery.md）。