# fi135 等价诊断：证据与边界

日期：2026-11-17，Asia/Shanghai。执行依据：已批准的 fi133 黑屏诊断计划。

| ID | 类型/可验证性 | 事实或边界 | 证据 |
|---|---|---|---|
| E1 | FACT ✅可命令 | 两轮 CI 原始内核均为 94,552,064 字节；整个 __TEXT_EXEC 完全一致。 | 原始文件逐段比较；生成的 manifest.json 保存路径、哈希与差异数。 |
| E2 | FACT ✅可命令 | fi115 相对旧原始内核有 4045 个修改字节；这些位置在新原始内核上的前像冲突为 0。 | 迁移工具再次计算并输出到 manifest.json。 |
| E3 | FACT ✅可命令 | 钩子修改 refer/xnu 的机制会遗漏隐藏目录 .cache/xnu-work；固定版本构建脚本先 clone、后运行 prepare-xnu-source.py。 | .github/workflows/kernel.yml:82–100；UniXNU-pin/scripts/build-xnu-4k-baseline.sh:25–58（git blob 与 CI 固定提交匹配）。Python glob 本机默认 include_hidden=False。 |
| E4 | FACT 👁只能看图 | fi134 照片复现 PC=0xfffffff00ad73a18、FAR=0xfffffff00c8c41f0、ESR=0x9600004f。 | 用户提供的 fi134 照片；旧照片哈希未在本轮核验。 |
| E5 | FACT 👁只能看图 | fi133 照片保留菜单背景，上方小字含退出 boot services / handoff；用户观察几秒后黑屏，未计时。 | 用户照片 sha256 a4e0c95f124cec5393269d0583135681cf5b109490c8024b011d157a9c39aa35；不据此断言内核未执行或 SoC 挂死。 |
| E6 | CONVENTION ✅可命令 | 新产物使用独立工作区目录，文件以独占方式创建；全部输入哈希在验收时重验。 | 工具脚本与 manifest.json / acceptance.json。 |
| E7 | CONVENTION ✅可命令 | 完整迁移已测试 fi115 本地补丁集，并非声称其全部是显示探针；不新增权限、PAC、异常路径行为变更。 | changed_ranges 记录每个局部前像/后像；输出与 fi115 代码段逐字节一致。 |
| E8 | EDGE ✅可命令 | FAT 中实际内核与生成内核必须一致，boot image 内的 payload 必须与已校验 payload 一致。 | 回读哈希、容器布局验收。 |
| E9 | EDGE ✅可命令 | 上机只对序列号 9f72e95c 执行一次 fastboot boot；连接未满足时保持待测，不写分区。 | boot-attempt.json 与 USB 状态记录；实际启动结果不预填。 |
| E10 | AMBIGUITY 👁只能看图 | fi135 实机复现旧 PC/FAR/ESR。 | 用户照片 sha256 06c1cfe2bca750794520543fa709b792d780e790ed0e22e607fd26f5dc7b52a0；本地 7/7 验收仍不代表修复通过。 |

已撤回：fi132 已消除旧写权限 panic；fi133 只比 fi115 多两行内核变化；触屏无响应或 USB 枚举为空足以证明 SoC 挂死。

本轮生成结果保存在工作区 out/diagnostics/fi135-equivalent/，不覆盖原有 CI 产物、镜像或日志。
