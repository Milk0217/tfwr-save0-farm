# 仓库整理说明（REPO_NOTES）

本文件记录 2026-11-02 对 TFWR Save0 存档工程做「精选 + 脱敏」的构建过程、收录/排除清单与校验结果，供维护者与审阅者核对。

> 本步骤只产出**工作副本**（`.oss-work/repo/`）；创建远端仓库与推送由 Lead 负责，本步骤未联网、未推送。
> 整理报告由 Lead 放入 `docs/report/`，本文件不替代它。

## 1. 构建信息

| 项 | 值 |
|---|---|
| 整理日期 | 2026-11-02 |
| 来源 | 本机游戏存档目录 Save0（路径已脱敏：`<USER>\AppData\LocalLow\TheFarmerWasReplaced\TheFarmerWasReplaced\Saves\Save0`） |
| 产物 | 本仓库工作副本（目标 GitHub 仓库 `Milk0217/tfwr-save0-farm`） |
| 方法 | 白名单复制 → UTF-8 归一化 → 正则脱敏 → 路径改写与工具适配 → `py_compile` 全量检查 → `git init` + 首次提交 |
| 版本管理 | 本地 git，`user.name = Milk0217`、`user.email = Milk0217@users.noreply.github.com` |

## 2. 收录清单

### 2.1 `scripts/`（49 个文件，16,379 行，635,278 字节）

| 分组 | 文件 |
|---|---|
| 主线 / 公共层（10） | `main.py`、`jobs.py`、`full_run.py`、`budget.py`、`layout.py`、`util.py`、`zones.py`、`block_farm.py`、`quests.py`、`w_pumpkin.py` |
| 各专线（21） | `wood_hay.py`、`hay_farm.py`、`wood_farm.py`、`carrot_farm.py`、`pumpkin_farm.py`、`pumpkin_farm2.py`、`pumpkin_farm3.py`、`pumpkin_farm4.py`、`cactus_farm.py`、`cactus_big.py`、`sun_farm.py`、`dino_bones.py`、`dino_fast.py`、`dino_fill.py`、`dino_greedy.py`、`dino_greedy2.py`、`dino_greedy3.py`、`maze_gold.py`、`maze_gold2.py`、`gold_mini.py` |
| 成就 / 排行榜 / 帽子（9） | `ach_cycle_a.py`、`ach_cycle_b.py`、`ach_five_hats.py`、`ach_stack_overflow.py`、`ach_wrong_order.py`、`flips_parallel.py`、`lb_enter.py`、`lb_probe.py`、`get_top_hat.py` |
| 完全复位榜分档（10） | `stage_row.py`、`stage_small.py`、`stage_w1.py`、`stage_w3.py`、`stage_w4.py`、`stage_w6.py`、`stage_w8.py`、`stage_w12.py`、`stage_w16.py`、`stage_w22.py` |

### 2.2 `tools/`（30 个文件，6,647 行，262,378 字节）

| 分组 | 文件 |
|---|---|
| 假引擎 / 假迷宫（2） | `farm_mock.py`、`maze_mock.py` |
| 策略模拟与 A/B（5） | `maze_sim.py`、`maze_sim2.py`、`maze_sim3.py`、`maze_size_ab.py`、`maze_cycle_ab.py` |
| 静态检查（8） | `audit_save0.py`、`gamelang.py`、`api_check.py`、`scope_check.py`、`deadcode.py`、`dedup_defs.py`、`contract_check.py`、`loop_check.py` |
| 回归测试（7） | `test_cactus_sort.py`、`test_dino_cycle.py`、`test_maze_reuse.py`、`test_serp.py`、`test_stage_assign.py`、`test_stage_owner.py`、`test_sun_worker.py` |
| 性能剖析 / 端到端（4） | `maze_profile.py`、`maze_wall_exploit.py`、`maze_worker_e2e.py`、`maze_wait_test.py` |
| 诊断 / 生成 / 格式化（4） | `diag_cactus.py`、`diag_dino.py`、`make_achievement_scripts.py`、`tidy.py` |

### 2.3 `docs/` 与根目录文档

| 内容 | 数量 | 说明 |
|---|---|---|
| `CONTEXT.md` | 1 | 领域术语表，保留在仓库根目录（原工程即如此，脚本注释直接引用；索引见 `docs/README.md`） |
| `docs/adr/` | 7 | 原 `docs/adr/` 原样收录 |
| `docs/journal/` | 8 | 原 `.codebuddy/memory/` 精选：4 篇逐日工作日志 + 2 篇 lessons + 2 篇 handoff，全部收录 |
| `docs/plans/` | 6 | 原 `.codebuddy/plans/`：含**已推翻**的 `cactus-parallel.md`（顶部保留负结果说明） |
| `docs/README.md` | 1 | 文档索引与阅读顺序（新增） |
| `README.md` / `LICENSE` / `.gitignore` / `REPO_NOTES.md` | 4 | 新增 |

### 2.4 `sample/`

`sample/save.snapshot.json`（3,473 字节）：只保留原 `save.json` 的 `items` + `unlocks` + `version`，编辑器状态（`dockedFiles` / `minimizedFiles` / `openFilePositions` / `openFileScrollPositions` / `openFileSizes` / `openDocPages`）全部移除。

## 3. 排除清单与理由

| 排除对象 | 数量 / 体积 | 理由 |
|---|---|---|
| `docs/game/`（游戏官方文档） | 47 篇 | 版权归游戏方所有；可从游戏安装目录 `StreamingAssets/Languages/<EN\|ZH>/docs` 直接读取，公开转存不合适 |
| `__builtins__.py`（社区类型存根） | 1 个 / 51 KB | 由 TFWR Discord 社区维护、版权归属不明；且实测与游戏行为多处不符（如向日葵加成写成 5 倍，实际 8 倍），不适合作为公开代码收录 |
| 根目录一次性探针 | 14 个 | `probe.py`、`probe2.py`~`probe8.py`、`probe_cost.py`、`probe_expand.py`、`probe_hf.py`、`probe_import.py`、`probe_pump.py`、`probe_spawn.py`；探针的结论已写进 `CONTEXT.md` / `docs/journal/` |
| `.codebuddy/tools/patch_*.py` | 60+ 个 | 按锚点字符串改文件的一次性补丁脚本，只服务于本工程历史版本，无复用价值；补丁纪律收录于 `docs/journal/lessons-*.md` |
| `.codebuddy/tools/probe_*.py` | 6 个 | 同上，一次性探针 |
| `.codebuddy/tools/_*.txt`、`_fert.md` | 17 个 | 原始运行输出 / 临时笔记，非工具 |
| `.codebuddy/tools/spec_*.json`、`extra_task3.json` | 30+ 个 | 补丁与文档生成用的一次性 spec 数据 |
| `.codebuddy/backup/` | 20 个大文件 | 历史版本备份（`main.py.build40/41/42`、`maze_gold2.py.v1~v27`、各脚本 `.vN` 等），属原始备份，不是精选内容 |
| 根目录 `dino_fast.py.v8` | 22 KB | 旧版本单文件备份，正式版为 `dino_fast.py` |
| `.codebuddy/tools/maze_gold.backup.py` | 1 个 | 备份副本（正式版为 `maze_gold.py`） |
| 一次性维护脚本 | 4 个 | `fix_ternary_and_linter.py`、`verify_ternary_fix.py`、`cleanup_v26.py`、`update_context_v27.py`：针对本工程历史文件的一次性修复/清理，复用价值低 |
| `__pycache__/`、`*.pyc` | — | 字节码缓存；`.gitignore` 已忽略 |
| 原始 `save.json` | 15 KB | 含编辑器打开文件、滚动位置等个人使用状态，只派生 `sample/save.snapshot.json` |
| `output.txt`、游戏安装目录内容 | — | 不在存档目录内 / 版权 |
| `.oss-work/` 其他目录 | — | 团队协作中间产物（`analysis/`、`history/`、`report/`），不属于公开仓库 |

> `.codebuddy/tools/` 原有 85 个 `.py`，收录 30 个、排除 55 个（补丁/探针/备份/一次性维护脚本）。

## 4. 脱敏记录

### 4.1 替换规则与命中数

对**全部收录文件**执行以下替换（仅文档/注释中出现，脚本逻辑无个人信息）：

| 类别 | 替换为 | 命中 |
|---|---|---|
| 本机 Windows 用户目录绝对路径（含原用户名） | `<USER>` | 1 处（`docs/journal/2026-09-12.md`） |
| Steam 游戏库绝对路径（含盘符） | `<GAME_DIR>` | 2 处（`docs/journal/2026-09-11.md`、`docs/journal/2026-09-12.md`） |
| 个人邮箱 | `<EMAIL>` | 0 处（源文件中未出现） |

合计 3 处敏感路径，全部位于 2 篇开发日志中；替换在构建脚本中完成，源工程文件未改动。

### 4.2 扫描校验（构建后对全仓库重扫）

| 检查项 | 结果 |
|---|---|
| 原用户名 / 本机用户目录字符串 / 原 Steam 库路径 / 原个人邮箱 | **0 命中** |
| 通用邮箱正则 `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` | **0 命中**（仅剩任务规定的 GitHub noreply 提交邮箱，见 §1） |
| token / password / secret / api_key / access_key / private_key / bearer / `ghp_` / `github_pat` 等敏感串 | **0 命中** |
| 二进制 / 密钥 / 证书文件 | 无（全部为文本文件） |
| `%APPDATA%` / `%AppData%Low` 等环境变量式路径 | 保留（不含个人信息） |

## 5. 路径与代码适配

1. **文档交叉引用改写**（只改文本，不改语义）：`.codebuddy/memory/` → `docs/journal/`（14 处）、`.codebuddy/plans/` → `docs/plans/`（11 处）、`.codebuddy/tools/` → `tools/`（42 处）。
2. **工具路径基准适配**：`tools/*.py` 中的 `SAVE` 常量由原「工具目录/../..（= 存档根）」改为「工具目录/../scripts」，使 `python tools/xxx.py` 在本仓库内即可直接定位 `scripts/` 下的被检文件。脚本本身的 import 关系（同目录 `import util/jobs/...`）保持不变。
3. **`api_check.py`**：需要 `__builtins__.py` 作为 API 白名单（因版权未收录），改为支持 `TFWR_BUILTINS` 环境变量指定路径；未指定且文件缺失时给出提示并以退出码 2 退出。
4. **保留的历史引用**：文档与注释中的 `docs/game/...`（74 处）、`probe*.py`、`patch_*.py`、`_*.txt` 等为开发期历史引用，未收录对应文件，已在 `README.md` 与 `docs/README.md` 中说明。
5. 其余未做任何行为/逻辑改动。

## 6. 语法检查

- 命令：`python -m py_compile scripts/*.py tools/*.py`（Python 3.14.7，Windows）
- 结果：**79 个 Python 文件全部通过，0 失败**（49 个游戏内脚本 + 30 个工具）。
- 检查后已清理 `__pycache__`，并写入 `.gitignore`。
- 注意：TFWR 方言是 Python 近似语法但不是 CPython。`py_compile` 通过不等于游戏内可执行；本工程用 `tools/gamelang.py`（方言陷阱）、`tools/api_check.py`（API 白名单）、`tools/audit_save0.py`（编辑残留）等专项检查补位，方法论见 `docs/journal/lessons-*.md`。

## 7. 数据统计（首次提交前实测）

| 类别 | 文件数 | 行数 | 字节 |
|---|---:|---:|---:|
| `scripts/` | 49 | 16,379 | 635,278 |
| `tools/` | 30 | 6,647 | 262,378 |
| `docs/`（adr + journal + plans） | 21 | 4,952 | 345,649 |
| `CONTEXT.md` | 1 | 338 | 38,103 |
| `sample/` | 1 | 217 | 3,473 |
| 根目录元文件（README / LICENSE / .gitignore / REPO_NOTES / docs/README） | 5 | — | 约 30 KB |
| **合计** | **107** | — | **约 1.31 MB（1.25 MiB）** |

## 8. 待办 / TODO（交接给 Lead）

- [ ] 确认完整开发起止日期与总时长（README 目前写「约 7 周（日志始于 2026-09-11）」，结束日期待定）。
- [ ] 如需在 README 引用最终实跑速率，建议用最终 `output.txt` 复核（现值 688k → 3.45M/分 引自 `CONTEXT.md` 与开发日志，本步骤未独立复算）。
- [ ] 补充 GitHub 仓库简介与 topics（如 `the-farmer-was-replaced`、`automation`、`game-ai`）。
- [ ] 将整理报告放入 `docs/report/`（本步骤按约定未写入该目录）。
- [ ] 确认 LICENSE 署名/年份，添加 remote 并推送（本步骤未推送）。
