import importlib.util, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
spec = importlib.util.spec_from_file_location('probe','scripts/patch-xnu-entry-probe.py')
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
K = '/home/yoox/android/artifacts/UniXNU-shennong/ci/42904596191/extracted/out/shennong/ios-27.0.1-24A446-iphone16pro/shennong/kernel/kernel.macho'
d = open(K,'rb').read(); probe.load_segments(d)
LO, HI = 0xFFFFFFF00AD00000, 0xFFFFFFF00B200000
md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
fo = probe.file_offset(LO)
blob = d[fo: fo + (HI-LO)]
bls = []
off = 0
while off < len(blob):
    got = False
    for insn in md.disasm(blob[off: off+0x40000], LO+off):
        got = True
        if insn.mnemonic == 'bl':
            try: bls.append((insn.address, int(insn.op_str.lstrip('#'),16)))
            except ValueError: pass
        off = insn.address - LO + insn.size
    if not got: off += 4
print('窗口内 bl 数', len(bls))
runs, cur = [], [bls[0]]
for prev, nxt in zip(bls, bls[1:]):
    if nxt[0]-prev[0] <= 0xC0: cur.append(nxt)
    else:
        if len(cur) >= 10: runs.append(cur)
        cur = [nxt]
if len(cur) >= 10: runs.append(cur)
print('长 bl 群', len(runs))
for r in sorted(runs, key=len, reverse=True)[:8]:
    tg = {}
    for a,t in r: tg[t] = tg.get(t,0)+1
    print(f'  {r[0][0]:#x}..{r[-1][0]:#x} n={len(r)} targets=' + str({hex(k):v for k,v in tg.items()}))
