# fi137 无内核异常画面的离线复核

## 当前结论

**阶段 C 未确认。种子长度的镜像契约已修复，但尚无实际 CPU 现场证明内核越过该检查。**

fi137 只执行一次临时 boot，未 flash。后续不追加设备操作、CI、提交、推送或电源策略改动；不恢复任何跳过随机数、栈检查、分配器或 TLBI 的旧补丁。

## 照片和交接边界

- 本次照片 SHA256：`b89a54ee70b31344960bf91691d38e074906b4da6a13284879ee593520d81a83`。可见 UniXNU 菜单背景、顶部绿色条、底部 SecurityLock/LockCapsuleInterface 字样；未出现可辨识的内核 panic/寄存器报告。细小加载器文字不逐字臆录。
- 实际载荷内 DarwinBoot.efi 为 27648 字节，SHA256 `cd9f343a04740f836f0e5461aedce2f2d4aea8b96b78c0a2d1d8de2fb33a4e9b`。
- 对实际 PE 的全部 `.text*` 节反汇编，确认交接函数从 RVA `0xa000` 开始：`msr daifset`，绿色写入在 `0xa01c`，随后 `dc civac`、`ic iallu`、关闭 SCTLR_EL1.M/C/I、`tlbi vmalle1`，最后 `0xa090: br x1`。
- 因此**绿色条位于跳入内核之前**；它不证明跳转已完成。旧菜单像素可以只是没有被后续代码覆盖，也不证明回到了菜单。SecurityLock 字样不作为本次根因，尚缺对应错误返回与控制流证据。
- 核对记录：[真实加载器指令](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/loader-handoff-machine-code.json>)。对照源码：[Entry.S:10–52](</home/yoox/android/workspace/UniXNU-pin/drivers/DarwinBoot/DarwinBootPkg/Driver/Entry.S#L10-L52>)。

## 已核对的静态候选

| 候选 | 实测/检查 | 结论边界 |
|---|---|---|
| ADT 仍为 64 字节 | 最终 boot 镜像 FAT 直接回读，10752 字节 ADT、11 节点、目标种子 256；其他 44 条属性及 6 个文件不变 | 镜像内容已排除该错误；不代替实际内核读取现场 |
| 移动后的摘要描述符未进入修复链 | 根集合链式指针共遍历 190822 个；PORT_CONST 链含 38368 个；SHA256/SHA512 描述符的 OID、初始状态、compress、final 共 8 个目标位置全部覆盖 | 排除这些位置从修复元数据遗漏；不证明硬件上成功走完修复 |
| 描述符指向错误哈希常量/回调 | format-8 解码得到正确 SHA256/SHA512 OID、标准 IV，compress/final 指向对应实际函数符号 | 静态目标一致；不证明运行时 PAC 值和密钥正确 |
| 根本未编入 PAC 签名 | 实际 arm_init 含 PACIBSP 和 10 条内部 PACIA/PACIB/PACDA/PACDB 指令，早期 C 调用链含 BLRAA | 不能把问题归因于签名代码整体缺失，也不能据此关闭 PAC |
| 早期 HMAC 无条件访问 DIT 系统寄存器 | 当前 cchmac/cchmac_init/ccdigest_init 路径没有相关 MRS/MSR；cc_disable_dit 实际为 BTI+RET | 该具体 DIT 指令猜测无二进制依据，不据此打补丁 |

磁盘中的编码链式指针不是运行时普通指针，不能因其非 canonical 就直接判坏或全部解码为未签名地址。XNU 的 arm_init 在早期执行 collection rebase/sign；须同时检查该过程和实际运行后的值。

证据：
- [链式修复覆盖](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/native-chain-membership.json>)
- [描述符目标与标准 IV](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/crypto-descriptor-targets.json>)
- [实际 PAC 签名代码](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/fixup-auth-machine-code.json>)
- [早期 crypto 指令](</home/yoox/android/workspace/UniXNU-shennong/out/diagnostics/fi137-seed-contract/early-crypto-machine-code.json>)
- [XNU 初始化修复源码](</home/yoox/android/workspace/UniXNU-pin/out/feeds/xnu-3199e8bc/osfmk/arm/arm_init.c#L230-L305>)

## 后续离线复核已完成

已核对真实入口与 VBAR/MMU 顺序，并确认低向量自旋、SP1 保存失败直接 WFE、panic 前的 trace 与状态访问、显示校验失败静默停机等盲区；冻结观察器 3144 字节可精确重建。另复现旧显存 magic 抑制新一轮显示的问题，生成了未合入活动代码/镜像的独立候选：3128 字节，14 项主机/编译/不变性检查通过。

完整结果、证据边界及下一次最小实验见[入口与异常可见性报告](<../fi137-exception-path-2026-11-18/RESULTS-AND-NEXT.md>)及[10 项离线证据验收](<../fi137-exception-path-2026-11-18/P0-EXEC.yml>)。fi137 的实际停止 PC 仍未取得，阶段 C 未确认；本轮没有追加手机操作。

## 已完成的原计划验收

14/14 离线验收；30/30 种子测试、21/21 PORT_CONST 回归、20 段 shell、5 个 Python 文件解析。该数字只用于对应的离线断言，不计算为启动阶段进度。
