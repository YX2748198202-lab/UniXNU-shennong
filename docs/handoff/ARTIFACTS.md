# 产物清单与获取方式

**本项目目标：让 Xiaomi 14 Pro（shennong）运行 iOS 用户态。**

底座固件用的是 UniXNU 官方的 OS profile `ipados-17.7.11-21H461`
（`unixnu/profiles/os/` 下 2026-11-02 核对是三个 ipados-*，**没有 iOS profile**），
即 iPad Pro `iPad7,1` 的 IPSW。
XNU / IOKit / BSD 层同源，iOS 与 iPadOS 只在用户态套件与 UI 层不同，
所以这不影响「移植 iOS」这个目标；涉及具体文件时才会出现 `ipados-` 字样。

本仓库**只存源码、文档和脚本**。所有 Apple 派生的二进制（`kernel.macho`、`payload.img`、
boot image）**刻意不入库**——它们包含原厂 kernelcache 的代码段（prelink 后的
`kernel.macho` 里就有完整的 `com.apple.iokit.IOStorageFamily`），公开分发有版权风险。

---

## 一、设备上现在只保留三个文件

2026-10-30 做过一次清理，中间产物全部删除。留下的三个各有不可替代的作用
（下表是**上一轮的记录**；2026-11-02 的会话没有设备，未复核文件是否还在这三个位置）：

| 路径 | 大小 | 作用 |
|---|---|---|
| `/sdcard/Download/Mu-shennong-smp.img` | 203,726,848 | **待测产物**。v0 头 + gzip(BootShim+FD) + 含 `sheng-smp=1` 的 payload |
| `/sdcard/Download/shennong/Mu-shennong-6-pmgr2.img` | 203,726,848 | **v0 打包模板**。`repack-v0-bootimg.py` 复用它前 2,400,256 字节 |
| `/sdcard/Download/shennong/SILICIUM_UEFI.fd` | 3,145,728 | **UEFI 固件卷**（`0x300000` 字节）。重建 kernel 区时必需 |

`Mu-shennong-smp.img` 的 sha256：

```
6b1be67c03cafd75d77559297e9ac12f8e6bbaabff5b6ba3720f75befdba4842
```

---

## 二、一个镜像就够：从 boot image 里把所有东西拆回来

**这一点很重要**：`unixnu payload` 永远输出固定 201,326,592 字节（192 MiB）的 FAT 卷，
所以一个由 `repack-v0-bootimg.py` 打出来的 v0 镜像，内部就是

```
offset 0                                   v0 header（page = 4096）
offset 4096                                kernel  = gzip(BootShim + UEFI FD)
offset page + align(kernel_size, page)     ramdisk = payload FAT 卷（固定 192 MiB）
```

也就是说 `Mu-shennong-smp.img` **同时是一份完整的 payload 备份和内核备份**，
即使 CI artifact 过期也能还原：

```bash
python3 scripts/extract-payload-from-bootimg.py \
    --image Mu-shennong-smp.img \
    --out   payload.img \
    --kernel kernel.macho
```

2026-10-30 实测结果：

```
payload      201,326,592 bytes  sha256 9f7e97e67e436639a933de2d154abb9e910fac285c2f4c356861e03a987945f1
kernel.macho  51,970,048 bytes  sha256 af6de3cf30e70e4de90ef3693a1ed1a8e7c475d15b1dbae571047159d7e83b6b
```

其中 `kernel.macho` 的 sha256 **等于** `payload.json` 里的 `payload_kernel_sha256`，可交叉核对。

注意区分两件事：

- **payload 里的 `Payloads/kernel.macho`** 才是 XNU 内核（prelink 后），可从上表还原
- **boot image 的 kernel 区** 是 `gzip(BootShim + UEFI FD)`，属于 UEFI 层，不含 XNU。
  它来自打包模板，只有在 UEFI 代码更新后才需要用 `unixnu firmware` + 重新打包

---

## 三、CI artifact（备查）

最近一次产出 payload 与 kernel 的运行：

```
run 40868470568  (#87)  head dfd46906
artifact shennong-kernel-1  21,832,980 bytes
过期时间 2026-11-05T12:00:24Z（北京时间 11-05 20:00）
```

里面有 `payload/payload.img`（201,326,592 B）与 `kernel/kernel.macho`。
**不是必需品**——上面第二节的方法不依赖它。

注意：**artifact 里的 `payload.img` 不能直接 `fastboot boot`**，它是 FAT 卷不是 boot image；
CI 里没有、也暂时无法加 `bootimg` 步骤（原因见 4.3，本轮已核实）。

2026-11-02 起，`Build payload` 之后多了一步 `Patch AppleARMCPU IONameMatch (cpu -> xpu)`：
同一目录会多出 `payload-xpu.img` 与 `payload-xpu.json`，两者都会上传。拿到后照 4.2 打包，
或者直接对设备上的旧镜像用 4.4 的一步到位命令。

---

## 四、重建任何一个镜像

### 4.1 改 bootargs（不重跑 CI）

```bash
python3 scripts/patch-payload-args.py --payload payload.img --show
python3 scripts/patch-payload-args.py --payload payload.img \
    --add sheng-smp=1 --anchor sheng-pmgr=2
```

脚本用 `mtype` 读回校验，改不动就报错。

### 4.2 打成可刷的 v0 boot image

```bash
python3 scripts/repack-v0-bootimg.py \
    --template shennong/Mu-shennong-6-pmgr2.img \
    --payload  payload.img \
    --out      Mu-shennong-new.img
```

模板必须满足：

```
ANDROID! magic
header_version = 0
page          = 4096
kernel_size   = 2,393,623      (gzip 后的 BootShim + UEFI FD)
kernel_addr   = 0x8000
ramdisk_size  = 201,326,592    （必须与 payload 等大，header 才不用改）
ramdisk_addr  = 0x1000000
```

### 4.3 为什么不用官方 `unixnu bootimg`（2026-11-02 读源码更正）

**v4 header 不是代码行为，而是设备配置的选择。** `unixnu/scripts/unixnu/bootimg.py`：

```python
DEFAULTS = {'header_version': 0, 'base': 0, 'kernel_offset': 0x8000, 'tags_offset': 0x1e00000, 'pagesize': 4096}
def settings(ctx, uefi):
    config = load_toml(uefi / 'Resources/Configs' / f'{fw["config"]}.toml') if fw.get('config') else {}
    values = dict(DEFAULTS); values.update(config.get('boot_image', {}))
    values.update(ctx.board.get('bootimg', {}).get('image', {}))
```

所以：默认 v0；v4 来自 `Mu-Silicium Resources/Configs/<device>.toml` 的
`[boot_image] header_version`，或者本仓库 `[bootimg.image]` 的覆盖。BootShim 需要 v0 的
`ramdisk_addr`（`0x1000000`），v4 没有这个字段 → UEFI 找不到 payload FAT 卷
→ `no boot entry found` → `Failed to Find an Operating System`。

`verify()`（`bootimg.py:122-123`）按 v0 布局比较 `kernel_address`（偏移 12）；v4 头里那个位置是
`os_version`，所以对 v4 必然抛
`boot image header does not match the requested parameters`——**但文件已正确写出**。

**当前真正的阻塞点（本轮核实）**：`bootimg` 第一步就 `load_toml(uefi/Resources/Configs/shennong.toml)`。

```
GET /repos/UniXNU/uefi-sheng/contents/Resources/Configs/shennong.toml?ref=sheng -> 404
Resources/Configs/ 目录（87 个机型）里没有 shennong.toml
```

也就是说 shennong 的 Mu-Silicium 设备层（该 toml + FD + DTB）既不在本仓库，也不在
`uefi-sheng@sheng`。**在把这一层固化进仓库之前，CI 里加 `bootimg` 步骤无解**，
`[bootimg.image]` 写什么都没用。

若本机有能用的 shennong Mu-Silicium checkout，还要满足：

- 在 `board.toml` 加 `["bootimg"."image"] "header_version" = 0`（否则拿到 v4）
- `["bootimg"]` 的 `dtb_node` 清空成 `[]`，否则 `fdtput` 报
  `Error at 'splash_region': FDT_ERR_EXISTS`
- `--local <dir>` 下要有 `socs/sm8550/`，否则报 `SoC sm8550 is not cached`

### 4.4 打修法 B 补丁：AppleARMCPU 不再抢 `/cpus`

为什么需要、依据是什么，见 [BRINGUP-STATUS.md](BRINGUP-STATUS.md) 第 3 节。
工具：`scripts/patch-applearmcpu-ioname.py`。它把 `kernel.macho` 的 `__PRELINK_INFO` 里
`com.apple.driver.AppleARMPlatform` → `IOKitPersonalities` → `AppleARMCPU` 的
`IONameMatch` 从 `cpu` 改成 `xpu`；等长替换，**整个产物相对输入只差 1 个字节**。

```bash
# 不需要任何产物：离线自检（3 个夹具，含诱饵与幂等检查）
python3 scripts/patch-applearmcpu-ioname.py --self-test

# 设备上的镜像：先只看不改，再一步生成待测镜像（自动抽 payload、改 kernel、回写、重打包、读回校验）
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img --check
python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img \
    --out Mu-shennong-xpu.img --report Mu-shennong-xpu.json
fastboot boot Mu-shennong-xpu.img          # 只启动，不写分区
```

也可以只处理 payload 或裸内核：

```bash
python3 scripts/patch-applearmcpu-ioname.py --payload payload.img --out payload-xpu.img
python3 scripts/patch-applearmcpu-ioname.py --macho kernel.macho --out kernel-xpu.macho
```

脚本的自我保证（不满足就报错退出）：

- 结构 diff 必须**恰好一处**，路径必须是 `…/IOKitPersonalities/AppleARMCPU/IONameMatch`
- 值必须是 `cpu` → `xpu`，文件长度不变，变化字节数必须等于 1
- 别的 kext 里同名的 `"cpu"` 诱饵、`__TEXT` 里的诱饵字节都不动
- 已经打过补丁时返回 `already-patched` 并且不再改动（幂等）
- 找不到 AppleARMPlatform / 找不到字符串时**报错**，绝不静默通过

`mcopy` 回写用 `-p -m` 保留原 FAT 时间戳，因此产物可复现（同样的输入 + 同样的脚本
= 同样的 sha256）。实测记录见
[VERIFICATION-2026-11-02.md](VERIFICATION-2026-11-02.md) 第 4 节。

---

## 五、刷机与回退

```bash
fastboot boot Mu-shennong-new.img     # 只启动，不写任何分区
```

失败就长按电源键重启，系统不受影响。
**本项目禁止 `fastboot flash`、`dd` 写分区、改分区表。**

---

## 六、被清理掉的中间产物（仅供追溯，不必找回）

2026-10-30 删除，全部可重建或确认无价值：

| 文件 | 是否可重建 |
|---|---|
| `payload-mockfs.img` / `payload-smp.img` | ✅ 用第二节的方法从任意镜像提取，或 `patch-payload-args.py` 再打一次 |
| `kernel-mockfs.macho` | ✅ 同上（`--kernel`） |
| `sk1/`（CI artifact 解压） | ✅ 重新下 artifact 解压，或第三节 |
| `Mu-shennong-mockfs-v0.img` | ✅ 模板 + 上面的 payload |
| `Mu-shennong-mockfs.img` | — v4 头坏镜像，废弃 |
| `shennong/Mu-shennong-0..5*.img` | — 10-27 的调试中间产物，已被 `6-pmgr2` 覆盖 |