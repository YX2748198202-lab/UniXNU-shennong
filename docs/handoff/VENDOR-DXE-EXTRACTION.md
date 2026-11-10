# 厂商 DXE：能不能用本机 abl 里的原厂驱动

结论先写：**这一版做不到**，`Binaries/giulia` 仍是替身。下面是把这件事查到底的全部证据，
以及下次换数据源时该怎么复用已经建好的工具。

## 一、工具（本轮新建，可复用于任何固件 blob）

| 工具 | 作用 | 自证 |
|---|---|---|
| `scripts/scan-uefi-fv.py` | 扫 FV → FFS → section 链，输出 GUID/类型/大小/UI 名，可 `--extract-guided` / `--extract-pe` | 解析我们自己的 FD 与 `FVMAIN.Fv`，列出 106 个文件、其中含 `UniXNU`(103,984 B)、`DarwinBoot`(33,846 B)、`PmicDxe`(274,540 B)、`UFSDxe`(143,414 B)、`BdsDxe`(385,166 B) |
| `tools/lzma-decode` | 用 EDK II 自己的 7-Zip SDK 解 LZMA guided 段（通用 xz 与 python-lzma 都会解错） | 解自建 `FVMAIN_COMPACT` 得 7,708,680 B，与 `Build/shennongPkg/DEBUG_CLANGPDB/FV/FVMAIN.Fv` **逐字节相同**（前面多 8 字节 section 头） |
| `scripts/test-scan-uefi-fv.py` | 合成 fixture 的结构契约测试 + 自建 FD 回归 | 全绿 |

顺带修掉一个真 bug：EDK II 的每个卷开头都有 **PAD 文件**（名字全 `0xFF`、类型 `0xF0`），
扫描器最初把「名字全 FF」当成「卷结束」，于是任何真卷都只报 0 个文件。现在按记录长度跳过 PAD。

## 二、本机 `abl_a` 里到底有什么

```
$ python3 scripts/scan-uefi-fv.py abl_a.bin
FV @0x1000 len=0x49000 guid=8c8ce578-8a3d-4f1c-9935-896185c32dd3 hdr=0x48
  FFS @0x1048 FIRMWARE_VOLUME_IMAGE size=0x46B06 9e21fd93-9c72-4c15-8c4b-e77f1db2d792
     GUID_DEFINED size=0x46AEE ee4e5898-3914-4259-9d6e-dc7bd79403cf lzma data_offset=0x18
1 volumes, 1 files, 0 with a UI name
```

- 整个 `abl_a`（8,389,735 B，`sha256` 记录在 `docs/agent-progress.md`）**只有一个 FV**，299,008 字节；
  里面**只有一个文件**：`9e21fd93-9c72-4c15-8c4b-e77f1db2d792`，也就是标准的 **FVMAIN_COMPACT**。
- 它的段是 EDK2 标准的 LZMA guided（`ee4e5898-…`，`DataOffset=0x18`，`Attributes=1`），
  载荷 289,494 字节，头部声明解压后 **1,343,688 字节**。
- `xbl_a`（8,393,597 B）里 **一个 FV 都没有**。

也就是说：shennong 的原厂 DXE 集合如果在本机固件里，就只能在这 1.34 MB 里。

## 三、这 1.34 MB 解不开（穷举过，不是没试）

先确认解码器本身是对的（见上表：自建卷解出来字节相同）。然后对 abl 的载荷做了穷举：

| 尝试 | 结果 |
|---|---|
| 标准 LZMA-Alone（13 字节头，`props=0x5D`、`dict=16 MiB`、`size=0x1480C8`） | 解出 **27 字节** 后 `SZ_ERROR_DATA` |
| `xz --format=lzma` | 同样只吐 27 字节 |
| 7-Zip `7za x -so` | 拒绝（`Cannot open the file as archive`） |
| 5 字节头假设（`props+dict`，流从 +5 开始） | 0 字节 |
| 12 字节 / 其他偏移 | 10 字节 / 0 字节 |
| **225 组 `props` 全枚举**（`--offset 13`） | 最好 **419 字节**（`props=0x5E`） |
| 8 组字典大小（4 KiB…64 MiB） | 恒为 27 字节 |
| `LZMA_FINISH_ANY`（容忍缺结束标记） | 仍 27 字节 |

27 字节这个数字很关键——它解出来的内容**与我们自己卷的开头完全同构**：

```
abl : 04 00 00 19 | c4 80 14 17 | 00×16 ...
ours: 04 00 00 19 | 04 a0 75 17 | 00×16 ...
```

前 4 字节是空的 RAW 段（size 4，type 0x19），接着是 `FV_IMAGE` 段头（type 0x17），
长度字段正好等于各自声明的解压大小（abl `0x1480C4`、ours `0x75A004`）。所以：

- 这段数据**确实是**用 EDK2 同一套封装压出来的，头部元数据是真的、能读懂；
- 但压缩流在**第 28 个字节处**就不再是合法 LZMA 了，两个独立实现同时在同一点失败。

最可能的解释是流被额外加密/变换过（小米 ABL 的签名流程），或者用了非标准的分块 LZMA 变体。
无论是哪一种，都不是「换个命令再试一次」能解决的，需要 ABL 的封装细节。

## 四、因此现在用谁

`Binaries/giulia`（一加，SM8650 / `LanaiPkg`）。本机 `abl` 取不出来，树里也没有第二个 SM8650 的
小米驱动集，横向对比可以看清风险面：

| 项 | giulia（在用） | muyu（小米 Pad 7 Pro，`PalawanPkg` = SM8635） |
|---|---|---|
| 平台包 | `Platforms/OnePlus/giuliaPkg` | `Platforms/Xiaomi/muyuPkg` |
| SoC 家族 | **SM8650（与本机同）** | SM8635（不同） |
| 驱动目录 / .efi / 体积 | 80 / 88 / 9.6 MB | 70 / 79 / 8.9 MB |
| 只在它这里有的 | `Oplus*`（厂商私有：`OplusStorageDxe`、`OplusVibrDxe`、`OplusSecurityDxe`…）、`OcdtDxe`、`OGaugeAuthDxe`、`XhciDxe`/`UsbBusDxe`/`UsbKbDxe`/`UsbMassStorageDxe`/`XhciPciEmulationDxe`、`PhoenixDxe`/`Phoenix2_0Dxe` | — |
| 只在它这里有的 | — | `BatterySecretDxe`、`ProjectInfoDxe`、`SPSSDxe` |

结论：**giulia 的 SoC 侧驱动（时钟、PMIC 总线、UFS、IOMMU、Display 控制器）与 shennong 同代同族**，
风险集中在两处：`Oplus*` 私有驱动（对本机无意义但也不致命）和**面板/PMIC 的具体配置**
（`DisplayDxe` 里的 panel init sequence、`PmicDxe` 里的 PMIC 型号表）。

## 五、下次从哪拿原厂驱动（三条路径，按可行性排序）

1. **本机 fastboot ROM 里的 `abl.elf`**：如果 ROM 包里的 `abl.elf` 与我们 dd 出来的分区内容不同
   （例如 ROM 里是未加密的），直接用 `tools/lzma-decode` + `--extract-pe` 抽出来。判断方法：
   `sha256` 比对，不同就试解压。
2. **同 SoC 小米机型的 abl**（`houji` = 小米 14、`manet` = K70 Pro）：同样是 SM8650，
   面板/PMIC 表与 shennong 更接近。取出它们的 `abl` 分区跑同一套工具即可。
3. **`Binaries/<dev>` 从别的 UniXNU 移植仓库拿**（houji 移植已经能进 iOS 桌面，说明它的驱动集可用）：
   如果 `lonzzi/UniXNU-houji` 里有 `uefi/overlay/Binaries/houji`，那是最省事的一条。

只要拿到可解的 1.34 MB，命令是现成的：

```sh
python3 scripts/scan-uefi-fv.py <abl.bin> --extract-guided /tmp/g
tools/bin/lzma-decode /tmp/g/lzma-*.bin /tmp/abl-fvmain.fv
python3 scripts/scan-uefi-fv.py /tmp/abl-fvmain.fv --extract-pe Binaries/shennong/QcomPkg/Drivers
python3 scripts/make-shennong-uefi-pkg.py --uefi <tree> --vendor-binaries shennong --force
bash firmware/build-shennong-uefi.sh
```
