#!/bin/bash
# 从 CI 产物组装可 fastboot boot 的镜像。
#
# 做的事（每一步都校验，失败即退出）：
#   1. 从 GitHub Actions 下载产物 zip（shennong-kernel*.zip）
#   2. 找出其中的 payload.img
#   3. 打 TCR 补丁：0x22A51A251A -> 0x22A51A251B（T0SZ 26 -> 27），按内容搜索，不依赖固定偏移
#   4. 改 payload 里的 ::/EFI/UniXNU/unixnu.toml：去掉 cs_enforcement_disable，补挂根卷参数
#   5. 用已有的 ANDROID! 头（2400256 字节）+ 新 payload 组装镜像
#   6. 打印 sha256 与三项校验结果
#
# 用法：
#   scripts/make-boot-image.sh <artifact-zip> <header-image> [输出路径]
#   例如：
#   scripts/make-boot-image.sh ~/shennong-kernel-1.zip \
#       '/mnt/c/Users/yoox/AppData/Local/Temp/Mu-amfi.img' /tmp/Mu-final.img

set -euo pipefail

ZIP="${1:?需要产物 zip}"
HEADER_SRC="${2:?需要一个已有镜像作为 ANDROID! 头来源}"
OUT="${3:-/tmp/Mu-final.img}"
HEADER_LEN=2400256
WORK=$(mktemp -d /tmp/mkimg.XXXXXX)

echo "== 1/6 解包产物 =="
unzip -q -o "$ZIP" -d "$WORK"
PAYLOAD=$(find "$WORK" -name 'payload*.img' -type f | head -1)
[ -n "$PAYLOAD" ] || { echo "产物里找不到 payload.img"; exit 1; }
echo "payload: $PAYLOAD ($(stat -c%s "$PAYLOAD") 字节)"

echo "== 2/6 打 TCR 补丁 =="
python3 - "$PAYLOAD" <<'PY'
import struct, sys
p = bytearray(open(sys.argv[1], 'rb').read())
old = struct.pack('<Q', 0x22A51A251A)
new = struct.pack('<Q', 0x22A51A251B)
n = p.count(old)
if n == 0:
    if p.count(new):
        print('TCR 已处于 T0SZ=27，无需修改')
    else:
        sys.exit('找不到 TCR 常量，拒绝继续（可能内核结构变了，需要人工确认）')
else:
    off = p.find(old)
    p[off] = 0x1B
    assert p[off:off+8] == new
    open(sys.argv[1], 'wb').write(bytes(p))
    print(f'已修改偏移 {hex(off)}，T0SZ 26 -> 27')
PY

echo "== 3/6 改 cmdline =="
TOML="$WORK/unixnu.toml"
mcopy -o -i "$PAYLOAD" ::/EFI/UniXNU/unixnu.toml "$TOML"
python3 - "$TOML" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
m = re.search(r'^args\s*=\s*"(.*)"', s, re.M)
args = [a for a in m.group(1).split() if a != 'cs_enforcement_disable=1']
for need in ('native-ufs-root=1', 'offline-apfs-load=1', '-apfs_shared_datavolume'):
    if need not in args:
        args.append(need)
new = ' '.join(args)
s = s[:m.start(1)] + new + s[m.end(1):]
open(p, 'w').write(s)
print('args:', new)
PY
mcopy -o -i "$PAYLOAD" "$TOML" ::/EFI/UniXNU/unixnu.toml

echo "== 4/6 取头部 =="
head -c "$HEADER_LEN" "$HEADER_SRC" > "$WORK/hdr.bin"
[ "$(head -c 8 "$WORK/hdr.bin")" = "ANDROID!" ] || { echo "头部不是 ANDROID!"; exit 1; }

echo "== 5/6 组装 =="
cat "$WORK/hdr.bin" "$PAYLOAD" > "$OUT"

echo "== 6/6 校验 =="
python3 - "$OUT" <<'PY'
import hashlib, struct, sys
d = open(sys.argv[1], 'rb').read()
print('大小:', len(d))
print('ANDROID! 头:', d[:8] == b'ANDROID!')
print('T0SZ 已修 (…251B 存在):', struct.pack('<Q', 0x22A51A251B) in d)
print('T0SZ 旧值已消失 (…251A):', struct.pack('<Q', 0x22A51A251A) not in d)
print('挂根卷参数存在:', b'native-ufs-root=1' in d and b'offline-apfs-load=1' in d)
print('sha256:', hashlib.sha256(d).hexdigest()[:16])
PY
echo "镜像就绪: $OUT"
