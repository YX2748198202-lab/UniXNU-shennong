# 项目状态（权威，随阶段推进更新）

最后更新：2026-11-14 03:20
当前基线：**fi102**

## 目标
把 XNU（iOS 27，iPhone17,1 27.0.1 24A446，device_class = d93ap）移植到小米 14 Pro
（shennong / 23116PN5BC / SM8650 / 12GB），最终在设备上启动 XNU 并运行 iOS 用户空间。
**不是 iPad / iPadOS。**

## 现在停在哪
`arm_init` 尾部。内核已能：
- 从 DarwinBoot 进入 `_start_first_cpu`（`0xad8305c`）
- 建完页表、开启 MMU（`msr sctlr_el1` 成功，band 14 亮）
- 跳进 `arm_init`（`0xb4768f0`）并跑到尾部 console 初始化（`0xb4774dc`）
- **把自己的 panic 打到屏幕上**（fi101 首次实现）

## 已验证的关键事实（均有真机照片或构建产物支撑）
| 项 | 值 | 来源 |
|---|---|---|
| kernel VA | `0xFFFFFFF007004000` | loader 屏显 |
| kernel PA | `0x8C0004000` | loader 屏显 |
| slide | `0xFFFFFFE747000000` | VA−PA |
| Mach-O VA → 运行 VA | `+0xFFFFFFF000000000` | 段映射核对 |
| `arm_init` | `0xFFFFFFF00B4768F0` | LC_UNIXTHREAD 链 |
| `_PE_init_printf` 返回地址 | `0xFFFFFFF00B4774DC` | 调用点 `0xb4774d8` |
| SP_EL1 期望值 | `0xFFFFFFF00CA27CB0` | fi101 panic `saved state` |
| 显存 | base `0xFC400000`, 1440x3200, row 5760, 32bpp | loader 屏显 |

## 已修复（fi 系列）
- **PAC 崩溃**（fi58）：`patch-arm-init-tail.py` 跳过 `_early_random` 导致 DRBG 回调为空 → `--keep-early-random` + ADT 种子扩到 256 字节。
- **cave 选址三处自伤**（fi79–fi88）：寄存器不能经 sp 暂存；cave 必须在全零且可执行（initprot 5）的区域；`CAVE_STRIDE` 必须是 8 的倍数；cave 尾部跳 `site+4` 不是 `site`。
- **x30 入口地址**（fi98）：`_start_first_cpu` 里 `adrp x30,#0xb476000 +0x8f0` 之后还叠了 `+virtBase −physBase`，在非 Apple 引导下算出错误入口。改为 `movz/movk` 硬编码 `0xFFFFFFF00B4768F0`。
- **console 通道**（fi101）：还原 `0xb4774c0`/`0xb4774d0`/`0xb4774d8` 三处 `bl`，Mu-Silicium 的 `FrameBufferSerialPortLib` 把内核 printf 画到屏幕。
- **栈指针**（fi102）：`0xad8309c/a0/b4/b8` 的 `+virtBase −physBase` 让 SP 落在 `0xCA20000` 而非期望的 `0xCA27CB0` → nop 掉该修正，`Invalid kernel stack pointer` panic 消失。

## 两条硬规则（踩过坑，务必遵守）
1. **`pacibsp` 之后的函数体不能插跳转型 cave**：PAC 用 SP 绑定，跳走再回来 `retabsp` 验签失败 → `brk`，表现是"完全没启动"（fi99 全灭真因）。`_start_first_cpu` 开头没有 PAC 序言，它后半段可安全插桩。
2. **`_start_first_cpu` 里 SP 和返回地址共用同一个滑动换算**：只删一边会让栈与入口同时对不上（fi96 全灭真因）。要么都改、要么都保留。

## 下一步（按优先级）
1. 确认 fi102 是否越过 console 初始化：在 `_PE_init_printf` 返回点（`0xb4774dc`）之后加不破坏 PAC 的检查点，或直接看是否出现新 panic。
2. 若已越过：把 `patch-arm-init-tail.py` nop 掉的调用**逐个还原**（顺序：`cpu` → `fiq` → 其余），每还原一个看是否出新 panic——现在有文字输出，一次定位一个。
3. 若 SP 还差 `0x350`：把 `0xad83094` 的 `adrp` 基址改为 `0xca27000` 并 `add #0xcb0` 精确对齐 `0xCA27CB0`。
4. 之后：`machine_startup` → `kernel_bootstrap` → `bsd_init` → 根卷挂载。根卷要到这一步才会被用到，**前期与根卷无关**。

## 设备事实
- 序列号 `9f72e95c`，只走 `fastboot boot`，刷写分区一律不做。
- ADT 保持 `dram-base = 0x80000000`、`dram-size = 0x300000000`、window `0x100000000`。**`dram-base` 不可随意改**（fi85 全灭真因）。

## 复现
```
python3 scripts/apply-fi102-patch.py \
  <pristine kernel.macho> <out kernel.macho>
```
输出 sha256 应为 `800b4412fd125aef002035d552d4ff47af8588902a3da2de8f19ebd11f94a976`。
补丁表：`patches/fi102/kernel-words.patch`（1146 个 word），元数据 `patches/fi102/meta.json`。
完整构建链（ADT、payload、boot image）见 `docs/bringup.md` 与 `docs/agent-progress.md` 的 fi89–fi102 章节。

## 色带语义（入口探针）
band 0 绿 = DarwinBoot 交接；band 1 蓝 = stage-1；band 2 品红 = stage-2；
band 3–15 = `patch-entry-bands.py` 的 13 个检查点（站点表见 `scripts/patch-entry-bands.py`）。
判读：**三条都没出现 = 根本没进内核；只有绿色 = 入口之前出了问题。**
