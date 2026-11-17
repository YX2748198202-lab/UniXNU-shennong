# 根因：__DATA_CONST,__const 被搬进 __KLDDATA（提前只读段）

## 结论

`-Wl,-rename_section,__DATA_CONST,__const,__KLDDATA,__const` 是早期启动
"权限错误 + 写入"panic 的唯一根因。

## 源码证据（apple-oss-distributions/xnu, osfmk/arm64/arm_vm_init.c）

`arm_vm_prot_init()` 里每段的处置：

| 段 | 调用 | 结果 |
|---|---|---|
| `__DATA_CONST` | `arm_vm_page_granular_RWNX(segDATACONSTB, …)`（行 1439，注释 "Can DATACONST start out and stay RNX?"） | **可写** |
| `__KLDDATA` | `arm_vm_page_granular_RNX(segKLDDATAB, segSizeKLDDATA, 0)`（行 1463） | **立刻只读** |
| `__DATA` | `arm_vm_page_granular_RWNX(segDATAB, …)` | 可写 |
| `__BOOTDATA` | `arm_vm_page_granular_RWNX(segBOOTDATAB, …)` | 可写，但 finalize 时 `ml_static_mfree` |

并且 `arm_vm_prot_finalize()` 在 `XNU_MONITOR` 下把 `__KLDDATA` 的 PTE 全部
置空（`*pte = ARM_PTE_EMPTY`）——**该段在启动后期会被整段 unmap**。

`SECURITY_READ_ONLY_LATE` 语义是"lockdown 前仍可写"，所以这类变量必须在
`__DATA_CONST` 这类启动期保持 RWNX 的段里；搬进 `__KLDDATA` 后从
`arm_vm_prot_init` 起就是只读，任何早期写都变成权限错误。

## 实机证据

| fixture | pc | far | esr |
|---|---|---|---|
| fi115 | `0xad73a18` | `0xc8c41f0` | `0x9600004f` 写+权限错 L3 |
| fi131（第一处落点改到 `__DATA`） | `0xb082cd4` | `0xc8dfbf8` | `0x9600004f` 同型 |

fi131 证明这是**一类**写（多个位置）而不是单点，与该结论一致。

`__KLDDATA` 文件内容 39.7% 非零、开头是 chained-fixup 指针表 ⇒ 里面装的确实是
`__DATA_CONST,__const` 的内容。

## 修复

把 rename 目标改为 `__DATA,__const`（`prot_init` 里 RWNX，永久可写）。

代价：这批常量在内核运行期可写，W^X 强度低于 Apple 原生布局；属于 bring-up 期
的取舍，等启动打通后再考虑用内核补丁把 `__KLDDATA` 改成"finalize 前可写"。

## 未验证

- `__DATA` 是否有足够空间容纳该 section（链接期才能知道；若失败，CI 日志会显示）
- 修复后内核能否越过 `0xb082cd4`

## 修复方案演进（2026-11-17）

1. 先把 rename 目标从 `__KLDDATA` 改成 `__DATA`（prot_init 里 RWNX）。
   **失败**：预链接套件 `fileset_layout.py:208` 报 `Native __DATA overlaps a retained
   segment`——原生段在参考文件集里是固定槽位，`__DATA` 装不下搬过去的常量。
2. 改回 `__KLDDATA`（唯一有空间的段），改为**在 CI 里给 XNU 打源码钩子**：
   在 `prepare-xnu-source.py` 末尾追加一段，把
   - `arm_vm_page_granular_RNX(segKLDDATAB, segSizeKLDDATA, 0)` → `RWNX`
   - `va < (segKLDDATAB + segSizeKLDDATA)` → `va < segKLDDATAB`（跳过 finalize 的 unmap）

   位置选在"所有上游补丁应用完之后、编译之前"，且用 glob 找 `arm_vm_init.c`，
   不依赖任何脚本变量名。

## 为什么是这两处

`arm_vm_init.c` 里 `segLOWESTRO / segHIGHESTRO / seg*B / segSize*` 都是
`SECURITY_READ_ONLY_LATE`，本该在 `__DATA_CONST`（prot_init 里 RWNX）里活到 lockdown。
搬家把它们送进了提前 RNX 的 `__KLDDATA`，所以早期写一律权限错误。
