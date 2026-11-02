# 文档索引

本目录收录开发过程中沉淀的设计文档，全部为中文，均写于真实开发过程中（未做事后润色）。

## 先读哪一篇

| 想知道什么 | 看这里 |
|---|---|
| 术语与领域模型（棋盘 / 功能带 / Harvest Gate / Tick Budget …） | [../CONTEXT.md](../CONTEXT.md) |
| 为什么这样设计、否掉了哪些替代方案 | [adr/](adr/)（7 篇架构决策记录） |
| 实际怎么干活的：实测读数、踩坑、纠错 | [journal/](journal/)（8 篇开发日志） |
| 路线图与方案（含已推翻的方案） | [plans/](plans/)（6 篇规划） |
| 整个工程投入了多少资源、产出了什么 | [report/开发投入总结报告.md](report/开发投入总结报告.md) |

## ADR · 架构决策记录

| 编号 | 决策 |
|---|---|
| [0001](adr/0001-board-layout-four-bands.md) | 棋盘划为四条功能带，而不是四象限平分（布局部分后来被 0003 取代，「区域判定收敛到单一事实来源」原则沿用） |
| [0002](adr/0002-mega-pumpkin-harvest-gate.md) | 巨型南瓜只在**整带**存活且成熟（Harvest Gate）时才收割 |
| [0003](adr/0003-five-bands-sunflower.md) | 五功能带：南瓜缩为 2×2，腾出向日葵带换全局 2 倍速 |
| [0004](adr/0004-polyculture-measure-only.md) | 混合种植只做测量，暂不主动满足伴生 |
| [0005](adr/0005-cactus-one-off-push.md) | 仙人掌不占永久功能带，只做一次性「补课」（触发条件部分被 0007 取代） |
| [0006](adr/0006-wood-hay-mode.md) | 木草模式独立成脚本，物种选择交给伴生投票 |
| [0007](adr/0007-cactus-target-selection.md) | 仙人掌补课目标 = 预算内最便宜的那一档，不追 Mazes |

## 开发日志（journal）

### 逐日工作日志

| 文件 | 内容 |
|---|---|
| [2026-09-11.md](journal/2026-09-11.md) | 第 1 天 / 11 轮迭代：8×8 实测 → 12×12 重划 → 伴生投票 → 仙人掌补课 → 木草模式 → 刷迷宫换金币 |
| [2026-09-12.md](journal/2026-09-12.md) | BUILD 40 → 42：`probe7` 定案补课线、静态分析删 25 个死函数、`dino_fast` v9/v10、`maze_gold` v33/v34 |
| [2026-10-05.md](journal/2026-10-05.md) | 金币 2,000,000/分 攻关：`maze_gold2` v1 → v2.7（离线模拟 + tick 级体检驱动） |
| [2026-10-05-fullrun.md](journal/2026-10-05-fullrun.md) | 完全复位榜 `full_run.py` 的零解锁侦察与进度交接 |

### 方法论与交接

| 文件 | 内容 |
|---|---|
| [lessons-2026-09-11.md](journal/lessons-2026-09-11.md) | 改游戏脚本的铁律：编辑工具、改前重读、三连验证 |
| [lessons-2026-09-12.md](journal/lessons-2026-09-12.md) | 能用 API 问出来的数不许猜；怎么安全地批量删代码；补丁纪律 |
| [handoff-2026-09-11.md](journal/handoff-2026-09-11.md) | 交接：现状、文件版本、下一轮任务清单 |
| [handoff-2026-09-12.md](journal/handoff-2026-09-12.md) | 交接：基本通关后只剩 Leaderboard（金币线 + 骨头线） |

## 规划（plans）

| 文件 | 内容 |
|---|---|
| [fastest-reset.md](plans/fastest-reset.md) | 完全复位榜达成路线图（起草 2026-10-06） |
| [full-run-modularization.md](plans/full-run-modularization.md) | `full_run` 以「棋盘档 × 无人机档」为键的模块化重规划 —— **当前架构** |
| [modularize-main.md](plans/modularize-main.md) | `main.py` 拆为「布局 / 工人 / 主控」三层的四步方案 |
| [cactus-parallel.md](plans/cactus-parallel.md) | 仙人掌并行化方案 —— **已被实测推翻**，顶部保留负结果记录 |
| [farm-32x32.md](plans/farm-32x32.md) | 棋盘扩到 32×32 后的重排方案（BUILD 25→26） |
| [pumpkin-first.md](plans/pumpkin-first.md) | 南瓜优先改版执行清单（BUILD 19→20） |

## 阅读建议

1. 先读 [../CONTEXT.md](../CONTEXT.md) 的「当前存档状态」与「Language」，建立术语；
2. 再看 [lessons-2026-09-12.md](journal/lessons-2026-09-12.md)，理解这个工程为什么强调「先实测再改」；
3. 对架构感兴趣 → [adr/](adr/) + [full-run-modularization.md](plans/full-run-modularization.md)。

## 开发投入总结

[report/开发投入总结报告.md](report/开发投入总结报告.md) —— 2026-09-11 → 2026-11-02 的开发投入核算：时间 / 迭代 / 代码与文档资产 / 工具链 / AI 协作 / 产出回报，附统计口径与复现命令。

## 路径说明（重要）

这些文档写于原开发工作区，文中的路径已按本仓库结构做过映射：

| 文中写法 | 在本仓库中 |
|---|---|
| `CONTEXT.md` | 仓库根目录 [../CONTEXT.md](../CONTEXT.md) |
| `.codebuddy/memory/` | [journal/](journal/) |
| `.codebuddy/plans/` | [plans/](plans/) |
| `.codebuddy/tools/` | [../tools/](../tools/) |
| `docs/adr/` | [adr/](adr/) |
| `docs/game/` | 游戏自带官方文档，**未收录**（版权原因，可从游戏安装目录 `StreamingAssets/Languages/…/docs` 读取） |
| `probe*.py` / `patch_*.py` / `_*.txt` | 开发期一次性探针/补丁/原始输出，**未收录**（原因见 [../REPO_NOTES.md](../REPO_NOTES.md)） |
