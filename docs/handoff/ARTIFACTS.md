# 产物清单与获取方式

**本项目目标：让 Xiaomi 14 Pro（shennong）运行 iOS 用户态。**

底座固件用的是 UniXNU 官方唯一的 OS profile `ipados-17.7.11-21H461`
（`unixnu/profiles/os/` 下没有 iOS profile），即 iPad Pro `iPad7,1` 的 IPSW。
XNU 内核 / IOKit / BSD 层同源，iOS 与 iPadOS 只在用户态套件与 UI 层不同，
所以这不影响「移植 iOS」这个目标；涉及具体文件时才会出现 `ipados-` 字样。

本仓库**只存源码、文档和脚本**。所有 Apple 派生的二进制（`kernel.macho`、`payload.img`、boot image）**刻意不入库**——它们包含原厂 kernelcache 的代码段（prelink 后的 `kernel.macho` 里就有完整的 `com.apple.iokit.IOStorageFamily`），公开分发有版权风险。

二进制留在测试设备上，用 `adb pull` 取，或用下面的脚本重建。

---

## 一、2026-10-30 这一批产物（在测试设备 shennong 上）

| 文件 | 大小 | sha256 | 说明 |
|---|---|---|---|
| `Mu-shennong-smp.img` | 203,726,848 | `6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842` | **待测**。v0 头，payload 里加了 `sheng-smp=1` |
| `Mu-shennong-mockfs-v0.img` | 203,726,848 | `e46ea1f3e99b57ee6089ab94ad32eeaad3fc79f65f6ecefc96d962cb92bb745e` | 已实测：内核跑起来了，panic 在 `AppleARMCPU.cpp:111` |
| `Mu-shennong-mockfs.img` | 203,730,944 | — | **废弃**。`unixnu bootimg` 生成的 v4 头，UEFI 找不到 ramdisk |
| `payload-smp.img` | 201,326,592 | — | 已加 `sheng-smp=1` 的 FAT 卷 |
| `payload-mockfs.img` | 201,326,592 | `a1ef77bfcd413be31a13eadd40445c32546d1f7dc0f3264362c4116feaa207af` | CI 原始产物 |
| `kernel-mockfs.macho` | 51,970,048 | `c527b761218afecbc7b59d870004058c541adb3473090bd423cdae67a0460e08` | prelink 后的内核，含 mockfs |
| `shennong/Mu-shennong-{0..6}*.img` | 各 203,726,848 | — | 历史镜像，**全部能进内核**，`6-pmgr2` 是最新的 |

---

## 二、从设备取回

设备已解锁且开了 adb：

```bash
adb devices                                     # 确认型号 23116PN5BC
adb pull /sdcard/Download/Mu-shennong-smp.img   .
adb pull /sdcard/Download/shennong/             ./shennong/
adb pull /sdcard/Download/sk1/                  ./sk1/     # CI artifact 解压内容
```

也可以把整个 `Download` 目录里相关的部分打包再传：

```bash
adb shell "cd /sdcard/Download && tar -czf shennong-artifacts.tar.gz Mu-shennong-*.img payload-*.img kernel-*.macho shennong/"
adb pull /sdcard/Download/shennong-artifacts.tar.gz .
```

---

## 三、重建这些产物

### 3.1 从 CI 出 payload

CI workflow（`.github/workflows/kernel.yml`）在 `Build payload` 步骤产出：
`out/shennong/ipados-17.7.11-21H461/shennong/payload/payload.img`（固定 201,326,592 字节）

注意 **workflow 没有 `bootimg` 步骤**，所以 CI 产物只能拿来做 ramdisk，不能直接刷。

### 3.2 改 payload 里的启动参数（不用重跑 CI）

```bash
python3 scripts/patch-payload-args.py --payload payload.img --show
python3 scripts/patch-payload-args.py --payload payload.img \
    --add sheng-smp=1 --anchor sheng-pmgr=2
```

脚本会用 `mtype` 读回校验，改不动就报错。

### 3.3 打成可刷的 boot image

**不要用 `unixnu bootimg`** 直接刷——它出 v4 header，BootShim 拿不到 `ramdisk_addr`，结果是
`no boot entry found` → `Failed to Find an Operating System`。

用模板法（已验证）：

```bash
python3 scripts/repack-v0-bootimg.py \
    --template shennong/Mu-shennong-6-pmgr2.img \
    --payload  payload.img \
    --out      Mu-shennong-new.img
```

脚本会打印 sha256 和解析出的 header，方便刷之前核对。

模板必须满足：

```
ANDROID!  magic
header_version = 0
page = 4096
kernel_size  = 2,393,623      (gzip 后的 BootShim + UEFI FD)
kernel_addr  = 0x8000
ramdisk_size = 201,326,592
ramdisk_addr = 0x1000000
```

`Mu-shennong-6-pmgr2.img` 全部满足。

### 3.4 如果确实要用官方 bootimg

```bash
cd <unixnu checkout>
./unixnu bootimg \
  -D <device repo> \
  --local <dir with socs/sm8550> \
  --uefi <uefi-sheng checkout> \
  --fd   <uefi-sheng>/Build/shennongPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --dtb  <uefi-sheng>/Resources/DTBs/shennong.dtb \
  --ramdisk payload.img \
  -o out.img --target DEBUG --skip-preflight
```

会以 `boot image header does not match the requested parameters` 退出，**但文件已经正确写出**。
即便如此，产物仍是 v4 头，**不能直接刷**，需要额外把 v4 头改写成 v0，或者改用 3.3 的模板法。

另外两个前置条件：

- `board.toml` 的 `["bootimg"]` 里 `dtb_node` 必须清空成 `[]`，否则 `fdtput` 报
  `Error at 'splash_region': FDT_ERR_EXISTS`（dtb 里已经有这个节点）
- SoC feed 必须有：`--local <dir>` 下要有 `socs/sm8550/`，否则报
  `SoC sm8550 is not cached`

---

## 四、刷机与回退

```bash
fastboot boot Mu-shennong-new.img     # 只启动，不写任何分区
```

失败就长按电源键重启，系统不受影响。**本项目禁止 `fastboot flash`、`dd` 写分区、改分区表。**
