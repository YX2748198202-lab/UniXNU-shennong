# 同步到 GitHub 的回执

本轮把 fi136–fi139 的进度文档、修复过程、方案、代码与回执推送到
`origin/bringup/premmu-locate`（`https://github.com/YX2748198202-lab/UniXNU-shennong`）。

## 提交

| sha | 主题 | 文件 |
|---|---|---|
| `6c983cc` | `fix(adt)`: 强制 ARM XNU 的 256 字节随机种子契约并加 CI 守卫 | 4 |
| `3ca05a6` | `feat(fatal)`: 完整检查下的异常与 panic 观察器 | 8 |
| `ace7bbd` | `fix(ledger)`: 常量段契约接受 PORT_CONST，并派生全部三处内联检查 | 5 |
| `6d0efc3` | `docs`: fi136–fi139 阶段进度、证据与验收回执 | 25 |

四个提交合计 42 文件、3667 行新增、90 行删除。本文件为同步完成后的追加回执。

## 实测

- 推送前远端该分支 = 本地 HEAD = `e386db83976395b6279a6a2a3be61d550333dee1`；`git push --dry-run` 返回 `Everything up-to-date`，认证与网络可用。
- `git push origin bringup/premmu-locate`：`e386db8..6d0efc3`，退出码 0。
- 推送后 `git ls-remote origin bringup/premmu-locate` = `6d0efc329f4b42c451303bdae92e4101579e9e9e`，与本地 `HEAD` 一致。
- `git fetch origin bringup/premmu-locate` 后从远端对象库 `git cat-file -e` 抽查 6 个新文件（含 `docs/research/fi139-ledger-2026-11-18/` 与回执 JSON），全部 present。
- 工作树 `git status --porcelain` 为空；`git diff --check` 通过。
- 提交前扫描待提交清单：无 `*.img` / `*.macho` / `*.ipsw` / `*.rsa` / `*.p12` 等二进制或凭据；`out/` 依 `.gitignore` 未入库。

## CI

`kernel.yml` 的触发条件只有 `workflow_dispatch`，push 不会启动构建，本轮没有手动触发。`api.github.com` 在本机直连超时、本机代理端口未开，因此 CI 运行列表未取得独立 API 复核；该判断依据的是仓库内的 workflow 定义本身。

## 未做的事

不改内核补丁逻辑、不重新构建、不再启动真机、不 force push、不触碰 `main` 与 `ci-logs-*` 分支。
`kernel.macho.crypto-hmac.json` 与已改内核不再自洽这一项仍未修，见 [RESULTS-AND-NEXT.md](<RESULTS-AND-NEXT.md>)。
