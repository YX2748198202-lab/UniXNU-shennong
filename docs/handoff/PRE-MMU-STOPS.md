# pre-MMU trampoline：站点、判据与修法

范围：内核入口（loader `br` 之后的第一条指令）到 `msr SCTLR_EL1` 之间。
2026-11-08 的判读结论是"iOS 27 供体卡在这个窗口里"（band 2 从未变白 → 没走到
`0xAD83418`），而窗口内全程 MMU 关闭、向量表在 KVA（不可达），所以**任何 C 代码、
panic 屏、串口、pstore 都来不及工作**：只能用"开 MMU 前能可靠写屏"的 cave 探针。
本文把这段代码的站点、静默自旋与判据固定下来，供下一轮直接判定。

## 1. 这段代码的源码位置

XNU `xnu-12377.121.6` 的 `osfmk/arm64/start.s`（本轮取回，24,685 字节）：

| 源码位置 | 内容 |
|---|---|
| `_start_first_cpu` 序言 | `msr OSLAR_EL1` → `DAIFSet` → 保存 `boot_args` → `msr VBAR_EL1`（物理向量）→ 读 `VirtualBase` / `PhysicalBase` / `MemorySize` → 装 SP_EL1/SP_EL0 → 清 bootstrap 页表池 → Mach-O 头 slide 修正 → `create_bootstrap_mapping` ×2 → `dsb ish` → `b common_start` |
| `common_start` | `MSR_TCR_EL1` → `bl set_mmu_ttb`(TTBR0) → TTBR1 → MAIR_EL1 → `tlbi vmalle1` / `ic iallu` → 热启动重装 TTBR1 → `msr VBAR_EL1`(KVA) → `#if HAS_APPLE_PAC` `PAC_INIT_KEY_STATE` → `msr SCTLR_EL1` → 回读自检 `b.ne .` → CPACR → TPIDR |

`HAS_APPLE_PAC` 是编译期开关：**arm64 构建没有 PAC 段，arm64e 构建有**。本板的 iPadOS
17.7.11 供体是 arm64，当前供体 iOS 27.0.1（24A446）是 **arm64e**，因此当前 payload 的这段
窗口比旧构建多出一整段 PAC 密钥写入。

## 2. 二进制实测站点表（旧供体内核，用于固定"机理"）

样本：`kernel.macho`（iPadOS 17.7.11 供体，XNU 12377，sha256
`cceb91703b80124b3426811dcdccad1156a8170b4db989da5aa2770f64a09deb`）。
用 `scripts/locate-pre-mmu-sites.py` 从二进制本身定位（不依赖文档里的硬编码地址）：

| 站点 | 地址 | 判据 / 备注 |
|---|---|---|
| `_start_first_cpu` 入口 | `0xfffffff0073f605c` | `msr OSLAR_EL1, xzr` |
| Mach-O 头守卫 | `0xfffffff0073f6104` | `cmp w1, #0x19`，下一条 `b.ne .`（`0x54000001`）→ **第一个 load command 必须是 LC_SEGMENT_64** |
| 建表循环越界自旋 | `0xfffffff0073f6284` | `b .`；由 `cmp x2, x25+0x10000; b.hs` 跳入 |
| `common_start` | `0xfffffff0073f6290` | `adrp` + `msr TCR_EL1, x1`（`0xfffffff0073f629c`）|
| TTBR0 安装 | `bl @ 0xfffffff0073f62a8` | 目标 `0xfffffff0073fa224`（单指令 `msr TTBR0_EL1` + `isb; ret`）|
| TTBR1 | `0xfffffff0073f62b8` | |
| MAIR | `0xfffffff0073f6300` | |
| TLB / I-cache | `0xfffffff0073f6308` / `0xfffffff0073f6314` | |
| VBAR（KVA） | `0xfffffff0073f633c` | 之后出错只能走不可达向量 |
| SCTLR 写入 | `0xfffffff0073f6350` | 常量重建为 `0x3454593d` |
| **SCTLR 回读自旋** | `0xfffffff0073f636c` | `cmp x0, x1; b.ne .` |
| CPACR / TPIDR | `0xfffffff0073f6374` / `0xfffffff0073f6378` | |

SCTLR 位的差别（这就是两个供体"同一个窗口、不同行为"的可见差异）：

| 构建 | 常量 | 置位的关键位 |
|---|---|---|
| iPadOS 17.7.11（arm64）| `0x3454593d` | M, C, SA, SA0, CP15BEN, SED, EOS, I, DZE, nTWE, TSCXT, EIS, UCI, nTLSMD, LSMAOE |
| iOS 27.0.1（arm64e，文档记录）| `0xfc54793d` | 上述全部 + **EnIA(31), EnIB(30), EnDA(27), EnDB(13)** |

差集 `xor = 0xc8002000`：arm64e 供体在开 MMU 的同一条指令里**同时启用指针认证**，
而 PAC 密钥写入发生在它之前（`start.s` 的 `PAC_INIT_KEY_STATE`）。这是当前窗口与旧供体
唯一结构性的差异，也是"旧供体能过、新供体过不去"时第一个必须排除的项。

## 3. 三个"无声停机"点（都可判定，不需要串口）

| # | 停机点 | 触发条件 | 观测 | 修法 |
|---|---|---|---|---|
| 1 | Mach-O 头守卫 `b.ne .` | payload 内嵌 kernel 的第一个 load command 不是 `0x19`（LC_SEGMENT_64），例如被 prelink 改成 fileset 头 | 方格镜像：白行有、红行全无；设备无 USB、不复位 | 让 payload 的内核保留 `LC_SEGMENT_64` 打头（builder 侧），或在 cave 里改写守卫 |
| 2 | 建表循环 `b.hs → b .` | `MemorySize`/窗口几何让 L2 页数超过池里剩余的 16 页 | 同上，且缺口位置在红行中段 | 收紧 `boot_args` 的窗口（`dram_size` / `owned_memory_size`）或加大池 |
| 3 | SCTLR 回读 `b.ne .` | 回读值与常量有位差（ARMv9.x 的 RES1/RAZ 位）| band 2 已变白、随后静默 | `scripts/patch-mmu-guard.py`：把自检改成记录 + 继续 |

注意 3 的真实顺序：它在 `msr SCTLR_EL1` **之后**。2026-11-08 的观测是 band 2 从未出现
（band 2 就画在 `0xAD83418` 之前的 `0xAD81560`），所以**当前卡点只能是 1 或 2，或者 PAC 段**
——回读自旋不能解释那次现象。

## 3.5 band 不是内核自己画的：是 payload 阶段注入的 cave（本轮新证据）

把旧 payload.img 里内嵌的 kernel 抠出来（`0xd7c00`，`filetype 0x2`）与构建产物
`kernel/kernel.macho` 逐字节对比，发现 payload 版本被改过两处：

| 位置 | 构建产物 | payload 版本 |
|---|---|---|
| `__start`（`0xfffffff0073f4488`）| `b _start_first_cpu` | `b 0xfffffff0073f4500`：从 `boot_args + 0x28` 起按 `(([+0x38] × [+0x48]) >> 4) & ~7` 算出条带长度，`stp w6,w6` 逐 8 字节填 **`0xff0000ff`（蓝）**，`dsb sy` 后 `b _start_first_cpu` |
| `common_start` 的 `msr SCTLR_EL1, x0`（`0xfffffff0073f6350`）| `d5181000`（真指令）| `b 0xfffffff0073f4560`：同样的填充循环，色值 **`0xffff00ff`（品红）**，填完才是 `msr SCTLR_EL1, x0` + `b 0xfffffff0073f6354`（回到 `isb`）|

这段注入与上游 pin 的 `scripts/patch-xnu-entry-probe.py` 完全一致：该工具用 `PAINT` 模板生成
"stage 1 蓝条（入口，MMU 关）"和 "stage 2 品红条（开 MMU 前一刻）"两个 cave，并把被替换的
`msr` 搬进 cave 执行。**注意颜色**：stage 2 是品红，不是白色；早期笔记里"band 2 白"的说法
是判读错误，已作废。

四个后果：

1. "band 2 没出现"只能证明**没走到 `msr SCTLR_EL1` 那条跳转**，不能区分"停在前面"还是"填充循环
   本身很慢/长度为 0"。
2. 填充长度取自 `boot_args` 的 `+0x38` 与 `+0x48` 两个字段。若 iOS 27 的 payload 改了这两个字段
   的含义或它们为 0，填充长度就是 0 → **循环一条都不写、屏幕毫无变化**，看起来和"没执行"一样。
3. 若这两个字段给出很大的乘积，填充会跑很久 → 表现为"卡住"，但其实在跑。**因此下次上机必须
   至少等 5 分钟再判定死亡**。
4. 该 cave 会破坏 `x1..x6`（`assembled` 代码里用到 x1/x2/x3/x4/x5/x6），`common_start` 之后只
   依赖 x0（SCTLR 常量）与 x20/x21/x22/x23/x25，所以不会直接破坏后续流程。

上面这套注入是**上游工具**做的，本仓库此前缺的正是这个工具：`scripts/patch-xnu-entry-probe.py`
已按 pin `c740efb5` 原样 vendor 进来（只加了一段来源说明），并配了
`scripts/test-entry-probe.py` 的契约测试（针对真实 `kernel.macho` 全绿）。

## 4. 判据矩阵（下一张照片怎么读）

镜像 `Mu-sq3.img`（`scripts/patch-pre-mmu-squares.py`，39 个 60×60 方块）：
第一行 17 个白色 = 入口序言（站点 1 在其中），后 22 个红色 = 建表到 PAC/SCTLR。
方块镜像与 band 镜像是两套独立探针：band 只有 2 个（蓝、品红），方块有 39 个，判读时不要混。

| 现象 | 结论 | 下一个最小动作 |
|---|---|---|
| 一个方块都没有 | loader 跳转或 `msr OSLAR_EL1` 之前出问题 | 在入口地址再放一个 cave，验证 `br x1` 目标与 `boot_args` 指针 |
| 白行部分出现 | 序言内具体位置死亡（`boot_args` 读取 / SP 切换 / 清池）| 按缺失方块的注入地址定停点 |
| 白行全有、红行全无 | 死在清池后到建表之间（站点 1 或 2）| 用 `locate-pre-mmu-sites.py` 确认守卫地址，再用单点 cave 二分 |
| 红行断在 PAC 段（只有 arm64e 构建有）| `msr API*Key*_EL1` 类指令在该核心未定义 | 先确认核心是否实现 FEAT_PAuth；必要时用 `patch-mmu-guard.py` 同法跳过密钥写入 |
| 红行断在 `msr SCTLR_EL1` 之前 | 表/TCR/TTBR/MAIR 之一 | 按缺失方块定位 |
| 39 个全出现 | 死在 `0xAD81560` 内部（画 band 2 或开 MMU）| 查恒等映射是否覆盖当前 PC 与 `_arm_init` 的 KVA |

## 5. 重建与验证命令（不依赖硬编码地址）

```bash
# 1. 从任意 kernel.macho 重新定位站点（站点缺失会返回非零）
#    报告里的 sctlr_sites 列出所有 "msr SCTLR_EL1, x0"；若 trampoline 处已是 b，
#    说明该内核带 band 注入，真正的开关在注入 cave 里
python3 scripts/locate-pre-mmu-sites.py kernel.macho --json /tmp/sites.json

# 2. 生成 39 方格镜像（脚本自带 cave 落在零填充区的断言）
python3 scripts/patch-pre-mmu-squares.py kernel.macho

# 3. 自检：每个站点必须跳进自己的 cave，cave 必须以跳回 site+4 结束
python3 scripts/verify-squares.py kernel.macho

# 4. 工具链自身的契约测试（针对真实 kernel）
python3 scripts/test-entry-probe.py kernel.macho
```

以上 1–4 在本轮已对旧供体内核跑通（`locate` 输出见第 2 节；`test-entry-probe` 全绿）。
对**已注入 band 的 payload 内嵌内核**（从 `payload.img` 的 `0xd7c00` 抠出）跑 `locate` 也能通过，
且会把真实开关报成 `msr SCTLR_EL1, x0 (injected cave) 0xfffffff0073f459c`。

## 6. 仍未验证的事项（不得当成结论）

1. iOS 27 供体的实际 payload 内核**不在本机**（CI artifact 保留 7 天，已过期），因此上面
   关于 PAC 段的推断只基于 `start.s` 源码与 SCTLR 常量差异，**没有该二进制的一手证据**。
2. `Mu-sq3.img` 从未上机拍照，39 方格的判据表仍未被执行。
3. `sheng-log` 通道今天接上了（`board.toml` 的 `sheng-log=1` + `scripts/read-sheng-log.py`），
   但它最早只能在 `SourceStorage.cpp` 起来之后写日志，**覆盖不到本窗口**；本窗口仍然只能靠
   cave 探针。
