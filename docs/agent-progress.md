# Agent 进度记录（机器可读的接续入口）

最后更新：2026-11-10 17:10 CST
本轮执行者：DSH Agent（接管轮）

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
