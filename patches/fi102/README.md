# fi102 kernel binary patch

可启动基线（2026-11-14 03:00）。

- `kernel-words.patch` — 1146 个 4 字节 word 的 (file_offset, va, original, patched)
- `meta.json` — 输入/输出的 sha256、大小、改动 word 数

应用：

```
python3 scripts/apply-fi102-patch.py <pristine kernel.macho> <out kernel.macho>
```

脚本会校验输入 sha256、逐 word 校验原始值、最后校验输出 sha256，任何不一致都会报错退出。

覆盖的改动（分类）：
1. 入口 stage-1/stage-2 检查点 cave（`0xad81500`–`0xad81620`）与入口跳转重定向
2. 13 个色带检查点 cave（`0xad81680`–`0xad81fd0`）与对应站点
3. `_start_first_cpu`：`x30` 硬编码为 `arm_init` 入口；SP 的滑动修正 nop
4. `arm_init` 尾部：Apple 专有调用 nop、`console`/`printf`/`serial` 还原
5. panic 屏绘制代码、kalloc 桩、ADT 相关地址常量
