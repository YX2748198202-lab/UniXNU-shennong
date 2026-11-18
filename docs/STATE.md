# 项目状态（权威，随阶段推进更新）

最后更新：2026-11-18 20:05
当前基线：**fi139**

## 目标
把 XNU（iOS 27，iPhone17,1 27.0.1 24A446，device_class = d93ap）移植到小米 14 Pro
（shennong / 23116PN5BC / SM8650 / 12GB），最终在设备上启动 XNU 并运行 iOS 用户空间。
**不是 iPad / iPadOS。**

## 现在停在哪
已越过 `arm_init` 尾部的 `_early_random`（`0xb477534`）与 `_machine_startup`（`0xb477550`）调用点，
进入后续内核初始化的 ledger 模板终结阶段。

- fi138 停在 `_ledger_template_finalize.cold.2+0xc` 的 `BRK #0xbffc`：常驻段改造把模板搬进了
  `__PORT_CONST`，而 `ledger.c` 的段归属检查只认 `__DATA_CONST`。
- fi139 已把该契约改为两段都接受，并覆盖源码里全部三处调用点，用新 256 字节种子打包，
  于 17:36:53 对 `9f72e95c` 执行唯一一次临时 boot，命令返回 0。
- **fi139 的实际停点尚无屏幕证据。** 命令返回 0 只证明 fastboot 交接完成。

阶段 C（到根设备挂载）**当前未通过**。历史旧基线（iPadOS 时代）于 2026-11-05 到过
`bsd_init` 之后的根卷挂载（`Failed to mount root device @IOKitBSDInit.cpp:984`）；
iPhone iOS 27 / arm64e 这条线还没有恢复到这个深度。

## 已验证的关键事实（均有真机照片或构建产物支撑）
| 项 | 值 | 来源 |
|---|---|---|
| kernel VA | `0xFFFFFFF007004000` | loader 屏显 |
| kernel PA | `0x8C0004000` | loader 屏显 |
| slide | `0xFFFFFFE747000000` | VA−PA |
| Mach-O VA → 运行 VA | `+0xFFFFFFF000000000` | 段映射核对 |
| `arm_init` | `0xFFFFFFF00B4768F0` | LC_UNIXTHREAD 链 |
| `_early_random` 调用点 | `0xFFFFFFF00B477534` | fi137/fi138 |
| `_machine_startup` 调用点 | `0xFFFFFFF00B477550` | fi137/fi138 |
| `_ledger_template_finalize` | `0xFFFFFFF00AB7F300`（492 字节） | fi139 |
| `_ledger_template_copy` | `0xFFFFFFF00AB7F4EC`（496 字节） | fi139 |
| `__DATA_CONST` 真实边界 | `0xFFFFFFF007DD0000 .. 0x7E31958` | Mach-O `segment$end$` |
| `__PORT_CONST` 真实边界 | `0xFFFFFFF00C8A0000 .. 0xC95AB08` | Mach-O `segment$end$` |
| 显存 | base `0xFC400000`, 1440x3200, row 5760, 32bpp | loader 屏显 |

`segment$end$` 是**未对齐的末节结束**，不是 `vmsize`。用 `vmsize` 算边界会多出一段，
让越界对象误判为合法。

## 已修复（fi 系列）
- **PAC 崩溃**（fi58）：`patch-arm-init-tail.py` 跳过 `_early_random` 导致 DRBG 回调为空 → `--keep-early-random` + ADT 种子扩到 256 字节。
- **cave 选址三处自伤**（fi79–fi88）：寄存器不能经 sp 暂存；cave 必须在全零且可执行（initprot 5）的区域；`CAVE_STRIDE` 必须是 8 的倍数；cave 尾部跳 `site+4` 不是 `site`。
- **x30 入口地址**（fi98）：`_start_first_cpu` 里 `adrp x30,#0xb476000 +0x8f0` 之后还叠了 `+virtBase −physBase`，在非 Apple 引导下算出错误入口。改为 `movz/movk` 硬编码 `0xFFFFFFF00B4768F0`。
- **console 通道**（fi101）：还原 `0xb4774c0`/`0xb4774d0`/`0xb4774d8` 三处 `bl`，Mu-Silicium 的 `FrameBufferSerialPortLib` 把内核 printf 画到屏幕。
- **栈指针**（fi102）：`0xad8309c/a0/b4/b8` 的 `+virtBase −physBase` 让 SP 落在 `0xCA20000` 而非期望的 `0xCA27CB0` → nop 掉该修正。
- **种子契约**（fi137）：ADT 的 `chosen/random-seed` 原来是 64 字节，ARM XNU 要 256。生成器改用系统 CSPRNG，扩展脚本改为严格节点解析 + 只读 `--check`，CI 加两处守卫。
- **fatal 观察器**（fi136b/fi138）：异常/panic 通路在完整检查下把 `PC/ESR/FAR/SPSR` 与来源标签画到屏幕，用于取代「只看颜色」。
- **ledger 常量段契约**（fi139）：三处内联检查全部接受 `__PORT_CONST`；原三条断言、原 PAC 栈帧、原失败调用点全部保留；只改 3 条入口分支共 12 字节。

## 两条硬规则（踩过坑，务必遵守）
1. **`pacibsp` 之后的函数体不能插跳转型 cave**：PAC 用 SP 绑定，跳走再回来 `retabsp` 验签失败 → `brk`，表现是"完全没启动"（fi99 全灭真因）。`_start_first_cpu` 开头没有 PAC 序言，它后半段可安全插桩。
2. **`_start_first_cpu` 里 SP 和返回地址共用同一个滑动换算**：只删一边会让栈与入口同时对不上（fi96 全灭真因）。要么都改、要么都保留。

修补丁时还有一条：改一处 `require_data_const` 类断言要先把源码里全部调用点数一遍。
只修 `finalize` 会让下次启动停在 `copy`。

## 下一步（按优先级）
1. 取 fi139 完整画面判读停点。若仍在 ledger 同一断言，说明段边界本身算错；若停在新位置，按新 `PC` 继续。
2. 全量扫源码里其它仍只认 `__DATA_CONST` 的段归属断言，一次清完，避免一次只修一个。
3. 补 `kernel.macho.crypto-hmac.json` 与内核的对应关系（当前该文件与已改内核不再自洽）。
4. 向阶段 C 推进：`kernel_bootstrap` → `bsd_init` → 根卷挂载。根卷到这一步才用到，**前期与根卷无关**。

## 设备事实
- 序列号 `9f72e95c`，只走 `fastboot boot`，刷写分区一律不做。
- ADT 保持 `dram-base = 0x80000000`、`dram-size = 0x300000000`、window `0x100000000`。**`dram-base` 不可随意改**（fi85 全灭真因）。
- 每个镜像只用一次新的 256 字节种子；同一镜像不重复启动。
- 本地没有完整 XNU 重链工具链（`xnu-host-cc`/`migcom`/`iig`/`lzfse` 与编译缓存均缺），
  因此走「从已启动内核派生原生二进制」的路子；这是派生，不是完整重建，manifest 里如实标注。
