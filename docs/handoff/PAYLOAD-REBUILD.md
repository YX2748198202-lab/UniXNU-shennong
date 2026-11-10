# payload 重建（离线）

`payload.img` 是 boot image 里那一段 FAT 卷，装载器（`Payloads/DarwinBoot.efi`）在里面找内核、
ADT 和菜单配置。这一轮把它从「CI 专属产物」变成了本机就能出的东西。

## 产物

| 文件 | 大小 | sha256 | 说明 |
|---|---|---|---|
| `payload/payload.img` | 201,326,592 | `30aa035a0aa61000a33172d2216962823036ae6cbed6500b26a033474d153b97` | 192 MiB，与 `board.toml [payload] size_mib` 一致（生产形状） |
| `payload/payload-64m.img` | 67,108,864 | `d534e93d661d7d115d74cb4d63055336d54a30cb1fbf9351ddd70c1914bbcce8` | 64 MiB，只为让 `fastboot boot` 快一点，内容相同 |
| `boot/Mu-shennong-fd2.img` | 68,390,912 | `de9a4cd8b11b4c46982e909db09c5e6363a130e9f29ff60747991d5e0c93b4dd` | 完整镜像：gzip(BootShim+FD) + 64 MiB payload |

卷内（用 mtools 从**镜像内部**读回复核，不是看暂存目录）：

```
Volume SHENNONGESP, serial 5348-4E47, 所有时间戳 1980-01-01
EFI/UNIXNU/unixnu.toml                     549
EFI/UNIXNU/PAYLOADS/DarwinBoot.efi      33,792   7463bf2d046f14cd
EFI/UNIXNU/PAYLOADS/kernel.macho.adt    10,416   9797959b38bfcb12
EFI/UNIXNU/PAYLOADS/kernel.macho    52,068,352   cceb91703b80124b
```

`unixnu.toml` 的 `[[driver]] path = "Payloads/DarwinBoot.efi"` 与
`[[entry]] path = "Payloads/kernel.macho"` 都在，`args` 与 `board.toml [payload] kernel_args`
逐字一致（契约测试会断言这一点）。

## 为什么不用框架的 `unixnu payload`

框架的 `scripts/unixnu/payload.py` 要求两样本机拿不出来的东西：

1. `build/sheng-source-storage/root-policies.bin`（`board.toml [payload] root_policies`）——
   这是从 iOS 27 IPSW 的 root policy 生成的，随 iOS 27 payload 一起丢了，仓库里没有生成脚本
   （只有消费方 `package/SourceRootPolicies.cpp`）。
2. `ctx.tree`——框架要先 `unixnu tree` 组装工作树（`work/` 目前是空的）。

所以 `firmware/make-payload-image.py` 直接按**同一个卷布局**写：一样的
`EFI/UniXNU/{unixnu.toml,Payloads/*}`、一样的 `mformat -C -F -T <sectors> -v <label> -N 53484e47`
+ `mcopy -s -Q -m`、一样的 1980-01-01 时间戳、一样的 95% 容量上限断言。装载器分辨不出是谁写的。

ADT 用设备自己的 `scripts/make-shennong-adt.py`（离线、SM8650 专用），参数取自 `board.toml`
（`dram_size`、`owned_memory_size`、`psci_method`、`cpu_regs`、`root_match_volume_uuid`）。

## 命令

```sh
# 1) 内核：legacy iPadOS 17 内核（iOS 27 内核到位后换掉 --kernel 即可）
unzip -o -j artifacts/UniXNU-shennong/legacy-ipados17/k8.zip \
  'out/shennong/ipados-17.7.11-21H461/shennong/kernel/kernel.macho' -d artifacts/UniXNU-shennong/legacy-ipados17/kernel

# 2) payload（DarwinBoot.efi 来自固件构建产物）
python3 firmware/make-payload-image.py \
  --kernel artifacts/UniXNU-shennong/legacy-ipados17/kernel/kernel.macho \
  --darwinboot sources/uefi-sheng/Build/shennongPkg/DEBUG_CLANGPDB/AARCH64/DarwinBoot.efi \
  --out artifacts/UniXNU-shennong/payload/payload-64m.img --size-mib 64 --verify

# 3) boot image
python3 firmware/make-boot-image.py --uefi sources/uefi-sheng \
  --fd artifacts/UniXNU-shennong/firmware/SILICIUM_UEFI-shennong-DEBUG.fd \
  --payload artifacts/UniXNU-shennong/payload/payload-64m.img \
  --out artifacts/UniXNU-shennong/boot/Mu-shennong-fd2.img --verify
```

## 验证（都跑过）

1. `--verify`：从写完的卷里 `mtype` 每个文件，逐个 sha256 与源文件比对。
2. 端到端：从 `Mu-shennong-fd2.img` 的 `0x139000` 处取出 64 MiB，sha256 与
   `payload-64m.img` **完全相同**，再用 `mdir` 列出卷内文件（见上表）。
3. `firmware/test-make-payload-image.py`：布局/菜单/`loader = payload` 缺 `--darwinboot` 必须报错/
   容量上限/非 Mach-O 内核拒绝/两次运行的可重复性（下一条）。

## 一个诚实的瑕疵

本机 `mformat` 会在镜像**最后一个扇区**留下约 19 字节未初始化内存，所以同一个输入跑两次，
镜像不是逐字节相同（文件内容、引导扇区、目录项都一致）。装载器不读那块区域；契约测试因此
断言「引导扇区 + 每个文件内容可复现」，而不是「整镜像可复现」。

## 还缺什么才能真进 XNU

| 缺的东西 | 影响 | 怎么补 |
|---|---|---|
| iOS 27 `kernel.macho` | 现在装的是 iPadOS 17.7.11 内核，与 `board.toml` 的 payload 配置（`kt_fixed_zones`、`sheng-*` 参数、prelink 补丁）不是同一套 | CI 的 `kernel.yml` 再产一次；拿到后只换 `--kernel` |
| `kernel.macho.trustcache` | 没有信任缓存，AMFI 会在启动早期拒绝 | 从 iOS 27 IPSW 提取，`board.toml` 已固定 sha256 `7416ca4f…` |
| `kernel.macho.vroot`（root policies） | `native-source-storage=1` 的根卷策略缺失，`/chosen` 里没有 RootPolicies 槽 | 随 IPSW 一起重新生成 |
| 真机验证 | 一次都没 `fastboot boot` | 等你在场 |

`--trust-cache` / `--vroot` 参数已经就位，拿到文件直接加参数重跑即可。

---

# 追加（同一轮）：找回 trust cache 与补丁内核，产出 fd3 镜像

## 找到的东西

`artifacts/UniXNU-shennong/legacy-ipados17/out/shennong/ipados-17.7.11-21H461/shennong/payload/payload.img`
（201 MB，2026-11-05 由框架产出）里还留着三样关键输入，已用 mtools 抽到
`legacy-ipados17/payload-extracted/`：

| 文件 | 大小 | sha256 | 与 board.toml 的关系 |
|---|---|---|---|
| `kernel.macho.trustcache` | 61,356 | `7416ca4f8377146626bb284e2133c76bee6cb4e3ee0af5d648b186235a7323a7` | **与 `[payload] trust_cache_sha256` 完全一致** |
| `kernel.macho.adt` | 10,468 | `d944136d…`（旧版本，内核参数是旧的那一套） | — |
| `kernel.macho`（已打补丁） | 52,068,352 | `0fb4ddd2abb27bafe7d9efeff9bb154a12e7383c15a25894212a0c922a03e7a3` | 与 `payload.json` 记录的 `payload_kernel_sha256` 一致 |

也就是说：旧 payload 里的内核是**打过 panic screen/入口探针补丁的**，不是原始内核。

## 补回一个仓库级 bug

`scripts/patch-xnu-entry-probe.py` 在 `--panic-screen` 分支里编译 `scripts/xnu-panic-screen.c`，
但**这个文件在设备仓库里不存在**（框架 `UniXNU-pin/scripts/xnu-panic-screen.c` 才有）。
所以在这台机器上重打补丁一定失败：

```
clang: error: no such file or directory: 'scripts/xnu-panic-screen.c'
```

已把框架那份（302 行，用 `VINFO`/`MAX_MEM`/`PAGE_TOTAL`/`PAGE_FREE` 宏）复制进
`scripts/xnu-panic-screen.c`。重打补丁即可成功：

```
UNIXNU_UEFI=/home/yoox/android/sources/uefi-sheng \
  python3 scripts/patch-xnu-entry-probe.py <kernel> --panic-screen --no-reset
→ stage 1 blue bar, stage 2 magenta bar, no reset probe,
  panic screen (0xa2f bytes at 0xfffffff0073f45c0; common funnel at 0xfffffff007279520)
```

结果与旧 payload 里的内核**不逐字节相同**（`fa362e24…` vs `0fb4ddd2…`）：旧产物是 11-05 用当时的
参数与当时的脚本打的，无法反推全部参数。可核实的是补丁本身是自洽的——大小不变
（52,068,352），只有 2,316 字节不同，集中在两处：文件偏移 `0x275520`（common funnel 的 4 字节
BL 改写）与 `0x3F04xx`–`0x3F45xx` 的 cave 区。

## fd3：目前最好的镜像

```sh
python3 firmware/make-payload-image.py \
  --kernel artifacts/UniXNU-shennong/legacy-ipados17/kernel/kernel-panoscreen.macho \
  --trust-cache artifacts/UniXNU-shennong/legacy-ipados17/payload-extracted/kernel.macho.trustcache \
  --darwinboot sources/uefi-sheng/Build/shennongPkg/DEBUG_CLANGPDB/AARCH64/DarwinBoot.efi \
  --out artifacts/UniXNU-shennong/payload/payload-fd3.img --size-mib 96 \
  --json artifacts/UniXNU-shennong/payload/payload-fd3.json --verify
```

| 产物 | 大小 | sha256 |
|---|---|---|
| `payload/payload-fd3.img` | 100,663,296（96 MiB） | `f1e47d3289db747a3f3f54b0b77844fd8d081be38f13b931618cd7a17a19034f` |
| `boot/Mu-shennong-fd3.img` | 101,945,344 | `e167a901df59d39ca2bda923d9009d7b48c9897a1ba96bb6a194d0f49360fb86` |

卷内（从镜像 `0x139000` 处读回，sha256 与源文件逐个相同）：

```
DarwinBoot.efi              33,792   7463bf2d046f14cd
kernel.macho            52,068,352   fa362e24b3cb327b
kernel.macho.adt            10,468   457de8638b546705   ← 带 trust cache 槽位
kernel.macho.trustcache     61,356   7416ca4f83771466   ← 与 board.toml 允许值一致
unixnu.toml                    549   6a4e345e9b9996fd
```

仍未验证：一次都没 `fastboot boot`。
