# fi139 常量段契约修复与单次启动证据

本轮把 `ledger` 的常量段归属检查从「只认 `__DATA_CONST`」改成「接受 `__DATA_CONST` 或 `__PORT_CONST`」，用原生机器码派生覆盖全部三处检查点，再用新 256 字节种子重打包并临时启动一次。

## 事实清单

- E1 ✅可命令：fi138 照片（sha256 `fab529ee3868a85b079c0115eab82d20…`）里的 `PC=0xfffffff00b43efac` 对应 `_ledger_template_finalize.cold.2+0xc`，即 `BRK #0xbffc` 断言陷阱；`LR=0xfffffff00ab7f4b8` 为 `_ledger_template_finalize+0x1b8`，`ESR=0x00000000f200bffc`，`FAR=0`。断言消息为 `ledger.c:349 Assertion failed: data_const_start <= (const char *)lt && (const char *)(lt + 1) <= data_const_end`。
- E2 ✅可命令：常驻段改造把三个模板搬进 `__PORT_CONST`：`_task_ledger_template 0xfffffff00c8abd40`、`_thread_ledger_template 0xfffffff00c8ac7f8`、`_coalition_ledger_template 0xfffffff00c8a0e40`。两段真实边界由 Mach-O `segment$end$`（未对齐的末节结束）给出：`__DATA_CONST 0xfffffff007dd0000..0xfffffff007e31958`，`__PORT_CONST 0xfffffff00c8a0000..0xfffffff00c95ab08`。
- E3 ✅可命令：源码里 `lt_require_data_const` 在 `ledger.c` 有且仅有三处非单元测试调用——`ledger_template_finalize`（形参 `lt`）与 `ledger_template_copy` 的 `lt`、`src`。机器码对应三处内联检查：`finalize+0x194 = 0xab7f494`、`copy+0x140 = 0xab7f62c`、`copy+0x164 = 0xab7f650`。只修一处会让下次启动停在 copy。
- E4 ✅可命令：派生内核 `c09c4b0970d364dfe38b838389d47b29eeb83347cfea0f6cec5b037af4cac8c5`，相对已启动的 fi138 内核 `955ae86dc07a3f24b76d22e2cacf0279ab2d7823e3d77920aaee6f7f733e0fbe` 只改 359 字节；检查代码 384 字节放在 `_LowExceptionVectorBase+0xa00` 的全零填充区；清单之外 0 字节改动；`__fips_hmacs` 已用真实算法重算通过。
- E5 ✅可命令：两个被改函数的非分支字节逐字节不变——`finalize` 492 字节、`copy` 496 字节，各自只有入口那 4 字节换成 BL。原「对象未初始化」「模板已初始化」「条目越界」三条断言的失败调用点全部保留，仍走原来的 `BRK`。
- E6 ✅可命令：三处检查各跑 1190 组机器码用例（共 3570），另跑 49 组 copy 目标+源串联、2 组原前置断言；结果分布 252 放行 / 560 模板非法 / 378 条目非法，三处完全一致。被调用者保留寄存器与 `SP` 全程无漂移。
- E7 ✅可命令：镜像 `33b9ba83e1b6f2d640226e4d76ba329c9da0d385bb204a4a8025faf80b649727`，203722752 字节；载荷 `1e7b25a8b0248aeb635249f2df1c665aa4a493b070cfcf183b66095305474eb8`。FAT 只换 `kernel.macho` 与 `kernel.macho.adt` 两个文件，其余 5 个（`DarwinBoot.efi`、`crypto-hmac.json`、`trustcache`、`vroot`、`unixnu.toml`）逐字节不变；BootShim/UEFI/DTB 区域不变。
- E8 ✅可命令：种子为新的 256 字节，ADT 10752 字节，与上一轮不相等；除 seed 外的属性原始记录与节点头全部不变。
- E9 ✅可命令：上海时间 2026-11-18 17:36:53 对 `9f72e95c` 执行本轮唯一一次临时 boot，返回码 0，发送 5.190s、Booting 0.083s、fastboot 总计 6.390s、进程墙钟 6.447575s，无 flash。attempt/result 回执均为独占创建，不会重跑。
- E10 ✅可命令：`build5-reproduce` 独立重编译与 `build4-complete` 字节完全一致，派生链可复现。源码回归 15/15，机器码验收 54/54，最终镜像回读 24/24。

## 只能看图

- V1 👁只能看图：fi139 的本次屏幕内容本轮未取得。菜单背景与绿条在跳入内核之前绘制，不构成内核进度证据；`SecurityLock` 字样同样没有建立故障因果链。

## 不知道

- U1 🤷不知道：fi139 是否真的越过 `ledger_template_finalize`——需要本次画面上的 `PC`/`ESR`/断言正文。
- U2 🤷不知道：PAC 的密码学校验。仿真按指令语义放行 `pacibsp`/`retab` 并保留原栈帧，签名与验签的硬件行为未建模。
- U3 🤷不知道：`kernel.macho.crypto-hmac.json` 未随内核更新。它在 FAT 里与上一轮逐字节相同，而内核已变；fi139 能进入内核说明当前加载路径不依赖它，但它与实际内核不再自洽，本轮不改动。

## 边界

- 这是原生二进制派生，不是完整 XNU 重链接。本地缺少 `xnu-host-cc`/`migcom`/`iig`/`lzfse` 与编译缓存，完整重建无法在本机进行；manifest 已如实记录该范围。
- 未执行 flash、CI、提交或推送（提交与推送在本轮之后单独进行）；未改动电源策略。
- 失败目录 `build1`、未上机的 `build2`（单处修复，264 字节）全部保留，不删除。
