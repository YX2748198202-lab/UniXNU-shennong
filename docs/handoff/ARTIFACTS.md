# 产物清单与重建方式

本仓库只存源码、文档和脚本。所有 Apple 派生的二进制（`kernel.macho`、`payload.img`、
boot image、根卷镜像）**刻意不入库**：它们包含原厂 kernelcache 的代码段，公开分发有
版权风险。签名私钥同理不入库。

## 当前一轮的产物（2026-11-05，阶段 E3）

| 产物 | 位置 | 字节 | sha256 |
|---|---|---|---|
| 启动镜像（策略包版） | `.artifacts/shennong/policy1/Mu-policy12.img` | 203,726,848 | `0f598ca54a59317985f9ebd83f024a2a0cd74c11447025392f145fd289f76a65` |
| 根卷镜像（已在手机 userdata） | `…/userdata/userdata-root.img` | 9,456,697,344 | `91d7a4591ab1bb7e86259402af58ffc9eeeabce7de48b89753fa14c788ccf4c2` |
| 根卷镜像副本（给 Windows fastboot 用） | `D:\unixnu\userdata-root.img` | 9,456,697,344 | 同上 |
| 内核构建 | Actions run `42003983808`，artifact `13403917953` | 41,973,584 | — |
| 绑定表（CI 产物） | `scripts/prelink-storage-bindings.json`（已入库，含 `slide_applied`） | 1,439 | — |

入库的小文件（公开完整性数据，非机密）：

| 文件 | 字节 | sha256 |
|---|---|---|
| `policies/verified-root-key.bin` | 395 | `432feb26441ff873ce4a4251ff151e31f47c561fe0107f80692860b7b5542d33` |
| `policies/OS.policy` | 544 | `95c186cbe76bc1abd228d2a3449ff1cfad0eb084b9fa2a7238980b8ce64022d6` |
| `policies/SystemOS.policy` | 544 | `2f5d00e87b6732adf2b6cef322227509823279217fff3b5c4696a95ffc68e3f7` |

## 必须在本地保留的东西

| 东西 | 为什么 |
|---|---|
| iPhone 17,1 iOS 27.0.1 (24A446) IPSW | **当前供体**：内核、kext、信任缓存都从它来 |
| iPadOS 17.7.11 (21H461) IPSW | 历史供体（A–E 阶段的根卷、kext、绑定测量来自它），iOS 27 线重做根卷前仍需对照 |
| `Mu-shennong-smp.img` 模板 | `repack-v0-bootimg.py` 复用它的前 2,400,256 字节（设备 `/sdcard` 已被覆盖，此模板现在只在电脑上） |
| 根策略私钥 | 重新生成策略头时才需要（`.artifacts/policy/root-key.rsa`） |
| `SILICIUM_UEFI.fd` | 重建 kernel 区时用（同样只在电脑上） |
| `backups/partitions/` | 87 个分区的只读备份，恢复 Android 用 |

## 2026-11-08 产物（iOS 27 供体，阶段 A 复验）

| 产物 | 位置 | 字节 | sha256 |
|---|---|---|---|
| 启动镜像（loader 协议修复 + iOS 27 payload） | 本机 `/tmp/Mu-fix-protocol.img` | 203,726,848 | `e4375a77aa6ce9747f5b930b3ddbb89c0434c1bbb3df7d17336ecffb4db5efe7` |
| v0 模板（前 2,400,256 B 复用） | `%TEMP%\unixnu-shennong\Mu-shennong-smp.img` | — | — |
| 内核 + payload | Actions run `42462550406`，artifact `shennong-kernel-1` | 299,154,030 | — |
| 诊断内核（进度屏打开） | Actions run `42468975624`（提交 `4f12b68`） | — | 构建中 |

要点：

- `board.toml` 的 `[payload] loader` 必须是 `"payload"`：本机固件自带的是旧版 DarwinBoot
  （拒绝 arm64e，并且已经占住 `gUniXNULoaderProtocolGuid`），内核必须随 payload 注入，
  由 `4484825` 卸载旧实例后再安装。
- `XNU_BOOT_PROGRESS=1` 由 CI 的 `Build kernel` 步骤 `env` 给出（`4f12b68`）。本地重编内核
  时同样要显式带上；缺了它内核只是被强制链入归档，`boot_progress_*` 调用点全是空操作，
  屏幕在 handoff 之后不会变化。
- 本次上机只用 `fastboot boot`，未写任何分区。

### 2026-11-08 入口探针镜像（本地现打，不改内核源码）

| 镜像 | 用途 | 字节 | sha256 |
|---|---|---|---|
| `Mu-stage3.img` | stage 3：MMU 打开后 6 秒复位（证明入口执行）| 203,726,848 | `e8f593b54c8c86db22da47deec764189aa3f49fc4ae0d697e1291dd1a2b5137a` |
| `Mu-ms.img` | stage 4：`_machine_startup` 调用前复位（二分）| 203,726,848 | `45f588ecd479ed4e477d2cd80197e740f66bb4d34486c08dba380bc9e837ea35` |
| `Mu-ladder.img` | 六个里程碑色带，照片判读卡点 | 203,726,848 | `4a9a54506a263e5d299fdc7177a51a7a3a5276d68828874b8cba22d537e4824e` |

构造方式：取 CI artifact 里的 `payload/payload.img` 与 `kernel/kernel.macho`，
用 `scripts/patch-xnu-entry-probe.py`（stage 3/4）或本地 `patch-milestones.py`（色带）
改内核副本 → `mcopy` 覆盖 payload 里的 `kernel.macho` → `repack-v0-bootimg.py`
套 `Mu-shennong-smp.img` 模板。payload 阶段没有再封 corecrypto POST（CI 日志里也没有该步骤）。

## 重建步骤

```bash
# 1. 内核与 payload（CI）
Actions → "kernel" → Run workflow
#   产出 shennong-kernel-1（kernel/payload）与 storage-bindings

# 2. 根卷（本机，需要 IPSW）
./unixnu build userdata

# 3. 根策略（本机，需要根卷与私钥）
python3 scripts/make-root-policy.py --image userdata-root.img \
  --report userdata-root.json --key root-key.rsa --out <dir>
python3 scripts/add-root-policy-objects.py --image userdata-root.img \
  --object OS.vroot=<dir>/OS.vroot --object SystemOS.vroot=<dir>/SystemOS.vroot

# 4. boot image（本机，需要模板）
python3 scripts/patch-payload-args.py --payload payload.img --set-args "<参数>"
python3 scripts/repack-v0-bootimg.py --template Mu-shennong-smp.img \
  --payload payload.img --out Mu-<variant>.img
```

## 为什么 boot image 不由 CI 产出

CI 只产出 `kernel.macho` 与 `payload.img`。boot image 的组装（header v0 +
gzip(BootShim+FD) + append_dtb）需要固定模板，而模板来自本机（UEFI 固件不在仓库）。
详见 [BRINGUP-STATUS.md](BRINGUP-STATUS.md) 的「已废弃路线」一节。
