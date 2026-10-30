# UniXNU-shennong 移植状态报告

最后更新：2026-10-30
设备：Xiaomi 14 Pro / codename `shennong` / model `23116PN5BC` / SM8650 (pineapple) / 12 GB RAM / 当前 Android 16
仓库：https://github.com/YX2748198202-lab/UniXNU-shennong

---

## 0. 先明确目标：移植的是 **iOS**

**目标是让这台小米 14 Pro 运行 iOS 用户态**，不是 iPadOS。

但必须说明一个客观事实，否则接手时会困惑：

**UniXNU 官方 `profiles/os/` 目录下只有一个 OS profile —— `ipados-17.7.11-21H461`，iOS profile 数量为 0。**

```
$ ls unixnu/profiles/os/
ipados-17.7.11-21H461
```

`board.toml` 里 `os_profile = "ipados-17.7.11-21H461"`，`[ipsw]` 段下载的是 iPad Pro（`iPad7,1`）的
`iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`。

**这意味着**：
- 我们编译的内核、prelink 用的 kernelcache、提取的 kext，**全部来自这份 iPadOS 固件**
- 这不是把目标改成 iPadOS。XNU 内核、IOKit、BSD 层是同一套代码，iOS 与 iPadOS 只在用户态套件和 UI 层不同
- 一旦内核能跑起来、用户态能起来，换成 iPhone 的固件/用户态是后续独立的步骤
- **在文档和代码里描述目标时统一写 "iOS"**；只有在指代具体 profile 路径/固件文件时才出现 `ipados-...` 字样

---

## 1. 当前状态（一句话）

**UEFI → BootShim → XNU 内核这条链已经完全打通**，内核能真正运行并输出 panic。
最新卡点在 `AppleARMCPU.cpp:111` 的 CPU 配置校验，根因已定位，修复镜像已产出但**尚未实测**。

---

## 2. 最新实测记录（决定性证据）

镜像：`Mu-shennong-mockfs-v0.img`（v0 header，203,726,848 B，sha256 `e46ea1f3…`）

现象顺序：

1. UEFI（Project Silicium）完整启动，全套驱动加载
2. `Successfully Enabled UFS Cache Coherency` —— UFS 驱动加载成功
3. UniXNU loader 0.1.0 菜单显示，`drivers 0 loaded / 0 failed`、`kits 0`
4. 因 `timeout = 0`，自动启动 `xnu` 条目
5. **XNU 内核启动，输出 panic 并停住**：

```
"CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111
Frames: ffffffff0049bcfe8 ffffffff004986a58 ffffffff0078a2958 ffffffff0078a207c
         ffffffff00789c028 ffffffff0078a45fc ffffffff0073f24a4
Fpage = 0x000000000000bb4c
Fres  = 0x0000000000000b450
```

**这条证据的意义**：内核真的跑起来了。此前阶段 C 停在 `IOKitBSDInit.cpp:984`（挂根设备），
现在停得更早（CPU 初始化）——说明内核镜像、BootShim、UEFI 这条链本身是好的。

---

## 3. 该 panic 的根因（有官方文档原文依据）

`unixnu/docs/.vitepress/device-records/sirius.toml:121`：

> With `sheng-smp=1` the native ArmCpu claims every /cpus nub; **without it the kernelcache
> AppleARMCPU takes the nubs and panics with "CPU configuration in device tree is invalid"**
> because it requires /cpus/max_cpus.

同文件 `:422` 更详细：

> AppleARMPlatform's CPU class matches cpu0..cpu7 because IODTPlatformExpert compares
> IONameMatch **by prefix（'cpu' matches 'cpu0'）**, starts first, and panics with
> 'CPU configuration in device tree is invalid'（its AppleARMCPU.cpp validates
> **max_cpus, cpu-id, interrupts and function-\* properties** that an Apple device tree carries）.
> The native ArmCpu personality (IOPlatformDevice, probe score 2000) did not win that match
> even after probe() added 40000, so make-uboot-payload.py **rewrites the AppleARMCPU
> IONameMatch from `cpu` to `xpu`** in the personality plist inside kernel.macho
>（equal length, nothing moves）.

**本项目的实际情况**：`board.toml:70` 的 kernel_args 是

```
-v serial=3 debug=0x14e armcpu-diagnostics=1 sheng-pmgr=2 native-ufs-probe=3
```

**缺少 `sheng-smp=1`**，这就是 panic 的直接原因。

**两种修法**：

- **A（已产出镜像，未验证）**：kernel args 加 `sheng-smp=1`，让原生 ArmCpu 抢占 `/cpus` nub
- **B（未做，更硬）**：改写 `kernel.macho` 里 AppleARMCPU personality 的 `IONameMatch`，
  `cpu` → `xpu`（等长替换，不移动任何字节）。sirius 最终用的是 B，因为 A 有时打不赢 probe 竞争

---

## 4. 待实测的修复镜像

```
Mu-shennong-smp.img
203,726,848 bytes
sha256 6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842
header: v0  ksize=2393623  kaddr=0x8000  rsize=201326592  raddr=0x1000000  page=4096
```

构造方式：沿用 `Mu-shennong-6-pmgr2.img` 的 v0 头 + kernel 区（前 2,400,256 字节），
ramdisk 段换成改过 args 的 payload。改动仅一处（payload 内 `/EFI/UniXNU/unixnu.toml`）：

```
args = "-v serial=3 debug=0x14e armcpu-diagnostics=1 sheng-smp=1 sheng-pmgr=2 native-ufs-probe=3"
```

**未验证**：`sheng-smp=1` 是否真能让 ArmCpu 抢到 nub。若仍是同一 panic，直接改用修法 B。

---

## 5. boot image 打包（关键，官方流程有缺口）

**`unixnu payload` 产出的是 FAT 卷（ramdisk 内容），不是可刷的 boot image。**
`payload.py` 第 1 行与末行都写明：

```
"""Boot payload: the FAT volume that becomes the ramdisk of the boot image."""
log('next: run ./unixnu bootimg to pack this payload into the boot image')
```

而 `kernel.yml` 里**没有 `bootimg` 步骤**，所以 CI artifact 直接 `fastboot boot` 必然失败。

**`unixnu bootimg` 有两个坑**：

1. 它生成 **v4 header**。BootShim 需要 v0 header 的 `ramdisk_addr`（`0x1000000`），
   v4 没有这个字段 → UEFI 找不到 payload FAT 卷 → UniXNU `no boot entry found`
   → UEFI `Failed to Find an Operating System`
2. 它的 `verify()`（`bootimg.py:122-123`）用 **v0 布局**解析 v4 镜像，必然抛
   `boot image header does not match the requested parameters`，**但文件已经正确写出**

**可靠打包法（已验证）**：用 `scripts/repack-v0-bootimg.py`
复用已知良好镜像的 v0 头 + kernel 区，追加新的 ramdisk：

```bash
python3 scripts/repack-v0-bootimg.py \
    --template shennong/Mu-shennong-6-pmgr2.img \
    --payload  payload.img \
    --out      Mu-shennong-new.img
```

前提：新 payload 必须**正好 201,326,592 字节**（`unixnu payload` 用固定 size_mib 生成，天然对齐）。

模板必须满足：

```
ANDROID! magic
header_version = 0
page = 4096
kernel_size  = 2,393,623      (gzip 后的 BootShim + UEFI FD)
kernel_addr  = 0x8000
ramdisk_size = 201,326,592
ramdisk_addr = 0x1000000
```

**若要改用官方 `bootimg`**，还需满足两个前置条件：

- `board.toml` 的 `["bootimg"]` 里 `dtb_node` 必须清空成 `[]`，否则 `fdtput` 报
  `Error at 'splash_region': FDT_ERR_EXISTS`（dtb 里已有该节点）
- SoC feed 必须就位：`--local <dir>` 下需要有 `socs/sm8550/`，否则报 `SoC sm8550 is not cached`

---

## 6. 阶段进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链（XNU 编译 / 链接） | ✅ 完成，CI 多轮成功 |
| B | UEFI 菜单（Device Tree / ADT 四道校验） | ✅ 完成 |
| C | XNU 内核启动 | ✅ **已达成**：内核运行，panic 前移到 `AppleARMCPU.cpp:111` |
| D | prelink（合并原厂 IOStorageFamily） | ✅ 完成 |
| E1 | payload / boot image 打包 | ✅ 完成（CI 仍缺 `bootimg` 步骤，待补） |
| E2 | UFS 块设备 ABI 绑定（11 个 `IOBlockStorageDevice` 符号） | ❌ **静态路线已证伪** |
| E3 | mockfs / RAM-only 根卷 | ⬜ 未开始（panic 发生在更早阶段，mockfs 尚未被验证） |
| E4 | iOS 用户态（launchd） | ⬜ 未开始 |
| F | 硬件功能（显示 / 触控 / GPU / Wi-Fi / 音频） | ⬜ 未开始 |

---

## 7. 已证伪的路线（别再走）

### 7.1 静态符号表查找（彻底证伪）

11 个 undefined 符号：

```
__ZN20IOBlockStorageDeviceC2EPK11OSMetaClass      (ctor)
__ZN20IOBlockStorageDeviceD2Ev                     (dtor)
__ZN20IOBlockStorageDevice10gMetaClassE            (gMetaClass)
__ZTV20IOBlockStorageDevice                        (vtable)
__ZN20IOBlockStorageDevice7doUnmapEP26IOBlockStorageDeviceExtentjj
__ZN20IOBlockStorageDevice4initEP12OSDictionary
__ZN20IOBlockStorageDevice20doGetProvisionStatusEyyPjP35IOBlockStorageProvisionDeviceExtenty
__ZN20IOBlockStorageDevice13setPropertiesEP8OSObject
__ZN20IOBlockStorageDevice13doSetPriorityEP26IOBlockStorageDeviceExtentjh
__ZN20IOBlockStorageDevice11requestIdleEv
getProperty
```

两轮独立 CI 实测：

- `kernel.macho`（prelink 产物）：exports **22550**，命中 **0/11**
- `kernelcache.decompressed`（原厂解压内核）：exports **6056**，命中 **0/11**

结论：原厂把这类做成**内部符号**，任何静态符号表都拿不到。**不要再尝试 nm / export 查找。**

### 7.2 `gdb-stop.json` 不是地址来源

`scripts/audit-storage-interface.py:180-192` 读
`build/darwinboot-storage-native-metadata/gdb-stop.json`，但它只做**验证**：

- `d['kernel_sha256'] == plan['candidate_sha256']`
- `not d['bounded_timeout_interrupted']`
- 校验 `superClassLink` / `classSize`（`IOBlockStorageDevice` 0x90、`IOService` 0x88）
- 校验 `TCR_EL1 >> 14 & 3 == 0`（原生 4K 页）

`vtable` 的 190 个指针来自 `audit:116-121` 的**静态扫描 `__DATA_CONST`**；
`gMetaClass` 来自 `audit:175-178` 的**指令解码**。
**gdb 不提供地址，只提供交叉验证。**

### 7.3 官方从未公开 audit inputs 的获取方式

- `docs/porting/ufs.md:124-125` 只有一句
  "Storage ABI bindings need the selected kernelcache and matching audit inputs"
- `docs/log-capture.md` 里 `kdp` / `gdb` / `lldb` / `debugger` 出现次数全为 **0**
- 28 个 `device-records/*.toml` 里 `gdb` 出现次数全为 **0**

**推断（非实证）**：其他机型用 lldb+KDP，且它们有网卡或 USB device 驱动作为通道；
shennong 目前两者都没有。

### 7.4 连跑到 UI 的机型也没做可写真根卷

`oneplus13t.toml:166`：
`XNU_NATIVE_UFS, OWNER_ROOT_AUDIT, TRUST_CACHE_RUNTIME, OWNER_UNION_SYSTEMOS, NATIVE_RAM_BLOCK enabled`；
**runtime UFS writes disabled**；**Data 是 1 GiB RAM seed，重启丢数据**；OS/SystemOS 只读走原厂 APFS/AMFI。

**结论**：「跑到 UI」这个目标**不需要**可写 UFS 真根卷。

---

## 8. 剩余工作

### P0｜验证 `sheng-smp=1`
刷 `Mu-shennong-smp.img`：

- 过了 `AppleARMCPU.cpp:111` → 继续 P1
- 同一 panic → 改用**修法 B**（改写 `kernel.macho` 内 AppleARMCPU personality 的 IONameMatch）
- panic 更早 / 黑屏 → 回退 `MOCKFS=n` 重建，隔离变量

### P1｜mockfs 验证（E3）

mockfs 已**确实链接进内核**（`kernel.macho` 里可查到 `mockfs_fixture.a`、`mockfs_vfsops`、
`mockfs_vnops`、`mockfs_fsnode_*`、`mockfs_mountroot` 相关符号）。两个已知缺口：

- `build-mockfs-fixture.py:54` 自称 `"Offline minimal-root fixture only"` —— **只有代码，没有真实 launchd**
- `mockfs-test-file.patch` 定义 `struct mockfs_test_header`
  （`launch_offset / launch_size / test_offset / test_size`），说明**完整版**需要把
  `/sbin/launchd` 与 `/probe.bin` 打进 fixture。这两个文件需从固件的 `Cryptex1,SystemOS` 提取

**触发机制**：`mockfs_vfsops.c` 提供 `mockfs_mountroot()`，XNU 的 `vfs_mountroot()` 会自动遍历尝试，
**不需要额外 bootarg**。`vfs_conf.c` 在 `-DMOCKFS=1` 时会把它注册进 vfsconf
（`build-xnu-4k-baseline.sh:252` 的 `vfs_conf.o_CFLAGS_ADD=-DMOCKFS=$MOCKFS_MODE`）。

`build-xnu-4k-baseline.sh` 相关行：

- `236`: `MOCKFS_MODE=${XNU_SOURCE_MOCKFS:-0}`
- `241`: `MOCKFS_MODE=1` 要求 `XNU_ARMCPU=1 && XNU_SOURCE_PTHREAD=1`
- `738-742`: `MOCKFS_MODE=1` 时硬检查 `build/mockfs-fixture/libmockfs_fixture.a` 并 `-Wl,-force_load`

### P2｜把 `bootimg` 补进 CI

当前 `kernel.yml` 步骤顺序：

```
Check out UniXNU → uefi-sheng → device → setup-python → Install host tools → Fetch device modules
→ Defconfig → Build kernel → Report failure details → Build ShengUfs archive → Build prelink
→ Probe storage bindings → Build payload → Probe kext symbol table → Upload kernel
```

**缺 `unixnu bootimg`**，也**缺 `unixnu firmware`**（fd 来源）。目前 fd 是既有产物
`uefi-sheng/Build/shennongPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。

### P3｜UFS 块设备（E2）+ 真根卷

只有 P0–P2 都过不去、或确实需要真根卷时才回到这里。可选路径：

- **KDP 通道**：给 shennong 做网卡或 USB device 驱动，建立 lldb/KDP，拿真实地址
  （工作量大，一劳永逸）
- **静态推导 + 跳过 audit**：vtable 扫描 + 指令解码拿地址
  （三层 ABI 假设未验证，错则真机崩溃）

---

## 9. 关键资产

### 产物（在测试设备 shennong 上，不入库，原因见 ARTIFACTS.md）

| 文件 | 大小 | sha256 | 说明 |
|---|---|---|---|
| `Mu-shennong-smp.img` | 203,726,848 | `6b1be67c…` | **待测**，含 `sheng-smp=1` |
| `Mu-shennong-mockfs-v0.img` | 203,726,848 | `e46ea1f3…` | 已测，panic 于 `AppleARMCPU.cpp:111` |
| `Mu-shennong-mockfs.img` | 203,730,944 | — | **废弃**，v4 头，UEFI 找不到 ramdisk |
| `payload-smp.img` | 201,326,592 | — | 已加 `sheng-smp=1` 的 FAT 卷 |
| `payload-mockfs.img` | 201,326,592 | `a1ef77bf…` | CI 原始产物 |
| `kernel-mockfs.macho` | 51,970,048 | `c527b761…` | prelink 后的内核，含 mockfs |
| `shennong/Mu-shennong-{0..6}*.img` | 各 203,726,848 | — | 历史镜像，**全部能进内核**，`6-pmgr2` 最新 |

### 完整哈希

- `kernel.macho`（prelink 后）：`1c5af7fa86820ddc457e7c60532025ee6c9ab7278353bdde28192aa74ffe8b7b`（早期）
  / `c527b761218afecbc7b59d870004058c541adb3473090bd423cdae67a0460e08`（run #87）
- `payload.img`：`a1ef77bfcd413be31a13eadd40445c32546d1f7dc0f3264362c4116feaa207af`
- `Mu-shennong-smp.img`：`6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842`
- IPSW：`iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`
  `https://updates.cdn-apple.com/2025SpringFCS/fullrestores/122-77166/DCA6CFE8-90E9-4B92-880D-3DE171798E40/`
- `kernelcache_sha256 = f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7`

---

## 10. 构建要求（项目本身的客观要求，与环境无关）

**必须有 macOS + Xcode 才能做的**

- XNU 编译（`build-xnu-4k-baseline.sh` 依赖 Apple SDK / Xcode toolchain）
- 官方推荐路径：GitHub Actions 的 `macos` runner（仓库 `kernel.yml` 已就绪）

**Linux / 任意平台都能做的**

- UEFI 固件卷（EDK2 + clang，需 Mu_Basecore 与 uefi-sheng）
- payload 打包（Python + mtools）
- boot image 拼装（纯 Python，见 `scripts/repack-v0-bootimg.py`）
- payload 内文件修改（mtools，见 `scripts/patch-payload-args.py`）
- 内核 / payload 的静态检查（`strings`、`llvm-nm`、段表解析）

**前置依赖**

- Python 3.9+
- `mtools`（`mcopy` / `mtype` / `mdir`）
- `clang` + `llvm-objcopy` + `llvm-nm`
- 可选：`aarch64-linux-gnu-gcc`（某些组件）

---

## 11. 关于本次会话的完成环境（与项目无关，接手者可忽略）

这一轮的排查、打包、推送是在**一台 Android 手机的 PRoot Ubuntu 容器里**做的，
环境限制很多：没有 Xcode、`git clone` 因 TLS 问题经常失败、GitHub 的 artifact Blob 域名
不可达。因此在那个环境里被迫走了几条绕路：

- XNU 编译全部放到 GitHub Actions
- artifact 先取 302 Location，再用能连通的方式下载
- 文档/脚本用 GitHub Contents API 逐文件推送
- boot image 用纯 Python 拼接代替 `mkbootimg`

**这些绕路只是那个环境的产物，不是项目的限制。** 在正常电脑上（macOS 或完整 Linux），
这些工作都可以直接做，不需要上述变通。

---

## 12. 硬件事实（不得用参考机数值替代）

- codename `shennong`，model `23116PN5BC`，SoC `SM8650`（msm-id `0x22d`，board-id `0x08`）
- DRAM 起始 `0x80000000`，12 GB
- UFS：`ufshc@1d84000`，reg `0x1d84000/0x3000`，MCQ SQD `0x1da5000/0x2000`，
  VS `0x1da4000/0x10`，SMMU SID `0x60`，逻辑块 4096 B，userdata LBA 2260480–64049146
- splash_region `0xFC400000 + 0x2B00000`
- GICv3 dist `0x17100000` / redist `0x17180000`（stride `0x40000`）
- timer 19.2 MHz（`0x124f800`）
- 8 核：2×A520@2.27GHz + 5×A720 + 1×X4@3.30GHz
- Adreno 750（rev 2770）
- 官方 uefi_a 入口 `0xA7000000`，FD_BASE `0xA7100000`，FD_SIZE `0x300000`

---

## 13. UEFI 日志中的已知失败项（暂不阻塞）

| 日志 | 含义 | 处理 |
|---|---|---|
| `tz_armv8_smc_call failed, TzStatus = 0x9FCCFFB9 / 0x80000001` | 没有厂商 TEE | **预期内，先不管** |
| `TOSEEComppatAppLoader_loadFromBuffer failed ret = 12` | 同上 | 同上 |
| `Failed to start fastenabler_a TA, status = 1` | 同上 | 同上 |
| `ButtonsInit failed to locate PmcGpioProtocol` | 按键驱动未起来 | 菜单无法操作，靠 `timeout` 自动启动；后续要修 |
| `No input device` | 同上 | 同上 |
| `SdhcKmDriver: Failed to Locate QTI Device Path` + `Failed to enable voltage regulator for drive number 1` | SD 卡控制器未定位 | 不影响 UFS，后续要用 SD 卡再补 |
| `ISRwWSmc() Return TRUE` / `LoadSecureApps ... keymaster ... QseeResponse->result = 0xE` | TEE 相关 | 预期内 |

---

## 14. 安全 / 合规约束

- 禁止 `fastboot flash`、`dd` 写分区、改分区表；测试一律 `fastboot boot`
- 禁止未经授权写 userdata
- 不得提交 Apple IPSW、厂商固件、密钥，或任何含原厂 kernelcache 代码的二进制到公开仓库
- 不得用 stub / 空心函数 / 全零密钥伪造验证结果
  （`verified_root_key={0}` + `vr_verify_block(){return1}` 曾存在，已按要求删除，不要加回）
