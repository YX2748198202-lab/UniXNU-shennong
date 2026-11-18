# 启动种子契约修复证据（2026-11-18）

| ID | 类型/验证方式 | 事实或验收约定 |
|---|---|---|
| E1 | FACT ✅可命令 | fi136b 实际 FAT 的 ADT 完整解析为 10560 字节、11 节点；根直属 chosen/random-seed 唯一且为 64 字节。 |
| E2 | FACT ✅可命令 | scripts/make-shennong-adt.py 原第 72 行调用 os.urandom(64)。kernel.yml 第 938–960 行生成并回读比较 ADT，但未验证种子契约。 |
| E3 | FACT ✅可命令 | 实际内核 PE_get_random_seed 在 0xfffffff00b3a1588/15a8 调用 SecureDTLookupEntry/SecureDTGetProperty。early_random 位于 0xfffffff00ad54ea0。 |
| E4 | FACT ✅可命令 | pinned XNU prng_random.c:51–75 对 ARM 要求 4*SHA512_DIGEST_LENGTH=256；实际 arm_vm_init.c:1895 在段发现与 2165 的保护初始化之前调用 early_random。 |
| E5 | EDGE ✅可命令 | 原 patch-adt-randseed.py 依赖全文件 find 和 chosen 字串先后，未结构化验证真实路径，缺少边界/重复/错误树处理；其补长逻辑不是当前 CI 的步骤。 |
| E6 | CONVENTION ✅可命令 | 严格解析器匹配 DarwinBoot 的 16 MiB 上限、深度 64、36 字节属性头、4 字节对齐及完整消费要求；缺失/重复 chosen 或种子、错误边界均失败。 |
| E7 | CONVENTION ✅可命令 | 只使用系统 CSPRNG 刷新完整 256 字节；不打印种子，不补零或重复；每次打包刷新，已有正确值在未要求刷新时保持不变。单次镜像不反复启动。 |
| E8 | CONVENTION ✅可命令 | 变更仅限 ADT 目标属性值/长度及其对齐；其余树语义和字节片段均保留。原件不可覆盖，损坏输入/随机源失败不得改变文件。 |
| E9 | FACT ✅可命令 | fi136b kernel-xpu.macho 为 94584832 字节，SHA256 6817570eda24b599f943b77671dcce8c29ec6c748ce0a46fc696c79ee895c609；本轮内核必须完全相同。 |
| E10 | CONVENTION ✅可命令 | 最终 FAT 除 ADT 外 6 文件完全不变；新 ADT 应为 10752 字节；引导图保留 192 MiB 卷、fd43、原模板和 DTB。 |
| E11 | CONVENTION ✅可命令 | 不提交、不推送、不触发新 CI。只对匹配序列号 9f72e95c 的设备执行本轮一次临时 boot；无 flash。设备未就绪时只保存 ready 状态。 |
| V1 | FACT 👁只能看图 | fi136 照片 SHA256 5ac0ad207e48086a65b2366054c1f71243a3a71ef7d56a3377eca1af899f1291：Expected 256 seed bytes from bootloader, but got 64，@prng_random.c:75。正常检查显示有效，尚未到常驻段保护初始化。 |
| V2 | TARGET 👁只能看图 | 本轮真实越过随机初始化与否、后续 panic 或阶段 C，均待本次实机日志/照片。新图标题仍为 fi136/full checks；以新镜像 SHA 和回执识别。 |

旧基线可能通过短路检查到达更后位置，不能继承为当前完整检查镜像的阶段 C 成功结论。resetWpar 在更早阶段查询成功也不证明稍后的 RWNX→RNX 生命周期已经通过。
