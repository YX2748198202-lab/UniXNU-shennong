# 项目状态（权威，随阶段推进更新）

最后更新：2026-11-20（青色候选仍仅黄条；Platform Expert 链接修复通过针对性构建）
当前可复现基线：**fi102**。当天新对照与 2026-11-14 历史实机记录分开判读。

## 2026-11-20：原哈希复跑仅黄条，检查点前移

`6fc36e3b…` 红带原镜像 13:54 单次复跑，Bootloader 接收，照片仍只有黄条。说明新增的 post-ISB 指令不是“只看到黄条”的必要条件；历史 XNU 红带成立，但目前入口未稳定复现。下一件事是只临时启动已预检的 `Mu-shennong-fi102-pre-branch.img`（`8338b7015c9d6f5cddbf5ab3a7384ccc6eb79417aebb039d30d8f3e5fbd06f6e`）：保留黄条，在 DarwinBoot 关 MMU、TLBI 和末尾 `isb` 之后、`br x1` 之前画一段青色。XNU、ADT、存储开关、FD 未变。14:01 已通过 `fastboot boot` 临时下发一次并收到照片：仍只有黄条，没有青色或红色。无法区分 MMU 关闭后未取指和显存写入不可见，暂停依赖色带的重复实验。

## 2026-11-20：post-ISB 诊断未命中，先核验入口可复现性

只做一次临时启动 `Mu-shennong-fi102-post-isb.img`（`8a71a5ea29e8cbcf660995de1cd5b5f7fc14ce3c78405e8437388f9967bd361b`）。Bootloader 接收成功；105 秒观测未见同一设备通过 USB 回来。用户明确确认无黑屏、自启，**是手动回到 Fastboot**。实机照片仅见加载器黄条和残留菜单，没有 XNU 红/蓝色带，所以这次不能用复位缺失把停点归到 `isb`，也不能证明没执行内核第一条指令。

从两份最终 boot image 的内置 FAT 反向取出 Mach-O，确认入口分支与整个 red/blue 探针槽逐字节相同；EFI、ADT、菜单、存储开关及其他 FAT 文件也未变。唯一内核差异在原 `isb` 后的跳转和同页空槽的 44 字节复位探针。详见 [实验记录](agent-progress.md#2026-11-20fi102-post-isb-复位探针与入口对照)。

## 2026-11-20：红色入口及 16 条主色带的实机证据

`Mu-shennong-fi102-entry-red.img`（SHA-256 `6fc36e3ba510de980c437b692bff8e304a050b0274d3ebd7340d4dada91f96de`）保留黄条 EFI，新增不读取 `boot_args` 的窄红带。照片确认红带、原蓝条及完整 16 个主色带：已执行 XNU 入口，原探针成功读取 `boot_args` 并写屏；最后一条绿色（band 15）来自 `0xfffffff00ad8341c` 转入 `0xfffffff00ad81f20` 的探针，已在 `msr SCTLR_EL1, x0` 之后、该探针补执行原 `isb` 之前。不能据此确认 `isb`、进入 `_arm_init`、console 或用户态。本轮照片没有新的 XNU panic 文字。详见 `entry-red-20261120.QAqVbe` 下的两张照片、`band-sites.txt` 和反汇编。

## 2026-11-20：黄色加载器标记确认缓存维护完成

同一份 fi102 内核、ADT、启动参数和 FD 上，只替换 `DarwinBoot.efi` 的绘制位置及颜色。新镜像 `4eaacdc82dc9d62a981519b87560c8f8768ee2537d1a82d9911380bfffe21e42` 实机照片显示顶部黄条，未见 XNU 蓝/品红或 panic。黄条在 cache 维护与屏障序列之后，仍在关闭 MMU 和 `br x1` 之前，故当前不再将缓存维护循环视为最后可见阻塞，也不声称已进入 XNU。照片见 `handoff-late-20261120.n9SjOv`。下一项用 `__TEXT_EXEC` 已存在的第一个探针槽验证能否执行不依赖 `boot_args` 的帧缓冲写入。

## 2026-11-20：初次实机对照只观察到加载器绿条

`Mu-shennong-fi102-storage-off.img`（SHA-256 `a2390d819d8b6e26d769e5ceb8725b42b79cf71e86d976c96620bae5b85c28a5`）只在归档 fi102 上关闭存储探测、根卷发布与持久日志，内核不变。照片确认 UEFI 启动项已执行，出现在 `ExitBootServices` 成功后、cache/MMU 交接与 `br x1` 之前的 DarwinBoot 绿条，未见蓝/品红探针或 panic。背景菜单是残留画面，并非等待按键；主机之后只读确认设备已回 bootloader Fastboot。

这轮不能判定 `br x1` 是否已执行，也不能排除早期 XNU 执行但探针没显示。先分辨加载器跳转前后；历史 fi101 的 console 写入故障仍是独立的待修问题。照片、哈希、反汇编见 [进度记录](agent-progress.md#2026-11-20-实机fi102-关闭存储诊断对照)。

## 2026-11-20：console 写入故障已定位，修复尚待完整链接

历史 fi101 的原始异常是 `_PE_init_printf(FALSE)` 写 `_PE_putc` 时发生的 EL1 L3 写权限 fault；屏幕的栈报错来自异常处理，不能作为 SP 偏移的证明。归档 native Mach-O 已把 `_PE_putc` 和 `_PE_kputc` 链进 `__KLDDATA,__const`，并非 prelink 首次搬过去。该段在 `arm_vm_prot_init` 即只读，Mach-O 自身标的 `rw-` 不代表运行时。`scripts/check-console-layout.py` 可在 native 和 fileset 上验收这两个符号的保护生命周期。

fi102 仍包含同一写入，但是否执行到该点未知；fi134 跳过该写入，不是修复。 独立的 `patches/experiments/pexpert-late-write-section.patch` 已在固定 XNU 源码上应用并通过 arm64e Mach-O 声明级链接回归：两个回调及同两文件的五个 late 变量从 `__KLDDATA,__const` 留在 `__DATA_CONST,__pe_late`，不改段保护。补丁未启用到默认构建，尚未做整核链接、prelink 或实机验证。优先在链接输入中保留 late-read-only 数据到 `__DATA_CONST`，仅搬移不需要晚写的数据，并验证布局容量、prelink 和实机。详细证据见 [进度记录](agent-progress.md#2026-11-20-console-写入异常与链接布局回归检查)。

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
- 走过早期页表构建，并执行 `msr SCTLR_EL1`；实际 fi102 的 band 14 在写入前，band 15 在写入后、恢复原 `isb` 前。
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
1. 暂停要求用户复跑色带或按键。当前冷暖启动是否影响交接未知；若再定位 DarwinBoot 交接，使用独立于显存的信号，并在有可验证的候选之后再约实机。
2. 先在固定 native 构建中验证 Platform Expert 窄补丁：不启用历史失败的 device patch series；完成整核链接，检查 `__pe_late` 所占页面、`__DATA_CONST` 至保留 kext 的布局边界，再在 prelink 输出上重跑 `scripts/check-console-layout.py`。该修复针对历史已证实的 console 写权限问题，不解释当前黄条。
3. 有手机时，用 SHA-256 绑定已预检对照与候选镜像，确认是否穿过 `_PE_init_printf(FALSE)` 及 `_machine_startup`。不因无输出认定已返回，不以 fi134 的 NOP 或改变栈顶作为修复。
4. 只有在证实越过 console 后，再按单变量推进 CPU/FIQ 初始化以及 `kernel_bootstrap` / `bsd_init` / 根卷挂载。

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
band 3–15 = 入口检查点；归档 fi102 应以实际反汇编为准，不直接套用 `patch-entry-bands.py` 的默认站点表。fi102 的 band 14 位于 `0xfffffff00ad83414`（MMU 写入前），band 15 位于 `0xfffffff00ad8341c`（写入后、原 `isb` 前），不是 `_arm_init` 标记。
判读：绿色只证明走到 `DarwinEnter` 的绘制循环（此版本在 `ExitBootServices` 成功后）；不证明已执行到 `br x1`。没有蓝/品红是未观察到 XNU 探针，不足以证明未进内核。
