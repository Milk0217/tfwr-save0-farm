# The Farmer Was Replaced · 编程农场 · Save0 自动化农场工程

> 一个 2026-09-11 → 2026-11-02（跨 52 天 / 约 7.4 周）的个人游戏开发存档：49 个游戏内自动化脚本、30 个离线工具、7 篇架构决策记录、8 篇开发日志与 6 篇规划文档。
> 精选自《The Farmer Was Replaced》(TFWR) 第 0 号存档，已脱敏，可直接阅读、复用与二次开发。

**English (short):** A curated, sanitized snapshot of a personal automation project for *The Farmer Was Replaced* (TFWR) — a programming game where you write code to farm. It contains 49 in-game scripts written in TFWR's Python-like dialect, 30 offline tools (mocks, simulators, static analyzers, regression tests), 7 ADRs, 8 development journals and 6 plans, plus a minimal save snapshot. Game-official docs and the community-maintained `__builtins__.py` are intentionally **not** included for copyright reasons. Licensed under MIT. Not affiliated with the game's developer or publisher.

---

## 目录

- [这个仓库是什么](#这个仓库是什么)
- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [主要成果](#主要成果)
- [文档导航](#文档导航)
- [数据来源与免责声明](#数据来源与免责声明)
- [许可](#许可)

## 这个仓库是什么

[《The Farmer Was Replaced》](https://store.steampowered.com/app/2060160/The_Farmer_Was_Replaced/) 是一款「用代码种田」的游戏：玩家用一门 Python 近似的脚本语言驱动无人机，在会环绕相连的棋盘上种植、收割、养恐龙、刷迷宫。游戏里没有现成攻略代码，所有自动化都要自己写。

这个仓库是一个真实存档里的完整工程：从 8×8 小棋盘的单无人机，一路做到 32×32、最多 32 架无人机的多产线并行；为了少走弯路，还写了一套**离线假引擎、假迷宫、策略模拟器和静态检查工具**，把「改一行 → 进游戏跑一轮 → 看日志」的试错成本压到最低。

仓库内容：

- **`scripts/`**：游戏内实际运行的脚本（TFWR 方言，Python 近似语法）。主线是 `main.py`（产业链）、`wood_hay.py`（木草专线）与 `full_run.py`（完全复位榜参赛程序，分档调度架构）；其余是针对特定目标的专线脚本、成就脚本与针对性小工具（如 `lb_probe.py`）。
- **`tools/`**：桌面 Python 工具，不依赖游戏即可运行：假引擎 `farm_mock.py`、假迷宫 `maze_mock.py`、策略模拟 `maze_sim*.py`、静态检查（重复定义 / 非法语法 / API 白名单 / 作用域 / 死代码 / 循环收敛 / 档位接口契约）与回归测试。
- **`docs/`**：7 篇 ADR（架构决策记录）、8 篇开发日志（逐日工作记录 + 方法论 lessons + 交接 handoff）、6 篇规划文档。另有 [`CONTEXT.md`](CONTEXT.md) 作为领域术语表。
- **`sample/`**：`save.snapshot.json`，从游戏存档 `save.json` 中只保留 `items` + `unlocks` + `version` 的最小快照，用于展示最终存档状态。

## 仓库结构

```
.
├── CONTEXT.md                  # 领域术语表：棋盘 / 功能带 / Harvest Gate / Tick Budget …
├── README.md
├── LICENSE                     # MIT
├── REPO_NOTES.md               # 收录与排除清单、脱敏记录、语法检查结果
├── scripts/                    # 49 个游戏内脚本（TFWR 方言）
│   ├── main.py                 #   产业链主线（五功能带布局）
│   ├── jobs.py                 #   算法层：只作用于脚下格或调用方给的矩形
│   ├── full_run.py             #   完全复位榜参赛程序（分档调度）
│   ├── stage_*.py              #   按「棋盘档」拆分的空间层（w1…w22）
│   ├── budget.py / util.py / layout.py / zones.py / block_farm.py
│   ├── wood_hay.py / *_farm.py / gold_mini.py / get_top_hat.py …
│   ├── dino_*.py / maze_gold*.py / ach_*.py / lb_enter.py …
│   └── pumpkin_farm*.py / cactus_*.py / sun_farm.py / quests.py …
├── tools/                      # 30 个离线工具（桌面 Python 3）
│   ├── farm_mock.py / maze_mock.py        # 假引擎 / 假迷宫，离线跑真脚本
│   ├── maze_sim*.py / *_ab.py             # 策略模拟与 A/B 对照
│   ├── audit_save0.py / gamelang.py …     # 静态检查与「方言陷阱」扫描
│   └── test_*.py / diag_*.py              # 回归测试与定点诊断
├── docs/
│   ├── README.md               # 文档索引与阅读顺序
│   ├── adr/                    # 7 篇架构决策记录
│   ├── journal/                # 8 篇开发日志
│   └── plans/                  # 6 篇规划（含已推翻方案的负结果）
└── sample/
    └── save.snapshot.json      # items + unlocks + version 最小快照
```

## 快速开始

### 1. 游戏内存档目录

Windows 下存档位于：

```
%USERPROFILE%\AppData\LocalLow\TheFarmerWasReplaced\TheFarmerWasReplaced\Saves\Save0
```

**使用前请先备份自己的存档**（至少备份 `save.json` 与原脚本）。把需要的文件从 `scripts/` 复制进存档目录后，在游戏内编辑器里运行即可。

脚本里引用的路径、目录结构都按「存档根目录 = 脚本所在目录」设计；本仓库把它们统一放进 `scripts/`，因此**离线工具已做路径适配**（默认从 `scripts/` 读取），但游戏内运行时请把 `.py` 文件复制到存档目录（而不是 `scripts/` 子目录）再运行。

### 2. 游戏内怎么跑

| 目标 | 运行 | 说明 |
|---|---|---|
| 产业链主线（木/草/胡萝卜/南瓜/向日葵/仙人掌补课） | `main.py` | `clear()` 会重建棋盘，跑之前确认存档状态 |
| 木草专线（大量木材 / 干草） | `wood_hay.py` | 与 `main.py` 互斥，二者不能同时跑（游戏一次只执行一个文件） |
| 完全复位榜参赛程序 | `full_run.py`（通过 `lb_enter.py` 的 `WHICH = 2` 启动） | 按 (棋盘尺寸, Expand 等级, 无人机数) 分档调度 |
| 刷仙人掌 / 南瓜 / 向日葵 / 迷宫金币 | `cactus_farm.py` / `pumpkin_farm.py` / `sun_farm.py` / `maze_gold2.py` | 各有版本迭代，详见开发日志 |
| 恐龙骨头 | `dino_fast.py` | 单机路线，走哈密顿回路，详见日志 |
| 成就 / 帽子 / 排行榜 | `ach_*.py`、`flips_parallel.py`、`get_top_hat.py`、`lb_enter.py` | `ach_*` 中有些脚本「报错就是成功」，文件头有说明 |

⚠ 游戏语言是 **Python 近似方言**，不是 Python：没有三元表达式、f-string、推导式等（见 [`tools/gamelang.py`](tools/gamelang.py)）。脚本在 CPython 下可通过语法检查，但真机运行前建议先过一遍静态检查（见下节）。

### 3. 离线工具（桌面 Python 3，无需启动游戏）

```bash
# 自带假引擎 / 假迷宫：把真脚本放进模拟环境跑
python tools/farm_mock.py [模拟秒数上限]     # 跑 full_run.py 的档位调度
python tools/maze_mock.py                    # 跑 maze_gold2.py 的迷宫策略

# 静态检查（改完脚本先过这几道）
python tools/gamelang.py scripts            # Python 有、TFWR 没有的表达式式语法
python tools/audit_save0.py scripts/main.py # 重复声明 / 下标越界 / 未定义名字
python tools/deadcode.py scripts/main.py    # 从入口出发不可达的顶层函数
python tools/dedup_defs.py scripts/main.py  # 重复的顶层 def（保留最后一个）
python tools/contract_check.py              # 档位文件接口契约（stage_* 必须同签名）
python tools/loop_check.py                  # 循环收敛性（必须能 break / 条件会更新）
python tools/scope_check.py scripts/*.py    # 跨函数引用局部变量

# API 白名单检查：需要一份 __builtins__.py（本仓库因版权未收录）
TFWR_BUILTINS=/path/to/__builtins__.py python tools/api_check.py scripts/full_run.py

# 回归测试
python tools/test_dino_cycle.py
python tools/test_cactus_sort.py
python tools/test_stage_assign.py
python tools/test_sun_worker.py
python tools/test_maze_reuse.py

# 策略模拟 / 性能剖析
python tools/maze_sim.py
python tools/maze_profile.py
python tools/maze_cycle_ab.py
```

工具默认从本仓库 `scripts/` 读取被检文件；也支持显式传文件路径。它们在原工程中位于存档目录的 `.codebuddy/tools/`，收录时已把路径基准改为本仓库的 `scripts/`（详见 [`REPO_NOTES.md`](REPO_NOTES.md)）。

### 4. 存档快照

[`sample/save.snapshot.json`](sample/save.snapshot.json) 只保留原 `save.json` 的 `items`、`unlocks`、`version` 三个字段（编辑器打开的文件、滚动位置等个人使用状态已移除）：

- `items`：各资源库存（`serializeList` 形式）；
- `unlocks`：164 项已解锁内容（形如 `grass_10`、`megafarm_5`、`leaderboard`）；
- `version`：存档格式版本（3）。

## 主要成果

### 存档状态（可复算）

按项目在 [`CONTEXT.md`](CONTEXT.md) 中定义的「通关 = 解锁 Leaderboard」，快照中 `leaderboard` 已解锁；同时包含 `top_hat`、六顶金帽与 164 项解锁记录。资源库存（快照精确值，摘录）：

| 物品 | 数量 | 物品 | 数量 |
|---|---:|---|---:|
| Wood | 222,025,502 | Carrot | 359,893,998 |
| Pumpkin | 476,904,302 | Cactus | 83,767,606 |
| Weird Substance | 25,460,128 | Bone | 587,249 |
| Gold | 594,740 | Hay | 739,334 |
| Water | 1,540,811 | Fertilizer | 41,981 |

### 三条主线

| 产线 | 做法 | 开发日志记录的关键读数 |
|---|---|---|
| 金币线 | `maze_gold.py` → `maze_gold2.py`：32×32 划分为 16 座 8×8 小迷宫并行，每区 2 架无人机；用「LCA 父链走位 + 距离场」把每条命的花费压到最低 | 旧版实跑 **688,178 金币/分**；`maze_gold2.py` v2.7 区间平均 **3.45M/分**、峰值 **4.42M/分**（用户目标 2M/分） |
| 骨头线 | `dino_fast.py`：单机走哈密顿回路吃苹果，骨头 = 尾巴长度² × 恐龙等级倍率（lv5 时 ×16） | v10 实跑「倍率确认、骨头线结案」（见 `docs/journal/2026-09-12.md`） |
| 农场线 | `main.py` 五功能带布局 + 伴生投票；后期 `full_run.py` 按「棋盘档 × 无人机档」分档并行 | 32×32 棋盘、`max_drones = 32`（Megafarm lv5） |

### 工程方法（这个仓库真正的重点）

- **先测再改**：凡是 `get_cost()` / `num_unlocked()` / `measure()` 能问出来的数，不许写估计值；结论必须带实测读数。
- **静态检查替代肉眼**：用 `deadcode.py` 一次性删掉 `main.py` 里 25 个不可达函数（2051 → 1432 行），并在删除后跑通三连验证（py_compile → 静态体检 → 几何自检）。
- **能用模拟就不用真机**：迷宫策略先在 `maze_sim*.py` / `maze_mock.py` 上验证，再进游戏；`maze_gold2.py` 的每一版改动都有对应的离线 A/B 工具。
- **负结果也记录**：`docs/plans/cactus-parallel.md` 保留了「被实测推翻」的完整方案与对账过程。

> **数据说明**：开发窗口为 **2026-09-11 18:53 → 2026-11-02 14:09**（跨 52 天，含首尾 53 个日历日；有文件证据的活跃开发日 15 天）。仓库自身的文件/行数统计为整理时实测；历史性能数字（688k、3.45M/分 等）引自开发日志、`CONTEXT.md` 与最后一次实跑日志 `output.txt`。完整的投入与产出核算见 [`docs/report/开发投入总结报告.md`](docs/report/开发投入总结报告.md)。

## 开发投入速览（2026-09-11 → 2026-11-02）

> 完整报告：[`docs/report/开发投入总结报告.md`](docs/report/开发投入总结报告.md)

| 维度 | 数字 |
|---|---|
| 时间 | 跨 52 天（含首尾 53 天，约 7.4 周）；有文件证据的活跃开发日 **15 天**（下限）；三个开发峰 09-11~09-13、10-05~10-08、11-01~11-02 |
| 代码 | 游戏内脚本 **63 个 / 17,679 行**（本仓精选 49 个 / 16,379 行）；外部工具 **85 个 / 12,647 行**（本仓 30 个 / 6,647 行）；全部 `.py` 149 个 / 32,647 行 |
| 文档 | 原创 **22 篇 / 5,290 行**（CONTEXT 338 + ADR 267 + journal 3,442 + plans 1,243）；另有游戏官方文档 47 篇仅作参考、不入库 |
| 迭代 | **44 个补丁脚本**（版本编到 v102）、20 份代码快照、18 份存档快照、1 份 49 个脚本的中程副本；`main.py` BUILD 13→42 |
| 工具 | 假游戏 `farm_mock.py`、假迷宫、策略模拟、8 个静态检查、7 个回归测试、补丁器与剖析器 |
| 产出 | **164/164 项解锁**（等级科技 14 项全部满级）；金币 688,178 → 3.45M/分均值 / 4.42M/分峰值；完全复位榜从零解锁跑通 **36,213.96 游戏秒** |
| 成本 | AI token / API 费用与人工工时：**本地无计费/工时记录，无法量化**；报告以活跃日、迭代版本与资产规模作为代理指标 |

## 文档导航

| 文档 | 内容 |
|---|---|
| [`CONTEXT.md`](CONTEXT.md) | 领域术语表（AI / 人类共用上下文入口） |
| [`docs/README.md`](docs/README.md) | 文档索引、ADR / 日志 / 规划逐篇导读、阅读顺序 |
| [`docs/adr/`](docs/adr/) | 7 篇架构决策记录 |
| [`docs/journal/`](docs/journal/) | 8 篇开发日志（逐日记录 + lessons + handoff） |
| [`docs/plans/`](docs/plans/) | 6 篇规划（含已推翻方案） |
| [`REPO_NOTES.md`](REPO_NOTES.md) | 收录/排除清单、脱敏记录、语法检查结果 |
| [`docs/report/开发投入总结报告.md`](docs/report/开发投入总结报告.md) | 开发投入总结报告：时间 / 迭代 / 代码与文档资产 / 工具链 / AI 协作 / 产出回报 |

推荐阅读顺序：`CONTEXT.md` → `docs/journal/lessons-2026-09-12.md` → `docs/adr/` → `docs/plans/full-run-modularization.md`。

## 数据来源与免责声明

- 本仓库是**个人游戏存档工程**的精选与整理，与游戏作者 / 发行商无关，不代表官方立场。
- **未收录游戏官方文档** `docs/game/`：那 47 篇文档版权归游戏方所有，且可从游戏安装目录的 `StreamingAssets/Languages/<EN|ZH>/docs` 直接读取。本仓库的注释、日志中仍会出现 `docs/game/...` 的引用，属历史写作记录，请对照游戏内文档阅读。
- **未收录社区维护的 `__builtins__.py`**：该文件由 TFWR Discord 社区维护、版权归属不明，且项目实测发现它与游戏实际行为多处不符（例如向日葵加成写成 5 倍，实际为 8 倍）。需要时请自行从游戏/社区获取，并通过 `TFWR_BUILTINS` 环境变量传给 `tools/api_check.py`。
- 未收录开发期的一次性探针（`probe*.py`）、补丁（`patch_*.py`）、原始运行输出（`_*.txt`）与历史备份；原因与清单见 [`REPO_NOTES.md`](REPO_NOTES.md)。
- 仓库内容已脱敏：本机路径替换为占位符（`<USER>` / `<GAME_DIR>`），不含邮箱、令牌或任何密钥。

## 许可

- 代码与文档：**MIT License**（[`LICENSE`](LICENSE)，Copyright (c) 2026 Milk0217）。
- 游戏《The Farmer Was Replaced》的名称、游戏内文本与美术资源版权归其作者所有；本仓库不包含这些资源。
