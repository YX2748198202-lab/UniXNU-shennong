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
