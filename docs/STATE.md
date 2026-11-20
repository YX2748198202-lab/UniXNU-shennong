# 项目状态（权威，随阶段推进更新）

最后更新：2026-11-20（接管复核，未重测手机）
当前可复现基线：**fi102**；以下实机细节来自 2026-11-14 历史记录。

## 2026-11-20：console 写入故障已定位，修复尚待完整链接

历史 fi101 的原始异常是 `_PE_init_printf(FALSE)` 写 `_PE_putc` 时发生的 EL1 L3 写权限 fault；屏幕的栈报错来自异常处理，不能作为 SP 偏移的证明。归档 native Mach-O 已把 `_PE_putc` 和 `_PE_kputc` 链进 `__KLDDATA,__const`，并非 prelink 首次搬过去。该段在 `arm_vm_prot_init` 即只读，Mach-O 自身标的 `rw-` 不代表运行时。`scripts/check-console-layout.py` 可在 native 和 fileset 上验收这两个符号的保护生命周期。

fi102 仍包含同一写入，但是否执行到该点未知；fi134 跳过该写入，不是修复。优先在链接输入中保留 late-read-only 数据到 `__DATA_CONST`，仅搬移不需要晚写的数据，并验证布局容量、prelink 和实机。详细证据见 [进度记录](agent-progress.md#2026-11-20-console-写入异常与链接布局回归检查)。

## 2026-11-20 基线复核

- fi102 已从本地 CI run `42904596191` 归档的原始 Mach-O 重放；结果与留存 fi102 字节一致。归档的 prelink manifest 标记 `mapping_complete=false`、`runtime_qualified=false`、`loadable=false`；打包预检通过不等于 prelink 或实机验收通过。
- 已核对 iPhone17,1 / 24A446 IPSW 与解码后的 arm64e KernelCache pin。**原厂供体是 `xnu-13432.2.10~2`（Darwin 27.0.0），`xnu-12377.121.6` 是 native kernel 源码 pin**，不是原厂 KernelCache 的源码版本。两套目标的符号不互换。
- `fi103`–`fi134` 有本地留存镜像。fi134 内核相对 fi102 只差 5 条指令：4 条恢复 SP 换算，另 1 条在 fi101 panic PC `0xFFFFFFF00B3A154C` 把 `str` 换成 `nop`。预检和字节核验已通过，但没有可归属到该镜像哈希的实机证据；不升级基线，不把屏幕静默当作通过或失败。
- 尚不能确认 fi102 是否从 `PE_init_printf` 返回。先用对应地址、段保护和日志证据区分 SP 处理与原写入故障；不要叠加 fi134 的 NOP 或重复此前失败的插桩。详细命令及证据见 [接管进度](agent-progress.md#2026-11-20-接管复核与镜像预检修复)。

## 目标
把 XNU（iOS 27，iPhone17,1 27.0.1 24A446，device_class = d93ap）移植到小米 14 Pro
（shennong / 23116PN5BC / SM8650 / 12GB），最终在设备上启动 XNU 并运行 iOS 用户空间。
**不是 iPad / iPadOS。**

## 历史实机证据截至哪里
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
| 异常保存帧地址 | `0xFFFFFFF00CA27CB0` | fi101 panic `saved state`；不是期望的初始 SP |
| 显存 | base `0xFC400000`, 1440x3200, row 5760, 32bpp | loader 屏显 |

## 历史改动（fi 系列）
- **PAC 崩溃**（fi58）：`patch-arm-init-tail.py` 跳过 `_early_random` 导致 DRBG 回调为空 → `--keep-early-random` + ADT 种子扩到 256 字节。
- **cave 选址三处自伤**（fi79–fi88）：寄存器不能经 sp 暂存；cave 必须在全零且可执行（initprot 5）的区域；`CAVE_STRIDE` 必须是 8 的倍数；cave 尾部跳 `site+4` 不是 `site`。
- **x30 入口地址**（fi98）：`_start_first_cpu` 里 `adrp x30,#0xb476000 +0x8f0` 之后还叠了 `+virtBase −physBase`，在非 Apple 引导下算出错误入口。改为 `movz/movk` 硬编码 `0xFFFFFFF00B4768F0`。
- **console 通道**（fi101）：还原 `0xb4774c0`/`0xb4774d0`/`0xb4774d8` 三处 `bl`，Mu-Silicium 的 `FrameBufferSerialPortLib` 把内核 printf 画到屏幕。
- **栈换算实验**（fi102）：将 `0xad8309c/a0/b4/b8` 置为 NOP 后不再看到 fi101 的 panic，不能据此认定 SP 已修复。`_intstack_top` / `_excepstack_top` 对应的地址分别是 `0xFFFFFFF00CA20000` / `0xFFFFFFF00CA28000`；不要把 `saved state` 地址用作栈顶。

## 两条硬规则（踩过坑，务必遵守）
1. **`pacibsp` 之后的函数体不能插跳转型 cave**：PAC 用 SP 绑定，跳走再回来 `retabsp` 验签失败 → `brk`，表现是"完全没启动"（fi99 全灭真因）。`_start_first_cpu` 开头没有 PAC 序言，它后半段可安全插桩。
2. **`_start_first_cpu` 里 SP 和返回地址共用同一个滑动换算**：只删一边会让栈与入口同时对不上（fi96 全灭真因）。要么都改、要么都保留。

## 下一步（按优先级）
1. 在当前 CI 固定的 native 链接路径分离启动写入数据与真正的常量，保持 `__DATA_CONST` 在 VM finalization 后收紧；以实测 `0x78000` 理论差额为上限验证对齐和真实保留 kext 边界，再在完整链接和 prelink 后各运行 `scripts/check-console-layout.py`。
2. 有手机时，用 SHA-256 绑定已预检对照与候选镜像，确认是否穿过 `_PE_init_printf(FALSE)` 及 `_machine_startup`。不因无输出认定已返回，不以 fi134 的 NOP 或改变栈顶作为修复。
3. 只有在证实越过 console 后，再按单变量推进 CPU/FIQ 初始化以及 `kernel_bootstrap` / `bsd_init` / 根卷挂载。

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
