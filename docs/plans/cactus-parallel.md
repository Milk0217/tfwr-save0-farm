# 仙人掌并行化（main.py BUILD 28 → 29）

> ## ⛔ 已推翻（2026-09-12）—— **不要按本文实现**
>
> 结论：把仙人掌田切成 ~32 个矩形**在几何上不可达，收益也只有 1.12~1.25×**。
> 用户已确认**跳过**。下面是逐条对账（细节见 `docs/journal/2026-09-12.md` 第 3 节）：
>
> 1. **6×6 方阵切不动**。两块相邻的仙人掌区会被 `swap()` 互踩（本文的校验清单第 3 条
>    自己要求了这条自检）⇒ 区域之间必须留 ≥1 格间隔，而 14 个方阵**彼此之间已经只剩
>    1 格间隔**。「680 格」里的另外 176 格来自胡萝卜带与木草带，只能切成窄条
>    （1×16 一次才 1,024 个），增量很小；木草带还要 `till` 再还原成草原，另算风险。
> 2. **吞吐模型漏了每轮的固定开销**。一轮 = 清地 + 播种 + 生长 + 收割 ≈ **4 秒**（与块
>    大小无关）+ 排序。本文的「吞吐 ∝ √(区域数)」等价于假设没有固定开销。
>    用**实测的那一个点**（14 块 × 36 格 ≈ 12 秒/轮 ⇒ `S(36) ≈ 8 秒`）反推 `S(n) ∝ n^1.5`，
>    代入 `k · 4n² / (F + S(n))` 后极值偏向**块大而少**，与本文结论相反。
> 3. **收益已经缩水**：2026-09-12 实测补课只差 22.5 万仙人掌（库存 2,364,726 /
>    恐龙档 2,590,000），按现有 14 方阵 ≈ **37 秒**跑完；1.2× 只能省 **5~8 秒**。
>    为这点收益去改已经验证过的排序/搬运下标换算（`cactus_push_value` 的 L 形路径安全性）
>    不划算。
>
> **仍然有效的部分**：如果将来地变多（再次 Expand）、或者方阵布局改了，本文的
> 「`CACTUS_CFG` 存 `[ox,oy,w,h]` + 区域不重叠自检」这个**结构改法**是对的，
> 可以直接拿来用；但**别再用 √(区域数) 那个模型估收益**，要按上面的 `k·4n²/(F+S(n))` 算。

> 目标：把「单工人跑 14 轮」变成「N 个方阵各一架并行跑」，让 72,000 仙人掌（买 Mazes 下一级）
> 从 14×10 秒的串行流水变成约 14/N × 10 秒。

## 为什么并行单位是「方阵」而不是「格子」

- 排序只能靠 `swap(dir)` 相邻交换，目标是**全局升序**（最大值必须到最后一格），
  v2 沿 L 形推值、路径会穿过已归位区域 ⇒ **两架同时推会互相踩 swap** ⇒ 一个方阵内无法并行。
- 实测：一次满序 **97 次相邻交换**（≈每格 2.7 次，已接近下界；随机 36 数的逆序数期望 315）。
- 一轮 = 清地+播种 ~2.4 s + 生长 1~2 s + 排序 ~6.5 s + 收割 ⇒ **~10~12 秒 / 5,184 个**。
- ⇒ **并行单位 = 6×6 方阵**：每架独占一片，清地/播种/排序/收割全独立，零共享状态。

## 改造清单（关键技巧：用「列表元素」当每架自己的配置）

游戏语言里函数**读**模块级变量没问题，但**赋值**会变成本地变量 ⇒ 用 `CACTUS_CFG[0]` 这种
**列表元素赋值**来给每架无人机设置「我负责第几个方阵」（这套代码里到处在用这个模式）。

1. 新增：`CACTUS_CFG = [0]`（`[0]` = 本机负责的方阵下标）；
2. `cactus_x(col)` → `return PUMPKIN_OX[CACTUS_CFG[0]] + col`；
3. **所有** `goto(cactus_x(col), row)` → `goto(cactus_x(col), PUMPKIN_OY[CACTUS_CFG[0]] + row)`
   （共 6 处：`cactus_cycle_v2` 清地、`cactus_plant_and_wait`、`cactus_plant_and_wait_v2`、
   `cactus_read_grid`、`cactus_count_violations`、`sort_cacti`、`sort_cacti_v2` 内的搬运）；
4. `cactus_cycle_v2(n)` 末尾的 `goto(cactus_x(0), 0)` → `goto(cactus_x(0), PUMPKIN_OY[CACTUS_CFG[0]])`；
5. `cactus_push_value(src, dst)` 的坐标换算不用改（它用 `PUMPKIN_SIZE` 的行列 → `cactus_x` 已带原点）；
6. **`cactus_push()` 改成多机版**：
   ```
   def cactus_worker(sq, target):
       CACTUS_CFG[0] = sq
       while num_items(Items.Cactus) < target:      # 库存是全局的，所以这就是共享的「够了没」
           cactus_cycle_v2(0)
   def cactus_push():
       ... need / cap 判断同上 ...
       # 用 **前 N 个南瓜方阵** 当仙人掌田（补课在 spawn 副机之前跑，所以不会和南瓜机抢地）
       N = 4
       i = 0
       while i < N and i < PUMPKIN_SQUARES:
           d = spawn_drone(cactus_worker, i, need)
           if d != None: append(drones, d)
           i = i + 1
       while i < len(drones):
           wait_for(drones[i]); i = i + 1
   ```
   **终止条件用「全局库存 >= need」**（`Items.Cactus` 是共享物品栏）⇒ 先完成的副机自动收工，
   不必精确分配轮数；每轮仍然打印 `[cactus] cycle … gained 5184`，可核对。

## 校验清单

1. `py_compile` + `audit_save0.py` 双验证 0 问题；
2. `BUILD = 29`；
3. 首轮 `[cactus] cycle N swaps ~97 violations 0 gained 5184` —— **violations 必须是 0**；
   若有非 0，说明 `CACTUS_CFG` 没生效（还在收第 0 片）或方阵间踩了；
4. 14 轮的墙钟应约等于 `14 / N × 10 秒`（N=4 时 ~35 秒）；
5. 买完 `[upgrade] bought target_index 10`（`Unlocks.Mazes`），之后 `maze_gold.py` 的
   `gold_per_maze_actual` 应从 2,048 变成 **4,096**。

## 注意

- 仙人掌会**暂时占用前 N 个南瓜方阵**（每株 2 南瓜，36 株 = 72 南瓜/轮，可忽略成本）；
  补课在 `spawn_drone(loop_*)` 之前完成 ⇒ 南瓜机出生时那些格子已经空了，会自动补种回去 ✓。
- `CACTUS_MAX_CYCLES` 的语义会变成「每个工人最多跑几轮」⇒ 设 16 足够（4 架 × 16 轮 × 5,184 ≫ 72,000）。
