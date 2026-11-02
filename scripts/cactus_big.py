# ============================================================
# cactus_big.py —— 仙人掌 **整片方案**：把整个 32x32 做成一片排好序的仙人掌
#
# ============ 为什么这是通往 20M/分 的路 ============
# 文档（docs/game/unlocks/cactus.md）原文：
#   * "If you harvest a fully-grown cactus and all neighboring cacti are in sorted order,
#      it will also harvest all neighboring cacti **recursively**."
#   * "if a square of grown cacti is sorted by size and you harvest one cactus,
#      it will harvest the **entire square**."
#   * "You will receive cactus equal to the **number of harvested cacti squared**."
#   ⇒ 产量 = n^2 x 等级倍率（实测倍率 = **16**：5x5 块 = 25^2 x 16 = 10,000 ✓）
#
#   ⇒ **整片 32x32 = 1,024 棵一起收 ⇒ 1,024^2 x 16 = 16,777,216 一刀！**
#
#   每格产量对比：  5x5 分块 10,000/25 = 400/格   vs   整片 16,777,216/1024 = 16,384/格  (41 倍)
#   每格成本对比：  分块约 5.4 个动作/格（46 次交换 + 89 次走位）  vs  整片约 47 个动作/格
#   ⇒ 产量涨 41 倍、成本涨 8.7 倍 ⇒ **净赚约 4.7 倍** ✓
#
#   旧的"25 块 + 留缝"布局之所以慢，是因为它把 n 限制在 25 —— 而产量是 **n^2**，
#   用 31 架去并行 25 个小方块，等于把二次收益拆成了 25 份线性收益 ✗
#
# ============ 排序：文档 Hint 1 的正确姿势 ============
#   "If the rows are already sorted, sorting the columns will not unsort the rows."
#   ⇒ **先逐行排、再逐列排** ⇒ 结果每格 <= 右邻 且 <= 下邻，正好满足文档的 sorted 定义
#     （North/East 更大或相等、South/West 更小或相等）。
#   * 两个阶段之间**必须**有屏障：列排序依赖行已排好 —— 这是真依赖，不是多余的同步。
#   * 每条线的排序用 1 维 gnome 冒泡（在**本线内**移动，绝不跨线）。
#   * **比较完全免费**：`measure()` 读脚下、`measure(East)/measure(North)` 读邻居，
#     都是 1 tick 的查询（probe_cost 实测）⇒ 只有 move/swap（各 200 tick）要花钱。
#
# ============ 并行分工（cap = 32 含主线）============
#   32 行（或 32 列）由 **31 架 helper + 主线自己** 分担：helper 排序 0..30 号，主线排 31 号。
#   播种同理（一架一行）。收割只需 1 架走到 (0,0) 割一刀，整个方块连锁收空。
#
# ============ 纪律（血泪）============
#  * **只认 Entities.Cactus**：clear() 后是草原、草永远可割、can_harvest() 恒真 ⇒ 先翻土再判定。
#  * **swap() 不移动无人机** ⇒ 必须 swap 之后紧跟同方向 move（旧注释实测过：不跟 move
#    会来回换同一对，交换 94 次而违规数不变）。
#  * **排序路径绝不跨线**（我试过跨行的 gnome：swaps 46->101、产量 10,000->32 全废）。
#  * 目标必须相对开局库存（绝对目标连栽两次）。
#  * 没有三元表达式；LF + 制表符；一律用完整原文锚点改代码。
# ============================================================

VERSION = 1
N = get_world_size()
LAST = N - 1
BIG_TARGET_GAIN = 940000000        # 相对增量。2026-10-05：高顶礼帽要 cactus 1e9，
# 现有 65,908,726 ⇒ 还差 934,091,274，取 9.4 亿留 0.6% 余量（实测 34.84M/分 ⇒ 约 27 分钟）。
# **必须相对开局库存**（绝对目标连栽两次：wood 设 1e9 而开局 1.33B、carrot 同理）。
REPORT_SEC = 15

TARGET = [0]
WOK = [1]
CACT = [0]                         # 本机收割到的仙人掌（诊断）


def goto(tx, ty):
	while get_pos_x() != tx:
		if get_pos_x() < tx:
			move(East)
		else:
			move(West)
	while get_pos_y() != ty:
		if get_pos_y() < ty:
			move(North)
		else:
			move(South)


def prep_row(y):
	# 把第 y 行整成土壤（并清掉杂物）—— 只做一次/轮，之后每轮只需补种
	while get_pos_x() != 0:
		move(West)
	while get_pos_y() != y:
		if get_pos_y() < y:
			move(North)
		else:
			move(South)
	x = 0
	while x < N:
		if get_ground_type() != Grounds.Soil:
			till()
		t = get_entity_type()
		if t != Entities.Cactus:
			if t != None:
				harvest()
			plant(Entities.Cactus)
		x = x + 1
		if x < N:
			move(East)
	return 0


def sort_row(y):
	# 第 y 行的 1 维 gnome 冒泡（升序沿 +x = East）。**只在行内移动。**
	# **不变式：无人机的位置恰好等于 i**，所以比较只用 `measure(West)`/`measure()`
	# （**查询 1 tick，等于免费**），而每次交换只要 `swap(West) + move(West)` **两个动作**。
	# 旧写法每交换一次要 4 个动作：`goto(i-1)` 走 2 格回来 + swap + move。
	# 实测旧写法行排序 51.45 秒 = 1,564 个动作，而 248 次交换的下界只要 280 个动作 ⇒ 5.6 倍浪费。
	# **升序方向必须是 +x（East）**：文档要求 North/East 的邻居更大或相等。
	goto(1, y)
	i = 1
	while i < N:
		if measure(West) <= measure():
			move(East)
			i = i + 1
		else:
			swap(West)                  # swap 不移动无人机 ⇒ 紧跟同向 move
			move(West)
			i = i - 1
			if i < 1:
				i = 1
				move(East)
	return 0


def sort_col(x):
	# 第 x 列的 1 维 gnome 冒泡（升序沿 +y = North）。**只在列内移动。**
	# 与 sort_row 同一套不变式：无人机位置 = i，交换朝 **South**（i-1 方向），每次 2 个动作。
	# **升序方向必须是 +y（North）**：文档要求 North/East 的邻居更大或相等。
	goto(x, 1)
	i = 1
	while i < N:
		if measure(South) <= measure():
			move(North)
			i = i + 1
		else:
			swap(South)
			move(South)
			i = i - 1
			if i < 1:
				i = 1
				move(North)
	return 0


def harvest_all():
	# 走到一角割一刀：整片已排序且成熟 ⇒ 连锁收空全农场，产量 = n^2 x 16
	goto(0, 0)
	c0 = num_items(Items.Cactus)
	harvest()
	CACT[0] = num_items(Items.Cactus) - c0
	return CACT[0]


def main():
	print("=== cactus_big v", VERSION, "start ===")
	print("board", N, "tiles", N * N, "max_drones", max_drones(),
		"lv_cactus", num_unlocked(Unlocks.Cactus),
		"cactus", num_items(Items.Cactus), "water", num_items(Items.Water))
	TARGET[0] = num_items(Items.Cactus) + BIG_TARGET_GAIN
	print("[big] 目标 =", num_items(Items.Cactus), "+", BIG_TARGET_GAIN, "=", TARGET[0],
		"| 单刀理论产量 =", N * N * N * N * 16,
		"（", N * N, "^2 x 16 ）")
	clear()
	G0 = num_items(Items.Cactus)
	T0 = get_time()
	rounds = 0
	while rounds < 200:
		rounds = rounds + 1
		tp = get_time()
		# ---- 阶段一：播种（31 架各一行 + 主线一行）----
		hs = []
		y = 0
		while y < LAST:
			d = spawn_drone(prep_row, y)
			if d != None:
				append(hs, d)
			y = y + 1
		prep_row(LAST)
		i = 0
		while i < len(hs):
			wait_for(hs[i])
			i = i + 1
		t1 = get_time()
		# ---- 阶段二：逐行排序（**屏障是必需的**：列排序依赖行已排好）----
		hs = []
		y = 0
		while y < LAST:
			d = spawn_drone(sort_row, y)
			if d != None:
				append(hs, d)
			y = y + 1
		sort_row(LAST)
		i = 0
		while i < len(hs):
			wait_for(hs[i])
			i = i + 1
		t2 = get_time()
		# ---- 阶段三：逐列排序 ----
		hs = []
		x = 0
		while x < LAST:
			d = spawn_drone(sort_col, x)
			if d != None:
				append(hs, d)
			x = x + 1
		sort_col(LAST)
		i = 0
		while i < len(hs):
			wait_for(hs[i])
			i = i + 1
		t3 = get_time()
		# ---- 阶段四：一刀收空整片 ----
		g = harvest_all()
		t4 = get_time()
		GN = num_items(Items.Cactus)
		DT = get_time() - T0
		R = 0
		if DT > 0:
			R = (GN - G0) / DT
		print("[big] round", rounds, "| 播种", t1 - tp, " 行排序", t2 - t1,
			" 列排序", t3 - t2, " 收割", t4 - t3, " 合计", t4 - tp,
			"| 本机一刀 =", g, "（理论", N * N * N * N * 16, "）",
			"| 累计", GN - G0, "per_min_M", R * 60 / 1000000, "(目标 20)")
		if g < N * N * N * N * 16:
			print("[big] *** 一刀产量低于理论值 ⇒ 整片没有全部成熟/没有全部排好序，",
				"下一轮先查这个，别继续 ***")
		if num_items(Items.Cactus) >= TARGET[0]:
			break
	GN = num_items(Items.Cactus)
	DT = get_time() - T0
	R = 0
	if DT > 0:
		R = (GN - G0) / DT
	print("=== cactus_big end ===", "rounds", rounds, "gained", GN - G0,
		"elapsed_s", DT, "cactus_per_s", R, "cactus_per_min", R * 60)


main()
