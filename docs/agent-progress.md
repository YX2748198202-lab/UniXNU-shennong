# 项目规定（用户第一轮原文，2026-11-11 重述，最高优先级）

> 本文件保存用户在本会话第一轮给出的《UniXNU-shennong 项目正式接管与持续开发指令》原文。
> 每轮开工前必须先对照本文件。任何与本文件冲突的临时判断一律作废。

## 0. 身份与目标
我是本项目唯一主力开发 Agent，负责接管、审计、开发、构建、调试和推进 Xiaomi 14 Pro
（shennong，23116PN5BC，SM8650，**12GB RAM**）的 UniXNU 移植工程。
目标不是反复分析或做计划，而是持续产出真实、可复现、可验证的工程成果，
尽可能推进到设备能启动 XNU、运行 iOS 用户空间。

## 1. 仓库关系与工作目录
- 设备主仓库（主落点，非只读）：YX2748198202-lab/UniXNU-shennong
- 官方上游（供框架/规范/通用修复）：UniXNU/UniXNU
- 迁移规范：https://unixnu.com/porting/migration
- 设备主仓库：/home/yoox/android/workspace/UniXNU-shennong
- 官方上游：/home/yoox/android/workspace/UniXNU
- 产物：/home/yoox/android/artifacts/UniXNU-shennong
- 禁止未分析就用上游覆盖设备仓库；禁止丢弃用户已有成果。

## 2-3. 设备与接管
已知历史线索 A–G 仅用于定位，不得当作当前 HEAD 已验证状态。
A 构建链/加载器有阶段性成果；B UEFI 启动菜单有阶段性成果；
C XNU 早期启动阻塞，历史指向 _arm_init 到 _machine_startup 之间；
D CPU/异常/中断/内存管理需按当前供体重新核验；E SM8650 UFS 与根卷有实机成果但旧供体不证明新供体；
F launchd/SpringBoard 未完成；G 显示/触控/GPU/网络/音频待适配。
已完成项不得无理由从零重做。

## 4-5. 审计与供体管理
必须建立基于证据的状态基线，禁止把文档"已完成"当实机成功。
供体必须记录型号/版本/Build/架构/XNU 版本/来源；符号、地址、偏移、补丁、二进制、哈希必须可追溯。
**严禁混用 iPadOS 17 与 iOS 27 的符号、地址、偏移、补丁或产物。**
IPSW 按需获取，先查缓存。

## 6. 阻塞点与开发
每次只针对明确问题提出**可验证假设**，选择**最小必要修改**，改完立即构建/测试/实机验证。
失败时分析具体错误和日志再修正，不得反复输出相同的推测。

## 7. 强制开发循环与验收
检查现状 → 提出可验证假设 → 选择最小修改 → 实施 → 构建/测试 → 分析结果 → 记录证据 → 下一项。
"已读代码/已做计划/已分析原因"不算完成。无法实机验证必须标"尚未实机验证"，不得伪称成功。
每次修改检查 diff，不得有无关改动或破坏已有成果。

## 8. Token/日志/资源规范
用 rg/grep/find/git diff/log 定向查询，不整份读源码或日志；
日志只提取关键片段；不把大量代码/二进制/重复构建信息输出给用户；
已验证步骤记录复用；不为显得有进展而重复分析或堆文档。

## 9. 进度记录
维护 docs/agent-progress.md：更新时间、两仓库 HEAD/分支/工作区状态、当前供体完整版本、
当前阶段、已验证成果及证据、本轮改动文件及目的、构建/测试/实机命令与结果、
未解决阻塞与具体错误、下一项最优先任务。每轮结束更新。

## 10. Git 与代码安全
本地专用分支；改前查 git status，必要时建检查点；重要成果可本地 commit；
**未经明确授权不得 push、不得覆盖远程分支、不得强推、不得重写远程历史**；
不得随意删除用户代码/补丁/配置/提交/产物；同步上游要可审查可回滚；
禁止大范围覆盖或无差别替换关键启动代码。

## 11. 设备操作授权边界
userdata 已被旧 iPadOS 17.7.11 根卷占用且无保留价值，允许按新供体需要修改/覆盖/清理/格式化/重建。
执行前必须核对设备连接、分区映射、块设备标识、目标分区，严禁凭猜测选设备节点。
授权仅限旧 userdata 根卷，**不得扩大为允许擦除整机**。
Bootloader、UEFI 持久分区、GPT、modem、persist、其他固件分区均不在授权内，需单独授权。
不得为方便做全盘擦除。所有设备写入要有目标、理由、结果、恢复方案。

## 12. 连续执行与暂停
默认继续执行，不频繁询问是否继续。仅在：缺关键资料/需账号密钥权限/超授权不可逆操作/
重大数据风险/关键依赖不可用时暂停并报告。
一般代码修改、构建失败、测试失败、常规调试自行解决。

## 13. 每轮结束必须说明
本轮真正完成了什么、验证证据是什么、还有什么阻塞、接下来正在执行什么。
不得只给计划就停止。

---

# Agent 进度记录（机器可读的接续入口）

最后更新：2026-11-11 01:05 CST
本轮执行者：DSH Agent（接管轮）

> **阶段 C 已达成（2026-11-11 00:45，fd34）**
> arm64e 内核在 EL1 真正执行并打印我们补丁自己的诊断：`args pa 0xBC1D0000`、
> `video base 0xFC400000 1440x3200 32bpp`、`entry words 1400001E`（ARM64 `b`）、
> `CurrentEL 1`、`SCTLR_EL1 0x30D0198D`、`PARange 2`、`SOFTWARE_LOCK`、
> `NATIVE_UFS adopt: list replaced` + `@NativeUFs.cpp:491` + `pages=0xbb1e free=0xb7a2`。
> 证据照片只留两张：`artifacts/UniXNU-shennong/device-runs/2026-11-11/milestones/`。
> 逐条判读见 `docs/bringup.md` 的「阶段 C 达成」一节。
> **iOS 27 阶段 C 复验通过（fd35，2026-11-11 01:03）**：去掉 UFS 探针与 source-storage 后，
> 屏显 `Failed to mount root device @IOKitBSDInit.cpp:984`，与 11-04 iPadOS 验收同一行。
> 由此确认 fd34 的 `@NativeUFs.cpp:491` 停死**只属于 UFS adopt 路径**。
> 里程碑照片 `device-runs/2026-11-11/milestones/stageC-ios27-vfs_mountroot.jpg`。
> 下一段目标：fd36 用 `native-ufs-probe=12 native-ufs-diagnostics=1` 复现 UFS 读路径 → 根卷 → `bsd_init` → `launchd`。

## 1. 仓库与工作区状态（实测）

| 项 | 值 |
|---|---|
| 设备仓库 | `https://github.com/YX2748198202-lab/UniXNU-shennong` |
| 设备仓库本地路径 | `/home/yoox/android/workspace/UniXNU-shennong` |
| 设备仓库 HEAD | `363cc770793ca998a70801b70798e17aadb64261`（`main`，2026-11-08 23:28:18 +0800，`fix(scripts): never displace adrp/b/bl into a cave`）|
| 本地工作分支 | `bringup/premmu-locate`（从 `main` 切出，未提交任何改动）|
| 工作区状态 | 干净（`git status --porcelain` 为空），跟踪文件 127 个 |
| 上游仓库 | `https://github.com/UniXNU/UniXNU` → `/home/yoox/android/workspace/UniXNU`（main，`d830d23`），pin 工作树 `/home/yoox/android/workspace/UniXNU-pin`（detached `c740efb5b23e94453bb179f7801eb592baafacf6`）|
| CI 使用的上游 pin | `c740efb5b23e94453bb179f7801eb592baafacf6`（`.github/workflows/kernel.yml` 第 15–23 行；该 commit 仍可取，raw 探测 200）|
| 上游 main 实测漂移 | 本会话 `ls-remote` 首测为 `1918c221`，`git clone` 时为 `d830d23b`（`build(drivers): ArmDTPlatform starts the calendar at the kernel's build date`）→ 上游在本轮期间仍有新提交 |
| pin..main 差异规模 | 210 个文件、+11825/−4641；`drivers/` 14 个组件目录**没有改名或删除**，但 11 个组件子模块指针发生变化（`ArmCpu` 93a5030c→16040839 等）|
| 产物目录 | `/home/yoox/android/artifacts/UniXNU-shennong` |

## 2. 当前供体（版本基准）

| 项 | 值 | 来源 |
|---|---|---|
| OS profile | `ios-27.0.1-24A446-iphone16pro`（设备仓库 `profiles/os/`，CI 会拷进 `unixnu/profiles/os`）| `board.toml`、`profiles/os/ios-27.0.1-24A446-iphone16pro/profile.toml` |
| 供体 IPSW | `iPhone17,1_27.0.1_24A446_Restore.ipsw`（product iPhone17,1，build 24A446，device_class d93ap，chip_id 33088，board_id 12）| 同上 `[ipsw]` |
| 架构 / XNU | `arm64e` / `xnu-12377.121.6`，`xnu_revision ac9718fb1af618d5ce8678d0dc6e8a58f252216f`，`driverkit_tag xnu-12377.121.6`，`trustcache_tag xnu-8796.101.5` | 同上 |
| kernelcache sha256 | `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95` | `profile.toml` + `board.toml [kernel.prelink]` 一致 |
| prelink slide | `-0x1000000` | `board.toml` |
| 旧供体边界 | iPadOS 17.7.11（21H461，arm64）只用于历史 A–E 验收；`profiles/os/ios-27.0.1-24A446-iphone17,1` 是并列的第二 iPhone profile | `README.md`、`profiles/os/` 目录实测 |
| 不一致点（待修） | `porting.toml` 的 `os_profile = "ipados-17.7.11-21H461"` 与 `board.toml` 的 iPhone 27 profile 不同步；`board.toml` 里 `[payload.adt] root_match_volume_uuid` 注释仍写 iPadOS 17.7.11 | 本轮读取 |

## 3. 设备状态（实测）

| 项 | 值 |
|---|---|
| 连接 | `adb devices` → `9f72e95c recovery`；`fastboot devices` 当前为空 |
| 身份 | `ro.product.device=shennong`，`ro.product.model=Xiaomi 14 Pro`，Android 16 base，`ro.boot.slot_suffix=_a`，`ro.boot.hardware=qcom` |
| 环境 | TWRP `3.7.1_16-Xiaomi_14_Pro-A15`，`twrp_shennong-eng`，adb shell 为 `uid=0(root) context=u:r:su:s0` |
| userdata | TWRP 未挂载（`mount` 只有 `/cache`(`sda28`)、`/metadata`(`sda20`)），`/data` 只剩 `recovery/`；与“userdata 已是 iOS 根卷、TWRP 无法识别其文件系统”一致 |
| 分区节点 | `boot_a=sde12`、`init_boot_a=sde27`、`modem_a=sde6`、`persist=sdf7`、`metadata=sda20` 等可见（本轮只读，未写任何分区）|

## 4. 阶段状态（文档口径，未经本轮实机复验）

| 阶段 | 内容 | 状态（文档） | 本轮核实 |
|---|---|---|---|
| A | 构建链与加载器 | ✅ 2026-11-08 复验（`drivers 1 loaded / 0 failed` + handoff）| 未复验；本地无该镜像 |
| B | UEFI 实机菜单 | ✅ v6 | 未复验；UEFI 固件源码与 FD 均不在本机 |
| C | XNU 早期启动 | 🟡 iOS 27 卡在**开 MMU 之前**（`0xAD830D4…0xAD83418` 窗口；band2 从未变白）| 见第 6 节，已有二进制级证据支持该窗口存在静默自旋 |
| D | 中断 / CPU / 内存 | 🟡 仅 iPadOS 供体验收 | 未复验 |
| E | UFS + 根卷 | 🟡 存储栈通，iOS 27 根卷待重做 | 未复验 |
| F/G | launchd / SpringBoard / 硬件 | ⬜ 未开始 | — |

## 5. 本地可用的产物（本轮清点）

| 产物 | 路径 | 说明 |
|---|---|---|
| 旧供体 CI 产物包 | `/mnt/c/Users/yoox/AppData/Local/Temp/unixnu-shennong/k1..k8.zip`、`art-test.zip`、`shennong-kernel-*.zip` | 均为 **ipados-17.7.11-21H461** profile 的 2026-11-04…11-06 产物 |
| 已解出的旧内核 | `artifacts/UniXNU-shennong/legacy-ipados17/out/shennong/ipados-17.7.11-21H461/shennong/kernel/kernel.macho` | 52,068,352 B，sha256 `cceb91703b80124b3426811dcdccad1156a8170b4db989da5aa2770f64a09deb` |
| 已解出的旧 payload | 同目录 `payload/payload.img` | 201,326,592 B，sha256 `a21de6e49c03ef9b25143223c94556fb95a7be08e8cdd1b394e4903c03b917ec`，`payload.json` 内 `payload_kernel_sha256 0fb4ddd2…` |
| 旧根卷镜像副本 | `/mnt/d/unixnu/userdata-root.img` | 9,456,697,344 B（iPadOS 17 根卷，对新供体无保留价值） |
| **缺失** | `SILICIUM_UEFI.fd`、`Mu-shennong-smp.img` 模板、`Mu-*.img`、两个 IPSW | 全盘（C:/D: 与 WSL）搜索未命中；Mu-Silicium `main` 的 `Platforms/Xiaomi` 36 个 pkg 中也没有 `shennongPkg` |

## 6. 本轮已获得的二进制级证据（离线，可复现）

对旧供体内核 `kernel.macho`（XNU 12377，iPadOS profile）全量反汇编（2,165,139 行），定位到与 iOS 27 payload 同构的 pre-MMU 段 `_start_first_cpu` / `common_start`：

| 站点 | 旧供体地址 | 指令 | 含义 |
|---|---|---|---|
| 建表循环越界自旋 | `0xfffffff0073f6284` | `b 0xfffffff0073f6284`（即 `b .`）| `cmp x2, x25+0x10000; b.hs` 命中后**永久自旋，无输出无复位** |
| MAIR 安装 | `0xfffffff0073f6300` | `msr MAIR_EL1, x0`（0xff/0xbb0000/0x4400/… 组装值）| |
| VBAR 安装 | `0xfffffff0073f633c` | `msr VBAR_EL1, x0`（`ExceptionVectorsBase + x22 - x23`）| 向量表是 **KVA**，MMU 未开时不可达 |
| SCTLR 写入 | `0xfffffff0073f6350` | `msr SCTLR_EL1, x0`，x0 由 `movk` 拼成 `0x3454_593D` | 旧供体期望值 |
| **SCTLR 回读自检死循环** | `0xfffffff0073f636c` | `cmp x0, x1; b.ne 0xfffffff0073f636c`（`b.ne .`）| 回读不一致即静默永久自旋（与 `docs/bringup.md` 记录一致） |
| 旧供体无 PAC 写入 | — | 全量 grep `apiakey/apibkey/apdakey/apdbkey/apgakey` **0 命中** | arm64 profile 不写 PAC；iOS 27 是 **arm64e** profile，`start.s` 会走 PAC 分支 → 结构不同，必须按当前 payload 内核核对 |

结论：`docs/bringup.md` 里“开 MMU 前存在静默自旋点”的描述在真实二进制中得到确认；但**具体地址会随 profile/patch 变化**（旧供体 SCTLR 常量 `0x3454593D`，iOS 27 payload 记录为 `0xFC54793D`；`_arm_init` 旧供体 `0xfffffff0079c1f70`，iOS 27 payload 为 `0xfffffff00b4768d0`）。因此文档里的硬编码地址不能跨构建复用，必须用脚本按模式重新定位。

## 7. 未解决阻塞

1. **实机验证能力缺失（最高优先）**：任何 `fastboot boot` 都需要 boot image = `header + gzip(BootShim + SILICIUM_UEFI.fd) + payload`；FD 与 boot 模板都已在 2026-11-10 16:05 的清理中丢失（`logs/unixnu-cleanup-20261110.log` 记录 `/tmp/tmp* x8 (728M)`），Mu-Silicium 上游没有 `shennongPkg`。
2. 供体 IPSW（iPhone17,1 27.0.1）不在本地；需要时须重新按 `board.toml [ipsw].url` 取（约 8 GB）。
3. 当前 payload/kernel 只能由 GitHub Actions（`kernel.yml`，macos-26）产出；本机无 Xcode，无法本地重编 XNU。

## 8. 已执行的命令与结果（本轮）

```
git clone https://github.com/YX2748198202-lab/UniXNU-shennong.git .        # OK, main 363cc77
git checkout -b bringup/premmu-locate                                     # OK
git clone --filter=blob:none --no-checkout https://github.com/UniXNU/UniXNU.git ../UniXNU
git -C ../UniXNU fetch origin c740efb5b23e94453bb179f7801eb592baafacf6    # OK
git -C ../UniXNU worktree add --detach ../UniXNU-pin c740efb5…            # OK
python3 (zipfile) 解 k8.zip → artifacts/legacy-ipados17/…                 # OK, sha256 见第 5 节
llvm-objdump -d kernel.macho > /tmp/k8.dis                                # 2,165,139 行
grep -nE 'msr\s+(SCTLR|MAIR)_EL1' /tmp/k8.dis                             # 见第 6 节
adb shell getprop / mount / ls -l /dev/block/bootdevice/by-name           # 见第 3 节
```

## 9. 下一项最优先任务

按 `docs/handoff/PRE-MMU-STOPS.md` 的判据表，用**模式匹配**在任意 payload 内核里重新定位 pre-MMU 站点（不依赖硬编码地址），并把 `sheng-log` 持久日志通道接上，使下一轮实机启动能拿到内核向量而不是只靠照片。

---

# 第 2 轮（2026-11-10 下午）：工具链修复、日志通道、band 注入的证据

## 10. 本轮结论（每条都有可复现证据）

1. **诊断工具链原来是断的，已修好。** 仓库里 14 个 `scripts/patch-*.py` 通过
   `importlib` 加载 `patch-xnu-entry-probe.py`（`load_segments`/`file_offset`/`branch`/
   `assemble`/`kernel_symbols`/`function_range`/`find_call`），而该文件**从未进过仓库**——
   所有 Mu-* 镜像过去都依赖 `/tmp/probe/` 里的临时副本，`/tmp` 被清理后就再也重建不出来。
   该文件的正式版本在上游 pin 的 `scripts/patch-xnu-entry-probe.py`（430 行，含 band 注入模板），
   本轮已**原样 vendor** 进本仓库并加了来源说明，另加 `scripts/test-entry-probe.py` 契约测试。
2. **band 是 payload 阶段注入的 cave，不是内核源码里的代码。** 把旧 `payload.img` 内嵌的内核
   （偏移 `0xd7c00`，`filetype 0x2`）与构建产物 `kernel/kernel.macho` 对比：
   - `__start`（`0xfffffff0073f4488`）：构建产物是 `b _start_first_cpu`；payload 版本跳到
     `0xfffffff0073f4500`，按 `boot_args+0x28/+0x38/+0x48` 算长度填 **蓝 `0xff0000ff`**，
     再 `b _start_first_cpu`；
   - `common_start` 的 `msr SCTLR_EL1, x0`（`0xfffffff0073f6350`）：payload 版本是
     `b 0xfffffff0073f4560`，填 **品红 `0xffff00ff`** 后才执行 `msr SCTLR_EL1, x0`。
   与上游工具源码里的 `PAINT` 模板逐条一致。**stage 2 是品红不是白色**，早期"band 2 白"的
   判读作废（见 `docs/handoff/PRE-MMU-STOPS.md` 第 3.5 节）。
3. **新的可检验推论**：band 填充长度 = `((boot_args[0x38] × boot_args[0x48]) >> 4) & ~7`。
   这个乘积为 0 → 一条都不填（屏幕无变化，与"没执行"无法区分）；这个乘积极大 → 填充跑很久
   （看起来像卡死，其实在跑）。**因此下次上机必须等 ≥5 分钟再判定死亡。**
4. **`sheng-log` 通道接上了**：`board.toml` 的 `kernel_args` 增加 `sheng-log=1`
   （只有 `package/SourceStorage.cpp:131` 与 `package/BootLog.c:1926` 解析它；这个树里
   **没有**任何地方解析 `sheng-log-reserve`，文档旧说法已修正）；配
   `scripts/read-sheng-log.py`（`--image`/`--image --scan`/`--device`，解析 `SHLOG001`
   头、msg 缓冲、文本 slot 环）与 `scripts/test-read-sheng-log.py` 合成窗自测。
   对真机 userdata 尾部 32 MiB 实读结果为 "no SHLOG001 header"——符合预期（payload 还没带
   这个参数、也还没走到存储栈）。
5. **payload 改参链路离线验证通过**：复制旧 `payload.img` → `scripts/patch-payload-args.py
   --add sheng-log=1 --anchor native-ufs-probe=3` → `mtype` 回读确认参数已落盘。
6. **`board.toml` 自带的板级补丁是坏的，不能接线**：`patches/xnu/series` 只有
   `zzzz-diag-marks.patch`，而 `patch_series` 没有 `device:` 层，所以它现在根本没被应用；
   本轮离线验证它对 `xnu-12377.121.6` 的 `startup.c` **应用失败**（原始文件失败，先打上游
   `zzz-boot-progress.patch` 后仍在 `startup.c:657` 失败）。已在 series 文件里写明"不要接线"
   与证据位置。详见 `docs/handoff/UPSTREAM-DELTA.md` 第 3 节。
7. **上游 pin 与 main 的差异重新核实**：`210 files changed, +11825/−4641`；无 submodule
   （旧笔记"11 个子模块指针变化"作废）；pin→main 新增 5 个 `patches/xnu-12377` 补丁，其中
   `native-pac-keys.patch`（pin 已有）解释了 payload 里 `cntpct` 派生 + AP*Key 写入的来源，
   `native-pac-arm64-user-jop.patch`（main 独有）属过 MMU 之后的工作。结论：**暂不升 pin**。

## 11. 本轮新增/修改的文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `scripts/patch-xnu-entry-probe.py` | 新增（vendor） | 上游 pin `c740efb5` 原样 + 来源说明；补上仓库缺失的依赖 |
| `scripts/test-entry-probe.py` | 新增 | 契约测试：段解析、符号表、`find_call`、`branch` 编解码、`assemble` 字节级校验 |
| `scripts/locate-pre-mmu-sites.py` | 新增 | 按指令模式定位 pre-MMU 站点、重建 SCTLR 常量、识别 band 注入后的重定向站点；站点缺失返回 1 |
| `scripts/read-sheng-log.py` | 新增 | 读 `SHLOG001` 窗口（镜像/设备两条路）|
| `scripts/test-read-sheng-log.py` | 新增 | 合成窗口自测（含"未写入"/"偏移错误必须报错"两个负例）|
| `scripts/patch-*.py`（8 个） | 修改 | `--probe-tool` 默认值由 `/tmp/probe/…` 改为仓库内同目录文件 |
| `board.toml` | 修改 | `kernel_args` 增加 `sheng-log=1` + 注释说明解析点与读取脚本 |
| `porting.toml` | 修改 | `os_profile` 由 `ipados-17.7.11-21H461` 改为 `ios-27.0.1-24A446-iphone16pro`；summary 更正为当前真实状态 |
| `patches/xnu/series` | 修改 | 标注未接线 + 补丁应用失败的证据 |
| `docs/handoff/PRE-MMU-STOPS.md` | 新增 | pre-MMU 站点表、三个静默自旋、band 注入证据、判据矩阵、重建命令、未验证项 |
| `docs/handoff/UPSTREAM-DELTA.md` | 新增 | pin↔main 差异、PAC 补丁、规范缺口 |

## 12. 本轮验证命令与结果

```
python3 scripts/test-entry-probe.py <kernel.macho>          # all checks passed
python3 scripts/test-read-sheng-log.py                      # all checks passed
python3 scripts/locate-pre-mmu-sites.py <kernel.macho>      # 11 个站点全找到，SCTLR 常量 0x3454593d
python3 scripts/locate-pre-mmu-sites.py /tmp/payload-kernel.macho
        # 真实开关被正确识别为 0xfffffff0073f459c (injected cave)
python3 scripts/read-sheng-log.py --device                  # "no SHLOG001 header"（预期）
python3 scripts/patch-payload-args.py --payload payload.img --add sheng-log=1 --anchor native-ufs-probe=3
        # mtype 回读确认
git apply (zzzz-diag-marks.patch on xnu-12377 startup.c)    # 失败 → 记录，不接线
```

## 12.5 仍然缺的工具源码（本轮查证结果）

`scripts/patch-fault-dump.py` 除了 probe 工具外还需要 `--src`（默认 `/tmp/probe/fault/`）目录里的
`cave.S` 与配套 C 源；上游 pin 与 main 都**没有**这份模板（`git ls-tree -r c740efb5 | grep cave`
为空），本仓库也没有。因此 Mu-fault 系列镜像暂时无法重建；这条不影响 band/方格/进度槽三套探针
（它们的 cave 由脚本内嵌 ASM 生成，不依赖外部模板）。

## 13. 下一步（按优先级）

1. **重建 boot image**（唯一的实机入口）：需要 `SILICIUM_UEFI.fd`；选项 A 从 Mu-Silicium
   `Platforms/OnePlus/giuliaPkg`（SM8650）+ `LanaiPkg` 在 WSL 上交叉编译，选项 B 让用户找回
   旧 FD/`Mu-*.img`。没有 FD 之前，第 2–4 项都只能离线推进。
2. 一旦拿到 FD：用 `firmware/make-boot-image.py` 组装 `fastboot boot` 镜像，先跑**band 镜像**
   （等 ≥5 分钟）判定是否只是填充慢，再跑 39 方格镜像二分。
3. 拿到 iOS 27 payload 内核后，先跑 `locate-pre-mmu-sites.py` 出站点表，再按
   `patch-pre-mmu-squares.py`/`patch-mmu-guard.py` 生成镜像（cave 断言会自动检查是否越界）。
4. 修复 `zzzz-diag-marks.patch`（按当前树重做或并入 `zzz-boot-progress` 语义），然后再考虑把
   `device:patches/xnu/series` 接进 `patch_series`。

---

# 第 3 轮（2026-11-10 17:30–17:50）：自己造出 SILICIUM_UEFI.fd

## 14. 结论

**固件不再是外部依赖**：本机（WSL x86_64）已能从源码构出 shennong 的 `SILICIUM_UEFI.fd`，
3,145,728 字节（0x300000），`sha256 362aefb7bbe9ab30d35fe08cfe4b66149bc2d0fdf90f06c3c9dee8de000c5ae3`，
内含 112 个 FFS 模块（含 `UniXNU`、`UniXNUDxe`、`UniXNURamDiskDxe`、`DarwinBoot`、`AdvancedLogDxe`、
`PmicDxe`、`UFSDxe`、`SimpleFbDxe`、`BdsDxe`）。
boot image 也已组装并通过字节级自检：`artifacts/UniXNU-shennong/boot/Mu-shennong-fd1.img`
（1,282,048 字节，`sha256 df5a7598…`，shim 192 B + FD 3 MB → gzip 1,277,940 B）。

## 15. 每块输入从哪来（全部可复查）

| 缺的东西 | 本轮来源 | 证据 |
|---|---|---|
| Mu 基树 | `UniXNU/uefi-sheng@sheng`（CI 用的同款），1.5 GB，子模块含 `Mu_Basecore` / `Common/Mu` / `Binaries` / `Silicium-ACPI` | `git clone --branch sheng` 完成 |
| BaseTools | 本地编译 `Mu_Basecore/BaseTools/Source/C`（`GenFw/GenFfs/GenFv/GenSec/EfiRom/VfrCompile`），补 `BrotliCompress`（git 子模块）与 `LzmaCompress`（FVMAIN 压缩必需） | `bin/` 九个工具齐全 |
| 平台骨架 | `Platforms/OnePlus/giuliaPkg`（同 SoC：`LanaiPkg` = SM8650，完全源码构建，不依赖私有 Binaries） | `giulia.dsc` `!include LanaiPkg/LanaiPkg.dsc.inc` |
| 内存映射 | **本机 xbl_config 实测**：`xbl_config_a` 里 37 条 DDR/IO 区域（base/size 为大端 u64），脚本解析成 `firmware/shennong-memory-map.toml` | `sha256 ebbc2e9cd3f98603…`，与 houji 同区域名逐条对齐 |
| 描述符策略 | 同 SoC 的小米 houji 移植生成的 `MemoryMapLib.c`（同区域名的 HobOption/ResourceType/ArmAttribute） | 8 个 carveout 数值与 houji 完全一致 |
| SMBIOS/面板 | 机身 23116PN5BC / Xiaomi 14 Pro；面板 1440×3200 | `shennong.dts` panel 节点 |
| UniXNU 模块 | 框架 `package/UniXNUPkg`（menu/Dxe/RamDisk/AdvancedLog/UniXNULib）+ `UniXNU/DarwinBoot` 的 `DarwinBootPkg` | 注入 DSC `[Components]`/`[LibraryClasses]` 与 FDF `[FV.FvMain]` |
| BootShim | 基树 `BootShim/BootShim.S`，只做"把 FD_SIZE 字节从 `_Payload` 拷到 `0xA7100000` 再跳"，不解析 Android 头 | `BootShim.S` 第 21–42 行 |

## 16. 复现步骤（四条命令）

```sh
cd /home/yoox/android/workspace/UniXNU-shennong
python3 scripts/extract-xbl-memory-map.py <xbl_config_a.bin> --toml --out firmware/shennong-memory-map.toml
python3 scripts/make-shennong-uefi-pkg.py --uefi /home/yoox/android/sources/uefi-sheng --vendor-binaries giulia --force
bash firmware/build-shennong-uefi.sh
python3 firmware/make-boot-image.py --uefi /home/yoox/android/sources/uefi-sheng \
  --fd /home/yoox/android/artifacts/UniXNU-shennong/firmware/SILICIUM_UEFI-shennong-DEBUG.fd \
  --out /home/yoox/android/artifacts/UniXNU-shennong/boot/Mu-shennong-fd1.img --verify
```

`build-shennong-uefi.sh` 绕开 `edk2-pytool` 的 ext-dep 阶段（它要 GitHub release 上的
`Mu-Basetools`/`mu_nasm`/`onecrypto-bin`，本机取不到），改为直连 `build.py`。
关键环境：`CLANG_BIN=/usr/bin/`（带尾斜杠，否则拼成 `/usr/binclang`）、
`PATH` 里必须有名为 `python` 的软链（BaseTools 包装脚本写死了 `python`）、
`PACKAGES_PATH` 必须含 `<tree>/Platforms/Xiaomi`、`<tree>`、`Mu_Basecore`、`Silicon/*`、
`Silicium-ACPI*`、框架的 `package/`（提供 `UniXNUPkg`）。

## 17. 踩过的坑（都已修）

1. `bin/DiskIoDxe` 与 `Fat` 被基树 `LanaiPkg`/`SiliciumPkg` 已经收进 FV，重复注入会让
   `GenFv` 报 `the 31th file and 97th file have the same file GUID` → 生成器现在先扫
   `Include/*.inc`、fdf、以及 SoC 包的 `dsc.inc` 去重。
2. FVMAIN 用 LZMA 压进 3 MB 的 `FVMAIN_COMPACT`，缺 `LzmaCompress` 时 `GenSec` 只会报
   `Error opening …SEC1.tmp` → 先编好 BaseTools 全部工具再构建。
3. `--vendor-binaries giulia` 时重命名顺序会把 `Binaries/giulia/` 也改成 `Binaries/shennong/`
   → 生成器最后一步把路径改回所选 vendor 目录。

## 18. 本轮**未**验证的（不要当成已知）

- **没有上机**：`Mu-shennong-fd1.img` 未 `fastboot boot` 过。屏幕、PMIC、UFS 是否正常全部未知。
- **厂商 DXE 是 giulia 的同 SoC 替身**（`Binaries/giulia`），不是本机 `abl`/`xbl` 里的原厂驱动；
  面板初始化序列与 PMIC 配置很可能需要换成本机自带的（`PmicDxe`/`DisplayDxe`/`UFSDxe`）。
- boot image **没有 payload**（`payload.img` 已丢），所以现在只能验到 UEFI 菜单，不能进 XNU。
- `Resources/DTBs/shennong.dtb` 已生成（由 `dts/shennong.dts` 编译，1,238,463 字节），
  但 `append_dtb` 只是照旧配置打开，未验证 ABL 是否吃这份 DTB。

---

# 第 4 轮（2026-11-10 18:40–19:20）：固件取证工具链 + payload 本地重建

## 19. 结论

两件事从"外部依赖"变成"本机能做"：

1. **payload 可以本地组装**：`payload/payload.img`（192 MiB）与 `boot/Mu-shennong-fd2.img`
   （68,390,912 B，含 64 MiB payload）都已产出，并从镜像内部读回复核。
2. **固件可以反过来拆**：新增 FV/FFS/section 扫描器 + EDK II 原版 LZMA 解码器，
   连"我们自己的卷"都能拆开逐个报出模块名和大小——这使"换厂商驱动"变成一条有工具的路。

## 20. 新工具（都有自证）

| 工具 | 自证 |
|---|---|
| `scripts/scan-uefi-fv.py` | 扫自建 `FVMAIN.Fv` 得 **106** 个文件，含 `UniXNU` 103,984 B、`DarwinBoot` 33,846 B、`PmicDxe` 274,540 B、`UFSDxe` 143,414 B、`BdsDxe` 385,166 B |
| `tools/lzma-decode` | 解自建 `FVMAIN_COMPACT` 得 7,708,680 B，与 `Build/shennongPkg/DEBUG_CLANGPDB/FV/FVMAIN.Fv` **逐字节相同**（多 8 字节 section 头） |
| `scripts/test-scan-uefi-fv.py`、`firmware/test-make-payload-image.py` | 全绿 |

顺带修掉两个真 bug：
- 扫描器最初把"名字全 0xFF"当成卷结束，而 **EDK II 每个卷都以 PAD 文件开头**，于是任何真卷都报 0 个文件；
- payload 契约测试第一版断言"整镜像可复现"，实测发现本机 `mformat` 会在最后扇区写 19 字节未初始化内存，改为断言引导扇区+文件内容可复现，并把这条写进文档。

## 21. 本机 abl 里的厂商 DXE：查证结果是**取不出来**

`abl_a.bin` 只有一个 FV，里面只有一个 FFS = 标准 FVMAIN_COMPACT，LZMA guided，头部声明解压后
1,343,688 字节。穷举结果：标准 LZMA 解 27 字节即失败；`xz`/`7za` 同样；225 组 props 最好 419 字节；
8 组字典大小恒为 27 字节；`FINISH_ANY` 无效。

27 字节解出来的内容与我们自己的卷开头**同构**（空的 RAW 段 + `FV_IMAGE` 段头，长度字段正好等于声明大小），
说明封装头部是真的、压缩流在第 28 字节起就不是合法 LZMA——最可能是额外加密或非标准分块变体。
详细证据与下次的数据源见 `docs/handoff/VENDOR-DXE-EXTRACTION.md`。

`Binaries/giulia` 因此继续作为替身，风险面已量化：giulia 80 目录/88 efi/9.6 MB（SM8650，与本机同族），
muyu 70/79/8.9 MB（SM8635，不同族）；差异集中在 `Oplus*` 私有驱动与面板/PMIC 配置表。

## 22. payload 重建（详见 `docs/handoff/PAYLOAD-REBUILD.md`）

`firmware/make-payload-image.py` 按框架 `scripts/unixnu/payload.py` 的**同一卷布局**离线组装：
`EFI/UniXNU/{unixnu.toml,Payloads/{kernel.macho,kernel.macho.adt,DarwinBoot.efi}}`，
`mformat -C -F -T <sectors> -v SHENNONGESP -N 53484e47` + `mcopy -s -Q -m`，时间戳固定 1980-01-01。

产物：
- `payload/payload.img` 201,326,592 B `sha256 30aa035a…`（192 MiB，生产形状）
- `payload/payload-64m.img` 67,108,864 B `sha256 d534e93d…`（64 MiB，为 fastboot 快一些）
- `boot/Mu-shennong-fd2.img` 68,390,912 B `sha256 de9a4cd8…`
- `payload.json`：每个文件的字节数与 sha256、内核参数行

端到端复核：从 `Mu-shennong-fd2.img` 的 `0x139000` 取出 64 MiB，sha256 与 `payload-64m.img` 完全相同；
`mdir` 列出 `SHENNONGESP`、`5348-4E47`、1980-01-01，`Payloads/` 下三个文件大小与源一致。

## 23. 仍然缺（不要当成已知）

| 缺 | 后果 |
|---|---|
| iOS 27 内核 | 现在装的是 iPadOS 17.7.11 内核（52,068,352 B，arm64 Mach-O，ncmds 25），与 `board.toml` 的 `kt_fixed_zones`/`sheng-*`/prelink 不是同一套 |
| `kernel.macho.trustcache` | 无信任缓存，AMFI 会在早期拒绝 |
| `kernel.macho.vroot`（root policies） | `native-source-storage=1` 的根卷策略缺失 |
| 真机 | `Mu-shennong-fd2.img` 一次都没 `fastboot boot` |

## 24. 追加：找回 trust cache + 修掉 panic screen 补丁链（同一轮）

在 `legacy-ipados17/out/.../payload/payload.img`（旧框架产物，201 MB）里找到了三样关键输入，
已用 mtools 抽到 `legacy-ipados17/payload-extracted/`：

- `kernel.macho.trustcache` 61,356 B `sha256 7416ca4f…` —— **与 `board.toml [payload] trust_cache_sha256` 一致**
- `kernel.macho`（已打补丁）52,068,352 B `sha256 0fb4ddd2…` —— 与旧 `payload.json` 的 `payload_kernel_sha256` 一致，
  说明旧 payload 的内核是**打过 panic screen/入口探针**的
- `kernel.macho.adt` 10,468 B（旧参数版本）

**修掉一个仓库级 bug**：`scripts/patch-xnu-entry-probe.py --panic-screen` 要编译
`scripts/xnu-panic-screen.c`，设备仓库里没有这个文件（只有框架 `UniXNU-pin/scripts/` 有）。
把框架那份（302 行）复制进来后补丁成功：

```
stage 1 blue bar, stage 2 magenta bar, no reset probe,
panic screen (0xa2f bytes at 0xfffffff0073f45c0; common funnel at 0xfffffff007279520)
```

结果 `sha256 fa362e24…`，与旧 payload 的 `0fb4ddd2…` 不逐字节相同（旧产物参数不可反推），
但大小不变、只有 2,316 字节不同，集中在 common funnel（文件偏移 `0x275520` 的 4 字节 BL）
与 `0x3F04xx`–`0x3F45xx` 的 cave 区，符合补丁语义。

## 25. fd3 镜像（当前最好的可上机产物）

| 产物 | 大小 | sha256 |
|---|---|---|
| `payload/payload-fd3.img` | 100,663,296（96 MiB） | `f1e47d3289db747a3f3f54b0b77844fd8d081be38f13b931618cd7a17a19034f` |
| `boot/Mu-shennong-fd3.img` | 101,945,344 | `e167a901df59d39ca2bda923d9009d7b48c9897a1ba96bb6a194d0f49360fb86` |

卷内（从镜像 `0x139000` 读回、sha256 逐个比对通过）：`DarwinBoot.efi` 33,792 / `kernel.macho`
（panic screen 版）52,068,352 / `kernel.macho.adt` 10,468（带 trust cache 槽位）/
`kernel.macho.trustcache` 61,356（与 board 允许值一致）/ `unixnu.toml` 549。

## 26. 上机前预检脚本

`scripts/verify-boot-package.py`（+ `scripts/test-verify-boot-package.py`）：17 项检查全部
对 fd3 实测通过，覆盖 FD 大小/卷结构/模块清单（走 lzma-decode 解开的 106 个模块）、
payload 文件与 trust cache 摘要（对 board.toml 允许列表）、ADT 解析与 memory-map 槽位、
菜单参数、boot image 头常量、gzip 流、BootShim 的 ARM64 头、`_Payload` 指向的 FV、
内嵌 payload 与输入逐字节一致、镜像总长。测试把这五类真实失败模式逐个造出来并断言会 FAIL：
payload 改过镜像没重打、trust cache 不被 board 接受、菜单指向不存在的内核。

## 27. 2026-11-11 凌晨：iOS 27 内核首次编译成功，fd44 上机

### 27.1 CI run 42878351134（sha `d1e65d3`）：内核编译通过，卡在 trust bundle

`Build kernel` 这一轮**成功了**，产物 `kernel/kernel.macho` 94,552,064 B，sha256 `feb5deb3b22d4478…`。
里面的两条版本串说明这确实是我们要的那个混合体：

```
@(#)VERSION: Darwin Kernel Version 27.0.0: ... root:xnu-13432.2.10~2/RELEASE_ARM64_T8140   ← iOS 27.0.1 原版 prelink 部分
@(#)VERSION: Darwin Kernel Version 25.5.0: Tue Nov 10 18:57:18 UTC 2026; runner:ios-obj/DEVELOPMENT_ARM64_BCM2837  ← 我们自己编的 xnu-12377
```

失败点前移到下一步：

```
step 18  Build the trust bundle   failure
File ".../unixnu/scripts/build-original-system-trust.py", line 29, in <module>
    with zipfile.ZipFile(ROOT / 'refer/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw') as archive:
FileNotFoundError: ... refer/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw
step 19  Build payload                          skipped
step 20  Replace the schema-2 ADT with the board ADT  skipped
```

根因（已验证，源码行号）：这个脚本把 **iPadOS 17.7.11 / j120ap** 的
`Cryptex1,SystemTrustCache` 硬编码在 `ROOT / 'refer/...ipsw'`，并对两个模块做 sha256 白名单校验
（`da88460e…` = 目标卷 static-trustcache、`d121ba89…` = j120ap 的 system trustcache）。board 切到
`iPhone17,1_27.0.1_24A446` 之后，CI 只下 iOS 27 的 IPSW，这份 iPadOS IPSW 不在机器上，于是直接抛
`FileNotFoundError`。要修就得把 IPSW 路径/DeviceClass/两条期望摘要一起从 board 派生 —— 属于明天的工作，
今晚的启动路径不依赖它（见 27.3 的 trust cache 校验）。

### 27.2 纠正一个我自己立的错误判据

之前 chain2 用“`kernel.macho` 里出现 `c3a4d926`”当作“这是 iOS 27 内核”的闸门，**这个判据是错的**：
`C3A4D926-…` 是 `board.toml:113` 的 `root_match_volume_uuid`，会被写进 **ADT**，不是内核二进制里的字符串。
实测两份内核的文本计数都是 0。正确判据是：内核里 `Darwin Kernel Version 27.0.0 … xnu-13432.2.10`
（Apple 原版 prelink）与 `runner:ios-obj/DEVELOPMENT_ARM64_BCM2837`（自编部分）同时存在。

### 27.3 fd44 组装（本地，不依赖 CI payload 步骤）

| 项 | 值 | 校验 |
|---|---|---|
| 内核 | CI `kernel.macho` 94,552,064 B | sha256 `feb5deb3b22d4478…` |
| trust cache | 61,356 B | sha256 `7416ca4f…` **与 board.toml:86 允许值逐字节相同** |
| ADT | `boot/adt-ios27.dtb` 10,468 B | payload 无 `.vroot` → 不带 RootPolicies |
| 菜单 | 补 `[[driver]] path = "Payloads/DarwinBoot.efi"` | 并把 `args` 对齐 board.toml:104 |
| boot image | `boot/Mu-shennong-fd44.img` 103,059,456 B | sha256 `6bc62eb7e3e916b2…` |
| 预检 | `scripts/verify-boot-package.py` | **0 failure(s)** |

`03:53:12` 下发：`Sending 'boot.img' (100644 KB) OKAY / Booting OKAY`，设备离开 fastboot（`fastboot devices` 为空、
`lsusb` 无匹配），即已进入我们自己的镜像。

### 27.4 坑：mtools 在终端里会静默等输入

组装脚本有一次卡死 10 分钟，原因是 `mcopy -o -i <不存在的镜像> ...` 在**有终端**时进入 mtools 的交互式
驱动器参数询问。以后所有 `mcopy/mdir/mattrib` 一律加 `</dev/null` 并配 `timeout`；脚本里已经这么改。

### 27.5 trust bundle 改成从 board 自己的 IPSW 生成（本次的第二个真修复）

`board.toml:83` 的注释本来就写着 “this board pins the bundle built from its own IPSW”，
但真正干活的 `unixnu/scripts/build-original-system-trust.py` 把 **iPadOS 17.7.11 / j120ap / 21H461**
硬编码进 `refer/` 路径和两条 sha256 白名单里。board 换成 iPhone17,1 之后这个步骤必然抛
`FileNotFoundError`，而且就算那条 IPSW 在场，产出的也是 **17.7.11 的信任缓存**——它盖不住 iOS 27 的
launchd，属于“能跑但错的产物”。

新增 `scripts/build-target-trust-bundle.py`（本仓库，不经框架），一切从 `board.toml` 派生：

| 输入 | 来源 |
|---|---|
| IPSW 文件名 | `[ipsw] url` 的 basename，在 `refer/` 下 |
| DeviceClass | `[ipsw] device_class` = `d93ap` |
| static 模块 | `StaticTrustCache` |
| system 模块 | `Cryptex1,SystemTrustCache` |

它只考虑**同时带这两个键**的 BuildIdentity：iPhone17,1 24A446 的第 3 个 identity 是
`Recovery Customer Install`，它的 StaticTrustCache 是恢复分区的
`043-68523-763.dmg.aea.trustcache` 且根本没有 `Cryptex1,SystemTrustCache`，混进来就会张冠李戴
（第一次跑就是这个报错，已按此修正）。每个模块都按 BuildManifest 里的 sha384 逐字节校验后才打包。

实测结果（本地用真实 IPSW 跑，两次独立计算一致）：

```
static: 3821 entries, 91728 B, sha256 28838d2c5f1c37c11ba4e58cad498ba9f65fd69a4cd62f42818019440dd6ef36
system: 130 entries,  3144 B, sha256 d9db3ecc5ad4a3fc11a440e0845acd0919ebadc0fff26b38542f2dba02d64b44
bundle: 94884 B sha256 a2a2566f41c6d3e7a48ba14a0502226c2d85eb2775587ac58c5433116b382d2c
```

`board.toml [payload] trust_cache_sha256` 已从 `7416ca4f…`（iPadOS 时期的包，61,356 B）改成
`a2a2566f…`；workflow 的 `Build the trust bundle` 改为调用本仓库脚本，
`Build payload` 与 ADT 步骤的取值 glob 增加 `build/target-static-system-trust/`。
`scripts/test-verify-boot-package.py` 复跑：`all checks passed`。

### 27.6 第三个真修复：payload 步骤的符号解析在 fileset 内核上必崩

新 run `42890124268`（sha `3b2bfff`）的结果：

```
step 18  Build the trust bundle → success
         trust bundle: bundle: 94884 B sha256 a2a2566f41c6d3e7a48ba14a0502226c2d85eb2775587ac58c5433116b382d2c
         trust bundle: board pin matches            ← CI 复算结果与本地完全一致
step 19  Build payload → failure
```

失败点是 `kernel_symbols()`：

```
scripts/patch-xnu-entry-probe.py:153  table.setdefault(int(parts[0], 16), parts[2])
ValueError: invalid literal for int() with base 16: 'Symbols'
```

`llvm-nm -n` 在 fileset 内核上会输出 `Symbols:` 这类非符号行，旧代码假定“三个字段的首字段一定是十六进制地址”。
根因不是这一行，而是**打补丁的时机**：

```
probe symbols: patched scripts/patch-xnu-entry-probe.py      ← 只改了仓库副本
##[error]== tree out/shennong/.../tree                        ← 之后 unixnu 才物化 tree
##[error]  tree/scripts/patch-xnu-entry-probe.py:153 崩        ← tree 副本仍是旧代码
```

workflow 里的运行期补丁只覆盖得到已经存在的文件；tree 是在 payload 步骤里才生成的，所以补丁落空。
修法是把容错直接写进仓库源文件（`scripts/patch-xnu-entry-probe.py` 的 `kernel_symbols()`：跳过解析失败的行、
不再依赖 nm 的退出码、表为空时打印 nm 的原始输出）。用桩 nm（输出 `Symbols:` + 两行真符号）本地验证解析正常，
得到 `{0xfffffff0073f45c0: '_panic_kernel', 0xfffffff007279520: '_cmn_funnel'}`。

顺带记录一个不阻塞的观察：`shennong-kext-exports-probe.py` 读 iOS 27 的 `kernelcache.decompressed` 时报
`ValueError: Only ordinary little-endian ARM64 is supported`（`kits/XnuPrelink/native_prelink.py:19` 只接受
cpusubtype 0；iPhone17,1 的内核是 `0xc0000002`，即 arm64e + ptrauth ABI）。该步骤失败时 `exit 0`，属诊断信息，
不影响打包。

### 27.7 第四个真修复：panic screen 比 iPhone17,1 的 cave 大 23 字节

run `42897412487`（sha `6cdd2cc`）里 `kernel_symbols` 的修复生效（不再报 `'Symbols'`），失败前移到
panic screen 落位：

```
panic screen is 0xa47 bytes at 0xfffffff00ad815c0, the padding ends at 0xfffffff00ad81ff0
```

实测这块内核的空白（本地用产物 `kernel.macho` 逐字节量，VA→文件偏移走 `__TEXT_EXEC` 段）：

| 位置 | 零填充长度 |
|---|---|
| `0xfffffff00ad815c0` 起向前 | **0xa43 = 2,627 B**（到 `0xfffffff00ad82003` 出现 `141f2003…`） |
| `0xfffffff00ad815c0` 之前 | **308 B 连续零**（上一个 cave 的 `CAVE_SIZE` 预留尾部） |

所以差得不多，但硬常量 `PANIC_CAVE_END` 只给 0xa30，比渲染代码还小。改法（`scripts/patch-xnu-entry-probe.py`）：

1. 记录每个 stage 实际用了多少字节（`cave_lengths`）；上一个 cave 的 `CAVE_SIZE - 实际长度` 是可证明没人跳进去的尾部；
2. panic screen 允许**向前**吃这段 slack（4 字节对齐、且只在原字节为 0 时移动）；
3. 结束边界不再信常量，改为**实测**零填充直到第一个非零字节（上限 0x1000）。

本地用真实产物复现并验证（同一命令：`patch-xnu-entry-probe.py <kernel.macho> --panic-screen --no-reset`）：

```
改前：panic screen is 0xa4f bytes at 0xfffffff00ad815c0, the padding ends at 0xfffffff00ad81ff0   (exit 1)
改后：patched kernel.macho: … panic screen (0xa4f bytes at 0xfffffff00ad815a8; common funnel at 0xfffffff00ab69d48)   (exit 0)
```

`scripts/test-entry-probe.py` 复跑：`entry-probe contract: all checks passed`。

### 27.8 CI run 42904596191 全绿：第一个配置正确的 iOS 27 引导包（fd46）

patch 层三处修好之后，CI 这一轮 **kernel / logs 两个 job 全部 success**，payload 步骤产出
`payload.img` 201,326,592 B（192 MiB）。产物实测：

| 项 | 值 | 验证方式 |
|---|---|---|
| payload 内核 | 94,552,064 B（与 CI `kernel/kernel.macho` **不同** sha：`ab2f3ecd…` vs `31e33289…`） | payload 里那份是打过 stage 色带 + panic screen 的副本，全图 4,460 字节差异 |
| owner-root 诊断串 | `owner-root: autherr=%d owner=%d readonly=%d mount_dev=%d selected_dev=%d trust=%d` | `strings -a` 在 payload 内核副本里直接命中 |
| panic screen | 写在 `0xfffffff00ad815a8`（首 8 字节 `e1030091 bb000014`），与本地跑出的地址逐字节一致 | 与未打补丁的 CI 内核对比该地址（原本全 0） |
| trust cache | 94,884 B sha256 `a2a2566f41c6d3e7…` | 卷内读回 |
| vroot 通道 | `kernel.macho.vroot` 1,152 B，头 `VROOTB01`，内含 `VROOT01` 条目 | `xxd` |
| ADT | 10,520 B，含 `RootPolicies` / `TrustCache` / `root-matching` 三个串 | `scripts/adt-ios27-vroot.dtb` |

组装结果：

```
Mu-shennong-fd46.img  203,722,752 B  sha256 2e735e6c6b9e091d…
verify: ok (kernel 2389419 incl. dtb 1238463, ramdisk 201326592, payload at 0x249000)
预检 verify-boot-package.py → 0 failure(s)
```

对比 fd44：fd44 用的是 **iPadOS 17.7.11 的 61,356 B 信任缓存**、没有 vroot 通道、ADT 也不带
RootPolicies；fd46 这四项全是 iOS 27 对应的正确件。**上机判断应以 fd46 为准**，fd44 的屏幕只说明
"无 vroot 时的失败形态"，信息量被 fd46 完全覆盖。

## 28. 2026-11-11 上午：用复位探针把 iOS 27 内核的死点收进 `_arm_vm_init` 开头 2,324 字节

### 28.1 设备规格更正（以用户 YG 确认为准）

| 项 | 值 | 依据 |
|---|---|---|
| 机型 | 小米 14 Pro（shennong，23116PN5BC，SM8650） | 实测 `fastboot devices` 序列号 `9f72e95c` |
| 存储 / 内存 | **256 GB + 12 GiB** | 用户本人确认「12+256」；`docs/bringup.md` 与 `porting.toml` 本来就写的 12 GB，只有对话里出现过一次错误的「16 GB」，现已更正 |
| DRAM 起始 | `0x80000000` | `porting.toml` 的 `inputs`；`firmware/shennong-memory-map.toml` 由本机 `xbl_config_a` 解析而来 |

内存容量这件事对当前判读有直接影响，所以把算式写在这里（**已验证：源码** `osfmk/arm64/arm_vm_init.c`）：

```
mem_size   = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase
panic 条件 = mem_size >= (VM_MAX_KERNEL_ADDRESS - VM_MIN_KERNEL_ADDRESS) / 2
VM_MIN_KERNEL_ADDRESS = 0xffffffe000000000   VM_MAX_KERNEL_ADDRESS = 0xfffffffbffffffff
门槛 = 0xdffffffff ≈ 56 GiB
12 GiB = 0x300000000  →  12 GiB ≥ 56 GiB 不成立  →  不会走 panic("Unsupported memory configuration %lx")
```

⇒ 之前那次「12 GiB 是不是超限」的疑虑可以闭环：**超限这条分支不走**。

### 28.2 探针表（每一行都是真机实测，`fastboot boot` 下发）

判读约定：探针=在某点等 N 秒后 `smc #0`（PSCI SYSTEM_RESET）；设备自己重启并落到 recovery = **命中**（该点确实执行到了）；USB 静默 = **未命中**。

| 镜像 | 探针位置 | 延时 | 结果 | 证据 |
|---|---|---|---|---|
| fd47 | `0xfffffff00ad83438`（`msr SCTLR_EL1, x0` 之后 0x20） | 20 s | **命中** | 屏幕黑掉后自行重启到 TWRP ⇒ MMU 翻译正确 + PSCI SYSTEM_RESET 在 SM8650 上可用 |
| fd49 | `_arm_init` 内 `bl _arm_vm_init` 之后（`0xb477374`） | 10 s | **未命中** | 105 s 采样 `fastboot=[] adb=[]` |
| fd50 | `_arm_init` 内 `bl _arm_vm_init` 之前（`0xb477370`） | 10 s | **命中** | 09:41:19 起 `adb` 出现 `9f72e95c recovery` ⇒ `_arm_init` 确实走到这个调用 |
| probe-walk/01 | `_arm_vm_init` 内 `_vm_set_page_size` 之后（`0xad782f8`） | 10 s | **未命中** | 09:43:15→09:46:13 无任何 USB 变化 |

结论（已验证）：死亡区间 = `_arm_vm_init` 入口 `0xad77ae4` 到 `0xad782f8` 之间，共 **2,324 字节**，其间只有 8 处调用：
`_phystokv`(0xad77bc0)、`_early_random`(0xad77bcc)、`_kvtophys`(0xad77c44)、`__bzero`(0xad77cd0)、
`_getsegdatafromheader`×18（首个 0xad77e14）、`_getsectdatafromheader`×2、`_PE_get_kc_header`(0xad780a0)、
`_PE_parse_boot_argn`(0xad78244)、`_getlastkerneladdr`(0xad782b4)。

### 28.3 新工具

- `scripts/probe-walk.py`：把「构建→预检→下发→判定→`adb reboot bootloader` 接管→下一探针」串成一条自动走查。命中会自己回到 fastboot 继续跑，只有未命中才需要人手断电。
  踩坑记录：`fastboot boot` 把 `OKAY` 写在 **stderr**，只看 stdout 会把成功判成失败（已修，`boot-failed` 判据现在合并输出）。
- `scripts/patch-xnu-entry-probe.py` 新增 `--panic-reset SECONDS`：把 `_panic` 改跳进空闲 cave，等 N 秒后 `smc #0`。用途是把「静默死亡」分成两类——设备自己重启 = 内核**主动 panic**；依旧静默 = **异常/自旋**。

### 28.4 尚未验证（不要当成已知）

- loader 实际填进 `boot_args->memSize` 的**具体数值**没有实测过（`未验证`）；只知道它必须 ≥56 GiB 才会触发那条 panic。
- 死亡是 panic 还是异常，当前**未知**，下一次上机（fd51）就是来定这件事的。

### 28.5 fd53 / fd54：死法是 panic，但 panic 屏在这个位置画不出来（2026-11-11 上午）

**fd53**（`_panic` 等 20 s 复位 + EL1/SPx 同步异常等 60 s 复位，双钩）：下发 09:54:02，09:55:36 以 recovery 身份回到 USB。
两条钩子的延时把两个等式钉死（`A` = 走到 `bl _arm_vm_init` 的时刻，`D` = 复位后 TWRP 起 adb 的耗时）：

```
fd50（探针 10 s 命中）: A + 10 + D = 76      →  A + D = 66
fd53（本次）           : X + 20 + D = 94      →  X + D = 74      （X = 进入 _panic 的时刻）
相减                   : X - A = 8 秒
```

若那次复位来自异常钩子（60 s），等式右边会变成 114 而不是 94，实测不符 ⇒ **死因是 `_panic()`，不是数据/未定义指令异常**（推断，依据是上面两条实测时刻）。

**fd54**（`--panic-screen`）：`panic screen (0xa4f bytes at 0xfffffff00ad815a8; common funnel at 0xfffffff00ab69d48)`，09:57:50 下发，120 s 采样无任何 USB 变化。
真机照片显示：屏幕仍是 DarwinBoot 菜单 + 蓝条 + 洋红条，**没有被清屏**，也没有白字。
渲染器 `scripts/xnu-panic-screen.c:222` 先读 `VINFO`，只要 `v_baseaddr == 0` 或 `v_depth != 32` 就直接 `park()`；清屏发生在这次检查之后。画面没被清 ⇒ **它停在了这个检查上**，即 `_vinfo` 在 `arm_vm_init` 这么早的时刻还没有内容（推断：`_vinfo` 是 XNU 侧稍后才填的全局）。

⇒ 结论：**panic 屏这条通道对 `arm_vm_init` 早期的 panic 无效**，要读消息得自己从 `gPhysBase`/`physmap_base` 算帧缓冲 KVA，而 `physmap_base` 恰恰是在那条 panic 之后才赋值（源码顺序），所以这条路暂时放弃。

### 28.6 改用「panic 15 s + 探针 60 s」双钩：每一轮都会自己重启，不再需要手动断电

`scripts/probe-walk.py` 新增 `--panic-reset` 与 `--hit-after`：panic 钩子早于探针复位，于是

- 探针**未**到达（内核先 panic）→ 复位≈`A+8+15`≈下发后 89 s 回到 USB
- 探针**到达** → 复位≈`S+60`（`S ≥ A`）≈下发后 126–134 s 回到 USB

两者相差 ~40 s，用 100 s 阈值分开即可。走查因此可以在没有任何人工干预的情况下把 `_arm_vm_init` 开头 2,324 字节里的 8 个调用点全部问一遍。

## 29. 2026-11-11 上午：panic 指纹通道（候选表 + 切片编码），以及走查分类器的真 bug

### 29.1 窗口的源码定位（已验证：反汇编 ↔ 源码逐条对应）

`_arm_vm_init` 开头 `[0xad77ae4, 0xad782f8)` 这 2,324 字节，用字节级 BL 扫描 + 符号反查，里面**没有任何 `bl _panic`**；它恰好覆盖 `osfmk/arm64/arm_vm_init.c` 第 1843–2090 行：

| 反汇编里的调用 | 源码行 | 含义 |
|---|---|---|
| `_phystokv` ×4 | 1863 | `physmap_base = phystokv(args->topOfKernelData)` |
| `_early_random` ×1 | 1866 | physmap 随机滑动 |
| `_kvtophys` ×4 | 1908 | `boot_ttep = kvtophys(&bootstrap_pagetables)` |
| `___bzero` ×3 | 1911 | 清 bootstrap 页表 |
| `_getsegdatafromheader` ×24 | 1994–2074 | 段表解析 |
| `_PE_get_kc_header` ×1 | 2026 | `KCKindPrimary` |
| `_PE_parse_boot_argn` ×1 | 2077 | `use_contiguous_hint` |
| `_getlastkerneladdr` ×1 | 2088 | `end_kern` |
| （窗口末尾） | 2090 | `vm_set_page_size()` ← 探针站点 |

⇒ panic 不是 `arm_vm_init` 自己直调，而是某个被调函数／它的 cold 段里（`_arm_vm_init.cold.18` = auxKC 检查、`_arm_vm_init.cold.31` = `BOOTSTRAP_TABLE_SIZE too small`，两条都在 `#if DEVELOPMENT||DEBUG` 或 auxKC 分支里）。

### 29.2 走查分类器的真 bug（已验证：修复前后各一次实机）

`fastboot boot` 返回后，设备仍以 `????????????  fastboot` 回答 `fastboot devices` 达数秒；旧判定把「看得到 fastboot」当成「探针回来了」，于是第 01 轮（`_phystokv`）报了一个**15 秒的假 panic**。
修法：新增 `wait_boot_started()`——以「bootloader gadget 消失」为 boot 真正开始的时刻，计时与判定都从这一刻起算；`unknown`（<5 s 就回来）单独成一类并重试一次。`scripts/test-probe-walk.py` 用桩 `fastboot`/`adb` 回放时间线，钉住 hit / panic / unknown / boot-failed / miss 五种判定，`probe-walk classifier: all checks passed`。

### 29.3 panic 候选表收集器（新工具）

`scripts/collect-panic-sites.py`：从符号表取函数区间 → 找 `bl/b _panic`、`_panic_trap_to_debugger` 等 → 回溯还原 `x0`（`adrp`+`add` 或 `ldr x0, #literal`）→ 从内核里读回格式串。踩到的坑（都已修）：
- `adrp` 在回溯顺序里出现在 `add` 之后，必须先把 page 映射收集完再解析 `add`；
- 编译器把 panic 分支放进 `.cold.N`，`_PE_get_kc_header` 本体里一条都没有——必须跟进 `.cold.*` 与 `_OUTLINED_FUNCTION_*`；
- cold 段常常用**尾分支 `b`** 而不是 `bl`。

### 29.4 指纹两轮实测（已验证）

`--panic-candidates` 把 `panic()` 拿到的格式串地址与候选表逐条比较，命中第 i 条就等 `10+6i` 秒后复位，未命中等 `34` 秒。判定用「校准轮」消掉启动时间与 recovery 启动时间：

```
校准（--panic-reset 10）: 65 s      → A + D = 55 s
候选表（4 条，10/16/22/28，未知 34）: 87 s
delay = 87 − 65 + 10 = 32 s
```

32 s 落在 28 s（`segLOWESTAuxKC`）与 34 s（未知）之间，偏向「未知」；且 28 s 那条所在的 `arm_vm_auxkc_init()` 在源码里位于第 **2208** 行，远在 `vm_set_page_size()`（2090）之后，本来就不可能是它。
⇒ **结论（已验证）：panic 不属于这 4 条候选，是别处（更深的被调函数 / `assert` / `_panic_trap_to_debugger` 路径）**。

同时得到一个有用常数：**A + D ≈ 55 秒**（A = boot 真正开始→进入 `_arm_vm_init`；D = 复位→recovery 的 adb 起来）。

### 29.5 下一步（正在跑）

用修好的分类器把窗口里 8 个调用点扫一遍（`--delay 60 --panic-reset 15 --hit-after 96`）：探针命中 ≈ 115 s 回来，panic 先发生 ≈ 78 s 回来，两个簇相差 ~37 s。拿到「最后到达 / 第一个未到达」的括号后，只对那一个被调函数跑收集器，候选数会降到个位数，再一轮候选表就能点名。

## 30. 2026-11-11 10:40–11:00：突破！`physmap_slide = 0` 让 `arm_vm_init` 越过 `_vm_set_page_size`

### 30.1 fd60 先把「走不走 panic」定死（已验证）

fd60 = 故障向量钩 10 s + panic 钩 90 s。boot 起点 ≈10:36:14，adb 于 10:38:38 以 `9f72e95c recovery` 回来 = **≈144 s**；故障臂预测 ≈56 s、panic 臂预测 ≈136 s ⇒ **`_panic()` 确实被调用**。旁证：fb5（无任何钩子）超过 3 分钟从不自己重启，说明 144 s 那次复位只可能来自我们的 panic 钩。
⇒ fb5 照片上没有白带，坏的是**显示通道**（存根或帧缓冲写），不是「没进 panic」。

### 30.2 `--zero-physmap-slide`：把 `_early_random` 换成 `x0 = 0`（已验证）

实现（`scripts/patch-xnu-entry-probe.py`）：定位 `_arm_vm_init` 内对 `_early_random` 的 `bl`（`0xad77bcc`，原值 `0x97ff74b5`），**先校验**该字确实是 BL 且目标等于 `_early_random`，再写 `mov x0, xzr`（`0xD2800000`）⇒ `physmap_slide = 0`，`assert(physmap_slide < ARM64_PHYSMAP_SLIDE_RANGE)` 自然成立。
踩坑记录：BL 目标校验里符号扩展写错（`(imm26 << 2) - (bit25 << 1)`，正确是 `imm26 - 0x4000000` 再 `<< 2`），导致把正确的调用点判成「不是 early_random」；已修。

### 30.3 fe01 真机：前沿首次推进（已验证：计时）

镜像 `Mu-shennong-fe01.img`，sha `1f2c9152ea9571c8…`，预检 `0 failure(s)`，补丁 = `--zero-physmap-slide` + `_vm_set_page_size` 探针（10 s）+ panic 钩（90 s）。
下发 10:40:38，boot 起点 ≈10:40:56，adb 于 **10:42:02** 回来 = 启动后 **≈66 s**。站点臂预测 `A+10+D ≈ 56 s`、panic 臂 ≈136 s ⇒ **命中站点探针：`_vm_set_page_size`（`0xad782f8`）第一次真正到达**。

### 30.4 尾巴走查（已跑，但阈值设计有缺陷，待复核）

`--zero-physmap-slide --delay 60 --panic-reset 90 --hit-after 110`：

| 锚点 | 回来耗时 | 粗判 |
|---|---|---|
| `_patch_low_glo_static_region`（`arm_vm_init` 最后一个实调用） | 144 s | ≥阈值，倾向命中 |
| `_pmap_bootstrap` | 134 s | 倾向命中 |
| `_arm_auxkc_init` | 134 s | 倾向命中 |
| `_set_mmu_ttb` | 106 s | 判定为 panic，但 106 = `A+60+D`（A+D=46）**恰好是站点臂**，实际应为命中 |

**设计缺陷**：panic 钩 90 s 与站点 60 s 只差 30 s，而 `D` 抖动 10–20 s，两个簇重叠 ⇒ 这一轮的分类不可信。改法：panic 钩拉到 **240 s**，站点臂 106–150 s、panic 臂 ≥286 s，两簇彻底分开。正在用 `--panic-reset 240` 复核 `_patch_low_glo_static_region` 与 `_arm_init` 里 `bl _arm_vm_init` 之后的点位。

### 30.5 已确定的修复形态（P2 要落进源码）

`early_random()` 在 iOS 内核里只用于生成 physmap 随机滑动量；本移植在 `arm_vm_init` 阶段还没有 corecrypto DRBG（`prng_funcs` 指向 kext），调用即死。正确落法是在 `osfmk/arm64/arm_vm_init.c` 里让滑动量可配置：默认 0，`PE_parse_boot_argn("physmap_slide")` 可覆盖；这样既保住原逻辑，又不依赖早期 DRBG。

## §31 越过 arm_vm_init 之后的死点点名（2026-11-11 12:05）

### 已验证
| 实验 | 配置 | 实测 | 结论 |
|---|---|---|---|
| fe10 | 候选表 3 槽（10/70/130 s） | 61 s = 槽 0 | panic 串 = `Kernel stack memory corruption detected @%s:%d` |
| fe11 | `--allow-stack-chk` + 站点 `_patch_low_glo_static_region`(10 s) | 68 s | arm_vm_init 最后一个调用**到达** ⇒ arm_vm_init 跑完 |
| fe12 | 站点 `_machine_startup`(10 s) panic 240 | 293 s = panic 臂 | machine_startup 未到达 |
| 阶梯 | 站点 `_ml_map_cpu_pio`(10 s) panic 60 | 116 s = panic 臂 | `ml_map_cpu_pio` **没返回** ⇒ panic 在它里面 |
| fi01 | 指纹 `0:4:10:20` | 166 s ⇒ 槽 5 | 串 VA 的 bit0-3 = 5 |
| fi02 | 指纹 `4:4:10:20` | 283 s ⇒ 槽 11 | bit4-7 = 0xB |
| fi03 | 指纹 `8:4:10:20` | 146 s ⇒ 槽 4 | bit8-11 = 0x4 ⇒ **VA ≡ 0x4B5 (mod 0x1000)** |

关键教训：fe13/fe14 第一次跑出 59 s 是**误读**——当时没加 `--no-reset`，默认的 stage-3 站点（MMU + 6 s）先复位了，panic 钩根本没轮到。
凡是只用 panic 钩的镜像必须显式 `--no-reset`。

### 串地址枚举（不依赖调用图）
严格按「字符串起点 + 前字节为 NUL」扫描整个 Mach-O，VA 低 12 位 = 0x4B5 且含格式符的只有 10 条，
其中与早期启动 CPU 初始化阶段相符的只有一条：

```
0xfffffff0071734b5   "CPU configuration in device tree is invalid" @%s:%d
```

该串**不在**本地 xnu-3199e8bc 源码树里（整棵树 grep 无命中）——线上内核是 xnu-13432.2.10，
属于更新的闭源部分（推断：arm64 的 CPU 拓扑解析器）。

### 回读通道实测（TWRP 侧）
```
/dev/mem      不存在
/dev/kmem     不存在
/proc/kcore   不存在
/sys/fs/pstore 已挂载但为空（total 0）
```
⇒ 没有直接回读物理内存的手段；时间通道仍是唯一通用水位线，**上限 4 bit/次启动**。

### 下一步
1. 看 shennong.dtb 的 `/cpus` 是否带 Apple 拓扑解析器要求的属性（`state`/`reg`/拓扑节点）；
   缺就在加载器里合成，缺得太多就把该 panic 的冷路径改成容错。
2. 确认 panic 确实发生在 `ml_map_cpu_pio` 内部：在它入口再挂一个站点（一次启动 ~2 分钟）。

## 32. 2026-11-11 下午 · AppleARMCPU 抢占 /cpus（本轮结论）

### 32.1 已证伪：改 kext 代码不生效
- fi07：`bl _validateConfiguration`(0x85f6f00) 改 `mov x0,#1` + 其后 `tbz` 改 nop → 设备仍 panic，110 s（= 50 s panic + 60 s 钩）。
- fi08：把 panic 分支 `bl`(0x85f746c) 直接改成跳到成功续接 0x85f71ec → 仍 115 s。
- fi10：把 panic 冷桩 0x86473b0 首指令改 `ret` → 仍 167 s、槽值 5（与 0x4b5 一致）。
- 对照：kernel 主文本区补丁（`__stack_chk_fail`、探针 cave）一直是生效的。
- 结论：`__TEXT_EXEC` 里 kext 代码段在运行时不是按我们改的字节执行（推断：运行期另有映射/副本）。
  → **放弃"逐个绕闭源检查"的代码补丁路线。**

### 32.2 已查明：panic 的真实来源是 AppleARMPlatform 抢节点
- panic 串 `0xfffffff0071734b5` "CPU configuration in device tree is invalid" 只被
  `0xfffffff0086473b0` 这个冷桩引用，冷桩唯一调用点是 `0xfffffff0085f746c`，
  它所在的函数在 `0xfffffff0085f6f00` 调 `_validateConfiguration`（0x85f751c）。
- `__PRELINK_INFO` 里 AppleARMCPU 的 personality：`IONameMatch = "cpu"`，
  前缀匹配会吃掉 `cpu@0` 和 `cpus` 容器；一旦匹配就要求 Apple 私有属性
  （`max_cpus`、每核 `cpu-id`/`interrupts`/`function-*`），Qualcomm ADT 没有 → panic。
- 项目自带的官方修法：`tree/scripts/patch-applearmcpu-ioname.py`，3 字节原地改
  `cpu` → `xpu`（等长、不动布局），rmx1971 / mondrian / sirius 都在用。
- 用该脚本 `--check` 验过：fi11（以及 fe/fd 系列）**都还是 `cpu`**，即此前所有启动
  实验都撞在同一个点上；fi13 是第一个带上该修的镜像（脚本输出 `cpu -> xpu, 1 byte`）。

### 32.3 尚未验证
- fi13 真机表现（推镜像后设备回到 UniXNU 加载器菜单，没拿到时序）。
- 下一次只需一次启动即可判定：命中站点探针≈60 s = 过了 CPU 关；≈110 s = 仍 panic。

## 33. 11-11 下午：作废读数、内核确实在跑、MMU 关已过

### 33.1 已被证伪的说法（不要再用）
- **“设备停在加载器菜单、内核没启动”**：错。把照片放大 3 倍读出加载器日志，最后两行是
  `DARWINBOOT: inputs validated; exiting boot services` / `DARWINBOOT: hand-off to the kernel`
  （源码 DarwinBoot.c:800），屏幕上的“菜单”是启动前画好的旧画面留在帧缓冲里，内核只在顶部叠了色带。
- **“56 秒处命中 CPU 配置 panic”**：读数不可信。那几次判定依赖“adb 隔多久回来”，而设备可能根本没进内核
  或停在别处；fi14/fi15/fi16 的秒数一律作废，不再参与推理。
- **“fi13 是第一个带 xpu 的镜像”**：`patch-applearmcpu-ioname.py --check` 对 payload-fd46 的输出是
  `nothing to do: AppleARMCPU IONameMatch is already xpu`，payload 一直是 xpu。

### 33.2 已验证（真机，fi19）
- payload 里的 `unixnu.toml` 原为 `timeout = 0`；这台机器 `CountInputDevices()` 为 0，改成 `timeout = 3`
  后行为不变（仍是加载器画面），说明“等按键”不是唯一原因，见 33.1。
- **fi19**（`stage 1 blue` + `stage 3 reset 6 s after the MMU is on` + `panic bands`，内核 sha 由构建日志给出）
  13:24:39 下发，`fastboot boot` 返回 0；随后设备**自己重启进入 Android 设置向导**（照片）。
  由于 panic 画带钩子触发时会画 32 条竖带并死循环、不会重启，这次重启只能来自 stage 3 探针
  → **MMU 打开那一步已经通过**（推断，证据链：fi19 的两个信号互斥 + 之前几次硬挂 10 分钟不重启）。
- 由此确认三处补丁有效：`physmap_slide = 0`（替换 `bl _early_random`）、两处 Apple-monitor `msr` 置 `nop`、
  `__stack_chk_fail` 置空。

### 33.3 下一步（fi20）
- `scripts/patch-init-ladder.py` 去掉了 capstone 依赖（纯 Python 解 `bl`/`ret`），可在本机直接生成阶梯。
- `Mu-shennong-fi20.img`：`_arm_init` 入口 + 前 15 个 `bl` 调用点各画一条带（band 0 白 … band 15），
  画在**调用之前**，所以死在被调用函数里也能留下最后一条带。一次开机即可把死点收窄到一个调用。
- 判读：没有白带 = 死在 `_arm_init` 之前；白带 + k 条 = 死在 `_arm_init` 第 k 个调用里；16 条全到 = 整段跑完。

### 33.4 fi21 的设计缺陷与 fi22 修正
- **fi21**：每站点等 `(序号+1)×10 s` 后复位。缺陷：入口标记必然先触发并复位，后面的站点永远轮不到，
  所以只能读出"入口到达"（实测 11 秒 ≈ 交棒 1 s + 入口 10 s），读不出更深的位置。
- **fi22**：改成倒计时（`--countdown`），第 k 个站点等 `(16-k)×8 s`，最深的到达点最先到期复位，
  复位时间直接对应站点：128 s=入口、120 s=call 1 … 8 s=call 15；永不重启=连入口都没到。
- 复位型探针不依赖内存映射（PSCI `smc #0`），MMU 打开后依然有效（fi19 已证）；画色带的方式在 MMU
  打开后不可靠，不再用于 `_arm_init` 内部。

### 33.5 fi22 作废 + 离线模拟 + fi23
- **fi22 的倒计时设计是错的**：标记是阻塞的（cave 里等完直接复位），所以最后一个被进入的标记永远挡住更深的标记。
  倒计时只能让入口（延时最长 128 s）先到期，读数恒为 ~128 s，即"两分多钟"与死点无关。
  **正确的编码是递增延时**（fi21 原本那样）：能被复位命中的是"最先遇到的、最浅的那个已到达标记"，其延时就是站点编号。
- **离线模拟**（unicorn，`/tmp/emu_trace.py`）：把文件集按加载器方式映射（VA == PA，窗口 0xfffffff007004000+94.5 MB），
  从 `_arm_init` 跑，PAC/bti 指令按 NOP 处理。结果：
  - `_arm_init` 的首段是**内联的 `arm_slide_rebase_and_sign_image()`**（源码 arm_init.c:349 第一句），
    走的是 fileset 分支（`_mh_execute_header` 在 0xfffffff007184000，flags=0x80218001，bit31=MH_DYLIB_IN_CACHE，静态核对过）；
  - 实际执行路径：0xb4768f0 → 跳到 **0xb476a94**，然后 4 段连续区间 a94..b20 / bb0..d40 / da8..f5c；
  - **0xb476a80 不在执行路径上**（那是非 fileset 分支的 bl），fi21 把它当成"call 1"是错误的；
  - 模拟跑完整个 fixup 走查（92 万基本块）**没有触发任何越界访问**，最后停在 PAC 签名指令上（unicorn 不支持，非内核问题）。
- **fi23**：实路阶梯（16 个标记，10..160 s）+ `--fault-reset 3`（EL1 同步异常向量 3 s 后复位）。
  一次开机三种结果可分辨：≤5 s=异常；10..160 s=命中的实路站点；一直不重启=连 0xb476a94 都没到或纯自旋无异常。

### 33.6 设备树/启动参数的静态核对（离线，未上机）
- **内核收到的设备树不是 boot 镜像里追加的 `shennong.dtb`**，而是加载器读的 `<KernelPath>.adt`：
  `DarwinBoot.c:648-657` → `EFI/UniXNU/Payloads/kernel.macho.adt`（10,520 B，Apple ADT 格式）。
  boot 镜像里 `--append-dtb shennong.dtb`（1,238,463 B）是给 UEFI 固件用的，不是给 XNU 的。
- ADT 解析（属性头 = 32 B 名字 + u32 长度 + 数据，4 对齐；整棵树正好 10,520 B，格式无误）：
  ```
  /device-tree                    model=Xiaomi-14-Pro compatible=qcom,pineapple-mtp,...
  /device-tree/chosen             dram-base=0x80000000  dram-size=0x10000000(256 MB)
                                  darwinboot-memory-size=窗口大小  random-seed  nvram-*  osenvironment
  /device-tree/chosen/memory-map  TrustCache, RootPolicies（无 RAMDisk，因为不传 ramdisk）
  /device-tree/cpus/cpu0          state, reg, device_type, compatible, timebase-frequency（**只有 cpu0**）
  /device-tree/defaults           sleep-disabled
  /device-tree/product            product-name, model
  /device-tree/arm-io/intc        compatible, reg, redistributor-stride
  ```
- boot_args ABI 正确（`DarwinBoot.c` 的 `DARWIN_BOOT_ARGS` = XNU `pexpert/pexpert/arm64/boot.h` 的 rev2 布局，0x480 B，偏移有 STATIC_ASSERT 保证）。
  但语义上有两处可疑，等 fi23 读数回来后再动：
  - `memSize = WindowSize`（≈94.5 MB）< 1 GB ⇒ `arm_init` 会选 `PAGE_SHIFT_CONST = ARM_PGSHIFT`（4 KB 页），而不是 `PAGE_MAX_SHIFT`（16 KB）；
  - `dram-size = 256 MB`、`cpus` 只有 cpu0；`hw.memsize` 大概率取不到 ⇒ `xmaxmem = 0` 传给 `arm_vm_init`。
- `_arm_init` 前 16 个 bl 的目标函数（供 fi23 读数对照）：
  ```
  f74  PE_set_kc_header            fac  kernel_collection_adjust_mh_addrs
  fb4  OSRuntimeSignStructorsInFileset  fc8  static_if_init(arm_static_if_init)
  fe0  memcpy(const_boot_args)     ff8  cpu_data_init
  ffc  ml_default_rop_pid          7004 ml_default_jop_pid
  7014 PE_init_platform            7018 boot_progress_init
  701c configure_timer_apple_regs  7020 wfe_timeout_configure
  7024 wfe_timeout_init            7028 configure_misc_apple_boot_args
  7030 configure_misc_apple_regs   7048 SecureDTLookupEntry（UPSI/chosen 块）
  ```
  `configure_timer_apple_regs / wfe_timeout_* / configure_misc_apple_*` 反汇编里没有 Apple 专有系统寄存器访问
  （只有 `mrs cntkctl_el1`、`mrs tpidr_el1` 这类标准寄存器），所以它们不是"Apple 专有指令"陷阱。

### 33.7 fi23 读数与 fi24 分类探针
- **fi23 = 13 秒**：命中第 0 号站点 `0xfffffff00b476a94`（10 s 档 + 约 3 s 交棒/上传开销），20 s 档 `0xfffffff00b476bb0` 未命中。
  由阻塞标记的语义，这只证明"执行到过 a94"，不能推出其后走了多远（一旦进入 cave 就停在原地等复位）。
  结合静态分析：fileset 分支的头部检查全部通过（`k_mh->flags` bit31、首个 LC 为 `LC_SEGMENT_KERNEL`、`slide=0`、
  `kc_mh->filetype == MH_FILESET`），死点在进入内联 `kernel_collection_slide()` 之后。
- **fi24**（20:18:35 下发）：`--panic-reset 4` + `--fault-reset 8` + 4 个深站点（20/40/60/80 s，分别在
  `0xb476f74` / `0xb476fc8` / `0xb477014` / `0xb477030` 之前）。一次开机把死法分成：panic / 同步异常 / 跑完滑动段 / 更深处 / 纯自旋。
- 新增工具能力：`scripts/patch-xnu-entry-probe.py --fault-fingerprint SHIFT:BITS:BASE:STEP`
  —— 把 `FAR_EL1`（出错地址）的指定位切片编码成复位延时（`FAR_SLICE_RESET` 模板，cave 0x5c 字节，已验证可生成）。
  用于异常分支：一次开机读出出错地址落在哪个 2–16 MB 区间，无需反复二分。

### 33.8 fi25 / fi26：从"测量"转为"跳过并继续"
- **fi25 = 10 秒**（14 站点、步长 10 s，首站在 `0xfffffff00b476fac`）：执行到达 `fac`，即 **`PE_set_kc_header` 成功返回**。
  已验证链条：入口 → 内联滑动段完整跑完 → `PE_set_kc_header` 返回 → 到达 `kernel_collection_adjust_mh_addrs` 调用点。
- **fi26（20:29:33 下发）**：`fac`(adjust_mh_addrs) 与 `fb4`(OSRuntimeSignStructorsInFileset) 两条 `bl` 直接改成 `nop`，
  从 `fc8` 起 10 个连续调用点做阶梯（步长 15 s，15..150 s），仍带 `--panic-reset 4` / `--fault-reset 8` 与 ADT `dram-size=0x300000000`。
  判读：4 s=跳过引发 panic；8 s=同步异常；15 s=越过两个调用到达 `static_if_init` 前；30..150 s=继续深入；不重启=跳过导致后续状态缺失。
- 反汇编复核：`ml_default_rop_pid` / `ml_default_jop_pid` 在本内核中为 `mov x0,#0; ret` 空桩，`cpu_data_init` 全为普通 store，
  均无 Apple 专有系统寄存器访问，不需要预防性打补丁。

### 33.9 fi28 结论：跳过不必要，回到干净内核
- **fi28 = 15 秒**（干净内核，无任何 nop，只在 `0xb476fe0` / `0xb477014` 放站点）：原版内核自己就能到达 `0xb476fe0`。
  ⇒ fi26/fi27 的三处 nop 全部撤销；fi25 的 10 s 只说明"到过 fac"，跳过从来不是必需的。
- 已验证可跑通的整段（干净内核、无 panic、无异常）：入口 → 内联滑动段 → `PE_set_kc_header` → `kernel_collection_adjust_mh_addrs`
  → `OSRuntimeSignStructorsInFileset` → `static_if_init` → `memcpy(const_boot_args)` 调用点 `0xb476fe0`。
- 反汇编排除了"Apple 专有寄存器陷阱"这条线（`bti; ret` 空桩）：`configure_misc_apple_boot_args`、`configure_misc_apple_regs`、
  `configure_timer_apple_regs`、`wfe_timeout_configure`、`wfe_timeout_init`、`ml_default_rop_pid`、`ml_default_jop_pid`。
  `ml_get_boot_cpu_number` 只是两次全局读。带实质逻辑的只剩 `ml_parse_cpu_topology`。
- **fi29**（20:38:10 下发）：干净内核 + 站点 `0xb477110`(15 s，`ml_parse_cpu_topology`/`ml_get_boot_cpu_number` 之后) 与
  `0xb4772fc`(30 s，`arm_init` 最后一个 bl)；`--panic-reset 4` / `--fault-reset 8`；ADT `dram-size=0x300000000`。

### 33.10 重大节点：fi30 到达 bl _arm_vm_init
- **fi30 = 15 秒** ⇒ 干净内核（仅 3 个基础补丁 + ADT dram-size 修正）到达 `0xb477370` 的 `bl _arm_vm_init`。
- 已验证连续跑通（无 panic、无异常）：入口 → 内联滑动段 → `PE_set_kc_header` → `kernel_collection_adjust_mh_addrs` → `OSRuntimeSignStructorsInFileset`
  → `static_if_init` → `memcpy` → `cpu_data_init` → `PE_init_platform` → `boot_progress_init` → `/chosen` DT 查找 → `ml_parse_cpu_topology`
  → `ml_get_boot_cpu_number` → `_thread_bootstrap`/`_cpu_bootstrap`/`_rtclock_early_init`/`_kernel_startup_bootstrap`/`_timer_call_init`/`_cpu_init`
  /`_processor_bootstrap` → `PE_parse_boot_argn`×4 / `PE_get_default` / `kern_feature_override`×2 / `nanoseconds_to_absolutetime` → `boot_progress_stage`
  → **`bl _arm_vm_init`**。整条早期路径跑完。
- fi26/fi27 的三处 nop 已证明不必要并全部撤销（fi28=15 s 原版即达 `fe0`）。
- `_arm_vm_init` 内部调用表已解出（237 个 bl），前段：`_phystokv`(0xad77bc0) / `_early_random`(0xad77bcc) / `_kvtophys`(0xad77c44)
  / `___bzero`(0xad77cd0) / `_getsegdatafromheader`×18 / `_PE_get_kc_header`(0xad780a0) / `_vm_set_page_size`(0xad782f8)
  / `_arm_vm_prot_init`(0xad783d8) / `_arm_vm_physmap_slide`(0xad78494) / `_qsort`(0xad78520) / `_set_mmu_ttb_alternate`(0xad7856c)
  / `_set_mmu_ttb`(0xad78580) / `_arm_auxkc_init`(0xad7862c)。
- **fi31**：站点 `0xad7862c`(15 s, `bl _arm_auxkc_init`) 与 `0xad78580`(30 s, `bl _set_mmu_ttb`)，用于判断 arm_vm_init 前段能走多深。

### 33.11 fi31/fi32：pmap_bootstrap 与 set_mmu_ttb 全部通过
- **fi31 = 30 秒** ⇒ 到达 `0xad78580` (`bl _set_mmu_ttb`)。注意两站点地址顺序：`0xad78580` < `0xad7862c`，阻塞式先命中前者，30 s 档才是 `set_mmu_ttb`。
- 已跑通：`_phystokv` / `_early_random`(被 patch) / `_kvtophys` / `___bzero`×4 / `_getsegdatafromheader`×18 / `_getsectdatafromheader`×2
  / `_PE_get_kc_header` / `_getlastkerneladdr` / `_vm_set_page_size` / `_arm_vm_prot_init` / `_arm_vm_physmap_slide`×2
  / `_arm_vm_page_granular_prot` / `_qsort` → **`_set_mmu_ttb`**。
- **fi32 = 15 秒** ⇒ 到达 `0xad78c0c` (`bl _patch_low_glo_static_region`)，即 `_set_mmu_ttb`、`_arm_auxkc_init`、
  4×`_arm_vm_page_granular_prot`、**`_pmap_bootstrap`**、`_disable_preemption`、`_pmap_init_pte_page`×2 全部返回。
  ⇒ **TTBR 已安装、内核 pmap 已起来**，`arm_vm_init` 主体跑完。
- **fi33**：单站点 `0xb477550` (`bl _machine_startup`, 15 s)。到达即表示 `arm_init` 完整返回，
  `_patch_low_glo` / `_serial_init` / `_kernel_startup_initialize_upto` / `_PE_init_platform`(2nd) / `_ml_map_cpu_pio` / `_early_random` 全部跑通。

### 33.12 panic 定位：kernel_startup_initialize_upto(STARTUP_SUB_KPRINTF)
- fi33 = **4 秒** ⇒ `panic()` 被调用。fi32 到达 `0xad78c0c`（arm_vm_init 尾部），fi33 未到 `0xb477550`。
- fi34 = **15 秒** ⇒ 到达 `0xb4773a4`（`_kernel_startup_initialize_upto` 调用点），未到 `0xb4774f4`。
  ⇒ panic 在 `kernel_startup_initialize_upto(w0=4)` 内部。
- 反汇编确认实参：`mov w0, #4` = `STARTUP_SUB_KPRINTF`（枚举 NONE=0, TUNABLES=1, TIMEOUTS=2, LOCKS=3, KPRINTF=4）。
  即该调用会执行全部 subsystem ≤ KPRINTF 的启动条目（TUNABLES/TIMEOUTS/LOCKS/KPRINTF），来源类 ~38 个不同函数、按 lock 声明实例化多次。
- 全内核 `bl _panic` 站点表：**3,166 条**（站点 VA / 格式串 VA / 所属符号 / 消息）→ `/tmp/panic_sites.txt`。
  与 sys≤KPRINTF 条目求交，自带 panic 的是 `PE_init_kprintf_config`("Platform Expert not initialized")、`ipc_sec_policy_configs_validate`、`stack_init`。
- **fi35**：单站点 `0xb4ef404`（`_PE_init_kprintf` 入口，KPRINTF 子系统第一条），15 s + panic-reset 4 s。
  4 s ⇒ panic 在 TUNABLES/TIMEOUTS/LOCKS 条目里；15 s ⇒ 已进 KPRINTF，panic 在 `PE_init_kprintf` 或其内部调用。

### 33.13 fi38/fi39：arm_init 收尾整段拆除 → 进入 kernel_bootstrap
- **修复动作（非探针）**：`scripts/patch-arm-init-tail.py` 把 `arm_init` 尾部 12 个 Apple 专有调用 nop 掉
  （switch_to_serial_console / PE_create_console / PE_init_printf / cpu_machine_idle_init / PE_init_platform(2nd) /
   pe_arm_debug_init_early / ml_map_cpu_pio / cpu_timebase_init / kptimer_curcpu_up / PE_init_cpu /
   apt_msg_init / apt_msg_init_cpu / fiq_context_init），`early_random` 改 `mov x0,xzr`。
- **fi38 = 15 s** ⇒ 越过整段，到达 `bl _machine_startup`。原 panic 卡点消失。
- **fi39 = 15 s** ⇒ 进入 `_kernel_bootstrap`（`0xfffffff00abb76b4`），`_machine_conf` 也通过。
- `machine_startup` 结构：`machine_conf()` → 尾调用 `kernel_bootstrap()`。
- `kernel_bootstrap` 步骤序列（每个 = boot_progress_stage + kprintf + 实际函数）：
  `_printf(version)` `_scale_setup` `_vm_mem_bootstrap` `_atm_init` `_kernel_startup_initialize_upto(OSLOG)`
  `_ubsan_minimal_init` `_trap_telemetry_init` `_console_init` `_stackshot_init` `_mac_policy_init`
  `_mapping_free_prime` `_machine_init` `_thread_machine_init_template` `_clock_init` `_thread_group_init` …

## 2026-11-11 夜间：panic 上屏通道与内存窗口（fi48–fi52b）

### 已验证（真机 + 产物）

| 事实 | 证据 |
|---|---|
| payload 内 ADT 的 `dram-size` 与 `darwinboot-memory-size` 原值都是 `0x10000000`（256 MB） | 从 `payload.img` 抽出 ADT，按 `DarwinBoot.c:273-372` 的 36 字节属性记录解析：`dram-size` 值 @0x218、`darwinboot-memory-size` 值 @0x244，均小端 u64 |
| DarwinBoot 把该窗口直接写进 `boot_args->MemorySize` | `sources/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c:750-751` |
| 文档早已记录“窗口 256 MiB、framebuffer 在窗口外、开 MMU 后写 FB 触发数据中止并双重故障” | `docs/bringup.md:260-310`；既有修法 `scripts/patch-fb-map.py` |
| `patch-fb-map.py` 的固定站点在当前 CI 内核里仍是 `mov x0, xzr`（`0xaa1f03e0`），cave 目标 `0xfffffff00b4fb000` 在原内核里全零 | 反汇编 + 逐字节比对 |
| `panic()` 钩子确实生效：fi51 刷入后屏幕无字但**约 20 秒自动重启**（该复位来自 `park()` 的倒计时） | 用户实测；`scripts/xnu-panic-screen.c` 的 `park_for()` |
| fi50 的 `Compromised Data` 由**大端写入**引起：`0x100000000` 落盘后被 `U64()` 按小端读成 `0x01000000`（16 MB），低于 `DarwinWindowSizeValid` 的 256 MB 下限 | `DarwinBoot.c:331-334`、`drmWindowSizeValid` 于 `WindowSize.h` |

### 新增/修改的工具

- `scripts/patch-adt-window.py`：只改原 ADT 里两个 u64（小端），不重建树（解析器要求 `Offset == TreeSize`，换树会被判 `EFI_COMPROMISED_DATA`）。
- `scripts/xnu-panic-screen.c`：`_vinfo` 为空时回退到 stage 2 存下的 `boot_args->Video` 六字段；**不做 physmap 换算**（`patch-fb-map.py` 把 FB 恒等映射到同一 VA）；`park_for()` 支持两档延时（8 s = 无可用帧缓冲，20 s = 已拿到帧缓冲）。

### 产物

| 镜像 | 内核 sha256 前缀 | 差异 |
|---|---|---|
| fi50 | 21f29faa | 4 GB 窗口 + 12 GB DRAM，**大端写错** → `Compromised Data` |
| fi51 | 21f29faa | 同上但小端正确；panic 屏含 physmap 换算 |
| fi52b | d0c14517 | 加 `patch-fb-map.py` + 恒等地址 + 两档 park |

### 待判读（fi52b，23:00:40 下发）

- 有文字 → panic 原文与 frames；
- 约 8 秒重启 → 渲染器拿不到帧缓冲几何；
- 约 20 秒重启 → 拿到帧缓冲但画面无字（行宽/宽度/清屏范围不符）。

## 2026-11-11 23:18 — panic 上屏成功，定位到真实崩溃点（fi58）

### 已验证（真机照片 + 反汇编 + 源码）

fi58 首次把 `panic()` 的原文与调用栈画到了真机屏幕上。屏幕内容：

```
PAC failure from kernel with IA key while branching to x9 at pc 0xfffffff00ad52664
  x9: 0x0    lr: 0x16b64ff00ad55e88   esr: 0x72000000
frames: 0b478394 ad7e5c0 0b478844 ad7d7e4 ad52664 ad55e88 ad55898
        0b44f808 0b45b07c abb773c 0b477554 0b4768f0
```

符号化（用本仓库的 kernel.macho 符号表 + 逐帧二分）：

| 帧 | 函数 |
|---|---|
| `0xfffffff00b4768f0` | `_arm_init` |
| `0xfffffff00b477554` | `_arm_init+0xc64` |
| `0xfffffff00abb773c` | `_kernel_bootstrap+0x88`（`bl _vm_mem_bootstrap` 的返回地址） |
| `0xfffffff00b45b07c` | `_vm_mem_bootstrap+0x3c` |
| `0xfffffff00b44f808` | `_zone_bootstrap+0xa0` |
| `0xfffffff00ad55898` | `_random_bool_init+0x90` |
| `0xfffffff00ad55e88` | `_read_erandom_generate+0x6c` |
| `0xfffffff00ad52664` | `_ccdrbg_generate+0x3c` ← 崩溃点 |

崩溃指令（`0xfffffff00ad52644..0xad52664`）：

```
ldr   x9, [x8, #0x18]!     ; 从 DRBG 结构 +0x18 取回调
blraa x9, x17              ; 带 PAC 的间接调用；x9 = 0
```

### 根因（源码级确定）

- `osfmk/prng/prng_random.c:289` `read_erandom_generate()` 直接用 `erandom.drbg_info` 调 `ccdrbg_generate`；
- `erandom.drbg_info` 只由 `early_random_init()` 里的 `ccdrbg_factory_nisthmac()` 填充，而 `early_random_init()` 只被 `early_random()` 惰性调用（`:267-280`）；
- 我们的 `scripts/patch-arm-init-tail.py` 曾把 `arm_init.c:685` 的 `bl _early_random` 换成 `mov x0, xzr`，于是 DRBG 从未初始化 → 回调为空 → PAC 失败。
- 另有前置条件：arm64 的 `BOOTLOADER_ENTROPY_REQUEST_SIZE = 4*SHA512_DIGEST_LENGTH = 256`（`:52-55`），`bootseed_init_bootloader()` 在拿不到 256 字节时 panic（`:65-79`），而 ADT 里 `random-seed` 原为 64 字节。

### 显存映射：为什么最终这样写（fi48–fi58 的教训）

| 做法 | 结果 |
|---|---|
| 靠 4 GB 窗口 + `gPhysBase/gVirtBase` 换算 | 失败：窗口基址在 `0x0DB0004000`，显存 `0xFC400000` 在其**下方**，`virt+(pa-phys)` 落出内核区（fi55 的 14 s） |
| `patch-fb-map.py` 改 V=P 表 `L1[3]`（池第 4/5 页） | 挂死：4 GB 窗口时池第 4/5 页正是窗口自己的 L2 表 |
| 自写 cave 改 V=P `L1[3]`（池第 15 页） | 仍挂死：显存地址落在 `dram-size` 覆盖的 DRAM 范围内，把它改成 Device 等于毁掉内核自己的内存 |
| **panic 现场建 TTBR1 `L1[1]` → `0xFFFFFFC040000000`**（fi58） | **成功画出整屏文字** |

fi58 的做法：`PE_state.video` 取几何（`pexpert/arm/pe_init.c:449`）→ `boot_args` 自带 `VirtualBase/PhysicalBase` 换算表地址 → `mrs ttbr1_el1` 取活根表 → 池第 15 页做 L2（stage 2 把其物理地址存进 `PANIC_TEXT+0xff8`）→ 填 64 个 2 MiB Device 块 → `tlbi vmalle1` → 画到 `0xFFFFFFC040000000`。TTBR1 索引 1 与内核镜像（索引 `0xC0`）相距 47 TiB，不改变任何 DRAM 语义。

### 新工具

- `scripts/patch-adt-randseed.py`：把 `/chosen/random-seed` 从 64 扩到 256 字节（`DarwinBoot.c:652` 的 `TreeSize` 就是文件大小，`:661` 只要求走查后 `Offset == TreeSize`，插入后自检通过：10712 字节，走查结束 `0x29d8`）。
  注意顺序：**先** `patch-adt-window.py`（固定偏移 0x218/0x244），**再** 插种子（插入点在 0x19c 之前的所有偏移都会移动）。
- `scripts/patch-arm-init-tail.py --keep-early-random`：保留 `bl _early_random`。

---

## 2026-11-12 23:45 — panic 通道三次翻车与修复（fi60–fi66）

### 本轮最重要的发现（已用反汇编 + 实机验证）

**1. `patch-arm-init-tail.py` nop 掉了 `_PE_init_platform`，而 `PE_state.video` 只有它填。**

被 nop 的 12 个调用及其目标（全部核对过）：

| 调用点 | 目标 |
|---|---|
| 0xb4774c0 | `_switch_to_serial_console` |
| 0xb4774d0 | `_PE_create_console` |
| 0xb4774d8 | `_PE_init_printf` |
| **0xb4774f4** | **`_PE_init_platform`** ← panic 屏几何的唯一来源 |
| 0xb4774fc | `_pe_arm_debug_init_early` |
| 0xb477510 | `_ml_map_cpu_pio` |
| 0xb477518 | `_cpu_timebase_init` |
| 0xb47751c | `_kptimer_curcpu_up` |
| 0xb477520 | `_PE_init_cpu` |
| 0xb477524 | `_apt_msg_init` |
| 0xb477528 | `_apt_msg_init_cpu` |
| 0xb477530 | `_fiq_context_init` |

后果：fi59–fi65 里所有"没看到 panic"的判读都不可靠——panic 可能一直发生，只是屏幕画不出来。
同时，放在 `_pe_arm_debug_init_early`/`_cpu_timebase_init`/`_PE_init_cpu`/`_fiq_context_init` 上的 beacon 全是死代码。
修法：`patch-arm-init-tail.py --keep-pe-init-platform`（fi65 起启用）。

**2. 三处自己引入的代码 bug，逐个修掉（每处都有反汇编证据）。**

| Bug | 后果 | 修复 |
|---|---|---|
| beacon stub `b site+4` 跳过 `pacibsp` | 函数返回时 `retab` 校验失败，内核直接崩（fi60/fi61 零输出） | stub 开头 `.inst` 重放首指令 |
| `fb_beacon` 的 `struct ctx g` 未初始化，而 `fb_setup` 首句 `if (g->base != 0) return 1` | 栈垃圾被当成"已映射"，用野指针写显存（fi62 黑屏重启） | 显式清零全部字段 |
| stub `sub sp,#0x60` 却存到 `[sp,#0x70]` | 溢出 0x18 字节写进调用者栈帧 | 栈改 `0xA0`，布局 16 字节对齐 |

**3. loader 屏幕上的真实内存布局（拍照确认，修正了此前错误记录）。**

```
va   = 0xFFFFFFF007004000
pa   = 0x8C0004000        ← 此前记录的 0xBB004000 是错的
args = 0x8C5A30000
window = 0x100000000 (4 GiB)，即 [0x8C0004000, 0x9C0004000)
video base = 0xFC400000  1440x3200  row 5760 bytes  32 bpp
```

显存 `0xFC400000`（3.9 GiB）确实远在窗口之外——这一点与旧结论一致。

### 实机结果

| 镜像 | 改动 | 结果 | 结论 |
|---|---|---|---|
| fi60/fi61 | 7 个 beacon | 零输出、不重启 | beacon stub 跳过 pacibsp |
| fi62 | 修 pacibsp + 加自检 | 几秒黑屏重启 | `ctx` 未初始化 |
| fi63 | 清 `ctx` | **10 秒**黑屏 | `msize` 误判 |
| fi64 | 去 `msize` + 修栈 + 传 boot_args | 一分钟不黑屏 | 映射写入未生效 |
| fi65 | 保留 `PE_init_platform` | **10 秒**黑屏 | virtu/phys 两条来源都为空 |
| fi66 | panic 屏改用池 KVA 常量，彻底不换算 | 待验证 | — |

### 修复要点：不再做 virt/phys 换算

trampoline 的 16 页池 KVA 固定（反汇编确认 `adrp x25, #0xFFFFFFF00C8B4000`）：
池第 1 页 = TTBR1 根表 `0xFFFFFFF00C8B5000`，第 15 页 = 我们的 L2 `0xFFFFFFF00C8BF000`。
`read_ttbr1()` 拿到根表物理后，L2 的物理就是 `root_pa + 0xE000`，两个 KVA 直接是常量。
**`_arm_init` 阶段 `PE_state.bootArgs` 必然为空、stage 2 的 stash 也没带上基址，所以任何换算都注定失败。**

### 改动文件

- `scripts/xnu-panic-screen.c`：`fb_setup(g, fatal, ba_hint)`，换算改为可选，缺省用池常量；`fb_beacon` 清零 ctx。
- `scripts/patch-beacons.py`：stub 重放 `pacibsp`/`bti`、栈 0xA0、传调用者 x0。
- `scripts/patch-arm-init-tail.py`：新增 `--keep-pe-init-platform`。
- `docs/agent-progress.md`：本文件，顶部加入用户第一轮规定原文。

### 下一步

fi66 实机判读：`CK 01` 出现 = 通道终于打通；12/14 秒 = 池常量路径也不对，改用 stage 1 在开 MMU 前把轨迹写进 DRAM 并下次启动画出的方案。

---

## 2026-11-13 01:30 — 显存通道的最终结论（fi60–fi72）

### 一句话结论

**这个 SoC 上，EL1 内核写不了显存 `0xFC400000`。** 映射存在、写入不 fault、cache 也 clean 过，写进去的数据就是不出现在屏幕上。只有 UEFI 固件和 MMU 关闭前的 trampoline 能写。所以内核侧任何"自建映射让 panic 屏显示"的方案都不可能成功——不是实现 bug，是硬件层面的显示孔径保护。

### 证据链（每条都可核）

| 版本 | 做法 | 实机结果 | 说明 |
|---|---|---|---|
| fi68 | 恢复 `PE_create_console`/`PE_init_printf`/`ml_map_cpu_pio` | 屏幕无变化 | console 初始化没执行到 |
| fi69 | `patch-fb-map-ttbr1.py`：TTBR1 L1[1] → 池页4 的 L2 | 10 秒黑屏重启 | L1 索引算错（见下），写入未生效 |
| fi70 | `FB_KVA = 0xFC400000`（物理地址直写，走 V=P 表） | 不崩、不重启、无画面 | **关键实验**：映射存在，写入被丢弃 |
| fi71 | fi70 + `clean_to_memory()`（`dc civac` + `dsb`） | 仍无画面 | 排除 cache 一致性 |
| fi72 | beacon 写内核 BSS，trampoline 下次启动读槽画带 | 待判读 | 绕开内核写显存这条死路 |

fi70 的"什么都不发生"是决定性证据：如果 `0xFC400000` 未映射，写入会 data abort → 看门狗复位；如果只是 cache 问题，fi71 的 flush 会让它出现。两者都排除后只剩硬件丢弃。

### 顺带纠正的三个错误假设（全部有反汇编证据）

1. **池基址不是 `0xFFFFFFF00C8B4000`**。`_arm_vm_init` 里 `adrp x25, #0xfffffff00c8b3000`（`0xfffffff00ad77c74`），所以池基址 `0xFFFFFFF00C8B3000`，页 1 = `0xC8B4000`、页 4 = `0xC8B7000`、页 15 = `0xC8C2000`。之前所有基于 `0xC8B4000` 的页号推算全部偏移了 `0x1000`。
2. **TTBR1 的 L1 索引不是 1**。`0xFFFFFFC040000000` 这类 VA 的 bits[47:39] 全是 1 → L1 index = 511；内核镜像 `0xFFFFFFF007004000` 自己也在 index 511。`root[1]` 指向 `0xFFFF008000000000`，和显存毫无关系。
3. **`MMU_ENABLE_VA` 常量 `0xFFFFFFF00B9D2330` 是错的**（那里是字符串数据 `0x635f1210`）。文件里 `msr sctlr_el1, x0` 唯一出现在 `0xFFFFFFF00AD83418`。不过 `patch-xnu-entry-probe.py` 运行时会按 `0xD5181000 / 0xD5033FDF / 0xD2A00600 / 0xD5181040` 四条指令序列在 `_start_first_cpu` 后 0x1000 范围内动态搜索，搜到的正是 `0xAD83418`，所以实际 stage 2/stash 一直是好的——常量只在动态搜索失败时才有害。

### 上游代码给出的正确做法（此前一直在自造轮子）

- `UniXNU/scripts/xnu-panic-screen.c` **不做任何 L1/L2 自建映射**，注释写明 "With the board observer it uses the retained GOP mapping prefix; otherwise it uses vinfo.v_baseaddr"。
- `uefi-sheng/DarwinBootPkg/Driver/Entry.S` 的 `DarwinEnter(x0=args, x1=entry, x2=owned, x3=size, x4=fb, x5=size)` 只做三件事：画绿带、`dc civac` 刷内核镜像、**关 MMU**、`br x1`。它不建立显存映射，`VideoBase` 只是填进 boot_args 的数值。
- 所以"内核里 v_baseaddr 直接可用"的前提在这块板子上不成立。

### 新增/修改的工具

- `scripts/patch-slot-bands.py`：在 MAIR 站点（`0xAD832C8`，MMU 关闭、物理地址可直接寻址）注入 108 字节 cave，读 `_boot_progress_panic_text + 0x800` 的物理地址（`0x8C46DC490`，由符号 + loader 的 va/pa 在构建时算出）并画 9 条带：band 0 白色=读出代码跑了，band 1..8 = tag 的 bit0..bit7。
- `scripts/xnu-panic-screen.c` 的 `fb_beacon` 改为把 tag 写进 `PANIC_TEXT + 0x800` 并 `dc civac` 刷到内存，不再碰显存。
- `scripts/patch-fb-map-ttbr1.py`：TTBR1 版本的显存映射尝试，fi69 证明无效，保留供参考但不要使用。
- 构建时必须 `export UNIXNU_UEFI=/home/yoox/android/sources/uefi-sheng`，否则 `--panic-screen` 找不到 `Font.h` 而静默失败（`patch-xnu-entry-probe.py:522`，脚本只认环境变量，不认 `--uefi` 参数）。

### 判读表（fi72 起）

| 屏幕 | 含义 |
|---|---|
| 顶部若干白/黑相间的细带 | 槽通道成功；数白色带子（band 1..8）读出 tag。`0x101` → bit0 和 bit8 置位，但 bit8 不进 band，所以 band1 白、band2..8 黑 |
| 完全无带子 | trampoline 的 cave 没跑到，或槽地址算错 |
| 仍然只是原来的绿带+蓝带 | cave 未执行 |

### 下一步

fi72 需要**两次启动**才有读数：第一次让内核写槽（会静默挂死），第二次由 trampoline 把它画出来。如果第一次的槽没保留（`fastboot boot` 走完整 bootloader，DRAM 可能被重新初始化），就必须改成同一次启动内可读的通道——候选是把 tag 写进 UEFI 变量区或让 trampoline 自己在跑完后立刻画（只能报"上次"的值）。

### fi72 细节（凌晨补记）

构建：`artifacts/UniXNU-shennong/boot/Mu-shennong-fi72.img`，`verify: ok`，payload 内核 `978ebdecbea8aadc`。

组成：
- `--panic-screen`（0xbc7 字节）+ `--stash-fb` 未启用（不再需要 stash 几何来自建映射）
- `patch-beacons.py --beacon _arm_init:0x101` → `fb_beacon` 把 tag 写进 `PANIC_TEXT+0x800`
- `patch-slot-bands.py` → 在 `0xAD832C8`（MAIR，MMU 关）注入 108 字节 cave，读槽画 9 条带
- `patch-arm-init-tail.py --keep-early-random --keep-pe-init-platform`（nop 11 个）
- `PE_state` 几何、kalloc 修复、ADT 12GB/4GiB + 256 字节种子

`fb_beacon` 写槽后 `dc civac` + `dsb sy`；`panic_screen_main` 在碰显存**之前**也写槽（0xFF），所以内核 panic 与静默挂死可以区分。

反汇编验证过 cave 的槽地址构造（`movz/movk` 得 `0x8C46DC490`）、band 0 恒白、band n 取 bit(n-1)——第一版写成了 `lsr x14, #1`，取到的是 bit2/bit1 而不是 bit0..7，已修。

### fi72 判读（需要两次启动）

第一次刷入 → 内核写槽（大概率静默挂死）→ 第二次刷同一镜像 → trampoline 在 MMU 关时读槽画带。

| 顶部可见 | 含义 |
|---|---|
| band 0 白 + band 1..8 全黑 | 通道工作，槽 = 0（DRAM 未保留，`fastboot boot` 冷启动清空了） |
| band 0 白 + band 1 白，其余黑 | 槽 = 0x101：`_arm_init` beacon 跑到了，之后无 panic |
| band 0 白 + band 1..8 全白 | 槽 = 0xFF：**内核 panic 了**（此前所有"静默挂死"可能都是这个） |
| 完全没有带子 | trampoline cave 未执行，或槽地址算错 |

### 下一步（fi73 方向）

若 fi72 证明通道可用，接下来的实质修复方向不再是显示，而是让内核往前走：
`patch-arm-init-tail.py` 现在 nop 掉 11 个调用，其中 `cpu_timebase_init`、`kptimer_curcpu_up`、`PE_init_cpu`、`fiq_context_init` 属于时间基准/CPU 初始化，缺失会导致任何依赖定时器的等待变成死循环——这是"静默挂死"最可能的成因。恢复顺序建议一次一个：先 `cpu_timebase_init` + `kptimer_curcpu_up`，观察是"更靠后"还是"崩"。

### fi73：静默挂死的成因修复（已构建，待验证）

`patch-arm-init-tail.py` 的 11 个 nop 里，有三个属于**时间系统**，而它们正是"不触发 panic 的静默挂死"最合理的解释：没有 `_cpu_timebase_init`，`mach_absolute_time()` 恒为 0，任何 `while (now < deadline)` 都会变成死循环——不 panic、不复位、屏幕不再变化，与观察到的现象完全一致。

反汇编确认这三个都是**通用内核代码**，没有一条 `msr` 触碰 Apple 专有寄存器，所以不会因为"非 Apple 硬件"立即崩：

- `_ml_map_cpu_pio`（`0xAD86B70`）：CPU 私有寄存器映射
- `_cpu_timebase_init`（`0xAD73710`，248 字节）：先 `bl _current_act` 取 act，再读 `[x20,#0x88]` 等字段
- `_kptimer_curcpu_up`（`0xAD448F4`，304 字节）：读全局 `0xB782B70`，`bl _current_processor`

fi73 = fi72 + 恢复这三个（`--keep=pio,timebase,kptimer`，nop 数从 11 降到 8）。`PE_init_cpu`、`fiq_context_init` 仍为 nop，保持一次只动一组变量。镜像：`artifacts/UniXNU-shennong/boot/Mu-shennong-fi73.img`，`verify: ok`。

### 用户操作流程（fi72 通道验证）

槽通道需要两次启动：第一次让内核写槽，第二次由 trampoline 读出来画。

1. 开机进 fastboot（音量下 + 电源），监听器会自动 `fastboot boot` fi72；
2. 内核跑完会停在菜单或静默挂死，长按电源重启，再进一次 fastboot；
3. 第二次 `fastboot boot` 同一镜像后，**屏幕顶部 180 行内会出现 9 条横向色带**；
4. 按上面的判读表读出 tag，就能知道这是"panic"还是"挂在 _arm_init 之后"。

手动命令：

```bash
cd /home/yoox/android/workspace/UniXNU-shennong
fastboot boot /home/yoox/android/artifacts/UniXNU-shennong/boot/Mu-shennong-fi72.img
```

## 2026-11-13 — panic 屏画不出的真正原因（fi76–fi77），以及外部同类项目的交叉验证

### 结论先行

1. **`fb_setup` 读错了结构体。** panic 屏一直从 STASH（`_boot_progress_panic_text + 0x800`）里取 `boot_args->Video` 的值当指针用，那是**物理地址 `0xFC400000`**；内核页表里没有这个 VA 的映射，写入落空。**这是 fi59–fi75 十七个版本全部“屏幕上什么都没有”的原因。**
2. **正确来源是内核自己的 vinfo。** 反汇编 fi58（唯一验证过能画屏的版本）得到：基址 `0xFFFFFFF00B782000`，字段 `+0x350 v_height / +0x354 v_width / +0x358 v_depth / +0x35C v_rowBytes / +0x360 v_baseaddr`，`v_baseaddr` 是**内核已映射好的虚拟地址**。fi76/fi77 已按此重写 `fb_setup`。
3. **uke 项目独立踩过同一个坑**，见 `UniXNU/docs/devices/uke.md` 所引 PROGRESS.md：
   > `PE_current_console returns physical PE_state.video, while mapped framebuffer is video_console vinfo.`
   两个项目、两条独立路线得出同一结论，可信度高。
4. **`--stash-fb` 才注入 stage 蓝带 cave。** `patch-xnu-entry-probe.py` 里 `CAVES` 只在 `args.stash_fb` 分支被 `branch()` 写入；`--panic-screen` 只注入 panic 屏本身。**fi76 没传 `--stash-fb`，所以“蓝带消失”是正常现象，不是内核没启动。** fi77 = fi76 + `--stash-fb`。

### 证据

| 主张 | 证据 |
|---|---|
| fi58 从 vinfo 读几何并直接用 `v_baseaddr` 当 VA | fi58 `kernel.macho` 反汇编 `0xB4F722C` 起：`movk x13,#0xb78,lsl#16` … `ldr x12,[x13,#0x360]`、`ldr w11,[#0x35c]`、`ldr w10,[#0x354]`、`ldr w9,[#0x350]` |
| fi58 的 panic 屏带定时复位 | 同段 `mrs x9,cntpct_el0` 循环 + `mov w0,#9; smc #0`（PSCI SYSTEM_RESET） |
| fi58 与 fi73 的差异集中在 panic blob 与 arm_init 尾部 | 逐字节比对 94,552,064 B，586 个差异区间；`0x44F2EEC–0x44F3027` = panic blob，`0x44728F0/0x44734F4…` = `_arm_init` |
| `_machine_startup` 未被 nop | fi77 `0xB477550: bl _machine_startup`；`0xB477534: bl _early_random`；`0xB47751C: bl _kptimer` 均保留 |
| `--zero-physmap-slide` 与 `--keep-early-random` 不冲突 | 前者改 `_arm_vm_init` 内的 `bl _early_random`（算 physmap slide），后者针对 `_arm_init` 尾部的调用；两个不同调用点 |

### 外部同类项目（联网查证，2026-11-13）

- **[ios-topaz / ios-sweet](https://github.com/MakrSas/ios-topaz)**：Redmi Note 12 4G（SM6225）跑 **iOS 16.7.16 真实 iPhone X 用户态**，主屏/设置/控制中心/触摸/音量键可用，已移植多机型。**它选 iPhone X 是因为那是最后一款无 PAC 的机型**；SM6225 是 Cortex-A73（ARMv8.0，无 PAC）。内核在 **GitHub macOS runner 上编译，约 8 分钟**。
- **[Snapintosh](https://raw.githubusercontent.com/Snapintosh/Snapintosh/refs/heads/main/docs/BOOT-CHAIN.md)**：骁龙 X2 Elite 上启动原生 XNU。**在 EL2 写 monitor 代替 SPTM/TXM**；文档明确 `856 字节 SPTM 引导结构首四字必须是 magic 0xd00f…，值错了会 spins forever`——与我们的“静默挂死”现象同型。
- **[HackiOS](https://gigazine.net/gsc_news/en/20261023-hackios)**（OOSEX GANG）、j0sh1x 的 HTC HD2 iOS 7。

### SPTM 是否为本项目障碍：不是

- 本内核确有 `__DATA_SPTM` 段与 `sptm_init` 等符号（`strings` 实证），但 **UniXNU 有 `patches/xnu-12377/public-pmap-without-monitor.patch`**，配合 `XNU_MONITOR=0` 走“无 monitor”的 pmap 路径；`CONFIG_SPTM` 在 `native-4k-shared-region-slide.patch` 中作条件编译出现。
- 结论：**不需照 Snapintosh 那样实现 SPTM monitor**。此前“SPTM 导致挂死”的推断作废。

### 待办 / 下一步

- 观察 fi77（panic 屏修好 + stage 蓝带 + 避开 PAC 崩溃）的真机画面。
- uke 的 `cluster-type` 是 **CPU0..2 = E、CPU3..7 = P（8 个字段）**；本项目 ADT 只有 cpu0，目前只给 cpu0 加了 `E`。若 fi77 能画出 panic 且报 AMP/`cluster-type` 相关，则补齐 cpu1..cpu7 节点与字段。
- `scripts/make-shennong-adt.py` 才是 ADT 的正规来源（CI 用板级 ADT 覆盖 payload 的 ADT）；`cluster-type` 应写进该脚本，而不是继续用 `patch-adt-cluster.py` 打二进制。
- 仓库 CI（`.github/workflows/kernel.yml`，macos-26，`workflow_dispatch`）可用；github.com 与 api.github.com 均可达（HTTP 200）。用户已授权 `git commit/push`。

## 2026-11-13 — 入口细粒度打点：两次自伤与修正（fi79–fi81）

### 结论

给 `_start_first_cpu` 加检查点这件事，前两版都栽在**我自己选的执行环境假设**上，不是内核的问题：

| 版本 | 现象 | 真正原因 |
|---|---|---|
| fi79 | 只有蓝带，无红带 | 插桩用 `stp x0,x1,[sp,#-16]!` 保存寄存器，但 `_start_first_cpu` 在 `0xad830c0` 设的 sp 是**高 VA**，只有 MMU 打开后才有效；MMU 还关着，插桩第一条指令自己就触发访存异常 |
| fi80 | 连蓝带都没有，10 秒看门狗复位 | cave 地址 `0xFFFFFFF00B4F8000` **不是空闲区**，pristine 内核那里是真实函数（首条 `0xD503237F` = `pacibsp`），7424 字节里 5255 个非零字节；8 段 cave 把活代码覆盖了，内核一进函数就崩 |
| fi81 | 待测 | cave 移到 `0xFFFFFFF00B4F7A50`（panic 屏 `0xb4f6ee8+0xb5f=0xb4f7a47` 之后到 `0xb4f8000` 之间的 1456 字节，已验证全零），stride `0xB4`，8 段共 1440 字节 |

### 两条硬约束（以后所有 cave 都必须遵守）

1. **MMU 关闭时的代码不能用 sp 做暂存。** `_start_first_cpu` 里 sp 指向的地址是给开了 MMU 之后用的。改用 `x16`（IP0，整段 239 条指令里未使用）指向 cave 内部缓冲区，`adrp x16, scratch; add x16, x16, :lo12:scratch`，MMU 关闭时按物理 PC 计算照样指向正确位置。
2. **cave 地址必须先验证全零。** `scripts/patch-entry-bands.py` 现在会在写入前检查整个 cave 窗口，非零直接 `SystemExit`，不会静默覆盖。

### 检查点表（band = 屏幕段号，每段 1/16 屏高）

| band | 站点 VA | 颜色 | 含义 |
|---|---|---|---|
| 3 | `0xad830d4` | 红 | 两个栈设置完成 |
| 4 | `0xad83128` | 绿 | Mach-O 头检查通过（`flags=0x80218001` bit31=1，首条 load command `cmd=0x19` = `LC_SEGMENT_64`，已验证通过） |
| 5 | `0xad83290` | 青 | L1/L2 页表建完 |
| 6 | `0xad832a8` | 品红 | 即将写 `TCR_EL1` |
| 7 | `0xad8330c` | 黄 | 即将写 `MAIR_EL1` |
| 8 | `0xad83318` | 橙 | `TLBI`/`ic` 完成 |
| 9 | `0xad833c4` | 紫 | 五组 PAC key 生成完 |
| 10 | `0xad83404` | 白 | PAC key 全部写入、`ISB` 完成 |

另有 stage 1（band 1，蓝，入口）和 stage 2（band 2，品红，`msr sctlr_el1`）。

### 已排除的嫌疑（静态证据）

- **Mach-O 头检查死循环** `0xad83108`（`b.ne` 自跳）：读 `0xFFFFFFF007184000` 得 `flags=0x80218001`、`[+0x20]=0x19`，检查通过。
- **页表越界死循环** `0xad8328c`（`b` 自跳）：按 window 4 GiB 算需 2048 个 2 MiB 项，第一轮 509 项、之后每轮 512 项共 5 轮，用到 `x25+0x6000`，上限是 `x25+0x10000`。
- **`SCTLR_EL1` 目标值 `0xFC54793D`**：高 6 位 `0xFC` 是 Apple 的 PAC key 使能位（对应 `native-pac-arm64-user-jop.patch` 里的 `SCTLR_PAC_KEYS_ENABLED`），loader 跳进来时是 `0x30D0198D`。若 fi81 显示白带在、品红带不在，这就是首要嫌疑；修复指令编码已备好：`0xad83410: 0xf2bf8a80 → 0xf2a61a00`（`movk x0,#0x30d0,lsl16`）、`0xad83414: 0xf28f27a0 → 0xf28331a0`（`movk x0,#0x198d`）。

## 2026-11-13 晚 — 入口打点的三次自伤与最终定位（fi79–fi85）

### 结论先行

`_start_first_cpu` 的执行范围已经从"整个内核"压缩到 **`0xad8312c`–`0xad831d4` 这 40 条指令**（页表构建循环的前半段）。这是本项目第一次用实测数据把死点确定到几十条指令内。

### 实机色带证据链

| 版本 | 屏幕上的带（从上到下） | 推论 |
|---|---|---|
| fi77 | 蓝 | 内核入口可达 |
| fi78 | 无蓝，10 s 黑屏 | 未查明（与 fi80 不同因） |
| fi79 | 蓝 | stage 1 正常；其余检查点因 sp 未映射而自伤 |
| fi80 | 无蓝，10 s 黑屏 | **我的 cave 覆盖了真实函数** |
| fi81 | 绿(loader)+蓝+红+绿 | 执行到 `0xad83128`（Mach-O 检查通过） |
| fi82 | 绿+蓝+红+绿 | 同上；band 5（`0xad831d4`）未出现 → 死点在 40 条内 |
| fi83 | 只有绿 | **cave 落在 `__DATA_SPTM`（RW-，NX）**，执行即异常 |
| fi84 | 待测（未刷） | cave 移到 `__TEXT_EXEC` 的 `0xb4f9688`（10616 B 零区） |
| fi85 | 待测（未刷） | fi84 内核 + ADT 修正（见下） |

### 我自己造成的三个 bug（全部已修）

1. **fi79**：插桩用 `stp x0,x1,[sp,#-16]!` 保存寄存器，但 `_start_first_cpu` 在 `0xad830c0` 设的 sp 是**高 VA**，只有 MMU 打开后才有效。MMU 还关着，插桩第一条指令自己就触发访存异常。→ 改用 `x16` 指向 cave 内部缓冲区。
2. **fi80**：cave 地址 `0xFFFFFFF00B4F8000` **不是空闲区**，pristine 内核那里是真实函数（首条 `0xD503237F` = `pacibsp`），7424 字节里 5255 个非零字节。8 段 cave 把活代码覆盖了。→ cave 区必须先验证全零，`patch-entry-bands.py` 现在会强制自检。
3. **fi83**：cave 搬到 `0xFFFFFFF0083E8000`，那是 `__DATA_SPTM` 段，`initprot=3`（**RW-，不可执行**）。代码放进去必然异常。→ 只能在 `__TEXT_EXEC`（`initprot=5`，R-X）里选 cave。

### 段属性表（cave 选址的硬约束）

| 段 | VA 起 | vsize | initprot | 权限 | 能否放 cave |
|---|---|---|---|---|---|
| `__TEXT` | `0x7004000` | `0x8000` | 1 | R-- | 否 |
| `__PRELINK_TEXT` | `0x700c000` | `0xdc4000` | 1 | R-- | 否 |
| `__DATA_CONST` | `0x7dd0000` | `0x618000` | 1 | R-- | 否 |
| `__DATA_SPTM` | `0x83e8000` | `0x4c000` | 3 | RW-（NX） | 否 |
| **`__TEXT_EXEC`** | `0x8434000` | `0x30c8000` | 5 | **R-X** | **是** |
| `__PRELINK_INFO` | `0xc620000` | `0x27c000` | 3 | RW-（NX） | 否 |
| `__DATA` | `0xb6b0000` | `0x2f0000` | 3 | RW-（NX） | 否 |
| `__LINKEDIT` | `0xb9a0000` | `0xc80000` | 1 | R-- | 否 |
| `__KLDDATA` | `0xc89c000` | `0xc0000` | 3 | RW-（NX） | 否 |
| `__BOOTDATA` | `0xc95c000` | `0xd4000` | 3 | RW-（NX） | 否 |

`__TEXT_EXEC` 里可用的零区（≥ `0x748` B）：

| VA | 长度 | 备注 |
|---|---|---|
| `0xb4f9688` | `0x2978` | **fi84/fi85 使用**，历史上探针用过 `0xb4f9700` |
| `0xb4f6ee4` | `0x111c` | panic 屏占用 `0xb4f6ee8`+`0xb5f` |
| `0xad80090` | `0xf71` | |
| `0xad8148c` | `0xb77` | stage 1 cave 占用 |
| `0xad82784` | `0x87c` | |

### 页表构建循环的完整反汇编（`0xad83128`–`0xad831d4`）

```asm
0xad83128: sub  x24, x24, x18        ; x24 = memSize - delta
0xad8312c: add  x22, x22, x18
0xad83130: add  x23, x23, x18
0xad83134: mov  x4, x0               ; x4 = virtBase
0xad83138: mov  x14, x22
0xad8313c: mov  x15, x23
0xad83140: mov  x1, x25              ; x1 = 页表区基址
0xad83144: add  x3, x1, #1, lsl #12  ; x3 = L2 表起点
0xad83148: mov  x2, x3
0xad8314c: lsr  x5, x24, #0x15       ; x5 = memSize >> 21（2 MiB 页数）
0xad83150: and  x6, x0, #0x3fe00000
0xad83154: lsr  x6, x6, #0x15        ; x6 = L1 索引
0xad83158: mov  x10, #0x200
0xad8315c: sub  x6, x10, x6          ; x6 = 512 - 索引
0xad83160: add  x2, x2, #0x1000      ; 下一个 L2 页
0xad83164: add  x10, x25, #0x10000   ; 页表区上限（16 页）
0xad83168: cmp  x2, x10
0xad8316c: b.hs 0xad8328c            ; 越界 → 死循环
0xad83170: and  x10, x0, #0x3fffffffff
0xad83174: lsr  x10, x10, #0x1e
0xad83178: lsl  x10, x10, #3
0xad8317c: add  x10, x1, x10
0xad83180: mov  x11, #3
0xad83184: and  x12, x2, #0xfffffffff000
0xad83188: orr  x12, x11, x12
0xad8318c: str  x12, [x10]           ; 写 L1 表项
0xad83190: cmp  x5, x6
0xad83194: csel x6, x5, x6, lt
0xad83198: and  x10, x0, #0x3fe00000
0xad8319c: lsr  x10, x10, #0x15
0xad831a0: lsl  x10, x10, #3
0xad831a4: add  x10, x2, x10
0xad831a8: mov  x11, #0x601
0xad831ac: orr  x11, x11, #0x40000000000000
0xad831b0: and  x12, x4, #0xffffffe00000
0xad831b4: orr  x12, x11, x12
0xad831b8: mov  x11, x6
0xad831bc: mov  x13, #0x200000
0xad831c0: str  x12, [x10], #8       ; 写 L2 表项（内层循环）
0xad831c4: add  x12, x12, x13
0xad831c8: subs x11, x11, #1
0xad831cc: b.ne 0xad831c0
0xad831d0: subs x5, x5, x6           ; band 5 站点
0xad831d4: b.eq 0xad831ec
```

### 已排除的静态嫌疑

- **页表越界**：memSize = window = 4 GiB → `x5 = 0x800 = 2048` 项；第一轮 `x6 = 512 - 384 = 128`，之后每轮 512，共 5 轮，用到 `x25+0x6000 < x25+0x10000`，**不会触发 `0xad8328c`**。
- **两条 `str` 的地址**：`x10 = x25 = 0x8C58B4000`（L1）与 `x2 + 0xC00 = 0x8C58B6C00`（L2），均落在 12 GiB DRAM（`0x8C0000000`–`0x8F0000000`）内，且 `x25` 所在 `__KLDDATA` 是 `RW-` 可写。
- **TCR_EL1 目标值** `0x00080022A51A251A`：T0SZ=26、T1SZ=26、TG0/TG1=4 KiB、**IPS=0b010 = 40 位 PA（1 TB）**，35 GB 的 DRAM 在范围内。
- **`0xad832b4` 的 `bl`**：目标是 `set_ttbr0`（`dsb ish; msr ttbr0_el1, x0; isb; ret`），只影响 TTBR0，不影响 EL1 取指。
- **`0xad83290` 的 `dsb ish`**：不是分支，可作插桩点（此前误判为 `b`）。

### 发现但尚未验证的配置错误

`build/*/adt-src-*.adt` 里：

| 字段 | 值 | 问题 |
|---|---|---|
| `dram-base` | `0x80000000`（2 GB） | 内核实际加载在 `0x8C0004000`（35 GB），**差 33 GB**；该值抄自 iPhone16,1 的 ADT |
| `dram-size` | `0x300000000`（12 GB） | 与设备相符 |
| `darwinboot-memory-size` | 原 `0x100000000`（4 GB） | 4 GB window 从 `0x8C0004000` 延伸到 `0x9C0004000`，**越过 12 GB DRAM 末尾 `0x8F0000000`** |

fi85 已按 `dram-base = 0x8C0000000`、`window = 0x80000000`（2 GB，覆盖 framebuffer 的 1.09 GiB 偏移且不越界）重建，`verify: ok`，尚未上机验证。

### 工程改进（已落地）

- `scripts/patch-entry-bands.py`：写入前强制校验整个 cave 窗口在 pristine 内核里全零，非零直接 `SystemExit`；允许在 `0xad8328c` 的 `b .` 死循环上插桩。
- `scripts/patch-adt-window.py`：新增 `--dram-base`，可同时修正 `dram-base`、`dram-size`、`window` 三个字段，写入前校验记录名与长度。

## 2026-11-14 凌晨 — 日志通道打通，卡点从"黑盒"变成"可见"（fi89–fi102）

### 结论先行
fi101 **第一次让 XNU 把自己打的 panic 显示到屏幕上**。此前五天所有"静默挂死"中的一部分，
其实是内核在 panic，只是没有 console 所以看不见。日志通道建立后，卡点从不可观测变成可读。

### 已验证事实（真机照片 + 构建产物）
| 版本 | 色带 | panic 文字 | 说明 |
|---|---|---|---|
| fi92 | 16 条（band 0–15） | 无 | MMU 开启成功，之后无输出 |
| fi93 | 1 条（仅 handoff 绿） | 无 | cave 放在 post-MMU 站点导致全灭 |
| fi94/95 | 13 条（band 0–12） | 无 | arm_init 检查点不出现 |
| fi96 | 1 条 | 无 | 删掉 x30 的 virtBase−physBase 修正 → 栈与入口不一致 → 全灭 |
| fi98 | 16 条 | 无 | x30 硬编码 0xFFFFFFF00B4768F0，与 fi92 齐平 |
| fi99 | 1 条 | 无 | 检查点放在 pacibsp 之后 → PAC 验签失败 |
| fi100 | 13 条 | 无 | 站点位移误伤 cave 池 |
| **fi101** | **16 条** | **有（Invalid kernel stack pointer）** | **console 打通** |
| fi102 | 16 条 | 无 | 去掉 SP 的 virtBase−physBase 修正后 panic 消失 |

### fi101 的 panic 原文（真机照片，02:52）
```
Invalid kernel stack pointer (probable corruption or early boot)
  at pc 0xFFFFFFF00B3A154C, lr 0xFFFFFFF00B4774DC
  saved state: 0xFFFFFFF00CA27CB0
  sp: 0xFFFFFFF00CA1FF30     fp: 0xFFFFFFF00CA1FFF0
  esr: 0x000000009600004F    far: 0xFFFFFFF00C950F38
  frames FFFFFFFF00B478394 FFFFFFFF00AD7FD14 FFFFFFFF00AD7D950 FFFFFFFF00B4774DC
```

**判读依据**：`lr = 0xFFFFFFF00B4774DC` 正是 `bl _PE_init_printf`（`0xb4774d8`）的返回地址，
证明内核**已经执行进 `arm_init` 并跑到尾部 console 初始化**。`pc = 0xb3a154c` 在
`_PE_init_printf` 内部。所以 arm_init 早就在跑，先前"进不去 arm_init"的判断是错的——
只是没有屏幕输出。

### 关键技术发现
1. **`_start_first_cpu` 里 SP 与返回地址共用同一个换算**：`0xad83094` 的 `adrp x0,#0xca28000`
   `+virtBase −physBase` 与 `0xad830c4` 的 `adrp x30,#0xb476000 +0x8f0 +virtBase −physBase`
   完全同构。删掉修正会让栈和入口同时偏移，二者仍不一致于内核期望值 → fi96 全灭。
2. **`pacibsp` 之后的函数体不能插入跳转型 cave**：PAC 用 SP 绑定，在函数中途跳走再回来，
   `retabsp` 验签失败 → `brk` → 看起来像"完全没启动"（fi99）。`_start_first_cpu` 开头没有
   PAC 序言，所以在它后半段（`0xad8341c`/`0xad8343c`）插桩是安全的。
3. **console 恢复方法**：`patch-arm-init-tail.py` 的 `KEEP_NAMES` 支持 `serial`/`console`/`printf`。
   把它们还原（`0xb4774c0`/`0xb4774d0`/`0xb4774d8` 的 nop → 原始 `bl`），Mu-Silicium 的
   `FrameBufferSerialPortLib` 就会把内核 printf 画到 framebuffer。

### fi102 的判读与悬而未决
fi102 把 SP 的 `+virtBase −physBase` 去掉后，`Invalid kernel stack pointer` **消失**，
但仍无任何文字输出。两种可能无法从照片区分：
- (A) SP 检查通过、arm_init 继续往下跑，随后在更深处静默挂死 —— 需要新的检查点或更多 printf；
- (B) SP 改动让内核在到 `PE_init_printf` 之前就死了 —— 需要用 band 池确认是否仍在 arm_init 内。

### 白天的下一步
1. 在 `arm_init` 尾部 `bl _machine_startup`（`0xb4774?`）之前插一个**不破坏 PAC** 的检查点，
   或在 `_PE_init_printf` 返回后立刻加 cave，确认 fi102 是否越过了 console 初始化。
2. 若 (A) 成立，把 `patch-arm-init-tail.py` 里剩下的 nop 逐个还原（先 `pio`/`timebase`/`kptimer`
   已在保留位，接着试 `cpu`/`fiq`），每还原一个看是否出现新 panic——现在有文字输出，可以一次定位一个。
3. `saved state: 0xFFFFFFF00CA27CB0` 与 nop 后的 `0xFFFFFFF00CA28000` 相差 `0x350`：
   若 (B) 成立，把 `0xad83094` 的 `adrp` 基址改为 `0xca27000` 并 `add #0xcb0` 精确对齐。

## 2026-11-20 接管复核与镜像预检修复

更新时间：2026-11-20 01:55 CST（Asia/Shanghai）。阶段：iOS 27 早期 XNU / `arm_init` bring-up，未确认进入 `machine_startup` 或用户态。

### Git 和 format 2

- 从 `YX2748198202-lab/UniXNU-shennong` 原位恢复空目录；恢复时 `main` 与 `origin/main` 同在 `acea8aa2dd5d2d591128a572cfdc87802532728b`，干净、无设备子模块。本轮在 `bringup/2026-11-20-takeover`，提交前仅本条所列文件有变更；不 push。接手用 `git status --short --branch && git log -1 --oneline` 取实际状态。
- 保留 `/home/yoox/android/workspace/UniXNU` 的 `main` `fa32589aa1bef4566e9f91eea9e2731eafe250bc`（相对本地 `origin/main` ahead 16，3 个修改，子模块未初始化）；也保留 `UniXNU-pin` 的 detached `3818889bccb352a8a2733ce76964aa0646ec338e`（带两个未跟踪 OS Profile，子模块已初始化）。没有 reset、覆盖或更新其工作树。
- 独立产物目录 `R=/home/yoox/android/artifacts/UniXNU-shennong/takeover-20261120.bdkq76` 中获取官方 `origin/main` `8542980d02b4d2cc5c32ee3542de1760b2562aac` 和 CI pin `c740efb5b23e94453bb179f7801eb592baafacf6` 的框架 checkout，未初始化全套组件子模块。官网 HTTP 连接超时，审计使用该已核对官方 HEAD 内的 `docs/porting/migration.md` 与 `device-repository.md`。
- 官方 `devices.toml` 已注册本仓库、`format = 2`，记录 `acea8aa`；设备 `board.toml` 是 `schema_version = 2`，`porting.toml` 独立使用 `schema_version = 1`。未重复迁移。官方 `python3 scripts/porting-record.py check --device "$D"` 检查通过（13 个 area）。`unixnu.lock`、`local.toml.example`、`proprietary-files.txt` 和官网所列的 packaging / porting-record 工作流仍缺；现有 `kernel.yml` 不是这些文件的等价替换。
- `D=/home/yoox/android/workspace/UniXNU-shennong`。截至 checkout，官方 CLI 先因 SoC 未缓存失败；只获取 `feeds.toml` 现有 `a9f45dc60c035084b95463781538380f4c3606c9`，并按 CI 将两个设备自带 OS Profile 复制到隔离框架，没有替换官方 Profile。从 `$R/framework-{ci,main}` 分别执行 `./unixnu defconfig shennong_defconfig -D "$D" --out "$R/out-$label"`、`./unixnu status --json -D "$D" --out "$R/out-$label"`。实际解析结果在 `status-{ci,main}-configured.json`：arm64e / sm8550 feed / `ios-27.0.1-24A446-iphone16pro` / shennong；输出为 `$R/out-$label/shennong/ios-27.0.1-24A446-iphone16pro/shennong`。
- 7 个组件均能解析，`ShengUfs` 依赖 `VerifiedRoot` 与 `VirtioMmioBlock`。CI 与 main 分别解析 71 / 76 个补丁；`ArmCpu`、`ShengUfs`、`RamBlock`、`XnuPrelink` pin 不同，部分 catalog ABI 只列旧供体。解析不等于源码就绪、ABI 验证或硬件兼容；不更新 CI pin 或 SoC。板级 `zzzz-diag-marks.patch` 不在实际序列，历史已验证无法直接应用；仍不启用。`dtc -I dts -O dtb -i "$SOC/dts" -o "$R/hardware.dtb" dts/shennong.dts` 出码 0，1549 条 warning 留在 `dtc.log`；板级 DTS 是 Pineapple 来源的独立树，不意味着已按官网的 SoC DTSI 分层，无实机/ADT 合格结论。

### 供体、历史产物、证据差距

- 缓存 `/home/yoox/android/cache/ipsw/iPhone17,1_27.0.1_24A446_Restore.ipsw`，没有重新下载。读取 ZIP 的 `BuildManifest.plist` 验证 iPhone17,1、27.0.1、24A446、d93ap → `kernelcache.release.iphone17`；压缩 IM4P 和完整 IPSW SHA-256 分别在 `sha256.txt`、`ipsw.sha256`。用本地 `ipsw img4 im4p extract --output "$R/kernelcache.decompressed" "$R/kernelcache.release.iphone17"` 解码，得到 arm64e MH_FILESET，SHA-256 `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`，与 board pin 一致。
- `strings -a` 的原厂 KernelCache 版本为 **Darwin 27.0.0 / xnu-13432.2.10~2 / RELEASE_ARM64_T8140**；两个官方配置的 **native 源码** pin 为 `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`（Apple tag `xnu-12377.121.6`）。CI prelink 候选同时包含 native Darwin 25.5.0 和原厂 Darwin 27.0.0 两条版本串。两者必须分别核对符号/ABI/地址；未使用 iPadOS 17.7.11 / 21H461。
- `ci/42904596191/shennong-kernel.zip` 的 device revision `dcf7c779f8c359776ce57beb4cdeea4317e1249d`。按 `patches/fi102/meta.json` 匹配归档原始 prelinked `kernel.macho`，运行 `python3 scripts/apply-fi102-patch.py "$R/fi102-pristine.macho" "$R/fi102-replayed.macho"`（1146 words），`cmp` 与留存 `build/fi102/kernel.macho` 完全一致，SHA-256 `800b4412fd125aef002035d552d4ff47af8588902a3da2de8f19ebd11f94a976`。归档的 `kernel.json` 声明 `allow_missing=true`，且 `mapping_complete/runtime_qualified/loadable` 均 `false`（`missing` 有 11 个 bundle 条目）；CI success 只证明候选产出，不能升级 prelink 兼容性结论。
- 留存 fi103–fi134 镜像，本轮对 fi134 实测读回：其 FAT 内 kernel SHA-256 与外部 Mach-O 一致；对照 fi102，`__TEXT_EXEC` 只有 5 个 4 字节 word 不同。fi134 恢复 VA `0xFFFFFFF00AD8309C/A0/B4/B8` 的 `add/sub`，且 VA `0xFFFFFFF00B3A154C`（对应 fi101 panic PC）在 offset `0x439d54c` 由 `str x16, [x8, #3896]` 变为 `nop`。历史 FAR `0xFFFFFFF00C950F38` 落在该 Mach-O 的 `__KLDDATA`（`initprot=maxprot=3`，有文件数据），**段声明可写并不证明 runtime 页表可写**。尚无能用镜像哈希对应的 fi134 实机结果。反汇编、VA/offset/权限、哈希在 `$R/fi134-changes-disassembled.txt`、`fi101-far-map.txt`、`sha256.txt`、`payload-adt.sha256`。

### 实际改动和验证

- `scripts/verify-boot-package.py`：旧版对独立 FD 及镜像分别验收、只在解压流里搜索 `_FVH`，不会比较内嵌与外部 FD。真实 fi102 镜像配一个尾字节不同、仍能被扫描器解析的 FD 副本，旧版退出 0。现检查 gzip 完整、ARM64 shim 头的地址和声明长度、由 FD 大小确定的 FV 边界；给 `--fd` 时逐字节比对。无 `--fd` 时明确跳过同一性检查。
- `scripts/test-verify-boot-package.py` 新增匹配/不匹配 FD、错误 shim 地址、截断 gzip 测试；`AGENTS.md` 同步项目规则；`docs/STATE.md`、本文件和 `porting.toml` 更新目前证据，不修改 XNU、UEFI、DTS 源或 donor 配置。
- `bash tools/build-lzma-decode.sh` 使用现存 Mu SDK 构建主机解码器（忽略的 `tools/bin/lzma-decode`，哈希在 `decoder.sha256`）。`python3 scripts/verify-boot-package.py --fd <缓存 FD> --payload <留存 payload> --image <留存 v0 镜像> --json <报告>` 对 fi102、fi134 均 0 failure；各确认 FD byte match、95 个模块、payload byte match；负例确认同一模块扫描仍成功但新增 `image firmware bytes` 检查失败，退出 1。`preflight-fi{102,134}.json`、`stale-fd-{before,after}.json` 可重查。
- 主机测试：`scripts/test-entry-probe.py "$R/fi102-pristine.macho"`（此项需要真实内核参数）、`test-extract-xbl-memory-map.py`、`test-probe-walk.py`、`test-read-sheng-log.py`、`test-scan-uefi-fv.py`、`test-verify-boot-package.py`、`firmware/test-make-payload-image.py` 都通过；`git diff --check` 通过。
- 本地 SDK 目录为空，默认 Linux `/opt/unixnu-linux` 工具链不存在，未跑完整 XNU 编译/链接或重新 prelink。CI 仍是手工 `workflow_dispatch` / macOS 26 / Xcode 26.6，并有构建时补救步骤；未触发新构建。`fastboot devices -l` 无设备；未做 `fastboot boot` 或任何分区写入。

### 交接优先任务

在现有分支继续。先用 `fi101` panic 的 FAR 与实际 `__KLDDATA` 页属性、对应 native/保留符号的反汇编核对 `PE_init_printf` 写点；区分原写入异常和栈诊断，不能将 fi134 的 NOP 当永久修复。复用已验证的 fi102 对照，不重复下载 IPSW、不混用供体、不重做已证伪的任意 cave / 单边 SP 滑动修改。可用手机时核对身份后只做临时启动，采集与启动镜像 SHA-256 对应的屏幕证据。并行前提未满足：Codex 与 Harness 不得同时改此工作树。

## 2026-11-20 console 写入异常与链接布局回归检查

更新时间：2026-11-20 10:10 CST（Asia/Shanghai）。阶段：iOS 27 `arm_init`/console，尚未证明 fi102 返回。设备分支 `bringup/2026-11-20-takeover` 从 `2ffcb7f24216f01bfb027973f199a225013edd5b` 续做；开始已有未跟踪 `.codex/`，保持不动、不提交。上游 checkout `fa32589aa1bef4566e9f91eea9e2731eafe250bc` 未修改；实际 CI pin 仍是 `c740efb5b23e94453bb179f7801eb592baafacf6`。供体仍是 iPhone17,1 27.0.1 / 24A446 / d93ap / arm64e / 原厂 `xnu-13432.2.10~2`，native 代码参考为 `xnu-12377.121.6`（`ac9718fb1af618d5ce8678d0dc6e8a58f252216f`）。只获取了公开 native 源码，没有重取 IPSW 或使用旧供体。

- **历史 fi101 的原始 fault 与 panic 名称分开。** `ESR=0x9600004f` 解为当前 EL Data Abort（EC `0x25`）、写（WnR=1）、L3 权限（DFSC `0x0f`）；`_arm_init` 的 `mov w0,#0` / `bl` 对应 `_PE_init_printf(FALSE)`。实测 PC `0xFFFFFFF00B3A154C`，offset `0x439d54c`，`__TEXT_EXEC,__text`，指令字节 `10 9d 07 f9`：`str x16,[x8,#3896]`。前面的 `adrp x8` 和 offset 得到 FAR `0xFFFFFFF00C950F38`，`llvm-nm` 精确匹配 `_PE_putc`，在内层 `__KLDDATA,__const`，不是 `_PE_kputc` 或 SP 访问。
- native 源码 `pexpert/gen/pe_gen.c` 中 FALSE 分支为 `_PE_putc` 安装 console 回调；`osfmk/arm/arm_init.c` 在 `arm_vm_init` 返回后调用它。`osfmk/arm64/arm_vm_init.c` 的 `arm_vm_prot_init` 立即把 `__KLDDATA` 设为 RNX，而 `__DATA_CONST` 先允许初始化写入、后续 finalize 才设 RNX。这与历史 ESR 一致；没有采集当时的页表或 `TPIDR_EL1`。`locore.s` 的 `CHECK_KERNEL_STACK` 在 EL1 data abort 时还会因早期 thread/stack 记录未初始化等原因走 `sleh_invalid_stack`；不能反推是栈触发最初写入故障。`saved state=0xFFFFFFF00CA27CB0` 是异常帧地址，而非预期 SP。
- 从 CI `42904596191` 归档取得 manifest 匹配的 native Mach-O（SHA-256 `3e9fdb95035f8d1a8b9ba31d752847facc344f7e5d7d417b8e425d439f7d4dbb`）。`_PE_putc`（native VA `0xFFFFFFF007CACF38`）和 `_PE_kputc` 在 **prelink 之前** 就位于 `__KLDDATA,__const`。这与 `kernel.yml` 整段 `__DATA_CONST,__const` 搬移的设计吻合；它无法区分晚写符号与不可变常量。fi101/102/134 内 `_PE_putc` 的磁盘槽均为零，fi102 保留写指令，fi134 是 NOP；仅跳过该写会丢失这次回调安装，不能当修复。
- 新增 `scripts/check-console-layout.py`，以真实 `llvm-nm -m` 的 section-backed 定义验收两个指针是否仍位于 `__DATA_CONST`，对过早只读、永久可写、缺失/歧义均失败；不修改内核和 CI 默认流程。新增 `scripts/test-check-console-layout.py`：本机 Clang/`ld64.lld-18` 链接四份真实小 Mach-O，复现整段误迁移、验证拆分后保持 late section 同时迁移不可变数据，并做永久可写与缺失符号负例。`python3 scripts/test-check-console-layout.py` 全通过；首次运行发现 LLVM 18 nm 不支持 `--`，已改用绝对路径参数。真实 CI native Mach-O 和 fi101/fi102/fi134 都按预期被新检查拒绝（退出 1，两个符号均落在 `__KLDDATA`）。这是已知故障的回归锁，不是完整 XNU 修复。
- 只读复核内层 Mach-O 段预算：native/fi102 inner `__DATA_CONST=0x64000`、`__LASTDATA_CONST=0x4000`；原厂 inner 分别 `0xdc000`、`0x4000`，其后即原厂 `com.apple.kec.pthread` 常量。若维持这个供体边界，理论差额 `0x78000`（480 KiB）；不是已验证可分配容量，仍需验证节对齐、重定位和实际保留 kext 边界。原始输出 `native-fileset-data-const-budget.txt`。
- 证据目录 `/home/yoox/android/artifacts/UniXNU-shennong/console-fault-20261120.X19KZ1`：`fi101-console-disassembly.txt`、`fi101.sha256`、`layout-{native,fi101,fi102,fi134}.txt`、`test-check-console-layout.log`、`ci-native-linkarguments.txt` 和 native 参考源码。未做完整 kernel link、prelink、固件改动或新镜像；`fastboot devices -l` 无连接，未读写设备分区。

下一项：以实测段预算为上限，做符号生命周期正确的链接布局候选，在保持 VM finalization 与保护不变的前提下让两类常量分区；真实完整链接和 prelink 后都要跑新检查。Codex/Harness 同分支交接；先 `git status --short --branch && git log -1 --oneline`，不接管 `.codex/`。实机必须分别记录启动镜像哈希和观察，不能把 host 夹具当作启动成功。

## 2026-11-20 实机：fi102 关闭存储诊断对照

记录时间：2026-11-20 11:53 之后（UTC+08:00，WSL）。阶段：早期 `arm_init`/console，等待本轮屏幕证据。设备分支 `bringup/2026-11-20-takeover`，HEAD `1980c55e81570a8169a22afdbbe7d40d5db588fa`；开工时 tracked 干净，本轮仓库仅改本进度记录，原有未跟踪 `.codex/` 不动。上游 checkout `fa32589aa1bef4566e9f91eea9e2731eafe250bc` 未改，CI 仍固定 `c740efb5b23e94453bb179f7801eb592baafacf6`。供体 iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e，原厂 KernelCache `xnu-13432.2.10~2`；native 源码基线 `xnu-12377.121.6` (`ac9718f`)；没有新下载、内核重链或混入旧供体。

- 原版 `Mu-shennong-fi102.img`（SHA-256 `3e4bf0ac2a580c04185aed19e241401209e58f35ef7826c65b7719d2ce751028`）离线预检 0 项失败，但其 FAT 实际 `unixnu.toml` 含 `sheng-log=1`，源码上可向 userdata 的保留区写诊断日志。**未向手机发送原版。** 本轮目标只到早期 console，因此不触及这项存储授权。
- 用 `scripts/patch-payload-args.py` 对独立 FAT 副本把 `native-ufs-probe=3`、`native-source-storage=1`、`sheng-log=1` 分别改为 `0`；其他配置不变。通过 `mdir` 枚举和 `mtype` 比对，FAT 的其余 6 个文件逐字节相同，包括内核（SHA-256 `800b4412fd125aef002035d552d4ff47af8588902a3da2de8f19ebd11f94a976`）、ADT、EFI 加载器、trust cache、root policy 与 crypto-hmac 清单。`scripts/repack-v0-bootimg.py` 重包后用 `cmp -n 2396160` 验证 header 到 ramdisk 前逐字节一致（含 BootShim、FD、附加 DTB），再用 `scripts/verify-boot-package.py --board <诊断副本> --fd <归档 FD> --payload <诊断 FAT> --image <诊断镜像> --json <报告>` 验证 0 项失败。不修改仓库默认 `board.toml`。诊断镜像 `Mu-shennong-fi102-storage-off.img` SHA-256 **`a2390d819d8b6e26d769e5ceb8725b42b79cf71e86d976c96620bae5b85c28a5`**。
- `2026-11-20T11:52:55+08:00` 再次校验镜像哈希、`fastboot devices -l`、`getvar product` = `shennong`、`getvar is-userspace` = `no`，随后只执行一次 `/usr/local/bin/fastboot -s 9f72e95c boot <诊断镜像的 Windows UNC 路径>`。`/usr/local/bin/fastboot` 指向 Windows platform-tools 的 `fastboot.exe`。传输 198948 KB `OKAY [5.181s]`，`Booting OKAY [0.083s]`，退出 0。未执行 flash、擦除、格式化、重启命令或针对分区的写入。USB 在 11:53:07/12 短暂报 `???????????? fastboot`，11:53:15/20/30 未枚举 Fastboot；这只是主机观测，不能判定内核是否运行或 console 是否返回。没有自动尝试下一版。UEFI 若停在菜单，XNU 项仍名为 `shennong XNU native UFS`。
- 证据：`/home/yoox/android/artifacts/UniXNU-shennong/device-fi102-20261120.8JvKp6` 下 `preflight.{log,json}`、`storage-off-package.log`、`storage-off-preflight.json`、`storage-off.sha256` 和 `fastboot-run.log`；其中打包日志记录完整命令，`storage-off-config.py` 可验证参数和其他 FAT 文件未变。首次预检调用因 PowerShell/WSL 转义失败；改为经 stdin 传递 Bash 后通过，失败调用未操作手机。

下一项：先把用户屏幕照片或按顺序描述的菜单、色带、文字与本镜像哈希绑定；若没有屏幕证据，不把 USB 消失、黑屏或 `Booting OKAY` 当作越过 `_PE_init_printf(FALSE)`。再推进独立的 native 链接布局修复，保留启动期可写、finalize 后只读机制；不能把 fi134 跳过回调安装视为修复，也不应依据历史保存帧地址调整 SP。Codex/Harness 接手前检查当前分支、HEAD 和此未提交文档，保持单写入者。

### 屏幕回报与恢复确认（2026-11-20 11:58 UTC+08:00）

- 用户提供了该次启动的照片并报告短按电源、音量上下无响应。照片中仅有横贯顶部的绿色条、DarwinBoot 交接文字和 UEFI 退出时的 `LockCapsuleInterface` 日志，未见蓝/品红检查点或 panic；菜单是残留画面，不再等待选择。原照片仅存本地证据目录 `screen-fi102-storage-off.jpg`，SHA-256 `d2903cad506e7fd50626d2931194564e1a72e664989ee9b77dc290137e7c88d5`，绑定上面的诊断启动镜像，不提交照片。
- 从该次 FAT 提取的 `DarwinBoot.efi` SHA-256 `cd9f343a04740f836f0e5461aedce2f2d4aea8b96b78c0a2d1d8de2fb33a4e9b` 与预检一致；`llvm-objdump-18 -d` 的 `screen-DarwinBoot.disasm.txt` 确认 `0xa01c` 写绿像素，之后才执行 cache 维护（`dc civac` @ `0xa04c`）、关 MMU（`msr SCTLR_EL1` @ `0xa07c`）并经 `br x1`（`0xa090`）跳转。CI pin 源码 `DarwinBoot.c` 仅在 `ExitBootServices` 成功时调用 `DarwinEnter`。绿条证明到达绘制点；缺少后续色带不证明 `br x1` 未执行，更不能等同历史 fi102 的 16 条色带。`LockCapsuleInterface` 是固件日志，不能从这一行认定 bootloader 被重新上锁。
- `2026-11-20T11:58:26+08:00` 主机只读确认同一序列号重新枚举，`product=shennong`、`is-userspace=no`。无第二次启动或分区写入，未重链内核。更新 `docs/STATE.md` 区分当前可观察界线与历史 console fault。Codex/Harness 下一项先核对实际入口地址、首条指令与第一个 XNU 探针，不重复原样重启，也不盲改 SP；console 链接修复另行保留。仍在原 HEAD/分支；仅两份文档有工作树改动，未推送。

## 2026-11-20 实机：fi102 黄色标记到达 cache 维护之后

记录时间：2026-11-20 12:14 后（UTC+08:00，WSL）。设备分支 `bringup/2026-11-20-takeover`；开工 HEAD `1980c55e81570a8169a22afdbbe7d40d5db588fa`，新源码本地检查点 `a33f4f414fe7ea4a4d660aa2cc939a32f1d1bcac`（沿用仓库现有 `Codex <codex@localhost>` 临时署名，不修改 Git 配置）。`docs/STATE.md` 和本进度仍为工作树改动，原有 `.codex/` 不动，未推送。上游 `fa32589aa1bef4566e9f91eea9e2731eafe250bc` 不变；CI `c740efb5b23e94453bb179f7801eb592baafacf6` 所引用的 DarwinBoot `3c75734014cdab0acd9541e88057b7606ee7ae08`。供体 iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e，原厂 KernelCache `xnu-13432.2.10~2`，native 源码 `xnu-12377.121.6` (`ac9718f`)。本轮未改内核、未重做 prelink。

- 新增 `scripts/darwin-handoff-marker.S` 和 `scripts/build-darwin-handoff-marker.py`。使用 `clang-18 --target=aarch64-none-elf` 和 `llvm-objcopy-18` 编译，先把固定提交的原版 `DarwinEnter` 汇编成与归档 EFI 等同的 0x94 字节。目标节 RX，RVA `0xa000` / 文件 `[0x6800,0x6894)`，无这段的重定位或签名。新版本仅把绘制移到 `dc civac`、`ic iallu` 和屏障完成之后并改黄色；cache 指令组和关 MMU/TLB 后 `br x1` 字节不变，只换入口函数内 23 条 4 字节指令，PE 节表与重定位报告一致。拒绝非 pin 原件、拒绝输出覆盖两项负测试通过。EFI SHA-256 `3f4683aeca36644eb715f7124b0f5129a649141b7f2b518bfedb78341b848184`。这是观察探针，不是修复。
- 在上轮关闭存储的 FAT 副本用 `mcopy` 替换 EFI，验证其他六个文件逐字节未变（包括内核、ADT、`unixnu.toml`）。`repack-v0-bootimg.py` 后核对 boot header、shim、FD、附加 DTB 未变，`verify-boot-package.py` 报 0 项失败。`Mu-shennong-fi102-late-marker.img` SHA-256 `4eaacdc82dc9d62a981519b87560c8f8768ee2537d1a82d9911380bfffe21e42`。
- `2026-11-20T12:08:04+08:00` 校验镜像后核对 `9f72e95c` / `shennong` / `is-userspace=no`，仅一次 `fastboot -s 9f72e95c boot <已验收镜像>`。`Sending OKAY [5.241s]` / `Booting OKAY [0.083s]` / 退出 0；12:08:24 起 host 不再枚举 Fastboot，最后一次观测 12:08:39。用户回传照片：**仅顶部黄条，无蓝/品红或 panic**。这证明已执行到 `stp` @ `0xa05c`，位于 cache 维护完成后、`msr SCTLR_EL1` @ `0xa07c` 和 `br x1` @ `0xa090` 前。不能从静止画面判定关 MMU、分支或 XNU 探针中的哪个动作停下。未发其他镜像、未刷写、未对分区执行写入；用户可手动恢复 Fastboot。
- 证据：`/home/yoox/android/artifacts/UniXNU-shennong/handoff-late-20261120.n9SjOv`，含构建/负测试、包内对照、`fastboot-run.log`、`screen-fi102-late-marker.jpg`（SHA-256 `b9e89024aefa670daa998d51ba5018c71d1396ae4b3317dbece3038668ec43ef`）及 `entry-audit.log`/`next-entry-slot-audit.log`。实际 `LC_UNIXTHREAD`：VA `0xfffffff00ad81488`（PA `0x8c3d81488`），文件 `0x3d7d488` 首字 `1400001e` 去 stage-1 VA `0xfffffff00ad81500`，之后第一个动作是从 `x0` 解引用 `boot_args`。stage-1 槽文件 `[0x3d7d500,0x3d7d560)` 位于 `__TEXT_EXEC` RX；匹配哈希的 pristine 全零，fi102 只使用前 0x40，后 0x20 实际全零。原 stage-1 最终跳 `_start_first_cpu` VA `0xfffffff00ad8305c`。

下一项：在已验证的 stage-1 槽内增加不依赖 `boot_args` 的短入口标记，保留原探针逻辑和分支目的地、保持黄色 loader 与存储开关不变。只有新入口色出现才能证明穿过 `br x1`；未出现不能单独否定物理 framebuffer 访问。该候选尚未实现、打包或发送。历史 console 权限修复仍独立待办。Codex/Harness 保持同分支单写入者，接续先看此记录和实际 Git 状态。

## 2026-11-20 实机：fi102 红色 XNU 入口标记已发送，待屏幕结果

记录时间：2026-11-20 12:36 后（UTC+08:00）。设备分支 `bringup/2026-11-20-takeover`，起点 `a33f4f414fe7ea4a4d660aa2cc939a32f1d1bcac`，新源码本地 HEAD `d25a69ac1f34ec8fc7085bbd76b9601e3f3ed2f8`。`docs/STATE.md` 与本进度仍是已知工作树改动，`.codex/` 原有未跟踪项未动，未推送。上游 `fa32589aa1bef4566e9f91eea9e2731eafe250bc` / CI `c740efb5b23e94453bb179f7801eb592baafacf6` 不变。供体：iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e / 原厂 `xnu-13432.2.10~2`；native 源码 `xnu-12377.121.6` (`ac9718f`)。本轮汇编诊断探针并重包归档 Mach-O，没有完整重链内核或重做 prelink。

- 新增 `scripts/fi102-entry-marker.S` 和 `scripts/build-fi102-entry-marker.py`；检查 pristine、fi102、配套黄条 EFI 的 SHA-256、arm64 fileset 入口、RX `__TEXT_EXEC`、pristine 空槽、fi102 空尾和原跳转。新探针只替换文件 `[0x3d7d500,0x3d7d560)` 的既有 stage-1 槽，前置 32 字节从上轮已验证的 loader `x11` 帧缓冲游标画窄红带，不读取 `boot_args`（`x0`），不使用栈、不碰 PAC。`x1..x3` 由原探针在使用前重载；原探针前 0x3c 字节完全相同，尾 B 从 VA `0xfffffff00ad8153c` 移到 `0xfffffff00ad8155c`，机器字 `140006c8` → `140006c0`，目标仍为 `0xfffffff00ad8305c`。因板上已观测的显示几何，此标记只覆盖原黄带最末的 `[0xfc4e9400,0xfc519400)`；原蓝条位置未变。用 `aarch64-linux-gnu-objdump` 复查跳转与读写，验证槽外逐字节一致；错误 loader、错误 pristine、拒绝输出覆盖三项负测试通过。内核 SHA-256 `2a3df2dc544b69e1446e346349cc1159f9fc457a5ce8485f01dfc70bcd7a3072`。
- 以已在实机显示黄条的镜像为对照，只向 FAT 副本替换 `kernel.macho`。FAT 其他文件逐字节相同（包括黄条 DarwinBoot、ADT 和禁用持久日志/存储的菜单），`cmp` 校验整个 payload 前缀相同（boot header、shim、FD、附加 DTB）。`verify-boot-package.py` 0 项失败；诊断镜像 SHA-256 `6fc36e3ba510de980c437b692bff8e304a050b0274d3ebd7340d4dada91f96de`。
- `2026-11-20T12:35:29+08:00` 核对镜像和连接设备 `9f72e95c` / `product=shennong` / `is-userspace=no`，只执行一次 `fastboot -s 9f72e95c boot <诊断镜像>`；`Sending OKAY [5.247s]` / `Booting OKAY [0.083s]`，退出 0。12:35:49 起直到 12:36:04 没有 Fastboot 枚举。未执行刷写、擦除或其他持久分区操作；未自动重试。没有本轮屏幕证据，不能把 host 交接判作内核执行。日志、命令、反汇编、SHA 和预检报告位于 `/home/yoox/android/artifacts/UniXNU-shennong/entry-red-20261120.QAqVbe`。

下一项先收与本镜像哈希绑定的屏幕照片：黄条下沿出现窄红带证明已执行到 XNU 的指令，之后无蓝条仍需检查 `boot_args` 读取或原蓝条写屏；若红、蓝都无，仍区分分支/取指和关 MMU 后的 framebuffer 写入。不要因无色带直接定论，也不反复试同一镜像。历史 console 权限修复另行保留。

### 屏幕回报：红带、蓝带及最高 band 15 均已实机观察

- 用户连发两张实机照片，绑上面 `6fc36e3b…` 镜像，均见顶部黄带下沿的窄红带和原蓝带。第一张仍留有部分菜单画面；第二张 16 个主色带位置均可见（band 0 底部叠红条），下方为 band 15 绿色，未见新 panic。仅据照片不判定第一张缺带的时序或成因。两张原件仅在本地 `entry-red-20261120.QAqVbe` 保存：`screen-entry-red-partial.jpg` SHA-256 `09c3ceeb93dfaeccc8043fa85c5fd618c89ff79044b325873379d8ca23825422`、`screen-entry-red-full.jpg` SHA-256 `ec6896d2ec485ae975c59eca0448dfc25b8b0d2add0d62131717fac6b2603eee`。红带确证 `br x1` 后进入 XNU；蓝带证明原 stage-1 已从 `boot_args` 读出显示地址和尺寸并写屏。
- 按实际诊断 Mach-O SHA-256 校验，从 `_start_first_cpu`/`_arm_init` 扫描分支、解码真实探针的 band 号及 BGRA、反汇编 band 2/14/15。band 14 的站点 `0xfffffff00ad83414` 在控制寄存器写入前，实际色 `0xffffff80`；band 2 绘制后在 `0xfffffff00ad8159c` 执行 `msr SCTLR_EL1,x0`；band 15（`0xff80ff00`，站点 `0xfffffff00ad8341c`）的 `stp` 在 `0xfffffff00ad81f64`，原 `isb` 晚于绘制，位于 `0xfffffff00ad81f84`，返回 `0xfffffff00ad83420`。实机证明抵达写入之后，不能证明执行了原 `isb` 或进入 `_arm_init`；实际 `_arm_init` `0xfffffff00b4768f0` 此镜像仍是 `pacibsp`，其后原 `sub sp`，与通用脚本默认 band 15 站点不同。完整证据 `band-sites.txt` 与 `band-sites.disasm.txt`。同步修正 `docs/STATE.md` 的旧色带语义。
- 接续：当前日志/文档修改，不改源码，HEAD 仍 `d25a69ac1f34ec8fc7085bbd76b9601e3f3ed2f8`。仅复核归档，没发新镜像，无新增设备操作。下一优先在实际 `isb` 及 `_start_first_cpu` 尾段的下一边界定位（现有自旋检查在 `0xfffffff00ad83434`）；不根据最后色带推断静止位置，不重复入口探针，不在 PAC 序言内注入。历史 fi101 console 写权限故障仍另处理。


## 2026-11-20：fi102 post-ISB 复位探针与入口对照

更新时间：2026-11-20T13:51:45+08:00（Asia/Shanghai）。阶段：XNU 入口至 `_start_first_cpu` 尾部，当前候选没有复现入口可见标记。设备分支 `bringup/2026-11-20-takeover`，修改基线 `d25a69ac1f34ec8fc7085bbd76b9601e3f3ed2f8`；上游 `fa32589aa1bef4566e9f91eea9e2731eafe250bc`（原有工作区改动不动），CI pin `c740efb5b23e94453bb179f7801eb592baafacf6`；未推送，`.codex/` 原有未跟踪项不动。供体仍为 iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e，原厂 `xnu-13432.2.10~2`、native 源码 `xnu-12377.121.6` (`ac9718f`)；本轮未重链 XNU 或重做 prelink。

- 新增 `scripts/build-fi102-post-isb-probe.py`。仅接受实测红带控制 Mach-O 与匹配 pristine 的固定 SHA，确认 `__TEXT_EXEC` 为 RX、原 `isb` 和原继续跳转、同页空槽在两份输入均为零。保持到 `0xfffffff00ad81f84` 的探针路径，将 `0xfffffff00ad81f88` 处继续 B 从 `0x14000526` 改为 `0x14000012`，目标 `0xfffffff00ad81fd0`，避开 `[0x…1f90,0x…1fd0)` 暂存内存。44 字节代码只使用寄存器与 generic counter，等待 `CNTFRQ_EL0 × 16` 后请求 PSCI SYSTEM_RESET，不访问栈、显存、PAC 或页表；若 SMC 返回则原地停住，不返回正常启动。该镜像是诊断工具，不是引导修复。
- 用 `clang-18`/`llvm-objcopy-18` 汇编，`aarch64-linux-gnu-objdump` 核对指令；内核只有 `[0x3d7df88,0x3d7df8c)` 和 `[0x3d7dfd0,0x3d7dffc)` 两处允许变化，SHA-256 `b508af03e1c0fd6e9092b133d578b152145f24acd88e8be8365dfe2ec9dc2258`。拒绝错误红带、错误 pristine、覆盖现有输出三项测试通过。FAT 内容仅替换 `kernel.macho`，其余文件逐字节相同；对照与候选 boot header、BootShim、FD、DTB 前缀相同，且菜单继续 `native-ufs-probe=0 native-source-storage=0 sheng-log=0`。`verify-boot-package.py` 0 项失败；`python3 scripts/test-verify-boot-package.py` 通过。镜像 SHA-256 `8a71a5ea29e8cbcf660995de1cd5b5f7fc14ce3c78405e8437388f9967bd361b`。
- 13:10:57（北京时间）核实 `9f72e95c` / `product=shennong` / `is-userspace=no` 后，执行一次 `fastboot -s 9f72e95c boot <候选镜像>`，13:11:03 `Booting OKAY`、退出 0。从可用观测 t+12s 至 t+105s 无 Fastboot 或 ADB 枚举。Windows PnP 在 13:48:03 重新发现该 Android Bootloader 接口；用户明确确认没有黑屏或自动重启，是自己手动回到 Fastboot，**不得计为探针命中**。未刷写、未擦除、未重复下发。
- 实机照片只有黄色加载器条及退出 UEFI 时的残留菜单、文字，未见 XNU 窄红带、蓝带或更后色带。归档 `screen-post-isb.jpg` SHA-256 `235cc20dc948cea0bc564dd9c6cb595fe5835b635ba9b144c9c3a2ec74bfb765`。从两份最终 boot image 的 FAT `0x249000` 提取内核，确认真实入口指令 `1e000014` 以及完整 96 字节红/蓝探针槽完全相同（`embedded-entry-audit.log`）。本次只确认到黄条，既不能证明没进 XNU，也不能将差异归因于 `isb` 或复位调用。上一张红带对照的 XNU 执行证据仍成立。
- `docs/bringup.md` 更正了 `cmp x0,x1` 的旧解释：当前路径没有 `mrs` 回读 `SCTLR_EL1`，不能把 RES1/RAZ 差异当作自旋原因；`docs/STATE.md` 更新当前证据和优先级。命令、日志、哈希、反汇编、原始照片和 `preflight.json` 均在 `/home/yoox/android/artifacts/UniXNU-shennong/post-isb-20261120.yxMQ5R`（不入 Git）。

下一优先是 **单次复跑原哈希 `6fc36e3b…` 的已知红带对照**，以确认早期标记能否复现。这不是重发失败的 post-ISB 候选。若对照也只黄条，先定位黄条之后的 MMU 关闭、分支与取指/显存可见性；若对照恢复，再用同基线的 pre-ISB 试验校准计时复位观测，或改用独立观测点；未确认越过 `isb` 前不推进到 `_arm_init`，不叠加 console/PAC 或页表修改。


### 原哈希红带复跑未复现 XNU 色带；构建 EFI 跳转前青色候选

更新时间：2026-11-20T13:58:45+08:00（Asia/Shanghai）。设备分支 `bringup/2026-11-20-takeover`，修改前 HEAD `d25a69ac1f34ec8fc7085bbd76b9601e3f3ed2f8`；上游 `fa32589aa1bef4566e9f91eea9e2731eafe250bc`，供体及 CI pin 同上。未修改上游、没有重新链接内核或修改供体、没有刷写及擦除。

- 13:54 核对设备为 `9f72e95c` / `shennong` / `is-userspace=no`，复核原红带镜像 SHA-256 `6fc36e3ba510de980c437b692bff8e304a050b0274d3ebd7340d4dada91f96de` 和包预检（0 项失败），用 `fastboot -s 9f72e95c boot <原红带镜像>` 仅临时启动一次。13:54:07 Booting OKAY；t+10s 只见无有效序列的瞬态枚举，t+12s 到 t+45s 无 Fastboot/ADB。实机照片仅黄条，没有 XNU 窄红带或蓝带；照片 `screen-red-recheck.jpg` SHA-256 `d0a5a60aecf909d81dc516cb9de3b22debb33da1792cd5d7fbfbd621430b79e9`，实机目录 `/home/yoox/android/artifacts/UniXNU-shennong/entry-red-recheck-20261120.7fuVCW`。原镜像也能出现只黄条，排除新增 post-ISB 指令是该画面出现的必要条件；不能因此断言硬件这次一定未取 XNU 指令。
- 新增 `scripts/build-darwin-pre-branch-marker.py`，仅基于固定的 DarwinBoot 黄条 EFI。在 `DarwinEnter` 最后 `isb` (RVA `0xa08c`) 后、原 `br x1` 位置 (`0xa090`) 插入无栈青色探针，其后在 `0xa0b0` 仍 `br x1`。保留关 MMU/TLB 路径、x0、x1、x11、SP、NZCV。沿用已实测游标，青色区 `[0xfc4a9400,0xfc4e9400)`，与 XNU 红带 `[0xfc4e9400,0xfc519400)` 不重叠。PE 末端填充全零，RX 节原始长度不变，VirtualSize 字段 `0x228` 从 `0x94` 到 `0xb4`；`llvm-readobj-18 --sections --coff-basereloc` 验证仅该字段报告改变，`llvm-objdump-18` 核对指令。拒绝错误原件和输出覆盖两项失败测试通过。
- 以同一红带 FAT 对照打包，逐文件证明只有 `DarwinBoot.efi` 变动（EFI SHA-256 `67deba5f1f97e64757fbd319568d277236008435b7a20af244a3b44195fe6b02`）；内核、ADT、菜单、关闭存储和持久日志开关不变。boot header、shim、FD、DTB 前缀不变；`verify-boot-package.py` 0 项失败。新镜像 SHA-256 `8338b7015c9d6f5cddbf5ab3a7384ccc6eb79417aebb039d30d8f3e5fbd06f6e`，完整命令 `build.sh`、日志、报告在 `/home/yoox/android/artifacts/UniXNU-shennong/pre-branch-20261120.cxUbGc`。构建完成时没有 Fastboot 枚举，**尚未下发青色候选**。

下一步：手机手动回 Fastboot，单次临时启动青色候选。青色出现可证明最后一条 DarwinBoot `isb` 后已到达绘制点，不等于执行了 `br x1`；青色有而 XNU 红色无，优先定位间接分支/取指与 XNU 入口写屏。青色无则不把缺色直接归因到 MMU，需要独立观测。Codex/Harness 继续本分支，开工核对 `git status --short --branch` / `git rev-parse HEAD`，无 push。


### 青色跳转前探针：已单次下发，待确认屏幕

更新时间：2026-11-20T14:02:30+08:00（Asia/Shanghai）。设备 `bringup/2026-11-20-takeover` HEAD `5a9451128d69ffa01123a6b0e60b8cbfb9c43a71`，开工仅原有未跟踪 `.codex/`；本次只更新 `docs/STATE.md`、`docs/agent-progress.md`。上游 `fa32589aa1bef4566e9f91eea9e2731eafe250bc` 未动，供体与 CI pin 同上；未重链、未推送。

- 用户手动回到 Fastboot。复核 `9f72e95c` / `shennong` / `is-userspace=no`、镜像 SHA-256 `8338b7015c9d6f5cddbf5ab3a7384ccc6eb79417aebb039d30d8f3e5fbd06f6e`，运行预检 0 项失败。14:01:06 仅一次 `fastboot -s 9f72e95c boot <青色镜像>`；14:01:12 `Booting OKAY`、退出 0。t+10s 瞬态枚举未报告有效序列；t+12s 至 t+46s 无 Fastboot/ADB。没有刷写、擦除或重试；USB 无枚举及 `Booting OKAY` 均不能验证屏幕色带或内核控制流。
- 从实际 v0 镜像的内置 FAT 提取 EFI，核对包含青色探针的 EFI SHA-256（`67deba5f…`）、`isb` @ `0xa08c`、`br x1` @ `0xa0b0`；内嵌 Mach-O、ADT、菜单与原红带镜像逐字节相同。预检、实际命令、USB 观测、内嵌文件核验在 `/home/yoox/android/artifacts/UniXNU-shennong/pre-branch-20261120.cxUbGc`（`device-preflight.log`、`fastboot-run.log`、`embedded-handoff-audit.log`）。

下一步先收并绑定 **14:01 这次**屏幕照片。青色出现证明抵达最后一道 DarwinBoot 屏障之后的绘制点，不证明已执行 `br x1`；青色与红色都出现则可确认此轮进入 XNU。若仍仅黄条，则不能区分关 MMU 后未取指和显存写入未可见；先换独立观测，不原样重复候选。


### 青色候选仍只见黄条；转向可复现的 console 链接修复

更新时间：2026-11-20T14:11:35+08:00（Asia/Shanghai）。设备 `bringup/2026-11-20-takeover` 开工 HEAD `5a9451128d69ffa01123a6b0e60b8cbfb9c43a71`，已有青色测试待回报的两份文档改动和原有未跟踪 `.codex/`（不动）。官方工作树 HEAD `fa32589aa1bef4566e9f91eea9e2731eafe250bc`（未修改），CI pin `c740efb5b23e94453bb179f7801eb592baafacf6`；iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e，原厂 `xnu-13432.2.10~2`、native `xnu-12377.121.6`。

- 用户提供 14:01 青色候选 `8338b701…` 的实机照片：仅加载器黄条和残留菜单，无青色、无红色。归档 `pre-branch-20261120.cxUbGc/screen-pre-branch.jpg` SHA-256 `88d5fdfcc5ad107aa8b5e06999bfaf8f457e0c5c948164093730ee31fa9a1ec5`。这次没有确认最后屏障后的绘制点，也不能断定 MMU 屏障失败；不再让用户重复同一颜色实验。本轮未下发镜像、未操作设备分区。
- 新增独立 `patches/experiments/pexpert-late-write-section.patch`，对 `ac9718fb1af618d5ce8678d0dc6e8a58f252216f` 的 `pexpert/gen/pe_gen.c`、`pexpert/arm/pe_kprintf.c` 保留原声明、初始化和平台 guard，仅把两文件七个显式 late-write 对象放入 `__DATA_CONST,__pe_late`，避开整段 `__const` 迁移。没有 NOP 写入，也没有令整个 `__KLDDATA` 可写。补丁尚未接入默认 series/CI，不把声明级结果当作完整内核修复。
- 在独立源码副本执行 `git apply --check`、`git apply` 和 `git apply --reverse --check` 通过；`python3 -u scripts/test-pexpert-late-write-patch.py <原始源码目录>` 利用 Clang 18 和 ld64.lld 18 构建并链接真实源码声明的 arm64e/iOS 27 小 Mach-O。原声明的两个回调被 layout 工具拒绝；修复后七个变量都落在 `__DATA_CONST,__pe_late`，原常量仍在 `__KLDDATA,__const`，两个回调通过。此测试用直接 rename 复现 CI 的最终 section 结果，未跑 Apple 完整链接。`python3 scripts/test-check-console-layout.py`、`python3 scripts/test-verify-boot-package.py` 均通过。源码输入、哈希、构建和验证日志在 `/home/yoox/android/artifacts/UniXNU-shennong/console-fix-20261120.6AhjXh`。

下一优先：有固定的构建依赖时，完整构建该实验 patch，先检查链接数据段实际端点、保留 kext 布局和 prelink 后指针归属，不能直接发镜像。它解决的是历史 fi101 最早可证实的 console 数据分类问题，不声称修好当前未稳定复现的入口。继续共用同一分支，不开启额外写入 Agent，不推送。


### 2026-11-20：原 CI prelink 字节级复现，WSL 开始实际整核工具链构建

- 设备 `bringup/2026-11-20-takeover` / `53007d1101faa551ee4a8ed3a8acd6cff805f22c`，开工 tracked 干净，原有未跟踪 `.codex/` 不动。官方工作树 `fa32589aa1bef4566e9f91eea9e2731eafe250bc` 的既有修改不动；本机参考检出 `UniXNU-pin` 实际 HEAD `3818889bccb352a8a2733ce76964aa0646ec338e`，实验框架按 **CI commit 对象 `c740efb5b23e94453bb179f7801eb592baafacf6`** 导出，子模块按该 commit 的 gitlink 逐个核验，不等同于以检出目录名推断 HEAD。SoC `a9f45dc60c035084b95463781538380f4c3606c9`，XnuPrelink `b1888c12456c46a2226d63c794465dfcee08d465`。
- 同一 iPhone17,1 / iOS 27.0.1 / 24A446 / d93ap / arm64e 供体；原厂 `xnu-13432.2.10~2` KernelCache SHA-256 `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`，native `xnu-12377.121.6` 源码 `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`。没有新下载 IPSW、混用旧供体或更改供应源。
- 用 CI `42904596191` 的 native `3e9fdb95035f8d1a8b9ba31d752847facc344f7e5d7d417b8e425d439f7d4dbb`、精确归档映射、固定 kit 和独立副本中相同的 chained-fixups 回退行为重放。首次只读 `board.toml` 漏合并 OS Profile 的 `early_security_init`；补齐后 **94,552,064 B / SHA-256 `31e33289e188085f21a63599809e7e69d75f53d5b5b8c29dddc79bb9de9af1f7`**，与归档完全一致。仍是 18 处未解析闭包引用、170 个 stub，`mapping_complete=false`、`runtime_qualified=false`、`loadable=false`。命令、输入哈希和结果在 `/home/yoox/android/artifacts/UniXNU-shennong/console-prelink-replay-20261120.tTzRgr/replay.sh` 和 `replay.log`。用旧 native 副本仅翻转 `LC_UUID` 的一个字节做负例，旧映射在 emitter 中明确拒绝（退出 1、无新产物，`check-map-mismatch.log`）；没有修改任何已归档 Mach-O。
- 在 `/home/yoox/android/artifacts/UniXNU-shennong/console-native-20261120.okIC8q` 建隔离构建。WSL 直连镜像/GitHub 超时且官方 installer 默认需 root；改用 Windows 下载、在 WSL 用已缓存的 apt 元数据校验 `.deb` 后仅解包到产物目录。用固定上游安装配方编出 cctools `ld64-956.6`（SHA-256 `eac73c8c14363bd15574a83310a66526e5b134d4e30d372b00920d3eb09c08ce`）、`migcom`、`iig`、`lzfse`；`xnu-host-cc` Mach-O 工具链接/运行测试通过，未写 `/usr/bin`。固定 LLVM `58c46bae21181fb4240cf964461bea738d96d50e` 已下载、应用框架 builtin 补丁并进入 CMake/Ninja 编译。源码快照 SHA-256 `e30ace42a3cae7cd5a69ffc46f3115bf1ba54b5dc436a2b77bd10cb0a9a0158a`；`bootstrap-llvm.log` 记录实际构建状态，不能用系统 Clang 18 代替。
- `scripts/test-pexpert-late-write-patch.py` 新增 `--kernel-link`：用真实 XNU 声明在 cctools 上执行 `-static -kernel` 和 CI 两级 section rename。未修复声明的两个回调仍错误进入 `__KLDDATA,__const`，补丁后的七对象均进 `__DATA_CONST,__pe_late`，不可变常量仍进 `__KLDDATA,__const`。默认 LLVM 夹具、cctools 夹具、`test-check-console-layout.py` 和 `test-verify-boot-package.py` 均退出 0，`test-regression.log` 存档；系统 Clang 18 的 arm64e 夹具仍触发 ld64 ABI 警告，**仅验证 section 放置**。实验补丁没进入默认 series/CI。
- format 2 状态重新解析出 `shennong_defconfig`、7 个组件和 **71 项正式补丁**（`status-baseline.json`）。用 pin 和本地 Feed 验证这 71 项可在正确 native 源码上顺序应用，再在隔离树中加实验补丁作为第 72 项；未启用未入选的旧设备补丁。按 OS Profile 恢复公开 TrustCache 缺失头文件 5 份，逐文件核对 Git blob hash（不是切换供体）；固定 AvailabilityVersions 已安装到实验 fakeroot。`patch-plan.log`、`native-prepare-offline.log`、`availability.log` 保存命令和版本。
- 未触发工作流、未推送、未操作手机。黄条之后的 DarwinBoot→XNU 控制流仍未稳定证实；历史 fi101 console 写权限故障和这个实机现象不能合并为同一结论。

接续：查看产物目录 `bootstrap-llvm.log` 与 `native-attempt.log`。先完成固定 Clang 的 arm64e builtin 检查，再用 `run-after-llvm.sh` 完成隔离 DEVELOPMENT native 构建（本地 iOS 27 shim、未复用映射、暂不做 RELEASE reference/prelink）。这次自动接续已执行并退出，结果见下方「WSL 实际原生构建结果」；不要重复启动同一编译器构建。完整 native 链接通过后，核验 symbol、`__DATA_CONST`/`__LASTDATA_CONST` 实际端点与保留 kext、split-segment/chained fixups 等重定位记录，再构建新 RELEASE reference 和新映射，比较未解析项。未过验收不打包、不要求重复启动。Codex/Harness 交接前核对同一分支及 diff，仅一个 Agent 写入。

**追加对照**：复查 CI native，实际含 432,649 条 split-segment 引用和 104,260 个 chained fixup。直接用未改动的固定 XnuPrelink 重放也得到同一 SHA-256；先前独立副本的缺段回退在这组输入上未触发，不需要带进新构建（`replay-pristine.sh` / `replay-pristine.log`）。以原厂 collection、实际 39 项闭包、同一 prelink `Layout` 复核：CI native 放置后的 `__LASTDATA_CONST` 结束于 `0xfffffff007e38000`，首个**保留** kext 常量是 AppleARMPlatform `0xfffffff007ef3578`，间距 `0xbb578`，已和归档的内层 Mach-O 交叉验证。之前的 `0x78000` 按全量原厂 kext 边界估计，两者不可互换；新链接必须重新测。`check-prelink-const-fit.py` / `.log` 可直接对新 native 复测，未写入镜像。

本轮检查点时间：2026-11-20T14:48:47+08:00（WSL）；改动 `scripts/test-pexpert-late-write-patch.py`、`docs/agent-progress.md`、`docs/STATE.md`。


#### WSL 实际原生构建结果（2026-11-20T15:01:16+08:00）

- 固定 LLVM 源码和 UniXNU builtin 补丁构建完成，Clang `24.0.0git` SHA-256 `471cd30e529f033c99e228aa19dba2d331e7a91122308ccbe2d13bb391d404af`。`-target arm64e-apple-ios27.0` 验证 `__builtin_xnu_type_summary` 成功。`run-after-llvm.sh` 用这个 Clang 和 `ld64-956.6` 复跑 `test-pexpert-late-write-patch.py --kernel-link`，结果仍通过，未见系统 Clang 18 的 arm64e ABI 警告；这仍只验证夹具，不是完整内核。
- `run-native.py native` 真实执行官方 DEVELOPMENT bootstrap（隔离树的 72 项补丁、基于有效 OS Profile 的本地 WSL 环境）。XNU `installhdrs` 完成；第一处阻塞是 `build-firehose.sh` 编译 `firehose_buffer.c`，经 `sys/ucred.h:164` 与 `os/base.h` 展开为四参数 `__ptrauth(..., "authenticates-null-values")`，编译器报 `__ptrauth qualifier must take between 1 and 3 arguments`；退出 1。`native-attempt.log` 与实验输出下 `logs/kernel-bootstrap.log` 保留完整实测。不是 console 补丁本身的编译失败；还未进入完整内核 C/C++ 编译、链接或 prelink。
- `bash check-ptrauth-schema.sh <上述 Clang>` 独立最小复现：同一 `arm64e-apple-ios27.0 -mkernel` 下普通三参数声明通过、四参数声明失败，退出 1。没有替换或禁用 PAC、没有删第四参数、没有混用旧供体。正确下一步是先用同一探针验证 26.6 Xcode 路线的 Apple Clang，或有等价语义及代码生成证据的 Linux 编译器；通过后在对应主机的隔离树继续：macOS 用 Apple Clang 的正常构建规则，Linux 才使用 `run-native.py native`；不要盲目重编当前 Clang。现有带强推步骤的 CI 未触发。两个后台任务都已退出，接手可直接检查 `native-attempt.log` 首个错误。无发布、无新 boot image、无实机测试或写入。
