# UniXNU-shennong development rules

- Work in `/home/yoox/android/workspace/UniXNU-shennong`. Keep framework sources and large/private build artifacts in their separate directories. Do not replace the device repository with UniXNU.
- Before editing, read the formal rules at the start of `docs/agent-progress.md`, its latest relevant entries, and `docs/STATE.md`. Check `git status --short --branch`, current HEAD and existing diffs. Keep Codex and Harness on the same device branch; only one agent writes the worktree at a time.
- Verify every change at the appropriate level. Record the exact inputs, commands, revisions and artifact hashes; distinguish host checks, builds and hardware evidence. Do not treat old reports as current validation.
- Keep the iPhone17,1 iOS 27.0.1 (24A446) and legacy iPadOS 17.7.11 (21H461) inputs, symbols, patches and outputs separate. Preserve prior code and experimental evidence; never commit private donor binaries or keys.
- Use temporary `fastboot boot` for device checks. No persistent writes outside explicitly authorized old userdata; before any authorized write, verify device identity, exact block range, image and recovery path. Never reset, clean or push destructively; no push without explicit authorization.
- Before handing off, stop writing and update `docs/agent-progress.md` with HEAD/branch/worktree state, touched files, verified results, open blockers and the next concrete task.
