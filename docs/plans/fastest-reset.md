# 完全复位榜（Leaderboards.Fastest_Reset）达成计划

> 起草：2026-10-06。依据 = `docs/game/` 全部 47 篇 + `docs/adr/` 7 篇 + 本仓现有代码
> + 最近一次实跑日志（`%AppData%Low\TheFarmerWasReplaced\TheFarmerWasReplaced\output.txt`，
> 2026-10-06 21:04 收尾的那一跑）。
> 纪律照旧：**能从 `get_cost()` / `num_unlocked()` 问出来的数，一律不写估计值**；
> 本文里凡是「重建/推断」的地方都明确标注，落地前必须先探针确认。

---

## 0. 目标与判定

「登上完全复位排行榜」＝ 让 `leaderboard_run(Leaderboards.Fastest_Reset, 文件名, speedup)`
开出的那一场模拟**成功**并且**程序自己结束**。

| 项 | 内容（`docs/game/unlocks/leaderboard.md`，权威） |
|---|---|
| 入口 | `leaderboard_run(Leaderboards.Fastest_Reset, filename, speedup)` |
| 等价模拟 | `unlocks = {}`、`items = {}`、`globals = {}`、`seed = -1`（随机）、`speedup` |
| 成功条件 | `num_unlocked(Unlocks.Leaderboard) > 0`（**模拟结束时**判定） |
| 终止要求 | 模拟**不会**自动结束；**程序必须自己结束**，否则这一跑无效 |
| 计分 | 单跑不足 2 小时（游戏时间）就**重复跑到满 2 小时**，取**平均**后上传 |
| 加速 | `speedup` 只减少等待，**不影响结果** |

**由计分规则推出的唯一结论：分数 ≈ 单次成功运行的用时。**
所以本计划只有一个优化目标：**缩短一次成功运行的游戏内用时**；
而第一阶段的目标更低——**先跑出一次能成功、能结束的运行**（哪怕要 3 小时）。

---

## 1. 零解锁起手的实测事实（2026-10-05 侦察 + 2026-10-06 实跑日志）

```
world 1x1 | max_drones 1 | 起点 (0,0) 草原+草 | 全部物品 = 0
白送（cost 空）：Loops Variables Operators Functions Lists Dictionaries
                 Senses Timing Utilities Simulation  以及 Grass
没有 Unlocks.Soil / Harvest / Pass 这三个枚举 —— 它们是白送动词，直接调
get_cost() / unlock() 在零解锁下即可用（实跑日志已证实：开局就打印了报价并买下了 Speed）
```

**动词纪律（本项目连栽四次的教训）：调用任何动词前先问「解锁了吗 / 付得起吗」。**
`plant(Carrot)` 要 Carrots、`plant(Tree)` 要 Trees、`use_item(Fertilizer)` 要 Fertilizer、
`use_item(Items.Weird_Substance)` 要… 用到之前一律先 `num_unlocked()`。

---

## 2. 解锁链与价格（实测）

| 解锁 | 第一级价格 | 上限 | 备注 |
|---|---|---|---|
| Speed | hay 20 | 5 | 每级**执行速度 ×2** ⇒ 满级 32×，全局乘数 |
| Expand | hay 30 | 9 | 见 §3.4 世界阶梯 |
| Plant | hay 50 | 1 | 灌木=Bush |
| Grass | hay? | 10 | 每级**割草产量 ×2** ⇒ hay 收入的乘数 |
| Carrots | wood 50 | 10 | 种 1 株耗 wood+hay（本仓实测 8+8，sim 里用 `get_cost(Entities.Carrot)` 复核） |
| Watering | wood 50 | 9 | 含水量 1 ⇒ 生长 5×；水箱每 10 秒 1 个 |
| Trees | wood 50 + carrot 70 | 10 | 树 = 5 wood/棵 |
| Fertilizer | wood 500 | 4 | 每 10 秒 1 个，每级翻倍 ⇒ 满级 0.8 个/秒 |
| Pumpkins | wood 500 + carrot 200 | 10 | 种 1 株耗 carrot 1 |
| Sunflowers | carrot 500 | 1 | power：每 30 个行动耗 1 点，有电即 **2× 速度** |
| Polyculture | pumpkin 3000 | 5 | 伴生倍率 ×5·2^lv（lv1=×10、lv5=×160）；**后续等级要骨头** |
| Cactus | pumpkin 5000 | 6 | 仙人掌：s×s 排好序一刀 = s⁴ |
| Mazes | **weird 1000** | 6 | 金币唯一来源 |
| Dinosaurs | **cactus 2000** | 6 | 骨头唯一来源 |
| Megafarm | **gold 2000** | 5 | 多无人机：lv5 = 32 架 |
| **Leaderboard** | **bone 2,000,000 + gold 1,000,000** | 1 | **终点条件** |

Expand 逐级成本（本仓探针实测，全部为**南瓜**计价从 lv4 起）：

```
lv0->1 hay 30 | lv1->2 wood 20 | lv2->3 wood 30 + carrot 20 | lv3->4 wood 100 + carrot 50
lv4->5 pumpkin 1,000 | lv5->6 8,000 | lv6->7 64,000 | lv7->8 512,000 | lv8->9 4,100,000
```

---

## 3. 三条产线的经济学（计划的核心）

### 3.1 骨头线（恐龙）—— 时间上的绝对大头

| 量 | 公式（文档 + 本仓实测） |
|---|---|
| 一颗苹果 | `2 × 2^(dino_lv−1)` 个仙人掌（帽子自动购买；仙人掌不够就不出苹果） |
| 收尾得骨头 | `尾巴长度² × 2^(dino_lv−1)`（实测：lv5 吃 445 颗 = 3,154,176 = 445²×16 ✓） |
| 移动成本 | 戴帽时 `move()` = 400 tick，每吃一颗 ×0.97（长尾后落到地板价 ~15 tick） |
| 独占性 | **只有一顶恐龙帽 ⇒ 恐龙跑无法并行** |
| 尾巴上限 | 蛇不能把自己堵死；走哈密顿回路时上限 ≈ `格数 − 格数/8`（32×32 → 896） |

**两条硬结论：**

1. **每单位仙人掌换到的骨头与恐龙等级无关**：`骨头/仙人掌 = 尾巴长度 / 2`。
   升级 Dinosaurs 的收益不是「更省仙人掌」，而是**同样的骨头用更少的趟数**。
2. **骨头的总 tick ≈ `1.74e10 / (格数 × 恐龙倍率)`**（推导：趟数 = 2e6/(N²m)，每趟 tick ≈ (C/2)×13,333，
   其中 N ≈ 0.875C、`13,333 = 400/0.03` 是帽子衰减的积分）。
   ⇒ **格数与恐龙等级都是一阶杠杆，两者等效**；而 16×16 相对 12×12 只赚 1.78×，
   却要多花 512,000 南瓜（见 §5 的判断）。

### 3.2 金币线（迷宫）—— 物质价格的账单是固定的

| 量 | 公式 |
|---|---|
| 建迷宫耗物质 | `边长 × 2^(mazes_lv−1)` |
| 宝藏给金币 | `边长² × 2^(mazes_lv−1)` |
| ⇒ **金币/物质** | **= 边长**（**与 Mazes 等级无关！**） |
| 一座迷宫寿命 | 建好 + 复用 300 次 = 301 次宝藏；复用时**同样耗物质**，金币不变 |

**两条硬结论：**

1. **升 Mazes 等级对物质账单零帮助**，只省「走位次数」。⇒ 除非走位成为瓶颈，否则不升。
2. **金币线的物质账单由世界大小定死**：100 万金币 = `1e6 / 边长` 个物质
   （12×12 → **83,333**；22×22 → 45,455；32×32 → **31,250**）。
   ⇒ **世界越大，金币线越省物质**——这是「扩地」除了骨头之外的第二份回报。

### 3.3 奇异物质线（肥料 + 感染）

- `use_item(Items.Fertilizer)` 让脚下植物**感染**；**感染的植物收割时一半产量变 weird**。
- 肥料自动到货：**每 10 秒 1 个，每级翻倍**（lv1 = 0.1/s，lv4 = 0.8/s）。
- ⇒ **weird 速率 = 肥料速率 × 单株产量 / 2**，而单株产量 = 基础产量 × 伴生倍率。
  树基础 5 wood ⇒ 伴生 ×10 时一棵树 = 50 wood ⇒ **一次肥料换 25 weird**。

**结论：weird 的杠杆是「肥料等级」与「伴生倍率」，不是格子数。**
而 Polyculture 的后续等级要**骨头**（真实存档 lv4→5 = 1,250,000 骨头；
`CONTEXT.md` 记 lv2→3 = 10,000 骨头）——**它和终点那 200 万骨头的账单直接抢钱**。
⇒ 买 Polyculture 前必须先把「多花的骨头」与「省下的时间」换算成 tick 比较（见 §5）。

### 3.4 世界的阶梯（**重建，落地前必须探针确认**）

`docs/game/unlocks/expand_1.md` 说 lv1 之后农场是「a nice row」，
`expand_2.md` 说下一级才「no longer in a nice row」⇒ **lv1 是一行，不是正方形**。
配合本仓实测（lv1 → `get_world_size()` = 3、lv6 = 12、lv8 = 22、lv9 = 32）：

```
lv0 1x1 | lv1 1x3(行) | lv2 3x3 | lv3 4x4 | lv4 6x6
lv5 8x8 | lv6 12x12 | lv7 16x16 | lv8 22x22 | lv9 32x32
```

⚠ **lv1 是 1×3 的一行，而 `full_run.py` 把它当 3×3 走**（`move(North)` 在三格的行上会绕回原行）
⇒ 同一格被走三遍、k 值每遍都不同 —— 这解释了实跑日志里 lv1 阶段那点零零碎碎的 wood。

---

## 4. 现状盘点：有什么、缺什么

### 4.1 已经就位的

- `lb_enter.py` 的 `WHICH = 2` 已经接到 `leaderboard_run(Leaderboards.Fastest_Reset, "full_run", 256)` ✓
- 真实存档已全解锁（含 Leaderboard / Simulation）⇒ **发令枪随时可开** ✓
- `full_run.py`（v75，686 行）已跑通 bootstrap：1×1 → hay → Speed/Expand/Plant → 灌木产 wood
  → Carrots/Trees，并带自动解锁（`try_buy(0)` 解锁 / `try_buy(1)` 升级）与 4 路轮作。
- 可复用模块：`block_farm.py`（南瓜方块）、`zones.py`（分区唯一事实来源）、
  `util.py`、`gold_mini.py`（单座 8×8 迷宫挣 2000 金）、`cactus_big.py`（整片仙人掌排序）、
  `dino_fast.py`（恐龙跑 v8~v10，含紧循环与哈密顿回路）。

### 4.2 造成当前一跑失败的真 bug（**已定位**）

2026-10-06 那一跑（`output.txt`）：**world 3 / expand 2 卡死 237 轮、2470 秒**，
读数恒为 `wood 3 carrot 0 harv 0`，只有 `hay` 在缓慢上涨。

根因：`full_run.farm_round()` 里的收割判据写反了——

```python
if can_harvest():
    if zones.is_farm(x, y) == 0:      # ✗ 反了
        harvest()
```

`zones.is_farm(x, y)` 的语义是「**1 = 这一格归轮作**」（`zones.py` 原文注释：
「轮作专用：只有落在 "farm" 的格子才归主机」）。于是 `== 0` 的意思是
「**只在别人的专区里收割**」。而在 3×3 及以上、又还没有南瓜方块/迷宫区的棋盘上，
`zones.geom()` 因 `bs < 2 → bs = 0` 让**全盘都判成 "farm"** ⇒ 收割**永不发生**，
只剩 `k == 2` 那条支线在收草 ⇒ 逐字对上日志的「hay 涨、wood 冻、carrot 0」。

第二个同源缺陷：`k = 9`（禁止轮作插手）**只挡了南瓜方块区**，没挡 sun / maze 专区
⇒ 轮作会往别人的地里种东西（v74 的注释本来就想修这个，结果把结构改坏、又改回来了）。

### 4.3 完全缺失或不适用的部分（这是本计划要补的活）

| 缺口 | 现状 |
|---|---|
| **骨头线** | `full_run.py` 里**一个 `change_hat(Hats.Dinosaur_Hat)` 都没有** ⇒ 2,000,000 骨头永远产不出来 |
| **仙人掌线** | 没有「零前置假设」的仙人掌田（`cactus_big.py` 假定 32×32 与多机） |
| **金币线** | 只有 `gold_mini`（单座 8×8、挣到 2000 金就退出）；离 100 万金币差三个数量级 |
| **交接判据** | `get_cost(Unlocks.Expand) == None`（＝Expand **满级**，要 **410 万南瓜**）在完全复位榜里是**死路** |
| **Power 存量** | 没有任何囤电策略；而恐龙跑期间盘上不能种向日葵（见 §5） |
| **停滞看门狗** | 没有「N 秒没有正收入就报警」的机制 ⇒ 这次卡死烧掉了 40 分钟才被人看见 |

---

## 5. 关键判断（写进计划的结论，先按此执行，实测再翻案）

1. **不要满级 Expand。** 第一目标世界 **12×12（lv6，累计 73,000 南瓜）**；
   视南瓜吞吐再决定要不要 16×16（lv7 再加 512,000 南瓜）。
   22×22 / 32×32 的 410 万南瓜在「最快」这个目标下不划算。
2. **不要升 Mazes 等级**（§3.2：金币/物质 = 边长，与等级无关）。
3. **恐龙等级是骨头线的一阶杠杆，尽量升**：仙人掌很便宜（6×6 排好序一刀 = 1,296 个，
   种 1 株耗 2 南瓜），而每升一级就把骨跑 tick 总量按倍率除一次。
4. **Megafarm 必须先拿**（gold 2000 ≈ 168 个奇异物质）：多无人机是全局乘数，
   也是唯一能让「仙人掌/南瓜/草料/电力」同时开工的手段。
5. **Power 走「存量」而不是「产线」**：恐龙跑期间盘面被尾巴占满、苹果只落在空地，
   农活没法并行 ⇒ 先在农活阶段囤够 `行动数/30` 的 power，再开始跑骨头。
   （12×12 目标下，2 百万骨头 ≈ 1.14e6 步 ⇒ 约 **3.8 万点 power**，一刀 8 点 ⇒ 约 4,800 刀。）
6. **农活阶段与恐龙跑阶段时间上互斥**（尾巴铺满整盘 + 苹果只落在空地），
   所以要按「阶段」推进，而不是让所有产线一直并行。
7. **Polyculture 等级是带刺的杠杆**：它同时放大 weird 与草料产出，但要花骨头。
   判据：只有当「省下的农活时间 > 多花的骨头对应的骨跑时间」时才买。
   第一版**只买 lv1（南瓜 3000，×10）**，后续等级留到骨头线成型后再算。

---

## 6. 路线图（里程碑 + 验收判据）

每个里程碑都必须有**能在 `output.txt` 里读出来的判据**，否则不算完成。

### M0 —— 止血与看门狗（先做，半小时内可验证）
- 把 `farm_round()` 的收割判据改回 `zones.is_farm(x, y) == 1`；
  并在 `k = 9` 那段补上「非 farm 格一律 k=9」。
  **只改条件表达式，不动 if/else 结构**（v74 就是插了语句把 else 的归属弄丢的）。
- 加**停滞看门狗**：每 `REPORT_SEC` 比较「三产（hay/wood/carrot）之和」的增量，
  连续 N 个报告窗口为 0 就打印 `[fr] !! 停滞` 并把当前决策分支（哪条 `if` 命中）打出来。
- 顺手修 lv1 的世界形状假设：用 `get_world_size()` 只推边长，
  行/正方形由「走一步 North 后 `get_pos_y()` 变没变」实测判定。

**判据**：从零跑到 world 3、expand 2 之后，`wood` 与 `carrot` **持续增长**，不再冻在 3/0。

### M1 —— bootstrap 稳定化（1×1 → 6×6）
- 购买顺序（每步都先 `get_cost()` 复核）：Speed(hay20) → Expand(lv1) → Plant(hay50)
  → Expand(lv2, wood20) → Grass 等级 → Carrots(wood50) → Expand(lv3) → Trees(wood50+carrot70)
  → Watering(wood50) → Sunflowers(carrot500)。
- 轮作从「4 路 `(x+2y)%4`」退化为**明确的带**：草带 / 木带 / 胡萝卜带，
  并按 §3.4 的行/方形自适应；`pb_size()` 与 `block_farm.block_size()` 保持**同一口径**。
- 每个阶段只保留**一个**「钱花在哪」的决策点（v40 的教训：买得越多、产得越少）。

**判据**：world ≥ 4 后，hay/wood/carrot 三条都单调上涨；`harv > 0` 出现。

### M2 —— 乘数（电力 + 等级）
- 向日葵带：**≥10 株**才吃 8 倍；收割必须**两趟**（先量全场最大花瓣，再割那一株）；
  割错会连坐一次（文档明说）⇒ 保守实现，宁可少割一刀。
- 只要 power > 0，全局就是 2× ⇒ 维持「每 30 个行动至少 1 刀向日葵」即可稳态吃满。
- Speed / Grass / Trees 等级跟着钱自然买（`try_buy(1)`）。

**判据**：`power` 长期 > 0；世界扩张速度明显快于 M1。

### M3 —— 南瓜方块 + 扩到 12×12
- 用 `block_farm.py` 的方块（6×6 吃满 `n²×6`），死瓜必须补种（20% 死亡率）。
- 目标：累计 **73,000 南瓜**（Expand lv6 = 12×12），并留下 buy Cactus/Polyculture 的余量。
- 南瓜成本链：`hay+wood → carrot → pumpkin` ⇒ 胡萝卜储备线要继续用 `carrot_stock()` 口径。

**判据**：`world 12`，且南瓜仍能持续入账。

### M4 —— 奇异物质 → Mazes → 金币 → Megafarm
- weird 目标 1000（`Mazes`），产法：**喂树 + 伴生 ×10**（一次肥料 ≈ 25 weird），
  先把肥料等级买到买不动（wood 计价，比骨头便宜得多）。
- 拿到 Mazes 后：建**满场迷宫**（`边长 = get_world_size()` 个物质），
  用 `measure()` 拿宝藏坐标 + 缓存墙图做最短路；**复用 300 次**（每次同样耗物质、同样给金币）。
- 攒 **2000 金币 → Megafarm**（多无人机）⇒ 之后再谈要不要更多无人机。
- 迷宫阶段会推平整盘 ⇒ 阶段结束后 `clear()` 重铺农场（种子成本只有 hay/wood/carrot）。
- 这一段直接把 `maze_gold2.py` 的 LCA 走位 / 距离场缓存搬过来（但注意复用后的迷宫**有环**，
  树结构不再成立 ⇒ 要么只在「无环的那 1 次」用 LCA，要么退回 BFS + 世代号）。

**判据**：`gold 2000` 到账、`max_drones() > 1`、`[gm]`/`[mz]` 行出现稳定金币速率。

### M5 —— 仙人掌 → Dinosaurs → 骨头线
- 仙人掌田：整片排序（行排完排列，`docs/unlocks/cactus.md` Hint 1 的正确姿势），
  一刀 = `n²`；**`swap()` 不移动无人机** ⇒ 必须 `swap` 后紧跟同向 `move`。
- 恐龙等级：用探针把 `get_cost(Unlocks.Dinosaurs)` 逐级问清楚后，能买就买。
- 骨跑移植 `dino_fast.py` 的 v10 结构：先判行进方向（**只允许翻一次**）、
  前 26 颗直走、之后进 `cycle_phase()` 紧循环（~25 条语句/步，实测 2× 提速）。
- 吃的颗数**由还差多少骨头反算**：`N = ceil(sqrt(need / 倍率))`，够了就收工卸帽。

**判据**：`bone` 单调上涨；一趟的 `bones_gained` 与 `N²×倍率` 对得上。

### M6 —— 终点：bone 2e6 + gold 1e6 → Leaderboard → 结束
- 金币 1,000,000：按 §3.2 的物质账单分段做（12×12 ⇒ 83,333 weird，
  所以要在 M4 的迷宫线上把「weird → 金币」做成可重复调用的阶段，而不是一次性）。
- **最后一步**：`unlock(Unlocks.Leaderboard)` 成功 ⇒ 立刻打印成功行并 `return`
  （排行榜硬性要求程序自己结束）。
- 现有的 1,000,000 秒兜底保险丝保留（正常永不触发）。

**判据**：`[fr] *** 终点达成：Leaderboard 解锁到手 ***` 之后程序结束。

### M7 —— 提交与调优
- 在真实存档跑 `lb_enter.py`（`WHICH = 2`），`speedup` 先用 256。
- 记录：单跑用时、成功的重复次数、平均分；再针对最大的 tick 消耗项优化
  （历史经验：**恐龙跑的走位与语句数**，以及**迷宫走位**是前两名）。

---

## 7. 迭代成本与测试台（省时间的关键）

**不要每次都从 1×1 重跑。** 用 `simulate()` 分段起跳：

```python
# 例：直接从「骨头阶段」起跳，固定 seed 做回归
sim_unlocks = {Unlocks.Expand: 6, Unlocks.Megafarm: -1, Unlocks.Dinosaurs: 2, ...}   # 负数 = 满级
sim_items   = {Items.Cactus: 100000, Items.Power: 100000, Items.Pumpkin: 100000}
t = simulate("bone_mini", sim_unlocks, sim_items, {}, 12345, 256)
```

- 固定 `seed` 的正整数做**可重复回归**；`-1` 用于随机性压测。
- `set_world_size(n)` 只用于**独立单元测试**（文档：执行结束会复位；本仓实测它**会清空农场**，
  绝不能在正式流程里调）。
- 短程回归：只验到 world 6 / 只验一趟恐龙跑，不要每次跑满全程。
- 分段探针一律走 `lb_enter.py` 的 `WHICH = 3` 那条路（把参赛文件名临时换掉）——
  这样问到的是**零解锁模拟里的真实价格**，而不是真实存档的（真实存档已满级，问不出来）。

---

## 8. 红线（本项目血泪纪律，逐条保留）

1. **动词先问解锁**（`plant` / `use_item` / `change_hat` 各要一个解锁）。
2. **不写死游戏数字**：一切价格/上限走 `get_cost()` / `num_unlocked()`；只允许写「策略缓冲」。
3. **一处一验**：一次只改一个判据，改完立刻短程回归（v20/v21/v65/v74 四次停滞都是「一次改一片」）。
4. **改条件不要动 if/else 结构**（v74 插语句弄丢 else 归属 ⇒ 轮作体永不执行）。
5. **一块地一个 owner**（`docs/unlocks/megafarm.md` 的 Race Conditions）——分区一律问 `zones`。
6. **跨机状态只走参数与返回值**（No Shared Memory）——凡是要打印的数必须显式赋值。
7. **不做 import 循环**；只用 `import 文件`，**不用 `from 文件 import *`**（文档明确警告）。
8. **不用 `trade()`**（语义未验证，`get_cost()` 也不接受 Item 参数）。
9. **改代码用 patch 脚本 + 锚点断言**（或 edit 工具）；**不要用 PowerShell 文本改写**
   （会把 UTF-8 中文搞成乱码还吃引号 —— 本轮真栽过）。
10. **`clear()` 会清空整盘**，只在阶段切换时用，且要立刻重铺。

---

## 9. 时间预算（第一版估计，用来判断值不值得做）

| 阶段 | 估计游戏内用时 | 主要成本 |
|---|---|---|
| bootstrap 到 Trees（world 4~6） | 15~30 分 | 单机走位 + 生长等待 |
| Sunflowers/Power + 等级 | 10~20 分 | 黄花田铺开 |
| 南瓜方块 → 12×12 | 30~60 分 | 6×6 方块反复补种 |
| weird 1000 → Mazes → gold 2000 → Megafarm | 20~40 分 | 肥料速率 × 伴生倍率 |
| 仙人掌 + 恐龙等级 + 骨头 2e6 | 30~60 分 | 骨跑 tick（`1.74e10/(格数×倍率)`） |
| 金币 1e6 | 20~40 分 | 83,333 weird + 迷宫走位 |
| **合计** | **约 2~3.5 小时** | |

⇒ 第一次成功多半会**超过 2 小时**（那就按单跑上传）；
把目标定在「先有一跑成功」，再按 M7 的读数决定优化哪一个乘数。

---

## 10. 立刻可做的下一步（按顺序）

1. **M0 止血**：改回 `zones.is_farm(...) == 1`、补 `k = 9`、加停滞看门狗；跑 5 分钟短程验证。
2. **探针一次问全**（在 Fastest_Reset 模拟里）：Expand 逐级、Speed/Grass/Trees/Carrots/Pumpkins/
   Fertilizer/Polyculture/Cactus/Mazes/Dinosaurs/Megafarm 的逐级价格与上限，
   以及 `get_cost(Entities.Carrot / Entities.Pumpkin / Entities.Cactus)` 的种植成本。
3. **拆骨线成独立文件** `bone_mini.py`（零前置假设 + 由缺口反算颗数 + 自带 power 检查），
   用 `simulate()` 直接从骨头阶段起跳做回归。
4. **拆金币线** `maze_gold3.py`（满场迷宫 + 复用 300 次 + 墙图缓存），同样可单独起跳。
5. **改交接判据**：`get_cost(Unlocks.Expand) == None` → 「世界 ≥ 目标尺寸 且 Megafarm 已解锁」，
   否则那条 `import main` 的交接在完全复位榜里永远不会触发。
6. **把 M1~M6 的判据做成一张 checklist**，每跑一次就对着 `output.txt` 打勾。

---

## 附：已读文档清单（本轮覆盖）

- `docs/game/`：backup.md、credits.md、external_editor.md、first_program.md、getting_started.md、
  home.md、output.md、stats.md
- `docs/game/scripting/`：break、comments、continue、debug、dicts、for、functions、if、import、
  lists、operators、scopes、sets、tuples、variables、while（16 篇）
- `docs/game/unlocks/`：auto_unlock、cactus、carrots、costs、debug2、dinosaurs、expand_1、expand_2、
  fertilizer、hats、**leaderboard**、mazes、megafarm、plant、polyculture、pumpkins、senses、
  simulation、speed、sunflowers、timing、trees、watering（23 篇）
- `docs/adr/`：0001~0007（7 篇）
- 项目内：`CONTEXT.md`、`docs/journal/2026-10-05-fullrun.md`、
  `docs/journal/2026-09-12.md`（探针读数段）、`tools/patch_fullrun_v13.py`，
  以及 `full_run.py` / `gold_mini.py` / `zones.py` / `util.py` / `block_farm.py` / `layout.py` /
  `dino_fast.py` / `lb_enter.py` 与 `output.txt`（最近一跑）
