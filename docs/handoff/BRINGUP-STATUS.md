# UniXNU-shennong 移植状态报告

最后更新：2026-11-02（本轮接手核查，无真机）
设备：Xiaomi 14 Pro / codename `shennong` / model `23116PN5BC` / SM8650 (pineapple) / 12 GB RAM / 当前 Android 16
仓库：https://github.com/YX2748198202-lab/UniXNU-shennong

> **本轮结论先行**：历史交接里的「P0：验证 `sheng-smp=1` 能否过 `AppleARMCPU.cpp:111`」
> **在源码层面不成立**——`sheng-smp` 在本机配置下只影响副核心，不可能改变启动核心
> `cpu0` 的驱动归属（第 3.2 节有完整证据链）。已改为实施并自测上游两个机型验证过的
> **修法 B：把 `AppleARMPlatform.kext` 里 `AppleARMCPU` personality 的 `IONameMatch`
> 由 `cpu` 改为 `xpu`**，工具 `scripts/patch-applearmcpu-ioname.py` 已完成并通过离线自检。
> 真机验证仍是唯一未完成项，需要设备在场。

---

## 0. 先明确目标：移植的是 **iOS**

**目标是让这台小米 14 Pro 运行 iOS 用户态**，不是 iPadOS。

但必须说明一个客观事实，否则接手时会困惑：

**UniXNU 官方 `profiles/os/` 目录下的 OS profile 全部是 iPadOS，iOS profile 数量为 0。**
2026-11-02 核对（上游 `main`，tarball 下载）：

```
$ ls profiles/os/
ipados-17.7.11-21H461
ipados-26.5.2-23F84
ipados-27.0.1-24A446
```

> 历史交接写的是「只有一个 profile」。本轮核对是**三个**，但「没有 iOS profile」这一
> 关键结论不变。

`board.toml` 里 `os_profile = "ipados-17.7.11-21H461"`，`[ipsw]` 段下载的是 iPad Pro（`iPad7,1`）的
`iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`。

**这意味着**：
- 我们编译的内核、prelink 用的 kernelcache、提取的 kext，**全部来自这份 iPadOS 固件**
- 这不是把目标改成 iPadOS。XNU 内核、IOKit、BSD 层是同一套代码，iOS 与 iPadOS 只在用户态套件和 UI 层不同
- 一旦内核能跑起来、用户态能起来，换成 iPhone 的固件/用户态是后续独立的步骤
- **在文档和代码里描述目标时统一写 "iOS"**；只有在指代具体 profile 路径/固件文件时才出现 `ipados-...` 字样

---

## 1. 当前状态（一句话）

**UEFI → BootShim → XNU 内核这条链已打通**，内核真正运行并输出 panic。
最新卡点是 `AppleARMCPU.cpp:111`「CPU configuration in device tree is invalid」；
根因已定位到 IOKit 的 `/cpus` 驱动归属，修法 B 已实现并离线验证，**等真机确认**。

---

## 2. 最新实测记录（决定性证据，2026-10-30）

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

**这条证据的意义**：内核真的跑起来了，UEFI/BootShim/内核镜像这条链是好的。

### 2.0 2026-11-02 晚：修法 B 的真机对照（已实测）

| 镜像 | 彩条 | 内核文字 |
|---|---|---|
| `Mu-shennong-smp.img`（未打补丁，`6b1be67c…`） | 绿、蓝 **2 条** | `"CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111` + frames + pages/free |
| `Mu-shennong-xpu.img`（B，`b8c96d62…`） | 绿、蓝、品红 **3 条** | **无** |
| `Mu-shennong-xpu-skipgic.img`（B + `armcpu-skip-gic=1`，`5d3dd179…`） | 同 B | 同 B |

判读：

- **B 生效**：旧 panic 消失，启动比对照多走一个 stage。
- 现在**不是 panic 而是静默挂起**：panic 屏（`scripts/xnu-panic-screen.c`）会从 `h/8`
  往下清屏再写白字，而 B 的画面 `h/8` 以下整片纯黑、无清屏痕迹 → `panic()` 未被调用。
- `skip-gic` 变体画面完全相同 → 挂起点**不在 `ArmCpu::prepareGic()`**。
- 剩余可能：`IOCpu::start` 之后的 `ml_processor_register()`（启动核已被 XNU 的
  `cpu_bootstrap()` 注册过，重复注册可能失败）、`initCPU(true)` 的中断注册，
  或 IOKit 匹配处 `/cpus` 无人认领。

因此下一步不是再猜，而是**恢复可观测性**：让内核把阶段画到屏上（诊断屏构建已在 CI 里）。

### 2.1 一个尚未解释的回归（本轮新发现，未验证）

历史记录里 `Mu-shennong-6-pmgr2`（2026-10-27/28）停在
`Failed to mount root device @IOKitBSDInit.cpp:984`，那是 **bsd_init 之后**的阶段；
`vfs_mountroot` 远晚于 IOKit 匹配。所以那两个镜像在 CPU 这一关表现不同。

本轮核对后发现**无法用 ADT 或 prelink roots 解释这个差异**：

- `scripts/make-shennong-adt.py` 自加入起就只有 `cpu0`（`git log -p --follow` 只有一次新增）
- `board.toml` 的 `[kernel.prelink] roots` 自首次提交（`03d1970`，2026-10-27）就包含
  `com.apple.driver.AppleARMPlatform`
- `configs/shennong_defconfig` 自首个 defconfig（`f82292d`）就 `CONFIG_XNU_ARMCPU=y`
- `6-pmgr2` → `mockfs` 之间唯一的配置改动是 `dfd4690` 增加 `CONFIG_XNU_SOURCE_MOCKFS=y`

**推断（未验证）**：`/cpus` 的归属取决于 IOKit 匹配顺序/同分竞态，内核镜像内容一变
（mockfs + pthread 改变镜像布局与 personality 顺序）结果就翻转。这条推断如果成立，
就说明**不能依赖 ArmCpu 靠 probe 分数赢下匹配**，必须是修法 B 这种确定性做法。

**隔离办法（需要真机或 CI 各跑一次）**：
- `MOCKFS=n` 重建（历史给的「回退隔离变量」），确认是否回到 `IOKitBSDInit.cpp:984`
- 若回到，则 mockfs 与 CPU 匹配之间存在镜像布局耦合，B 仍然适用，但记录要写清

---

## 3. 该 panic 的根因（两层，均已静态核实）

### 3.1 第一层：Apple ARM CPU 类的 personality 会前缀匹配 `cpu0`

官方 device record 原文（`unixnu@main`，本轮逐字核对）：

`docs/.vitepress/device-records/sirius.toml:437`
（历史文档写 `:422`，本轮实际行号是 437，内容一致）：

> AppleARMPlatform's CPU class matches cpu0..cpu7 because IODTPlatformExpert compares
> IONameMatch **by prefix（'cpu' matches 'cpu0'）**, starts first, and panics with
> 'CPU configuration in device tree is invalid'（its AppleARMCPU.cpp validates
> **max_cpus, cpu-id, interrupts and function-\* properties** that an Apple device tree carries）.
> The native ArmCpu personality (IOPlatformDevice, probe score 2000) did not win that match
> even after probe() added 40000, so make-uboot-payload.py **rewrites the AppleARMCPU
> IONameMatch from `cpu` to `xpu`** in the personality plist inside kernel.macho
>（equal length, nothing moves）.

同文件 `:121`：

> With `sheng-smp=1` the native ArmCpu claims every /cpus nub; **without it the kernelcache
> AppleARMCPU takes the nubs and panics** ... because it requires /cpus/max_cpus.

本机 ADT（`scripts/make-shennong-adt.py:80-82`）里 `/cpus` 只有一个子节点：

```
cpu0: state=running, reg=0, device_type=cpu, compatible=qcom,kryo, timebase-frequency=19200000
```

**没有** `/cpus/max_cpus`，也没有每核的 `cpu-id` / `interrupts` / `function-*`。
也就是说 AppleARMCPU 一旦拿到这个 nub，它要校验的输入全都不存在 → 必然 panic。
（推断：ADT 缺属性是 panic 的**直接输入条件**；本轮无真机，未逐字节对照原厂
`DeviceTree.j120ap.im4p`。）

### 3.2 第二层：为什么 `sheng-smp=1` 解决不了这件事（本轮核心结论）

ArmCpu 组件是 `UniXNU/ArmCpu`，`board.toml` 里 `component:ArmCpu` 由上游
`components.toml` 固定到 revision `93a5030c5d983d0ef90f0fca93879d6e36ad1ba8`。
该 revision 的 `ArmCpu.cpp:209-227`（本轮逐行核对）：

```cpp
IOService *ArmCpu::probe (IOService *provider, SInt32 *score)
{
  ... device_type must be "cpu", reg must be >= 4 bytes ...
  memcpy (&id, reg->getBytesNoCopy (), sizeof (id));
  if (ml_get_cpu_number (id) != ml_get_boot_cpu_number ()) {   // 只在“不是启动核”时
    unsigned smp = 0;
    PE_parse_boot_argn ("sheng-smp", &smp, sizeof (smp));
    if (smp == 0 || ml_get_cpu_number (id) < 0 || ml_get_cpu_number (id) >= ARMCPU_SMP_SLOTS) {
      return nullptr; // Secondary startup is opt-in (sheng-smp=1).
    }
  }
  return IOCPU::probe (provider, score);   // 启动核无条件进入这里
}
```

也就是说：

- `sheng-smp` 只控制**副核心**的 `probe` 是否被拒绝；
- 对启动核 `cpu0`（`reg = 0`，`ml_get_cpu_number(0) == ml_get_boot_cpu_number() == 0`）
  `sheng-smp` **完全不参与判断**；
- `ArmCpu.cpp:439` 的 `start()` 里读 `sheng-smp` 只用于 `gSmpWanted` / 副核心 `drainPending`，
  同样不改变启动核的归属；
- 本机 ADT **只暴露一个 CPU 节点**，没有副核心节点可启动。

**结论（静态证明，非真机实测）**：只加 `sheng-smp=1`、ADT 不变，`/cpus` 的竞争关系
一个字都不会变。因此待测的 `Mu-shennong-smp.img` 极可能**复现同一个 panic**。
这条结论对「ArmCpu 到底有没有赢下 cpu0」两种情形都成立：

- 若 AppleARMCPU 赢了 → 加 `sheng-smp` 不影响竞争，照样 panic；
- 若 ArmCpu 因为 `ml_get_cpu_number(0) < 0` 之类的理由拒绝了 cpu0 → `sheng-smp` 分支里
  仍然会 `return nullptr`，也照样 panic。

所以「加 `sheng-smp=1` 就能过这一关」这个前提，可以不用真机就否掉。

### 3.3 两条可用修法

| | 做法 | 证据 |
|---|---|---|
| **B（已实现，推荐）** | 改 `kernel.macho` 里 `AppleARMPlatform.kext` 的 `AppleARMCPU` personality，`IONameMatch` `cpu` → `xpu`（等长，1 字节差） | rmx1971 实测记录：`docs/devices/rmx1971.md:142`「rewritten cpu -> xpu at payload assembly time so the native ArmCpu owns /cpus」、`:494`「Kernel patches applied at assembly: ... the IONameMatch cpu->xpu rewrite」；sirius/sirius-huajifruit/sirius-dddqmmx/sirius-yooglery 同 |
| **C（备选，未实现）** | 直接改 AppleARMCPU 代码，绕过 `_validateConfiguration` | mondrian-mzyxsl 记录：`docs/devices/mondrian-mzyxsl.md:149`「the AppleARMCPU multi-CPU validation is bypassed by the kext patch on `_validateConfiguration`」；需要符号地址解析，未做 |

**为什么「把 ArmCpu 的 probe 分数调高」也不是可靠修法**（本轮读 XNU 源码核实，
tag `xnu-10063.141.1`，即上游 `build-xnu-4k-baseline.sh` 的默认值）：

- `iokit/Kernel/IOService.cpp:4111-4112`：每个 match category 的候选放进取胜队列
  `OSOrderedSet::withCapacity(1, IOServiceOrdering, gIOProbeScoreKey)`
- `:4153`：注释 `start the best (until success) of each category`，然后
  `startList->getFirstObject()` 依次 `start()`
- `IOServiceOrdering`（`:3698`）返回 `score(obj1) - score(obj2)`；
  `libkern/c++/OSOrderedSet.cpp` 的 `setObject()` 插入循环是
  `while (ORDER(array[i], anObject) >= 0) i++;`
  → **高分在前，同分按插入顺序 FIFO**
- 分数初值来自 personality 自己的 `IOProbeScore`（ArmCpu 是 `2000`），
  `IOService::probe` 默认实现不改分数

也就是说 ArmCpu 只有在 `AppleARMCPU` 的 `IOProbeScore <= 2000` 时才会排到前面。
它实际排在后面，说明 Apple 的分更高；而 sirius 记录「+40000 仍然没赢」，
说明这条路是分数竞速、结果不可控。更关键的是：**Apple 的 `start()` 直接 panic，
不是 `return false`**，所以「排第二」也不会被兜底重试——没有第二次机会。

**为什么选 B 而不是「给 ADT 补 `max_cpus`」**：补属性是让 **Apple 的** CPU 管理代码
跑起来，而 UniXNU 的设计是用原生 ArmCpu 取代它（GIC/定时器/PSCI 全在 ArmCpu
里）。补齐 Apple 属性只会让它继续往前走，然后在更后期以更难诊断的方式失败。
上游所有能进用户态的机型都选 B。

### 3.4 修法 B 的实现与验证（本轮完成）

`scripts/patch-applearmcpu-ioname.py`：

- 解析 Mach-O，找 `__PRELINK_INFO` **segment**（与上游
  `kits/XnuPrelink/emit_prelink.py:272` 的产出方式一致：`ET.tostring(...)` 序列化、
  根节点是 `<dict>`、**没有 `<plist>` 包裹**、末尾补 `\0`）；
- 用 ElementTree 解析，定位 `_PrelinkInfoDictionary` 里
  `com.apple.driver.AppleARMPlatform` 的 `IOKitPersonalities` → `AppleARMCPU`；
- 只改该 personality **所在 `<dict>` 内**的那个 `IONameMatch` 值，写回同一位置；
- 逐项读回校验：结构 diff 必须**恰好一处**、路径必须是
  `…/IOKitPersonalities/AppleARMCPU/IONameMatch`、值必须是 `cpu`→`xpu`、
  文件长度不变、变化的字节数必须等于 1。

支持三种输入（都自带读回校验）：

```bash
# v0 boot image：抽 payload → 改 kernel.macho → 回写 → 用原 header 重打包（输出等长）
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img \
    --out Mu-shennong-xpu.img --report Mu-shennong-xpu.json

# payload FAT 卷
python3 scripts/patch-applearmcpu-ioname.py --payload payload.img --out payload-xpu.img

# 裸 kernel.macho
python3 scripts/patch-applearmcpu-ioname.py --macho kernel.macho --out kernel-xpu.macho

# 只看不改
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img --check

# 不需要任何产物的离线自检
python3 scripts/patch-applearmcpu-ioname.py --self-test
```

离线自检覆盖 3 个夹具（手写 XML、上游 `emit_prelink` 序列化格式、`<plist>` 包裹 +
`IONameMatch` 为数组），并验证：另一个 kext 的同名 `"cpu"` 诱饵不动、`__TEXT`
里的诱饵字节不动、二次运行是 no-op、缺少 AppleARMPlatform 时报错而不是静默通过。
实际输出与哈希记在 [VERIFICATION-2026-11-02.md](VERIFICATION-2026-11-02.md)。

**未验证**：真实 `kernel.macho` 上的效果（产物不在本机），以及真机现象变化。
**副作用（已实测，已消除）**：`mcopy` 回写默认会改 payload FAT 目录项的时间戳。
现在读写都用 `mcopy -p -m` 保留原 FAT 时间戳，因此**整个产物相对输入只差 1 个字节**
（离线夹具上实测：`payload.img` 与 `payload-xpu.img` 只在偏移 `0x4443b`（279611）差
`c`→`x`，长度相同，跨时间重跑哈希一致）。

---

## 4. 待测镜像与新镜像构造

### 4.1 历史待测镜像（`sheng-smp=1`，**预期无效**）

```
Mu-shennong-smp.img
203,726,848 bytes
sha256 6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842
header: v0  ksize=2393623  kaddr=0x8000  rsize=201326592  raddr=0x1000000  page=4096
```

按第 3.2 节，它不会改变 `AppleARMCPU.cpp:111`。**仍然建议测一次**，因为它是
「B 之前」的对照，且能顺便验证 2.1 那个未解释的回归。

### 4.2 本轮产出的新镜像（待生成，产物在设备上）

```bash
adb pull /sdcard/Download/Mu-shennong-smp.img .
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img \
    --out Mu-shennong-xpu.img --report Mu-shennong-xpu.json
fastboot boot Mu-shennong-xpu.img        # 仅启动，不写分区
```

`--image` 模式会自动核对：输出字节数与输入相同、v0 header 的 8 个字段逐项不变、
payload 读回一致。**这仍然需要你本人在设备旁执行**（本会话无设备）。

### 4.3 CI 侧

`kernel.yml` 已新增 `Patch AppleARMCPU IONameMatch (cpu -> xpu)` 步骤，在
`Build payload` 之后：

- 对 `out/shennong/.../payload/payload.img` 打补丁，产出 `payload-xpu.img` +
  `payload-xpu.json`，并上传；
- 再把 `payload-xpu.img` 以 `--check` 重跑一次，日志里必须出现
  `"status": "already-patched"`（幂等性证据）；
- 补丁失败会让 job 变红（不会静默产出未打补丁的镜像）。

拿到 `payload-xpu.img` 后，**若没有 boot image 模板**，仍用
`scripts/repack-v0-bootimg.py` 配 `shennong/Mu-shennong-6-pmgr2.img` 打包；
若设备上有 `Mu-shennong-smp.img`，直接用 4.2 的 `--image` 模式更简单（一步到位）。

---

## 5. boot image 打包（官方流程的缺口，本轮补充核实）

**`unixnu payload` 产出的是 FAT 卷（ramdisk 内容），不是可刷的 boot image。**
`payload.py` 首行与末行都写明。`kernel.yml` 里没有 `bootimg` 步骤。

**`unixnu bootimg` 的真实行为（本轮读源码核实，`scripts/unixnu/bootimg.py`）**：

1. `DEFAULTS = {'header_version': 0, ...}` —— **默认就是 v0**；
2. 实际值 `values.update(config.get('boot_image', {}))` 来自
   `<uefi>/Resources/Configs/<[firmware].config>.toml`，再被 `board.toml` 的
   `[bootimg.image]` 覆盖（`values.update(ctx.board.get('bootimg', {}).get('image', {}))`）；
3. 所以「bootimg 生成 v4」**不是代码行为，而是设备配置的选择**；
4. `verify()`（`bootimg.py:122-123`）用 v0 布局解包并比较 `kernel_address`（偏移 12），
   在 v4 头里那个位置是 `os_version`，因此对 v4 必然抛
   `boot image header does not match the requested parameters`——**但文件已正确写出**。

**为什么 CI 还是不能加 bootimg 步骤（本轮新证据）**：
`unixnu bootimg` 会 `load_toml(uefi/Resources/Configs/shennong.toml)`。本轮用
GitHub API 核对：

- `GET /repos/UniXNU/uefi-sheng/contents/Resources/Configs/shennong.toml?ref=sheng` → **404**
- `Resources/Configs/` 目录里有 87 个机型配置（`sheng.toml`、`houji` 没有、`pagani`、
  `pipa`、`sweet_k6a` …），**没有 `shennong.toml`**
- `BootShim/BootShim.S` 与 `Resources/Scripts/mkbootimg.py` 在 `uefi-sheng@sheng` 里**存在**

结论：shennong 的 Mu-Silicium 设备层（`Resources/Configs/shennong.toml` + FD + DTB）
既不在本仓库，也不在 `uefi-sheng@sheng`。它当初是在另一处本地环境构建的。
**要把 bootimg 自动化，先要把这一层固化进仓库**（或把 `[firmware]` 指向一个确实含
`shennong.toml` 的 checkout）。在那之前，`[bootimg.image]` 写什么都不起作用。

**可靠打包法（已验证）**：`scripts/repack-v0-bootimg.py`，复用已知良好镜像的 v0 头 +
kernel 区，追加新 payload。前提是新 payload 必须**正好 201,326,592 字节**。

**若要改用官方 `bootimg`**（本机有 Mu-Silicium shennong checkout 时）还需：
- `board.toml` 的 `["bootimg"]` 里 `dtb_node` 清空成 `[]`，否则 `fdtput` 报
  `Error at 'splash_region': FDT_ERR_EXISTS`（dtb 里已有该节点）
- `--local <dir>` 下需要有 `socs/sm8550/`，否则报 `SoC sm8550 is not cached`
- 要在 `board.toml` 加 `["bootimg"."image"] "header_version" = 0` 才能得到 v0

---

## 6. 阶段进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| A | 构建链（XNU 编译 / 链接） | ✅ 完成，CI 多轮成功（最近 run 40868470568 / #87） |
| B | UEFI 菜单（Device Tree / ADT 四道校验） | ✅ 完成 |
| C | XNU 内核启动（AMFI / bsd_init / 内核栈） | 🟡 启动序列进行中：已过 arm_vm_init、kernel_bootstrap、console、sched、clock；卡在 `early_random()`（详见 §16，**此前记的「已达成」不成立**） |
| D | prelink（合并原厂 IOStorageFamily） | ✅ 完成 |
| E1 | payload / boot image 打包 | 🟡 payload 完成；CI 现会产出打过 B 的 payload；boot image 仍缺设备层（见 §5） |
| E2 | UFS 块设备 ABI 绑定（11 个 `IOBlockStorageDevice` 符号） | ❌ 静态路线已证伪 |
| E2.5 | `/cpus` 归属（修法 B） | ✅ 真机验证生效（panic 消失、彩条 2→3，见 §15/§16） |
| E3 | mockfs / RAM-only 根卷 | ⬜ 未验证（panic 发生在更早阶段） |
| E4 | 8 核 SMP | ⬜ 未开始（ADT 现只有 cpu0） |
| E5 | iOS 用户态（launchd） | ⬜ 未开始 |
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

### 7.5 「加上 `sheng-smp=1` 就能过 AppleARMCPU」（本轮证伪）

见第 3.2 节：`sheng-smp` 只作用于副核心的 probe 门控，启动核 `cpu0` 无条件进入
`IOCPU::probe`；本机 ADT 又只有一个 CPU 节点。所以这条路线**数学上不可能改变结果**。

---

## 8. 剩余工作

### P0'｜修法 B：已完成真机确认（2026-11-02），现转入「让挂起可见」

B 已在真机确认生效（见 2.0 节）：`AppleARMCPU.cpp:111` 消失、启动多走一个 stage、
`skip-gic` 对照排除 `prepareGic()`。当前卡点是**静默挂起**，没有文字可判读，
所以下一步是把诊断屏（`CONFIG_XNU_BOOT_PROGRESS=y` + `boot-progress=2`）构建出来，
让屏幕直接写出阶段行与内核控制台最后几行。构建侧的坑（`QcomMdt.h` 缺失、
上游的 UFS/owner-root 守卫）已在 `f2f758c` 处理。

原始流程（留档）：

```bash
# 在你自己的电脑上（设备已插入）
adb devices                                    # 应看到 23116PN5BC
adb pull /sdcard/Download/Mu-shennong-smp.img .
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img --check
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img \
    --out Mu-shennong-xpu.img --report Mu-shennong-xpu.json
fastboot boot Mu-shennong-xpu.img
```

判读：

- panic 不再是 `AppleARMCPU.cpp:111` → **本轮验收达成**，记录新的 panic 点
  （预期回到 `IOKitBSDInit.cpp:984`，或进 mockfs 的更后面）
- 仍是同一个 panic → B 在该镜像上没生效。先看 `--check` 是否真的找到并改了
  （工具会打印 `offset`、`status`、`changed_bytes`），再看 `payload` 里的
  `kernel.macho` 是否被 UniXNU loader 真正加载（对比 sha256）
- panic 更早 / 黑屏 → 回退 `MOCKFS=n` 重建，把两个变量分开

### P1｜mockfs 验证（E3）

mockfs 已**确实链接进内核**。两个已知缺口：

- `build-mockfs-fixture.py:54` 自称 `"Offline minimal-root fixture only"` —— **只有代码，没有真实 launchd**
- `mockfs-test-file.patch` 定义 `struct mockfs_test_header`
  （`launch_offset / launch_size / test_offset / test_size`），说明**完整版**需要把
  `/sbin/launchd` 与 `/probe.bin` 打进 fixture。这两个文件需从固件的 `Cryptex1,SystemOS` 提取

**触发机制**：`mockfs_vfsops.c` 提供 `mockfs_mountroot()`，XNU 的 `vfs_mountroot()` 会自动遍历尝试，
**不需要额外 bootarg**。`vfs_conf.c` 在 `-DMOCKFS=1` 时会把它注册进 vfsconf。

### P2｜8 核 SMP（E4，修法 B 之后）

现在 ADT 只有 `cpu0`。要跑 8 核需要同时满足（参考同 SoC 的 houji 记录
`archive/docs/cpu-scheduling.md` 与 rmx1971）：

1. ADT 暴露 8 个 `cpu*` 节点，`reg` = 实测 affinity（SM8650：MPIDR `0x81000000 + n*0x100`，
   即 `0, 0x100, … 0x700`；2×A520 + 5×A720 + 1×X4）
2. kernel args：`sheng-smp=1 cpus=8 armcpu-self-ipi=1 armcpu-timer-intid=…`
3. ADT 与驱动接收到的核数必须一致（否则 ArmCpu 会 panic 而不是少核启动）

**必须先有 B**，否则 Apple 的 CPU 类仍然抢 nub。

### P3｜UFS 块设备（E2）+ 真根卷

只有前面都过不去、或确实需要真根卷时才回到这里。可选路径：

- **KDP 通道**：给 shennong 做网卡或 USB device 驱动，建立 lldb/KDP，拿真实地址
  （工作量大，一劳永逸）
- **静态推导 + 跳过 audit**：vtable 扫描 + 指令解码拿地址
  （三层 ABI 假设未验证，错则真机崩溃）

---

## 9. 关键资产

### 产物（在测试设备 shennong 上，不入库，原因见 ARTIFACTS.md）

下表是**上一轮（2026-10-30）的记录**，本轮无设备，**未复核**。

| 文件 | 大小 | sha256 | 说明 |
|---|---|---|---|
| `Mu-shennong-smp.img` | 203,726,848 | `6b1be67c…` | 含 `sheng-smp=1`；按 §3.2 预期无效，可作对照 |
| `Mu-shennong-mockfs-v0.img` | 203,726,848 | `e46ea1f3…` | 已测，panic 于 `AppleARMCPU.cpp:111` |
| `Mu-shennong-mockfs.img` | 203,730,944 | — | **废弃**，v4 头，UEFI 找不到 ramdisk |
| `payload-smp.img` | 201,326,592 | — | 已加 `sheng-smp=1` 的 FAT 卷 |
| `payload-mockfs.img` | 201,326,592 | `a1ef77bf…` | CI 原始产物（run #87） |
| `kernel-mockfs.macho` | 51,970,048 | `c527b761…` | prelink 后的内核，含 mockfs |
| `shennong/Mu-shennong-{0..6}*.img` | 各 203,726,848 | — | 历史镜像，`6-pmgr2` 最新（v0 打包模板） |
| `shennong/SILICIUM_UEFI.fd` | 3,145,728 | — | UEFI 固件卷（`0x300000`） |

### 完整哈希（上一轮记录）

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

- XNU 编译（`build-xnu-4k-baseline.sh` 依赖 Apple SDK / Xcode toolchain；
  上游默认 XNU tag 是 `xnu-10063.141.1`）
- 官方推荐路径：GitHub Actions 的 `macos` runner（仓库 `kernel.yml` 已就绪）

**Linux / 任意平台都能做的**

- UEFI 固件卷（EDK2 + clang，需 Mu_Basecore 与 uefi-sheng）
- payload 打包（Python + mtools）
- boot image 拼装（纯 Python：`scripts/repack-v0-bootimg.py`）
- payload / kernel 内文件修改（mtools + 本仓库脚本）
- kernel.macho 的 static 检查与打补丁（`scripts/patch-applearmcpu-ioname.py`）
- 内核 / payload 的静态检查（`strings`、`llvm-nm`、段表解析）

**前置依赖**

- Python 3.9+（本仓库脚本只用标准库）
- `mtools`（`mcopy` / `mtype` / `mdir`）
- `clang` + `llvm-objcopy` + `llvm-nm`
- 可选：`aarch64-linux-gnu-gcc`（某些组件）

---

## 11. 本次会话的环境（与项目无关，接手者可参考）

2026-11-02，本会话在 **WSL2 Ubuntu 24.04** 上，**没有设备、没有 macOS**：

- 网络：`github.com:443` 与 `raw.githubusercontent.com` **不可达**；
  `codeload.github.com` 与 `api.github.com` **可达**。取上游源码用
  `https://codeload.github.com/<repo>/tar.gz/<ref>`，查文件/提交用 GitHub API。
- 因此本轮**无法 `git push`**（见提交说明），也无法跑 GitHub Actions。
- 所有结论要么来自仓库内容，要么来自下载的上游源码；真机行为一律未测。

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

> 与 ADT 的对应关系（本轮核对）：`/arm-io` 的 `ranges` 把 GIC 窗口基址定在
> `0x17000000`，`/arm-io/intc` 的 `reg` 给 dist 偏移 `0x100000`、redist 偏移
> `0x180000`，于是 dist=`0x17100000`、redist=`0x17180000`，与上表实测值一致；
> `redistributor-stride = 0x40000`。这三项都在 `scripts/make-shennong-adt.py` 里。

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

---

## 15. 真机 boot-progress 结果（2026-11-02 深夜）

第四次构建 `41464721313`（commit `65450b3`）的产物
`shennong-kernel-1` 经修法 B（`AppleARMCPU` IONameMatch `cpu`→`xpu`）打补丁、
用 `repack-v0-bootimg.py` 重打包成 203,726,848 字节的 v0 镜像后，
`fastboot boot` 到真机（`9f72e95c`，Android 14 出厂、未解锁刷写，仅内存启动）。

**屏幕读数**：
- 顶部绿、蓝、品红三条彩条（与之前 xpu 测试相同，第三条出现即修法 B 生效）
- 中部一行白/绿相间小方块，约 30 个，**没有 panic 清屏、没有白字**
- 由此确认：内核已绑定帧缓冲（`boot_progress_bind` 成功）、跑完
  `kernel_bootstrap_thread` 的日志序列、进入 `bsd_init()` 并走到中后段；
  之前"静默挂起"的卡点被推后了，`AppleARMCPU.cpp:111` 与 `initCPU()` 都已通过
- 按 `startup.c` / `bsd_init.c` 的事件顺序折算，约 30 个事件方块对应
  `bsd_init` 的 `calling socketinit` / `domaininit` / `skywalk_init`
  一带（网络栈初始化），**尚未**到 `vfs_mountroot`（到那里需要 33 个以上）
- 下一版诊断（commit `7bd7470`）：12 个命名阶段改为固定位置+固定颜色的
  「阶段信道」（`y = h/4`），`bsd_init: ` 打印单独放 `y = h/2 + 70` 的蓝色行，
  事件行按 30 个一组自动换行；一张照片即可直接读出过了哪些命名阶段。

**注意**：fastboot boot 后手机停在诊断屏，需长按电源+音量减重启进 fastboot
才能再次烧录；本次全程未写任何分区。

---

## 16. v5 / v6 诊断屏结果（2026-11-03 凌晨）

第五次构建 `41474782494` 因 GitHub macOS 跑器排队约 15 分钟被系统取消（kernel 任务 
steps 为空，与代码无关）；重发的 `41477516638`（commit `816641b`）成功，
产物 `shennong-kernel-1` 41,618,851 字节，经修法 B + `repack-v0-bootimg.py`
得到 `Mu-shennong-v6.img`（203,726,848 字节，sha256
`b241ba71ca99b57258ddaad2d4513b5d9d7379241c94c6391539b3d24f97610b`），
`fastboot boot` 成功（Sending 5.07s / Booting 0.08s）。

**屏幕读数**（照片 + 肉眼双重确认）：
- 顶部绿、蓝、品红三条带 ✔ 修法 B 继续有效
- **没有任何命名阶段彩色牌**（12 个阶段一个都没点亮）
- 白绿事件格子 **2 行**（第一行 30 个满行 + 第二行余数）

**结论（修正）**：事件数 ≥ 30，但 `bsd_init` 一次都没到达
（`bsd_init enter` 的黄色牌、`bsd_init: ` 打印行都不存在）。
之前"卡在 `bsd_init` 中后段、`socketinit` 一带"的推断**作废**——那是按
可见方块数外推的误判。真实卡点仍在 `kernel_bootstrap()` / `startup.c`
的早期启动序列里：`arm_vm_init` 已通过、帧缓冲已绑定、≥30 个启动事件后停住。

**下一步（已提交，待真机验证）**：commit `3a0d66c`（run `41484351048`）把诊断屏
升级为 v3：
- `y = h/3`：8 位二进制方块 = `boot_progress_stage()` 事件总数（白=1、深灰=0）
- `y = h/3+100`：8 位二进制 = `bsd_init: ` 打印数
- `y = h/3+220`：12 格命名信道 = 板级里程碑（arm_vm_init → bsd_init → vfs_mountroot）
- `y = h/3+320`：12 格命名信道 = 早期启动里程碑（console_init → sched_init → PE_init_iokit 等）
- `y = h/2`：事件格子，换行间距改 50px，不再和别的行重叠

这样一张照片就能精确读出"第几个事件"和"过了哪些命名里程碑"，无需数格子。

**运行环境备注**：2026-11-03 凌晨 github.com 的 443 端口再次不可达，
`git push` 改为走 api.github.com 的 Git Data API（blob → tree → commit → ref），
产物下载仍被 Azure 存储段封锁，需用户浏览器手动下载。
