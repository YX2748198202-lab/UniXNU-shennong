# fi136 产物验收证据（2026-11-18）

| ID | 类别 | 已掌握的证据 |
|---|---|---|
| E1 | FACT ✅可命令 | CI 44127921741 / e386db83976395b6279a6a2a3be61d550333dee1 已 success。artifact 14351688283 为 299364655 字节，官方 SHA256 e1b9be37c26d88c564248055562109d9fa26166e5c5882f8eac83bade29075ad；本地下载一致。53 文件、928206283 字节解压、CRC/越界错误 0。 |
| E2 | FACT ✅可命令 | 归档 9 份编译证据哈希一致；实际 arm_vm_init.c 含全部 7 组补丁，MakeInc.def 有独立段次序。目标为 arm64e。 |
| E3 | FACT ✅可命令 | 原生内核含 1474120 字节 split-segment v2 记录；原生和最终 fileset 段位置一致。linkarguments 是局部记录，其中没有追加的 add_split_seg_info 参数；不能以该记录作为完整链接命令。 |
| E4 | FACT ✅可命令 | 实际机器码：arm_vm_prot_init 在 0xfffffff00ad776a0 调用保护函数，APX=0、TTE/PTE XN=1；finalize 在 0xfffffff00ad77b0c 调用 APX=2、XN=1，后接 DSB/TLBI/DSB/ISB。 |
| E5 | FACT ✅可命令 | fi135 FAR 对应 _ResetHandlerData；本轮该符号为 0xfffffff00c8c6198，位于常驻 PORT_CONST [0xfffffff00c8a0000, +0xbc000)。实际运行页表权限仍待观察。 |
| E6 | EDGE ✅可命令 | fi115/fi135 旧补丁包含 stack_chk_fail 改 ret、kalloc_type_view_parse 改 mov0/ret、TLBI 改 NOP 等功能短路。旧 7/7 只证明字节和容器一致，不是语义验收。fi136 不迁移这些修改。 |
| E7 | CONVENTION ✅可命令 | fi136b 仅修改两个 fatal 分派点（PACIBSP 之后），使用未占用代码填充和 PORT_CONST 尾部常量页，并重算原生 corecrypto HMAC；其余正常执行指令与原始 CI 完全相同。 |
| E8 | CONVENTION ✅可命令 | fatal 观察器仅在 panic 后使用私有 TTBR0 显示视图；不改 TTBR1、MAIR、PAC 控制，不在正常启动时调整映射。其动态显示效果未验证。 |
| E9 | FACT ✅可命令 | AppleARMCPU 的 cpu→xpu 沿用 CI 原有元数据修正，仅改变 1 字节，不改变代码。 |
| E10 | CONVENTION ✅可命令 | 待测镜像使用同一 fd43、fd46 头模板、shennong DTB；FAT 从本轮 CI payload-xpu 派生，除 kernel.macho 外文件应保持一致。 |
| E11 | EDGE ✅可命令 | STABS 调试符号可能保留未重定位地址；本地审计器已改为只采用 N_SECT，并增加回归测试。不得把调试条目当运行地址。 |
| V1 | FACT 👁只能看图 | fi135 照片旧故障为 PC 0xfffffff00ad73a18 / FAR 0xfffffff00c8c41f0 / ESR 0x9600004f。 |
| V2 | TARGET 👁只能看图 | fi136 的实际启动阶段、panic 文本及 resetWpar，须由新照片或等价设备日志确认。当前未观察，不因 fastboot OKAY 判定通过。 |

## 产物路径

- 原始 CI 与验证报告：`out/ci/44127921741/`。
- 第一版未上机候选：`out/diagnostics/fi136-fatal-only/`，保留原件。
- 最终待测候选：`out/diagnostics/fi136b-fatal-only/`，含版本标识及 resetWpar 查询输出。

本轮只运行了一次 CI，不继承旧集合的正常流程短路补丁。无已完成实机修复结论。
