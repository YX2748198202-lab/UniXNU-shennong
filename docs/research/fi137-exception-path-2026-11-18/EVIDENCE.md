# fi137 入口与异常可见性证据

能力选择：当前技能目录为 Windows ACL 与 Office；本任务匹配现有 Mach-O 审计器、Capstone、LLVM 和只读源码工具，无匹配技能。命令复核由独立只读验证器执行。

| ID | 类型 | 状态 | 实测/依据 |
|---|---|---|---|
| E1 | FACT | ✅可命令 | 固定内核 SHA256=6817570eda24b599f943b77671dcce8c29ec6c748ce0a46fc696c79ee895c609；最终镜像=64bfd792e51ddff46a05d41d8ea8b04f0930c0fff501c06ddacb0d6dccd58dff |
| E2 | CONVENTION | ✅可命令 | 唯一 boot 回执、原14项验收和照片/镜像哈希一致；本轮仅创建派生审计/观察器候选，没有改冻结内核或 boot 镜像 |
| E3 | FACT | ✅可命令 | 实际 __start 含到 start_first_cpu 的直接 B；冷启动 x21=0 |
| E4 | FACT | ✅可命令 | LowExceptionVectorBase 的16个128字节槽全部为0x14000000，即 B self |
| E5 | FACT | ✅可命令 | common_start 中高 VBAR=0xfffffff00ad83348，SCTLR=…83418，CPACR=…8343c，RET=…83450；顺序为高向量→MMU→NEON→arm_init |
| E6 | FACT | ✅可命令 | SP1 spill-failed=0xfffffff00ad7d310:WFE / …d314:B self，不进入 panic；panic_with_thread_kernel_state 另有 hook 前的状态读取、原子写和 socd_client_trace |
| E7 | FACT | ✅可命令 | 冻结fatal-screen.c重编3144字节，与已启动内核对应字节完全相同；SHA256=e0000b5af466ba01d98c7e0e5fd9b7dcde343cb9e1289e72e939b17926480695 |
| E8 | EDGE | ✅可命令 | fb_setup失败会在画屏前进入WFE；格式化/页计数读取之后才统一清理缓存；两个fatal hook均保留PACIBSP |
| E9 | AMBIGUITY | 🤷不知道 | 本次实际停止PC及ELR/ESR/FAR/SPSR/TTBR/异常嵌套状态缺失；照片和回执没有补足这些值，不据此选硬件根因或修改正常逻辑 |
| E10 | EDGE | ✅可命令 | 旧源码读取显存末行两个magic决定是否禁止本轮显示，复现条件为旧像素存在而本轮claim=0；这是可证明的跨启动可见性缺陷，尚未证实fi137触发 |
| E11 | FACT | ✅可命令 | 派生候选把claim放到本轮零初始化缓冲区最后字节，并为日志NUL预留空间；14/14主机/离线用例通过，ARM64候选3128字节，未合入活动生成器或任何启动镜像 |
| E12 | FACT | ✅可命令 | _boot_progress_panic_text=0xfffffff00b6dbc90，2048字节在物化__DATA,__data内且文件内容全零；loader源码先ZeroMem再逐段CopyMem，作为每次加载初始化契约 |
| V1 | FACT | 👁只能看图 | 照片b89a54ee70b31344960bf91691d38e074906b4da6a13284879ee593520d81a83：绿色顶部、旧菜单背景，无可辨识内核异常报告 |
| V2 | EDGE | 👁只能看图 | 后续若进入新的测试轮次，应取得含PC/ESR/FAR/SPSR及记录来源的完整画面；本轮不执行 |

## 命令证据

- [入口/向量机器码与原始CI对照](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/entry-audit-r2/entry-exception.json>)。
- [冻结观察器源码](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi136b-fatal-only/fatal-screen.c#L336-L429>)。
- [候选重现与离线用例](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/claim-candidate-r2/claim-candidate.json>)。主机用例检查提取的C原语，非实机执行；ARM64编译验证独立观察器，无新内核/镜像。
- [只读验证器](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/verify-entry.py>)；运行 `python3 -B out/diagnostics/fi137-seed-contract/verify-entry.py` 生成本目录实测矩阵。
- [加载器清零/逐段复制源码](</home/yoox/android/workspace/UniXNU-pin/drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c#L737-L750>)。

## 外部参考的用途与边界

- [UniXNU故障排查](https://unixnu.com/reference/troubleshooting)也明确顶部绿条在kernel branch之前；与本轮机器码一致，不作为独立真机证明。
- [固定版本调试文档补丁](https://github.com/UniXNU/UniXNU/commit/35558d78c2d30e6fe6465c651da5d8b63a26742e.patch)包含“claim位于本轮清零BSS、旧显存不决定新一轮panic、2048字节缓冲区末字节预留”的说明。只借鉴状态生命周期原则；本地缓冲区实际已物化在__DATA,__data，并非声称节名为__bss。
- [baihem同机型分支](https://github.com/baihem/UniXNU-shennong)和[houji同SM8650项目](https://github.com/lonzzi/UniXNU-houji)已查看；后者页面标明iOS16。它们不证明本项目iPhone iOS27 arm64e基线通过；不迁移旧阶段C结论。
- 获取远程同名脚本曾返回404；未把未知远端实现当作已读代码。候选由本地冻结源码生成并独立编译验证。
