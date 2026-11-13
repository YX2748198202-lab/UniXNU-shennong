#!/usr/bin/env python3
"""把 fi102 的完整内核补丁应用到一份原始 kernel.macho 上。

fi102 是 2026-11-14 凌晨的可启动基线：MMU 开启、arm_init 尾部 console 初始化跑通、
内核能把 panic 打到屏幕（fi101 首次实现该通道）。

用法:
    python3 scripts/apply-fi102-patch.py PRISTINE_KERNEL OUT_KERNEL

补丁文件: patches/fi102/kernel-words.patch
校验: patches/fi102/meta.json 里的两个 sha256（输入和输出都要对得上）
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / 'patches' / 'fi102' / 'kernel-words.patch'
META = ROOT / 'patches' / 'fi102' / 'meta.json'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_words(path):
    words = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        off, _va, orig, new = line.split()
        words.append((int(off, 16), int(orig, 16), int(new, 16)))
    return words


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    meta = json.loads(META.read_text())
    words = load_words(PATCH)

    data = bytearray(src.read_bytes())
    if len(data) != meta['kernel_size']:
        raise SystemExit(f'kernel size mismatch: got {len(data)}, want {meta["kernel_size"]}')
    digest = sha256(bytes(data))
    if digest != meta['kernel_sha256_pristine']:
        raise SystemExit(f'pristine sha256 mismatch:\n  got  {digest}\n  want {meta["kernel_sha256_pristine"]}')

    for off, orig, new in words:
        got = struct.unpack_from('<I', data, off)[0]
        if got != orig:
            raise SystemExit(f'word at {off:#x}: expected original {orig:#010x}, found {got:#010x}')
        struct.pack_into('<I', data, off, new)

    out = sha256(bytes(data))
    if out != meta['kernel_sha256_fi102']:
        raise SystemExit(f'result sha256 mismatch:\n  got  {out}\n  want {meta["kernel_sha256_fi102"]}')
    dst.write_bytes(bytes(data))
    print(f'fi102 补丁应用成功: {len(words)} 个 word -> {dst}')
    print(f'  sha256 {out}')


if __name__ == '__main__':
    main()
