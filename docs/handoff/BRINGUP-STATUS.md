<!-- 本文由设备端会话自动生成，2026-10-30 -->

> 配套文档：`docs/handoff/ARTIFACTS.md`（产物清单、哈希、获取与重建方式）
> 二进制不入库，原因见 ARTIFACTS.md 开头。

# UniXNU-shennong 移植交接文档

生成时间：2026-10-30（设备本地时间 Asia/Shanghai）
设备：Xiaomi 14 Pro / shennong / 23116PN5BC / SM8650 (pineapple) / 12GB RAM / Android 16
目标：在 shennong 上运行真实 iOS 用户态（iPadOS 17.7.11 / 21H461）
仓库：https://github.com/YX2748198202-lab/UniXNU-shennong

---

## 一、当前状态（一句话）

**UEFI → BootShim → XNU 内核这条链已经完全打通**，内核能跑起来并输出 panic。
最新卡点从「挂根设备」前移到 **`AppleARMCPU.cpp:111` CPU 配置校验**，已定位根因并产出修复镜像（`Mu-shennong-smp.img`），**尚未实测**。

---

## 二、最新一次实测（决定性证据）

镜像：`Mu-shennong-mockfs-v0.img`（v0 header，203,726,848 B，sha256 `e46ea1f3…`）

现象：
1. UEFI（Project Silicium）完整启动，全套驱动加载
2. `Successfully Enabled UFS Cache Coherency` —— UFS 驱动加载成功
3. UniXNU loader 0.1.0 菜单出现，`drivers 0 loaded / 0 failed`、`kits 0`
4. 自动启动 `xnu` 条目（`timeout = 0`）
5. **XNU 内核启动，输出 panic 并停住**：

```
"CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111
Frames: ffffffff0049bcfe8 ffffffff004986a58 ffffffff0078a2958 ffffffff0078a207c
         ffffffff00789c028 ffffffff0078a45fc ffffffff0073f24a4
Fpage = 0x000000000000bb4c
Fres  = 0x0000000000000b450
```

**这条证据的意义**：内核真的跑起来了。之前阶段C停在 `IOKitBSDInit.cpp:984`（挂根设备），现在停得更早（CPU 初始化），说明内核镜像和启动链本身是好的。

---

## 三、该 panic 的根因（有官方文档依据）

`unixnu/docs/.vitepress/device-records/sirius.toml:121` 原文：

> With `sheng-smp=1` the native ArmCpu claims every /cpus nub; **without it the kernelcache AppleARMCPU takes the nubs and panics with "CPU configuration in device tree is invalid"** because it requires /cpus/max_cpus.

同文件 `:422` 更详细：

> AppleARMPlatform's CPU class matches cpu0..cpu7 because IODTPlatformExpert compares IONameMatch **by prefix（'cpu' matches 'cpu0'）**, starts first, and panics with 'CPU configuration in device tree is invalid'（its AppleARMCPU.cpp validates **max_cpus, cpu-id, interrupts and function-\* properties** that an Apple device tree carries）. The native ArmCpu personality (IOPlatformDevice, probe score 2000) did not win that match even after probe() added 40000, so make-uboot-payload.py **rewrites the AppleARMCPU IONameMatch from `cpu` to `xpu`** in the personality plist inside kernel.macho（equal length, nothing moves）.

**本项目的实际情况**：`board.toml:70` 的 kernel_args 是

```
-v serial=3 debug=0x14e armcpu-diagnostics=1 sheng-pmgr=2 native-ufs-probe=3
```

**缺少 `sheng-smp=1`**。这就是 panic 的直接原因。

**两种修法**（官方都记录过）：
- **A（已做）**：kernel args 加 `sheng-smp=1`，让原生 ArmCpu 抢占 `/cpus` nub
- **B（未做，更硬）**：改写 kernel.macho 里 AppleARMCPU personality 的 IONameMatch，`cpu` → `xpu`（等长替换，不移动任何东西）。sirius 最终用的是 B，因为 A 有时打不赢 probe 竞争。

---

## 四、本次已产出的修复镜像（待实测）

```
/sdcard/Download/Mu-shennong-smp.img
203,726,848 bytes
sha256 6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842
header: v0  ksize=2393623  kaddr=0x8000  rsize=201326592  raddr=0x1000000  page=4096
```

构造方式：沿用 `Mu-shennong-6-pmgr2.img` 的 v0 头 + kernel 区（前 2,400,256 字节），ramdisk 段换成改过 args 的 payload。

修改内容（payload 内 `/EFI/UniXNU/unixnu.toml`）：

```
args = "-v serial=3 debug=0x14e armcpu-diagnostics=1 sheng-smp=1 sheng-pmgr=2 native-ufs-probe=3"
```

**未验证**：`sheng-smp=1` 是否真的能让 ArmCpu 抢到 nub。若刷完仍是同一个 panic，直接改用修法 B。

---

## 五、boot image 打包（关键，官方流程缺失）

**重要事实**：`unixnu payload` 产出的是 **FAT 卷（ramdisk 内容）**，**不是可刷的 boot image**。
`payload.py` 第 1 行和末行都写明：

```
"""Boot payload: the FAT volume that becomes the ramdisk of the boot image."""
log('next: run ./unixnu bootimg to pack this payload into the boot image')
```

而 **workflow 里没有 `bootimg` 步骤**，所以 CI 的 artifact 直接 `fastboot boot` 必然失败。

**正确打包方式（本地已验证可跑）**：

```bash
cd /root/shennong-ios/src/unixnu
./unixnu bootimg \
  -D /root/shennong-ios/device \
  --local /root/localsocs \
  --uefi /root/shennong-ios/src/uefi-sheng \
  --fd /root/shennong-ios/src/uefi-sheng/Build/shennongPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --dtb /root/shennong-ios/src/uefi-sheng/Resources/DTBs/shennong.dtb \
  --ramdisk <payload.img> \
  -o <out.img> --target DEBUG --skip-preflight
```

**已知 bug**：`bootimg.py` 的 `verify()`（第 122-123 行）用 **boot image v0 布局**去解析 **v4 镜像**，必然抛 `boot image header does not match the requested parameters`，**但镜像文件已经正确写出**。不要被这个报错误导。
**更严重的坑**：它生成的是 **v4 header**，而 BootShim 需要 v0 的 `ramdisk_addr`。**v4 镜像会导致 UEFI 找不到 payload FAT 卷**，表现为 UniXNU `no boot entry found` → `Failed to Find an Operating System`。

**因此推荐用的打包方式（最稳，已验证）**：
直接拼接头 + kernel 区 + 新 ramdisk，复用旧镜像的 v0 头：

```python
old = open('shennong/Mu-shennong-6-pmgr2.img','rb').read()
pay = open('payload.img','rb').read()
ks,ka,rs,ra,ss,sa,tags,page = struct.unpack_from('<8I', old, 8)
assert len(pay) == rs                      # 必须等大，header 就不用改
head = old[:page + ((ks + page - 1)//page)*page]
open('out.img','wb').write(head + pay)
```

**注意**：payload 必须**正好 201,326,592 字节**（rs=201326592）。`payload.build` 用固定 size_mib 生成，所以每次都能对齐。

---

## 六、完整阶段进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链（XNU 编译/链接） | ✅ 完成，多轮 CI 绿 |
| B | UEFI 菜单（Device Tree / ADT 四道校验） | ✅ 完成 |
| C | XNU 内核启动 | ✅ **本轮达成**（内核跑起来并 panic） |
| D | prelink（合并原厂 IOStorageFamily） | ✅ 完成，`kernel.macho` sha256 `1c5af7fa…` |
| E1 | payload / boot image 打包 | ✅ 完成（但 CI 缺 bootimg 步骤，需补齐） |
| E2 | UFS 块设备 ABI 绑定（11 个 `IOBlockStorageDevice` 符号） | ❌ **静态路线证伪** |
| E3 | mockfs / RAM-only 根卷 | ⬜ 未开始（本轮 panic 在更早阶段，mockfs 未被验证） |
| E4 | 真实 iOS 用户态（launchd） | ⬜ 未开始 |

---

## 七、已证伪的路线（别再走）

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
- `kernel.macho`（prelink 产物）：exports 22550，**命中 0/11**
- `kernelcache.decompressed`（原厂解压内核）：exports 6056，**命中 0/11**

结论：原厂把这类做成**内部符号**，任何静态符号表都拿不到。**不要再尝试 nm/export 查找。**

### 7.2 `gdb-stop.json` 不是地址来源
`scripts/audit-storage-interface.py:180-192` 读 `build/darwinboot-storage-native-metadata/gdb-stop.json`，但它只做**验证**：
- `d['kernel_sha256'] == plan['candidate_sha256']`
- `not d['bounded_timeout_interrupted']`
- 校验 `superClassLink` / `classSize`（`IOBlockStorageDevice` 0x90、`IOService` 0x88）
- 校验 `TCR_EL1 >> 14 & 3 == 0`（原生 4K 页）

vtable 的 190 个指针来自 `audit:116-121` 的**静态扫描 `__DATA_CONST`**；`gMetaClass` 来自 `audit:175-178` 的**指令解码**。**gdb 不提供地址，只提供交叉验证。**

### 7.3 官方从未公开 audit inputs 的获取方式
- `docs/porting/ufs.md:124-125` 只有一句 "Storage ABI bindings need the selected kernelcache and matching audit inputs"
- `docs/log-capture.md` 里 `kdp` / `gdb` / `lldb` / `debugger` 出现次数全为 0
- 28 个 `device-records/*.toml` 里 `gdb` 出现次数全为 0

**推断**（未证实）：其他机型用 lldb+KDP，且它们有网卡或 USB device 驱动作为通道；shennong 目前两者都没有。

### 7.4 连跑到 UI 的机型也没做可写真根卷
`oneplus13t.toml:166`：`XNU_NATIVE_UFS, OWNER_ROOT_AUDIT, TRUST_CACHE_RUNTIME, OWNER_UNION_SYSTEMOS, NATIVE_RAM_BLOCK enabled`；**runtime UFS writes disabled**；**Data 是 1 GiB RAM seed，重启丢数据**；OS/SystemOS 只读走原厂 APFS/AMFI。

**结论**：「跑到 UI」这个目标**不需要**可写 UFS 真根卷。

---

## 八、剩余工作（按建议优先级）

### P0｜验证 `sheng-smp=1`（当前手里就有镜像）
刷 `Mu-shennong-smp.img`：
- 过了 `AppleARMCPU.cpp:111` → 继续 P1
- 同一 panic → 改用**修法 B**：改写 `kernel.macho` 内 AppleARMCPU personality 的 `IONameMatch`（`cpu`→`xpu`，等长替换）。**注意**：改的是 **kernel.macho**，它在 payload 的 `Payloads/kernel.macho` 里，改完还要注意签名/校验哈希（`payload.json` 里的 `kernel_sha256`）。

### P1｜mockfs 验证（E3）
mockfs 已经**确实链接进内核**（`kernel.macho` 里可查到 `mockfs_fixture.a`、`mockfs_vfsops`、`mockfs_vnops`、`mockfs_fsnode_*`、`mockfs_mountroot` 相关符号）。但存在两个已知缺口：
- `build-mockfs-fixture.py:54` 自称 `"Offline minimal-root fixture only"` —— **只有代码，没有真实 launchd 二进制**
- `mockfs-test-file.patch` 定义 `struct mockfs_test_header`（`launch_offset/launch_size/test_offset/test_size`），说明**完整版**需要把 `/sbin/launchd` 和 `/probe.bin` 打进 fixture。这两个文件要从 IPSW 的 `Cryptex1,SystemOS` 提取。

**mockfs 触发机制**：`mockfs_vfsops.c` 提供 `mockfs_mountroot()`，XNU 的 `vfs_mountroot()` 会自动遍历尝试，**不需要额外 bootarg**。`vfs_conf.c` 在 `-DMOCKFS=1` 时会把它注册进 vfsconf（`build-xnu-4k-baseline.sh:252` 的 `vfs_conf.o_CFLAGS_ADD=-DMOCKFS=$MOCKFS_MODE`）。

`build-xnu-4k-baseline.sh` 相关行：
- `236`: `MOCKFS_MODE=${XNU_SOURCE_MOCKFS:-0}`
- `241`: `MOCKFS_MODE=1` 要求 `XNU_ARMCPU=1 && XNU_SOURCE_PTHREAD=1`
- `738-742`: `MOCKFS_MODE=1` 时硬检查 `build/mockfs-fixture/libmockfs_fixture.a` 并 `-Wl,-force_load`

### P2｜把 bootimg 补进 CI
workflow 目前顺序：
```
Check out UniXNU → uefi-sheng → device → setup-python → Install host tools → Fetch device modules
→ Defconfig → Build kernel → Report failure details → Build ShengUfs archive → Build prelink
→ Probe storage bindings → Build payload → Probe kext symbol table → Upload kernel
```
**缺 `unixnu bootimg`**，也**缺 `unixnu firmware`**（fd 来源）。目前 fd 是本机遗留的 `uefi-sheng/Build/shennongPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。

### P3｜UFS 块设备（E2）+ 真根卷
只有 P0-P2 都过不去、或者确实需要真根卷时才回到这里。可选路径：
- **KDP 通道**：给 shennong 做网卡或 USB device 驱动，建立 lldb/KDP，拿到真实地址（工作量大，一劳永逸）
- **静态推导 + 跳过 audit**：vtable 扫描 + 指令解码拿地址（三层 ABI 假设未验证，错则真机崩溃）

---

## 九、关键资产清单

### 本机镜像（shennong 的 /sdcard/Download/）
| 文件 | 大小 | 说明 |
|---|---|---|
| `Mu-shennong-smp.img` | 203,726,848 | **待测**，含 `sheng-smp=1`，sha256 `6b1be67c…` |
| `Mu-shennong-mockfs-v0.img` | 203,726,848 | 已测（panics at AppleARMCPU），sha256 `e46ea1f3…` |
| `Mu-shennong-mockfs.img` | 203,730,944 | **v4 头，坏的**（UEFI 找不到 ramdisk），废弃 |
| `payload-smp.img` | 201,326,592 | 改过 args 的 FAT 卷 |
| `payload-mockfs.img` | 201,326,592 | 未改 args 的 FAT 卷 |
| `shennong/Mu-shennong-{0..6}*.img` | 各自 | **历史镜像，v0 头，全部能进内核**（`6-pmgr2` 是最新的） |
| `kernel-mockfs.macho` | 51,970,048 | 当前内核，含 mockfs |
| `sk1/` | — | run #87 artifact 解压，含 `kernel/kernel.macho`、`payload/payload.img`、`payload/payload.json` |

### 关键哈希
- `kernel.macho`（prelink 后）：`1c5af7fa86820ddc457e7c60532025ee6c9ab7278353bdde28192aa74ffe8b7b`（旧）/ `c527b761…`（run #87）
- `payload.img`：`a1ef77bfcd413be31a13eadd40445c32546d1f7dc0f3264362c4116feaa207af`
- `Mu-shennong-smp.img`：`6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842`

### 本地工作区（Android + PRoot Ubuntu）
- `/root/shennong-ios/src/unixnu` — UniXNU 主仓库
- `/root/shennong-ios/src/uefi-sheng` — Mu-Silicium checkout，含现成 fd + dtb + mkbootimg.py
- `/root/shennong-ios/device` — 最小 device repo（只放了 `board.toml` + `feeds.toml`，**无 dts**）
- `/root/localsocs/socs/sm8550` — 本地 SoC feed（`--local` 用）
- `/root/shennong-ios/src/sm8550` — SoC 源码（soc.toml / kits / patches）
- 工具链齐全：`clang` / `llvm-objcopy` / `llvm-nm` / `aarch64-linux-gnu-gcc` / `mtools` / `python3`

---

## 十、环境与约束

### 能做什么
- ✅ 本地跑 `unixnu bootimg` / `payload` / `prelink`（工具链齐全）
- ✅ 用 mtools 直接改 payload FAT 卷里的文件（`mcopy` / `mtype` / `mdir`）
- ✅ 本地拼装 v0 boot image（纯 python）
- ✅ 从 GitHub API 下载 artifact（**必须先拿 302 Location，再用 Operit 的 download_file，curl 直连 Blob 会被 reset**）

### 不能做什么
- ❌ 本地编译 XNU / UEFI（无 Apple SDK / EDK2 完整环境），必须走 GitHub Actions
- ❌ `git clone`（PRoot 里 GnuTLS 报 `-110`），只能走 `api.github.com` 的 contents API 拉单文件
- ❌ 从 PRoot 或 Android shell 下载 GitHub artifact（Blob 域名 `code=000`）

### 硬性安全约束
- 禁止 `fastboot flash` / `dd` 写分区 / 改分区表
- 禁止未经授权写 userdata
- 测试一律 `fastboot boot`（只启动不写入，失败重启即恢复）
- 不得提交 Apple IPSW、厂商固件、密钥
- 不得用 stub / 空心函数 / 全零密钥伪造验证（`verified_root_key={0}` + `vr_verify_block(){return1}` 已按要求删除）

---

## 十一、硬件事实（不得用参考机值替代）

- codename `shennong`，model `23116PN5BC`，SoC `SM8650`（msm-id `0x22d`，board-id `0x08`）
- DRAM 起始 `0x80000000`，12 GB
- UFS：`ufshc@1d84000`，reg `0x1d84000/0x3000`，MCQ SQD `0x1da5000/0x2000`，VS `0x1da4000/0x10`，SMMU SID `0x60`，逻辑块 4096 B，userdata LBA 2260480–64049146
- splash_region `0xFC400000 + 0x2B00000`
- GICv3 dist `0x17100000` / redist `0x17180000`（stride `0x40000`）
- timer 19.2 MHz（`0x124f800`）
- 8 核：2×A520@2.27GHz + 5×A720 + 1×X4@3.30GHz
- Adreno 750（rev 2770）
- 官方 uefi_a 入口 `0xA7000000`，FD_BASE `0xA7100000`，FD_SIZE `0x300000`

---

## 十二、本轮 UEFI 日志里值得记下的失败项（暂不阻塞）

| 日志 | 含义 | 处理 |
|---|---|---|
| `tz_armv8_smc_call failed, TzStatus = 0x9FCCFFB9 / 0x80000001` | 没有厂商 TEE | **预期内，先不管** |
| `TOSEEComppatAppLoader_loadFromBuffer failed ret = 12` | 同上 | 同上 |
| `Failed to start fastenabler_a TA, status = 1` | 同上 | 同上 |
| `ButtonsInit failed to locate PmcGpioProtocol` | 按键驱动没起来 | 菜单无法操作，靠 `timeout` 自动启动；后续要修 |
| `No input device` | 同上 | 同上 |
| `SdhcKmDriver: Failed to Locate QTI Device Path` + `Failed to enable voltage regulator for drive number 1` | SD 卡控制器没定位到 | 不影响 UFS，后续要用 SD 卡再补 |
| `ISRwWSmc() Return TRUE` / `LoadSecureApps ... keymaster ... QseeResponse->result = 0xE` | TEE 相关 | 预期内 |

---

## 十三、下一步最小动作

1. 刷 `Mu-shennong-smp.img`（`fastboot boot`）
2. 记录 panic 是否还在 `AppleARMCPU.cpp:111`
3. 若还在 → 实施修法 B（改写 kernel.macho 的 AppleARMCPU IONameMatch）
4. 过了 CPU 这关 → 关注下一个 panic 点（大概率回到 `IOKitBSDInit.cpp:984`，那时才是 mockfs/UFS 的战场）
