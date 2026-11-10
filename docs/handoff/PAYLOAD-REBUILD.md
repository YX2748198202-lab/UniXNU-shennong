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
