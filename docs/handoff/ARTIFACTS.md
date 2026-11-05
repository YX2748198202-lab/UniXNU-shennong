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
| iPadOS 17.7.11 (21H461) IPSW | 根卷、kext、绑定测量都从它来 |
| `Mu-shennong-smp.img` 模板 | `repack-v0-bootimg.py` 复用它的前 2,400,256 字节（设备 `/sdcard` 已被覆盖，此模板现在只在电脑上） |
| 根策略私钥 | 重新生成策略头时才需要（`.artifacts/policy/root-key.rsa`） |
| `SILICIUM_UEFI.fd` | 重建 kernel 区时用（同样只在电脑上） |
| `backups/partitions/` | 87 个分区的只读备份，恢复 Android 用 |

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
