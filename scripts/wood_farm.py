# ============================================================
# wood_farm.py —— **高速产木（Wood）v4：棋盘格 + 浇水**
#
# 目标：**1,000,000,000 木/分钟**（= 16,666,667/秒）。
#
# ============ v3 为什么只有 92.6M/分（实测）============
#   v3 的布局是「偶数行整行连排的树」。而 docs/game/unlocks/trees.md 写着：
#     "The growing time is **doubled for each tree that is on a tile directly to the
#      north, east, west or south of it**. So if you plant trees on every tile,
#      they will take 2*2*2*2 = 16 times longer to grow."
#   ⇒ 整行连排时每棵内部树东西各有一个树邻居 ⇒ 生长 **x4**（文档的提示就是"`%` 判偶"）。
#   ⇒ 实测「1.5 刀/圈」（满速应 32 刀/圈）不是动作不够，是**树没长好**；
#     反推 T_tree = 512 格 ÷ 18.9 刀/秒 ≈ 27 秒 = 基准 6.75 秒 x 4 —— 与文档完全吻合 ✓
#     （而门槛是 T <= 6.3 秒才够 1B/分 ⇒ 差的就是这 4 倍。）
#
# ============ v4 布局：棋盘格 = 文档规则下的最优解 ============
#   树只种在 `(x + y) % 2 == 0` 的格子 ⇒ 512 棵，每棵东南西北**全是空格** ⇒ x1 生长。
#   这是"零树邻居"前提下能放下的**最大树数**（网格的最大独立集）✓
#   另外 512 格留作**草地**：草不用播种、割完 0.47 秒长回来 ⇒ 零维护的伴生源 ✓
#   棋盘格命中率 = P(落点在伴生格)/3 = (24/48)/3 = **0.167**
#     （连排条带是 28/48/3 = 0.194，高 16%，但代价是 x4 生长 —— 棋盘格完胜。）
#   顺带算过：{x偶, y偶}（256 棵）命中率升到 0.25，但树数减半 ⇒ 总产率反而低 26%。
#
# ============ 第二个杠杆：浇水（docs/game/unlocks/watering.md）============
#   "growth speed scales linearly from 1x at water level 0 to **5x at water level 1**"
#   "the ground ... loses 1% of its current water per second"
#   "One tank of water (0.25) is automatically added to your inventory every 10 seconds"
#   ⇒ 只在 `get_water() < 0.6` 时浇（浇一次 +0.25，之后约 51 秒才会再触发）
#     水位在 0.6~0.85 振荡、均值约 0.72 ⇒ 生长 x(1 + 4 x 0.72) ≈ **x3.9**
#     耗水 = 512 x 0.25 / 51 ≈ **2.5 水/秒**（理论上限 0.01 x 0.72 x 512 = 3.7）
#     收入约 6.4 水/秒（Watering lv9）⇒ **可持续**，不会把 1.1M 库存抽干 ✓
#     （反面：若每格每圈都浇，需求 23.7 水/秒 ⇒ 会把库存烧光 —— 所以门槛**不能**设高。）
#
#   预计：不浇水 512/6.75 x 平均每刀 ≈ **320M/分**；浇水 x3.9 ⇒ 约 **1,250M/分**（首次越过 1B）。
#
# ============ 纪律（血泪）============
#   * **标定必须种在土壤上**：草原上割完那格变回草原、草 0.47 秒就长回来、
#     `can_harvest()` 立刻 True ⇒ 量到的是"草的再生"而不是树的（v3 就栽在这里：
#     报 regrow_s = 0.47，与草一模一样，掩盖了真实的 27 秒）。
#   * **标定必须自己摆伴生**：`get_companion()` 给的物种/位置是随机的，不管它的话
#     产量忽高忽低（v3 量到 409,600 只是碰巧命中）。本版按 get_companion() 摆好再割 ⇒ 读数确定。
#   * **不能假设 `clear()` 之后满地是草**：前一个脚本（pumpkin 等）可能把地全翻成土壤，
#     裸土不长草 ⇒ "抢 Grass"的伴生请求全部落空、命中率归零。所以伴生格**显式补种草**。
#   * **没有三元表达式**（`A if C else B`），也**没用过 `**`** ⇒ 一律不写（用实测值代替）。
#   * `num_items()` 是**全局库存**，多机同时收割时差值是脏的 ⇒ 单次产量必须单机单格量。
#   * **扁平多下标数组多留余量 + 开机自检**（hay 那次 `TALLY[k*3+sp]` 越界一格崩过）。
# ============================================================

VERSION = 6
SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD
WOOD_TARGET = 10100000000           # 2026-10-05：高顶礼帽要 wood 1e10，留 1% 余量。
# **必须够大**：判据是绝对库存，设小了会一进去就收工（上一版设 1B 而开局已有 1.33B；
# 这一版原本设 5B，而开局已有 5.057B —— 又踩了一次同一个坑）。
								   # ⇒ 第 10 圈就停了，而前 5 圈全在种树+灌水（启动期），
								   # 于是报出来的"平均"只有 862M/分，把稳定段的 1,150M/分拖没了。
								   # 跑够 50 圈以上，启动期占比才降到 10% 以内。
CALIB = 1                          # 1 = 开局先做标定（约 20 秒，只在开始时做一次）
REPORT_LAPS = 10                   # 每 10 圈报一次（**只有主机那一行报**，否则 32 行刷屏会挤爆 output.txt）
GOAL_LAPS = 5                      # 每 5 圈查一次目标，别冲过头太久
# 实测（上一场 output.txt）：树 无伴生再生 6.79 秒；单行走一圈 2.07 秒 ⇒ 每圈只有 ~77% 的树长好，
# 剩下 23% 是"走过去了却没得割"的白跑。把水位顶到 0.8 附近 ⇒ 再生 ≈ 6.79/4.2 = 1.6 秒 < 2.07 秒
# ⇒ 每格每圈都能割 ⇒ 预计 +19%（977.8M -> 约 1,160M/分，越过 1B）。
WATER_LEVEL = 0.75                 # 低于此水位就浇（每次 +0.25 ⇒ 水位在 0.75~1.0 之间走）
# ---- 下面三个开关是"把逐格开销搬出逐格循环"用的，砍掉的是纯空转的 API 调用 ----
WATER_EVERY = 2                    # 稳态下每 2 圈查一次水位
WARMUP_LAPS = 4                    # 开局每圈都浇：水位从 0 顶到满要 4 次浇水（每次 +0.25）
STARTUP_S = 12                     # 启动期时长（估算用）：4 圈灌水 + 一茬树长好 ≈ 12 秒
CHECK_EVERY = 8                    # 每 8 圈补查一次"格子空了没有"（播种失败保险）
WATER_FLOOR = 20000                # 库存保底：低于此数停止浇水
WATER_BOOST = 3.9                  # 浇水后的生长倍率（水位均值 0.72 时 1+4*0.72）
TIMEOUT_S = 60                     # 标定单步等待上限。树基准约 6.75 秒，给 60 秒足够；
								   # **不要用 120** —— 万一等不到，空等 2x120 秒看起来就像卡死。

HARV = [0]                         # 本机割了多少刀（逐机独立，只做诊断）


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


def wait_grown(max_sec):
	t0 = get_time()
	while get_time() - t0 < max_sec:
		if can_harvest():
			return get_time() - t0
	return -1


def cut():
	# 割一刀，返回产了多少木（**单机单格时才是干净读数**）
	w0 = num_items(Items.Wood)
	harvest()
	return num_items(Items.Wood) - w0


def calib_one(ent, label):
	# 量一个物种，返回 [满伴生产量, 再生秒数]。
	# 三步都是坑，缺一个读数就是错的：
	#  1) clear() 保证"零同族邻居"——否则上一次标定摆下的伴生树会拖慢这一次的生长；
	#  2) till() 到土壤——草原上割完草就长回来，`can_harvest()` 立刻 True，量到的是草；
	#  3) 按 get_companion() 把伴生摆好再割——否则产量是随机的（命中与否看运气）。
	clear()
	print("[wood] CALIB", label, "开始: 已是土壤 =", get_ground_type() == Grounds.Soil,
		" 水位 =", get_water())
	if get_ground_type() != Grounds.Soil:
		till()
	plant(ent)
	print("[wood] CALIB", label, "已播种，等它长好（最多", TIMEOUT_S, "秒）…")
	r = wait_grown(TIMEOUT_S)
	if r < 0:
		print("[wood] CALIB", label, "生长超时（>", TIMEOUT_S,
			"秒）—— 邻居拖慢？还是地被抽干了？")
		return [0, 0]
	print("[wood] CALIB", label, "长好了，用了", r, "秒；现在按 get_companion() 摆伴生")
	# 走到它指定的位置、种上它指定的伴生（位置一定在 3 格内、且不是它自己）
	plant_type, (cx, cy) = get_companion()
	goto(cx, cy)
	if get_entity_type() != None:
		harvest()
	if plant_type == Entities.Carrot:
		if get_ground_type() != Grounds.Soil:
			till()
	plant(plant_type)
	goto(0, 0)
	y = cut()
	# **必须补种再等！** 土壤上割完不会自己长回来（v3 在草原上量，草 0.47 秒长回来，
	# 于是把"草的再生"当成了"树的再生"；v4 改到土壤上却不补种 ⇒ wait_grown 必然空等满
	# TIMEOUT_S 秒 ⇒ 屏幕上看起来就是"卡死了"，而读数还是假的 -1。这就是上一次的现象。）
	plant(ent)
	r2 = wait_grown(TIMEOUT_S)
	print("[wood] CALIB", label, "yield =", y, " first_grow_s =", r,
		" regrow_s =", r2, "(土壤上量，伴生已摆好)")
	return [y, r2]


def calib():
	# 开场只量两个真正要用的数：树和灌木的"满伴生产量 + 再生时间"。
	# **删掉了草参考那一刀**：上一场它 `wait_grown(60)` 空等了整整 60 秒（读数是 0，因为
	# 上一场把 (0,0) 翻成了土壤、土壤上不长草），白烧 1/3 的标定时间，而且那个数根本不用。
	rb = calib_one(Entities.Bush, "bush")
	rt = calib_one(Entities.Tree, "tree")
	# ---- 判据：把量到的再生时间直接换算成产量，省得再猜 ----
	# 满伴生 = 基础 x 160（Polyculture lv5 = 5 x 2^5）；场上平均 = 基础 x (1 + 159 x 命中率)
	match = (24 / 48) / 3
	base_t = rt[0] / 160
	base_b = rb[0] / 160
	avg_t = base_t * (1 + 159 * match)
	print("[wood] CALIB 换算：树 无伴生基础 =", base_t, "(满伴生", rt[0], ") 平均每刀 =", avg_t)
	print("[wood] CALIB 换算：灌木 无伴生基础 =", base_b, "(满伴生", rb[0], ") 平均每刀 =",
		base_b * (1 + 159 * match), "| 灌木再生 =", rb[1])
	if rt[1] > 0:
		# **两个上限取小** —— 这是上一场跑完才校准出来的正确模型：
		#   生长上限 = 512 格 / 有效再生时间
		#   动作上限 = 32 架 x 27 动作/秒 / 4 动作每刀（走两格 + 割 + 补种）
		# 上一场实测 181 刀/秒，而动作上限 = 32*27/4 = 216 刀/秒 ⇒ **卡在动作上**，不是卡在生长上。
		# （这也解释了为什么"多浇水"只能帮到 216 为止。）
		act = 32 * 27 / 4
		print("[wood] 判据：生长上限 干", 512 / rt[1], "湿", 512 / (rt[1] / WATER_BOOST),
			"刀/秒 | **动作上限", act, "刀/秒**（取小者）")
		print("[wood] 判据(512 棵 棋盘格)：不浇水",
			512 / rt[1] * avg_t * 60 / 1000000, "M/分",
			"| 浇水 x", WATER_BOOST, "后",
			512 / (rt[1] / WATER_BOOST) * avg_t * 60 / 1000000, "M/分",
			"| 目标 1000")
	else:
		print("[wood] 判据：树再生没量到（regrow_s = 0），下面的预计不可信")


def worker(row, target, verbose):
	# 一行一架。只对 `(x + row) % 2 == 0` 的格子动手；
	# 其余格子是**伴生草地**：踩过去但**不收**（收了草就没伴生了）。
	# 世界是环面 ⇒ 一路向东 32 步会回到原处 ✓
	goto(0, row)
	h0 = num_items(Items.Wood)
	t0 = get_time()
	tprev = t0
	hprev = h0
	laps = 0
	while True:
		# ---- 每圈只算一次的开关 ----
		# **绝对不能放进逐格循环**：放进去就是 32 倍的开销。上一场实测每圈约 185 次 API 调用，
		# 其中 64 次是 `water_here()` 里的四连查（num_items/get_ground_type/get_entity_type/get_water），
		# 另 32 次是"这格空了没有"——而稳态下水位一直在 0.75 以上、树也从来不会缺
		# ⇒ 这些查询 99% 是空转，却吃掉了整圈 1/3 以上的时间（lap_s 2.41 秒就是这么来的）。
		water_now = 0
		if num_items(Items.Water) > WATER_FLOOR:
			if laps < WARMUP_LAPS:
				water_now = 1
			else:
				if laps % WATER_EVERY == 0:
					water_now = 1
		check_empty = 0
		if laps == 0:
			check_empty = 1
		else:
			if laps % CHECK_EVERY == 0:
				check_empty = 1
		x = 0
		while x < SIZE_OF_BOARD:
			if (x + row) % 2 == 0:
				if laps == 0:
					# 只翻树格：① 树可以种在土壤上 ② **只有土壤能浇水** ③ 土壤上不长草、信号干净
					if get_ground_type() != Grounds.Soil:
						till()
				if check_empty == 1:
					if get_entity_type() == None:
						plant(Entities.Tree)
				if can_harvest():
					harvest()
					plant(Entities.Tree)
					HARV[0] = HARV[0] + 1
				if water_now == 1:
					if get_water() < WATER_LEVEL:
						use_item(Items.Water)
			else:
				if check_empty == 1:
					# 伴生格：必须是草。**裸土上不长草**（前一个脚本可能把地全翻了）⇒ 缺了就补种。
					# 没有任何东西会收它 ⇒ 只在第 0 圈查一次就够，不必每圈花 16 次调用去确认。
					if get_entity_type() == None:
						plant(Entities.Grass)
			move(East)
			x = x + 1
		laps = laps + 1
		if laps % REPORT_LAPS == 0:
			now = get_time()
			dt = now - tprev
			if verbose == 1:
				if dt > 0:
					# **只报本机自己的刀数**：`num_items()` 是全局库存，32 架同时收割时每架读到的
					# 都是同一个总数 ⇒ 早期版本报的 "gain_per_s" 全是虚高的假数（每行都 1,600 万）。
					# harv_per_s 是干净的；lap_s 反映动作成本；water_lvl 反映浇水到底顶没顶上去。
					print("[wood] row", row, "laps", laps, "harv", HARV[0],
						"harv_per_s", (HARV[0] - hprev) / dt,
						"lap_s", dt / REPORT_LAPS,
						"water_lvl", get_water(),
						"stock", num_items(Items.Water))
			tprev = now
			hprev = HARV[0]
		if laps % GOAL_LAPS == 0:
			if target > 0:
				if num_items(Items.Wood) >= target:
					break
	print("[wood] row", row, "DONE laps", laps, "harv", HARV[0],
		"gained", num_items(Items.Wood) - h0, "elapsed_s", get_time() - t0)
	return HARV[0]


def main():
	print("=== wood_farm v", VERSION, "start ===")
	print("world_size", SIZE_OF_BOARD,
		"have_wood", num_items(Items.Wood),
		"max_drones", max_drones(),
		"lv_trees", num_unlocked(Unlocks.Trees),
		"lv_poly", num_unlocked(Unlocks.Polyculture),
		"water", num_items(Items.Water))
	if CALIB == 1:
		calib()
	# 棋盘格树格数自检（判据就是 (x+y)%2，不需要预排数组了）
	n_tree = 0
	ty = 0
	while ty < SIZE_OF_BOARD:
		tx = 0
		while tx < SIZE_OF_BOARD:
			if (tx + ty) % 2 == 0:
				n_tree = n_tree + 1
			tx = tx + 1
		ty = ty + 1
	print("[wood] 棋盘格树格 =", n_tree, "(应为", CELLS // 2, ") 伴生格 = 草地",
		CELLS - n_tree, "| 命中率 = (24/48)/3 =", (24 / 48) / 3)
	if n_tree != CELLS // 2:
		print("[wood] ERROR: 棋盘格格数不对，停下来")
		return
	clear()
	# ---- 场地普查：把地面/实体的真实情况打出来 ----
	# "clear() 之后满地是草"曾经是个**假设**，而假设正是这条产线反复出错的地方。
	# 伴生格必须有草；如果前一个脚本把地全翻成了土壤，裸土不长草 ⇒ 伴生请求全部落空、
	# 每刀只剩无伴生基础值（树 2,560 而不是 81,530 平均）⇒ 产量掉到 1/30。
	c_g = 0
	c_s = 0
	c_e = 0
	cw = 0
	_cy = 0
	while _cy < SIZE_OF_BOARD:
		_cx = 0
		while _cx < SIZE_OF_BOARD:
			if get_ground_type() == Grounds.Soil:
				c_s = c_s + 1
			else:
				c_g = c_g + 1
			if get_entity_type() != None:
				c_e = c_e + 1
			cw = cw + get_water()
			move(East)
			_cx = _cx + 1
		move(North)
		_cy = _cy + 1
	print("[wood] 普查: 土壤", c_s, "草地", c_g, "有实体", c_e,
		"平均水位", cw / CELLS)
	if c_s > 0:
		print("[wood] 注意: 有", c_s, "格是裸土 —— 这些格子没有草，做不了伴生（worker 会补种）")
	goto(0, 0)
	cap = max_drones()
	drones = []
	n = SIZE_OF_BOARD
	if n > cap:
		n = cap
	i = 1
	while i < n:
		d = spawn_drone(worker, i, WOOD_TARGET, 0)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[wood] launched", len(drones), "helpers + main on", n, "rows")
	W0 = num_items(Items.Wood)
	T0 = get_time()
	worker(0, WOOD_TARGET, 1)
	total_harv = HARV[0]
	i = 0
	while i < len(drones):
		total_harv = total_harv + wait_for(drones[i])
		i = i + 1
	W1 = num_items(Items.Wood)
	DT = get_time() - T0
	RATE = 0
	if DT > 0:
		RATE = (W1 - W0) / DT
	print("=== wood_farm end ===",
		"wood", W1, "gained", W1 - W0, "elapsed_s", DT,
		"wood_per_s", RATE, "wood_per_min", RATE * 60)
	# ---- 稳定段估算：把启动期刨掉 ----
	# 启动期（种 512 棵树 + 水位从 0 灌满 + 等第一茬树长好）约 STARTUP_S 秒，这期间几乎不产木。
	# 总刀数是 32 架各自的 HARV 相加（逐机独立、干净），所以能算出干净的平均每刀产量；
	# 再按"总刀数 ÷ (总时长 - 启动期)"估稳定速率。**这是估算，不是实测**，只用来判断是否达标。
	if total_harv > 0:
		avg = (W1 - W0) / total_harv
		print("[wood] 总刀数", total_harv, "平均每刀", avg)
		steady_s = DT - STARTUP_S
		if steady_s > 0:
			print("[wood] 稳定段估算(刨掉前", STARTUP_S, "秒启动):",
				total_harv / steady_s * avg * 60 / 1000000, "M/分",
				"| 目标 1000")


main()
