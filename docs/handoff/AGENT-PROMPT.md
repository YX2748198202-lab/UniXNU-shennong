# 交接提示词（复制以下整段给电脑端 agent）

---

你要接手一个**已经在进行中**的工程，不要从零开始规划，也不要只给方案——直接在工作区动手执行，遇到失败就继续排查直到推进。

## 一、项目背景

把真实 iPadOS 17.7.11（21H461）移植到 **Xiaomi 14 Pro（代号 shennong，型号 23116PN5BC，SoC SM8650/pineapple，12 GB RAM）**。
方案的骨架是 UniXNU：用 UEFI（Mu-Silicium，代号 Project Silicium）加载 BootShim 与固件卷，再跳进 prelink 过的 XNU 内核，最后接 iOS 用户态。

**目标设备目前仍能正常开机（Android 16），它是唯一的测试机，不要把它弄成不能启动的状态。**

仓库（公开，直接 clone）：

```
https://github.com/YX2748198202-lab/UniXNU-shennong
```

## 二、你接手后必须最先读的两份文档

```
docs/handoff/BRINGUP-STATUS.md    # 完整进度、panic 根因、已证伪的路线、剩余步骤、硬件事实
docs/handoff/ARTIFACTS.md         # 产物清单与 sha256、二进制为何不入库、本地重建方法
```

`README.md` 顶部也有指向。**读完再动手**，那里面记着几条“已经踩过的坑”，重复踩会浪费几小时。

## 三、当前真实状态（截至 2026-10-30）

- ✅ 阶段 A 构建链：GitHub Actions 上 XNU 编译 + 链接稳定成功
- ✅ 阶段 B UEFI 实机：UniXNU loader 0.1.0 菜单能稳定显示
- ✅ 阶段 C **内核已经真正运行**：panic 从 `Failed to mount root device @IOKitBSDInit.cpp:984` 前移到 **`AppleARMCPU.cpp:111`「CPU configuration in device tree is invalid」**
- ✅ 阶段 D prelink：`kernel.macho` 已合并原厂 `com.apple.iokit.IOStorageFamily`
- 🟡 阶段 E UFS 块设备：11 个 `IOBlockStorageDevice` 符号**静态路线已彻底证伪**（详见文档第 7.1 节，两轮 CI 实测 `0/11`）
- ⬜ 阶段 F 用户态 / G 硬件功能：未开始

**当前唯一待办**：验证加了 `sheng-smp=1` 的内核能否过 `AppleARMCPU` 那一关。

## 四、下一步的具体动作

### 第 1 步：拿到待测镜像

镜像在测试设备上（不在仓库里，原因见 ARTIFACTS.md）：

```bash
adb devices                                    # 应看到 23116PN5BC
adb pull /sdcard/Download/Mu-shennong-smp.img .
```

校验：

```
203,726,848 字节
sha256 6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842
```

### 第 2 步：刷

```bash
fastboot devices
fastboot boot Mu-shennong-smp.img          # 只启动，不写入任何分区
```

### 第 3 步：按结果分支

- **panic 位置变了 / 过了 CPU 这关** → 记录新的 panic 点，继续往下推（大概率回到 `IOKitBSDInit.cpp:984`，那时才是 mockfs / UFS 的战场）
- **还是一模一样的 `AppleARMCPU.cpp:111`** → 改用**修法 B**：`sheng-smp=1` 是软方案（靠原生 ArmCpu 抢 probe），官方记录里它有时打不赢。硬方案是**改写 `kernel.macho` 里 AppleARMCPU personality 的 `IONameMatch`，把 `cpu` 改成 `xpu`**（等长替换，不移动任何字节）。参考 `docs/handoff/BRINGUP-STATUS.md` 第三节引用的 `unixnu/docs/.vitepress/device-records/sirius.toml:121` 和 `:422`。
- **panic 更早 / 黑屏** → 回退 `MOCKFS=n` 重新构建，隔离变量

## 五、几个必须知道的坑（文档里有，这里再点一遍）

1. **`unixnu payload` 产出的不是 boot image**，是 FAT 卷（ramdisk 内容）。CI 里没有 `bootimg` 步骤，所以 CI artifact 直接 `fastboot boot` 一定失败。
2. **`unixnu bootimg` 会生成 v4 header，这是坏的**。BootShim 需要 v0 header 的 `ramdisk_addr`（`0x1000000`）。v4 没有这个字段 → UEFI 找不到 payload FAT 卷 → `no boot entry found` → `Failed to Find an Operating System`。
3. **`bootimg.py` 的 `verify()` 有 bug**（第 122-123 行用 v0 布局解析 v4 镜像），必然抛 `boot image header does not match`，**但文件已经正确写出**。别被误导。
4. **可靠打包法**：用 `scripts/repack-v0-bootimg.py`，复用 `shennong/Mu-shennong-6-pmgr2.img` 的 v0 头 + kernel 区（前 2,400,256 字节），拼上新的 201,326,592 字节 payload。
5. **改 bootargs 不用重跑 CI**：`scripts/patch-payload-args.py` 能直接改 payload FAT 卷里的 `/EFI/UniXNU/unixnu.toml`，带读回校验。
6. **`sheng-smp=1` 尚未验证有效**，这是推断，不是实测结论。

## 六、硬约束（不可越界）

- **禁止** `fastboot flash`、`dd` 写分区、改分区表。测试一律 `fastboot boot`。
- **禁止**未经授权写 userdata。
- **禁止**提交 Apple IPSW、厂商固件、密钥，或任何含原厂 kernelcache 代码的二进制到公开仓库。仓库是 public。
- **禁止**用 stub、空心函数、全零密钥伪造验证结果（历史上 `verified_root_key={0}` + `vr_verify_block(){return1}` 已被要求删除，不要加回来）。
- 只在 Apple Silicon / macOS 上能做 XNU 编译的话就走 GitHub Actions（仓库已有 workflow），本地 Linux 用 `scripts/repack-v0-bootimg.py` 这类纯 python 工具。

## 七、工作方式要求

- 结论先行，再给依据。
- 区分「已实测证实」「推断」「未验证」三者，不要混为一谈。
- 每一步改动后要能自己验证（哈希、header 解析、读回校验），不要改完就交给人试。
- 如果某个报错消失，不要就此宣布“修好了”，要说清它消失的原因和剩下什么没验证。
- 需要用户配合的动作（刷机、拍屏幕）要给**可直接复制执行的命令**，并说明在哪台设备上执行。

## 八、设备与硬件事实（不要用参考机数值替代）

- codename `shennong`，model `23116PN5BC`，SoC `SM8650`（msm-id `0x22d`，board-id `0x08`），DRAM 起始 `0x80000000`
- UFS：`ufshc@1d84000`，reg `0x1d84000/0x3000`，MCQ SQD `0x1da5000/0x2000`，VS `0x1da4000/0x10`，SMMU SID `0x60`，逻辑块 4096 B，userdata LBA 2260480–64049146
- GICv3 dist `0x17100000` / redist `0x17180000`（stride `0x40000`）
- timer 19.2 MHz（`0x124f800`）
- 8 核：2×A520@2.27GHz + 5×A720 + 1×X4@3.30GHz
- Adreno 750（rev 2770）
- 官方 uefi_a 入口 `0xA7000000`，FD_BASE `0xA7100000`，FD_SIZE `0x300000`
- splash_region `0xFC400000 + 0x2B00000`

## 九、验收标准

这一轮算成功，指的是下面任一条：

1. panic 不再出现在 `AppleARMCPU.cpp:111`，且能拿到**新的、更靠后的** panic 或日志
2. 或者明确证明 `sheng-smp=1` 无效，并给出修法 B 的实现与验证结果

**不要**把“CI 绿了”“日志没报错”当成完成——只有真机现象变化才算进展。