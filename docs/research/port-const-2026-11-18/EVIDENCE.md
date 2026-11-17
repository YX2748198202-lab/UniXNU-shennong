# PORT_CONST 修复证据（2026-11-18）

## 已验证

| ID | 类别 | 证据与结论 |
|---|---|---|
| E1 | FACT 👁只能看图 | fi135 用户照片 sha256 `06c1cfe2bca750794520543fa709b792d780e790ed0e22e607fd26f5dc7b52a0`：PC `0xfffffff00ad73a18`、FAR/x20 `0xfffffff00c8c41f0`、ESR `0x9600004f`。与 fi134 相同。 |
| E2 | FACT ✅可命令 | fi135 实际内核该 PC 的指令为 `str xzr, [x20]`。原生 `__KLDDATA,__const` 起址 `0xfffffff00c89c000`、长度 `0xbe9a0`；故障地址在其中。 |
| E3 | FACT ✅可命令 | 本地 XNU 源码的 `arm_vm_init.c` 对 KLDDATA 初始 RNX，monitor finalize 清 PTE；`OSKext.cpp:1214–1254` 执行段析构并通过 IODTFreeLoaderInfo/ml_static_mfree 回收 KLDDATA。常驻变量放入此段存在权限与生命周期双重冲突。 |
| E4 | CONVENTION ✅可命令 | 新实现仅针对实际 `.cache/xnu-work`；不存在时失败，不回退修改 refer/xnu。所有文本变换先完成上下文校验，再写文件；每次执行单独记录哈希。 |
| E5 | CONVENTION ✅可命令 | `__PORT_CONST` 在预链接尾部分配区、BOOTDATA 之前独立分配，KLD 原有生命周期不改。初始 RWNX，finalize RNX；monitor physmap 使用与 DATA_CONST 相同的只读别名策略。 |
| E6 | FACT ✅可命令 | 测试覆盖原布局回归、新段边界/地址转换、重叠失败、未知段失败、源补丁幂等/失败行为、审计器的格式和保护验证。实际执行测试总数由 P0-EXEC.yml 记录。 |
| E7 | EDGE ✅可命令 | 缺失 split-segment 记录时不得以 chained pointer fixups 代替指令重定位；CI 保持上游严格检查，并检查实际 linker probe 的 v2 split-info 和 RW/NX 段元数据。 |
| E8 | EDGE ✅可命令 | CI 将审计实际原生带符号内核及 fileset 的新段，归档实际源码、目标文件、补丁回执、链接参数和哈希。 |

## 未验证的边界

- 真正的 macOS/Xcode 链接与完整内核编译尚未执行；本地测试不等同于 CI 编译通过。
- 新内核中的启动、finalize 页表权限和是否越过 fi135 故障尚未实机验证。
- 元数据 initprot/maxprot 仅证明 loader 请求的初始保护，不代替实际运行页表观测。
- 新源码构建会变化地址，现有固定地址探针须重新定位和校验；不复用 fi115 整段字节补丁。
- 当前尚未提交/推送本轮修改，也未启动本轮 CI；待用户明确许可提交推送。

## 实现入口

- `scripts/apply-port-const.py`：构建框架安装、实际编译树补丁与回执。
- `scripts/audit-port-const-kernel.py`：linker probe、原生内核、fileset 段及符号审计。
- `scripts/record-port-const-evidence.py`：归档编译证据，不读取环境或凭证内容。
- `tests/test_port_const.py`：本地测试。
- `.github/workflows/kernel.yml`：安装、显式链接参数、严格重定位、产物审计、证据归档。
