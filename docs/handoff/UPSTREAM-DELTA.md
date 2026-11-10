# 上游 pin 与 main 的差异、以及本仓库对迁移规范的符合度

本文件记录两件事：CI 固定的上游 pin（`c740efb5`）与上游 main 的真实差异，以及设备仓库
相对 `docs/porting/migration.md` 要求的缺口。所有数字都是本轮在本机用 git 重新算的，
不是从旧笔记抄的。

## 1. pin 与 main 的差异（实测）

```
git diff --shortstat c740efb5b23e94453bb179f7801eb592baafacf6 d830d23b0d19c9322d906c21afeca1d6c54aeffe
 210 files changed, 11825 insertions(+), 4641 deletions(-)
```

改动集中的目录（前 10）：

| 目录 | 文件数 |
|---|---|
| `docs/zh` | 48 |
| `profiles/os` | 26 |
| `scripts/appsync` | 17 |
| `docs/porting` | 15 |
| `docs/devices` | 12 |
| `docs/drivers` | 11 |
| `patches/xnu-12377` | 10 |
| `docs/.vitepress` | 10 |
| `scripts/unixnu` | 6 |
| `patches/xnu` | 3 |

结论：

* 本仓库**没有** submodule（`git ls-tree c740efb5 | awk '$2=="commit"'` 为空），所以早期笔记里
  "11 个子模块指针变化"的说法不成立，已作废。
* `patches/` 与 `profiles/os/` 有改动，说明 pin 与 main 之间**内核补丁集不同**；这两个目录正是
  shennong 构建实际消费的东西，因此升级 pin 必须伴随一次可验证的内核构建。

### 1.1 pin → main 的补丁增删

* 删除：`patches/`、`profiles/os/`、`scripts/unixnu/` 下无文件被删除。
* 新增（`patches/xnu-12377/`，5 个）：
  `native-at-par-sync.patch`、`native-modload-lock-order.patch`、`native-pac-arm64-user-jop.patch`、
  `native-union-readdir-eof.patch`、`native-union-statfs-fsid.patch`。
* 新增（`profiles/os/`）：`macos-27.3-26C5035r` 整包（与手机无关）。
* 设备仓库 `profiles/os/ios-27.0.1-24A446-iphone16pro/patches/xnu/series` 引用的 4 个补丁
  （`zzz-boot-progress`、`darwin26-syscalls`、`darwin26-kpi`、`darwin26-shared-region`）
  在 pin 与 main **都存在**，升级不会踩空。

### 1.2 与当前卡点直接相关的两个补丁

| 补丁 | pin | main | 作用 |
|---|---|---|---|
| `native-pac-keys.patch` | 有 | 有 | 给 `arm64/pac_asm.h` 的 `PAC_INIT_KEY_STATE` 加 `HAS_NATIVE_PAC` 分支：用 `CNTPCT_EL0` + splitmix64 派生 10 个密钥字，落在 `__DATA` 的 `native_pac_keys`，并把 APIA/APIB/APDA/APDB/APGA 写进架构寄存器；存储用 `adrp/add` 相对寻址，所以 MMU 关闭时也能落到物理地址。**这解释了为什么 payload 的 pre-MMU 窗口里会出现 "PAC key seed from cntpct_el0"、"msr apiakeylo_el1" 这些站点**（见 `docs/handoff/PRE-MMU-STOPS.md`）。 |
| `native-pac-arm64-user-jop.patch` | **无** | 有 | 处理 arm64 线程在 EL0 关闭 PAC 键、回到 EL1 需要重新打开的问题（`SCTLR_PAC_KEYS_ENABLED`、`HAS_NATIVE_PAC`）。这是**过 MMU、进用户态之后**的问题，与当前 pre-MMU 停点无关，但一旦内核能起来就是下一个必修项。 |

`HAS_NATIVE_PAC` 的定义方式值得注意：pin 里它只出现在 `patches/xnu-12377/native-pac-keys.patch`
（`pexpert/pexpert/arm64/BCM2837.h` 的 `#if defined(__arm64e__)` 分支）与 `native-arm-pan.patch`。
也就是说，arm64e 构建要拿到这套 PAC 代码，必须走到那个板级头。当前 payload 里确实出现了
`cntpct` 派生 + 键寄存器写入（旧笔记的方格表里已记录这两个站点地址），说明本构建确实编译了
`HAS_APPLE_PAC` + `HAS_NATIVE_PAC`；但**具体由哪个头提供宏定义，本轮没有定位到**（未验证项）。

## 2. pin 升级策略

建议：**暂不升级**，直到满足下面三条之一：

1. 需要 main 独有的补丁（目前唯一相关的是 `native-pac-arm64-user-jop.patch`，属过 MMU 之后的工作）；
2. pin 与新 XNU 版本不匹配（现在都是 `xnu-12377.121.6`，没有这个问题）；
3. 有可验证的内核构建（本机无 macOS，只能靠 CI）。

升级动作本身很小（`kernel.yml` 里一处 `ref`），但会同时换掉 `patches/xnu-12377` 10 个文件与
`profiles/os` 26 个文件，属于"改了就要重新验一遍"的改动。若将来要升，步骤是：改 `ref` →
`workflow_dispatch` 构建 → 与本次 pin 的构建产物比对 `kernel.macho` 的段/symbol 数量与
`payload.json` 的哈希 → 上机。

## 3. 设备仓库对迁移规范的缺口（逐条实测）

规范示例（`docs/porting/migration.md:204`、`docs/porting/device-repository.md:152`）要求
`[kernel] patch_series` 有四层：

```toml
patch_series = ["arch:patches/xnu/series", "soc:patches/xnu/series",
                "os:patches/xnu/series", "device:patches/xnu/series"]
```

本仓库 `board.toml:45` 只有前三层。框架只解析**声明过的**层（`scripts/unixnu/patches.py:12`
遍历 `patch_series`），所以仓库自带的 `patches/xnu/series`（`zzzz-diag-marks.patch`）**从未被应用**。

### 3.1 这份板级补丁现在是坏的，不能直接接上

本轮做了离线验证（`xnu-12377.121.6` 的 `startup.c` 取自
`apple-oss-distributions/xnu` 的同名 tag）：

1. `patches/xnu/zzzz-diag-marks.patch` 对**原始** `startup.c` 应用失败（`startup.c:657`）。
2. 先应用 arch 层的 `zzz-boot-progress.patch`（它是唯一改 `startup.c` 的前序补丁）后，
   `zzzz-diag-marks.patch` **仍然**在同一位置失败。
3. `zzz-boot-progress.patch` 单独应用于 `startup.c` 是干净的（新增 2 处 `boot_progress_stage`）。

结论：`zzzz-diag-marks.patch` 是在一个已经被改过的 `startup.c` 上生成的，与当前树不匹配；
把 `device:patches/xnu/series` 直接加进 `patch_series` 会让内核构建在打补丁阶段就失败。
处理办法（本轮只记录，不动手）：要么按当前树重做这份补丁，要么删掉它、把需要的诊断点并进
已有的 `zzz-boot-progress.patch` 语义里。

### 3.2 其它缺口

| 规范要求 | 本仓库 | 说明 |
|---|---|---|
| `AGENTS.md` | 缺 | 所有者明确不希望每个项目再加项目级 AGENTS.md，属有意省略 |
| `scripts/package.sh` | 缺 | 打包走 `.github/workflows/kernel.yml` + `firmware/make-boot-image.py` |
| `proprietary-files.txt` | 缺 | 本移植不带厂商 blob（UFS/SMMU 走源码实现） |
| `local.toml.example` | 缺 | 无本地覆盖需求 |
| `unixnu.lock` | 缺 | 依赖由 `feeds.toml` 的 pin 固定，尚未生成 lock |
| `.github/workflows/porting-record.yml` | 缺 | 规范要求的记录流水线没有装 |
| `.github/workflows/package.yml` | 缺 | 同上 |
| `.gitmodules` | 缺 | 本仓库无 submodule（上游也没有） |

这些缺口不影响当前构建（`kernel.yml` 是自足的），但会让 `porting-record check` 之类的规范
检查报错。优先级低于"内核能否起来"，本轮不改。
