# UEFI 固件重建（shennong）

`shennong` 的 `SILICIUM_UEFI.fd` 不在任何仓库里，上游 Mu-Silicium 也没有 SM8650 小米平台包。
本文件是把它从源码造出来的**唯一可复现路径**，以及每次构建的校验值。

## 产物

| 文件 | 大小 | sha256 |
|---|---|---|
| `artifacts/UniXNU-shennong/firmware/SILICIUM_UEFI-shennong-DEBUG.fd` | 3,145,728 (0x300000) | `362aefb7bbe9ab30d35fe08cfe4b66149bc2d0fdf90f06c3c9dee8de000c5ae3` |
| `artifacts/UniXNU-shennong/boot/Mu-shennong-fd1.img` | 1,282,048 | `df5a759850d25172fab148b51ce15241e63701828f0738efdb8502f379819f09` |

`Mu-shennong-fd1.img` = 4096 字节 v0 头 + gzip(BootShim 192 B + FD) + （空 payload 段）。
只能验到 UEFI 菜单；要进 XNU 还需要 `payload.img`。

## 依赖位置

```
/home/yoox/android/sources/uefi-sheng        Mu 基树（UniXNU/uefi-sheng @ sheng，含子模块，1.5 GB）
/home/yoox/android/sources/DarwinBoot        UniXNU/DarwinBoot → 拷成 uefi-sheng/DarwinBootPkg
/home/yoox/android/workspace/UniXNU-pin      UniXNU 框架（提供 package/UniXNUPkg）
```

`uefi-sheng` 里必须存在：`Mu_Basecore/BaseTools/Source/C/bin/{GenFw,GenFfs,GenFv,GenSec,EfiRom,VfrCompile,LzmaCompress,BrotliCompress}`、
`DarwinBootPkg/Driver/DarwinBoot.inf`、`Platforms/Xiaomi/shennongPkg/`（生成物）、
`Resources/Configs/shennong.toml`（生成物）、`Resources/DTBs/shennong.dtb`（生成物）。

## 步骤

```sh
# 1) 本机 xbl_config → DDR/IO 区域表（区域 base/size 是大端 u64，脚本会校验不重叠）
adb shell 'dd if=/dev/block/by-name/xbl_config_a bs=1M 2>/dev/null' > xbl_config_a.bin
python3 scripts/extract-xbl-memory-map.py xbl_config_a.bin --toml --out firmware/shennong-memory-map.toml

# 2) 生成平台包（SM8650 骨架 giuliaPkg + 本机内存映射 + 小米/面板/SMBIOS + UniXNU 模块）
python3 scripts/make-shennong-uefi-pkg.py --uefi /home/yoox/android/sources/uefi-sheng \
  --vendor-binaries giulia --force

# 3) 构固件卷（直连 EDK II build，绕开 pytool 的 ext-dep 下载阶段）
bash firmware/build-shennong-uefi.sh

# 4) 组 boot image（无 payload = 菜单冒烟镜像）
python3 firmware/make-boot-image.py --uefi /home/yoox/android/sources/uefi-sheng \
  --fd /home/yoox/android/artifacts/UniXNU-shennong/firmware/SILICIUM_UEFI-shennong-DEBUG.fd \
  --out /home/yoox/android/artifacts/UniXNU-shennong/boot/Mu-shennong-fd1.img --verify
```

## 生成器做了什么（每项都有来源）

| 生成物 | 来源 |
|---|---|
| `Platforms/Xiaomi/shennongPkg/{dsc,fdf,dec,DeviceBuild.py,Include/*.inc}` | `Platforms/OnePlus/giuliaPkg`（同 SoC SM8650，源码构建）重命名 + 平台常量替换 |
| `Library/MemoryMapLib/MemoryMapLib.c` | `firmware/shennong-memory-map.toml`（本机 xbl_config 实测）；`UEFI_FD` 的 4 MB 跨度按 `FD_BASE/FD_SIZE` 切成三段 |
| 每行的 HobOption/ResourceType/ArmAttribute | 同 SoC 小米 houji 移植生成的同名区域策略 |
| `PcdSmbios*` / `PcdFrameBuffer*` | `23116PN5BC`、`Xiaomi 14 Pro`、`1440×3200`（`dts/shennong.dts` panel 节点） |
| DSC `[Components]`+`[LibraryClasses]`、FDF `[FV.FvMain]` | `UniXNUPkg/{Application/UniXNU,Driver/UniXNUDxe,Driver/UniXNURamDiskDxe,Driver/AdvancedLogDxe}`、`DarwinBootPkg/Driver/DarwinBoot`、`UniXNULib`、`AdvancedLoggerAccessLib`、`QrEncoderLib`、`HobLib`、`FdtLib`；已在 SoC 包里的 `DiskIoDxe`/`Fat` 不重复注入（否则 GenFv 报同 GUID） |
| `Resources/Configs/shennong.toml` | FD 基址/大小与 `board.toml` 一致；boot image 用 **header v0 + append_dtb**（v4 在 `fastboot boot` 场景拿不到 ABL 的 DTB） |

## 构建环境要点（不满足会报奇怪的错）

- `CLANG_BIN` 必须带尾斜杠（`/usr/bin/`），否则工具链被拼成 `/usr/binclang`。
- `PATH` 里要有名为 `python` 的解释器（BaseTools 的包装脚本写死 `python`）。
- `PACKAGES_PATH` 必须包含 `<tree>/Platforms/Xiaomi`、`<tree>`、`<tree>/Mu_Basecore`、
  `<tree>/{Common/Mu,Common/Mu_OEM_Sample}`、`<tree>/Silicon/{Qualcomm,Silicium}`、
  `<tree>/Silicium-ACPI{,/Platforms/OnePlus}`、`<框架>/package`。
- `LzmaCompress` 必须有：FVMAIN 用 LZMA 压进 3 MB 的 `FVMAIN_COMPACT`，
  缺它只会看到 `GenSec: Error opening …SEC1.tmp`。

## 已知缺口

1. **厂商 DXE 是替身**：`Binaries/giulia` 与 `Binaries/shennong` 属于同 SoC 不同机型；
   `PmicDxe`/`DisplayDxe`/`UFSDxe` 的面板序列与 PMIC 配置需要换成本机 `abl`/`xbl` 里的原厂模块。
   生成器已支持 `--vendor-binaries shennong`，只等把 `Binaries/shennong` 提取出来。
2. **FD 从未上机**：`Mu-shennong-fd1.img` 还没 `fastboot boot`。
3. **payload 缺失**：`payload.img` 已丢，需要先用框架产出（CI 或本地 payload 构建）。
4. `AdvancedLogDxe` 已编进 FV，但 QR 导出是否可用未验证。

## 校验清单（每次重建都跑）

```sh
stat -c %s .../SILICIUM_UEFI-shennong-DEBUG.fd        # 必须 3145728
ls .../Build/shennongPkg/DEBUG_CLANGPDB/FV/Ffs | grep -icE 'unixnu|darwinboot'   # 4
grep -E 'FVMAIN_COMPACT \[' .../logs/firmware-shennong-DEBUG.log   # 占用率 < 100%
python3 firmware/make-boot-image.py ... --verify        # 结构自检
```
