#!/usr/bin/env python3
"""把 panic() 里的 assert 文案识别出来，并把断言所在行号编码成复位延时。

背景：assert() 走 `_Assert(file, line, expr)` -> `panic("%s:%d Assertion failed: %s", ...)`，
本 binar 里这个格式串在 0xfffffff0071d942d（另一份 0xfffffff0070460ac 是死副本，无人引用）。
panic() 入口处寄存器：x0=格式串, x1=文件指针, x2=行号, x3=表达式指针。

复位延时 = BASE + ((line >> SHIFT) & 0x3F) 秒；不是 assert 则固定 UNKNOWN 秒。
两次开机（SHIFT=0 与 SHIFT=6）即可还原 0..4095 的精确行号。
"""

import argparse
import importlib.util
import struct
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    'probe', _HERE / 'patch-xnu-entry-probe.py')
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

ASSERT_FMT = 0xFFFFFFF0071D942D

SOURCE = """.text
.global _start
_start:
  ldr x9, ={assert_fmt:#x}
  cmp x0, x9
  b.ne 2f
  lsr x9, x2, #{shift}
  and x9, x9, #0x3f
  add x9, x9, #{base}
  b 3f
2:
  movz x9, #{unknown}
3:
  movz x10, #{tb_lo}
  movk x10, #{tb_hi}, lsl 16
  mul x9, x9, x10
  mrs x1, cntpct_el0
  add x2, x1, x9
1:
  isb
  mrs x1, cntpct_el0
  cmp x1, x2
  b.lo 1b
  movz w0, #0x0009
  movk w0, #0x8400, lsl 16
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  smc #0
4:
  wfe
  b 4b
.ltorg
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('macho', type=Path)
    parser.add_argument('--shift', type=int, default=0, help='行号取位起点（0 或 6）')
    parser.add_argument('--base', type=int, default=10, help='基准秒数')
    parser.add_argument('--unknown', type=int, default=90, help='非 assert 时的秒数')
    args = parser.parse_args()

    data = bytearray(args.macho.read_bytes())
    probe.load_segments(bytes(data))

    top = max(probe.CAVES, key=lambda stage: probe.CAVES[stage])
    cave = probe.CAVES[top] + probe.CAVE_SIZE
    source = SOURCE.format(assert_fmt=ASSERT_FMT, shift=args.shift, base=args.base,
                           unknown=args.unknown,
                           tb_lo=probe.TIMEBASE & 0xFFFF,
                           tb_hi=(probe.TIMEBASE >> 16) & 0xFFFF)
    with tempfile.TemporaryDirectory() as tmp:
        code = probe.assemble(source, cave, {}, Path(tmp))
    # 基地址会随 patch 的 slide/physmap 调整而移动，所以从 CAVES 尾部开始找一段真正为零的空间
    offset = None
    while cave + len(code) <= probe.PANIC_CAVE_END:
        try:
            candidate_offset = probe.file_offset(cave)
        except BaseException:
            cave += 4
            continue
        if not any(data[candidate_offset:candidate_offset + len(code)]):
            offset = candidate_offset
            break
        cave += probe.CAVE_SIZE
    if offset is None:
        raise SystemExit(f'找不到 {len(code):#x} 字节的空 cave（PANIC_CAVE_END={probe.PANIC_CAVE_END:#x}）')
    if abs(cave - probe.PANIC_VA) >= 0x7FFF000:
        raise SystemExit(f'cave {cave:#x} 离 panic {probe.PANIC_VA:#x} 太远，b 指令够不到')
    data[offset:offset + len(code)] = code
    struct.pack_into('<I', data, probe.file_offset(probe.PANIC_VA),
                     probe.branch(probe.PANIC_VA, cave))
    args.macho.write_bytes(bytes(data))
    print(f'assert 行号探针：cave {cave:#x} ({len(code):#x} 字节)，'
          f'延时 = {args.base} + ((line>>{args.shift})&0x3F) 秒，'
          f'非 assert = {args.unknown} 秒')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
