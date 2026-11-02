# ============================================================
# pumpkin_farm3.py —— 南瓜 v3 架构：**半块 tender + 兄弟互认收割门**
#
# 目标 20M/分。前两版的结构性教训：
#   * v1（现状，16 块各 1 架）实测 16.3M/分，周期 8.8 秒；
#     打点实测周期 = tend 270 格 + replant 140 格（走位 200 tick/格 ⇒ 99.7% 的预算）
#   * v2（硬屏障，收齐 32 个再收）实测 **11.0M**：屏障把"各块平均"变成"最慢那块"，
#     再加 47 次 spawn 与 STATE 重扫 ⇒ 亏
#
# ============ 本版要解决的问题 ============
# 周期里 **270 格是"每修一代死瓜就得把 49 格走一遍"** —— 机制强制，单架躲不掉。
# 唯一的砍法是**把一块劈成两个半块、各派一架**（每次扫描走位减半）。
# 而两架不能共享收割门的记忆 ⇒ 本版用**两架互认**解决，**不要屏障、也不要主线仲裁**：
#
#   前半块 tender（anchor）：长驻扫自己那半块，全熟就返回 0
#   后半块 tender（closer）：长驻扫自己那半块；扫完**轮询 has_finished(兄弟)**，
#                            兄弟也报 0 ⇒ 它自己就在块里，**直接割一刀**
#                            （合并后的 7x7 收任意一格都拿整块的钱 ✓ 已实测）
#
# ⇒ 收割不需要额外派机器；主线派完 32 架就只管等 ⇒ 比 v2 少两个角色。
#
# ============ 全部依据都是实测（probe_* 系列）============
#   move / harvest / plant = 200 tick    查询(can_harvest/get_entity/get_water) = 1 tick
#   has_finished 轮询 = 4 tick           wait_for 取值 = 1 tick
#   spawn_drone = 211 tick               引擎 6,075 tick/秒 ⇒ 单机 30.4 动作/秒
#   生长：干 1.1~1.5 秒；**满水 0.14 秒**（⇒ GROW_MIN=0.15）
#   预期：半块走位约 180 格 ÷ 30.4 = 5.9 秒 + 32 次 spawn 1.1 秒 ≈ **7.3 秒 ⇒ 19.8M/分**
#   （⚠️ 180 格是模型推算不是实测 ⇒ 实际可能 19~24M，目标卡在区间里）
#
# ============ 无人机配额（cap=32 含主线）============
#   主线：派 block 0 的 anchor，然后**自己当 block 0 的 closer**
#   其余 15 块：各派 anchor + closer = 30 架
#   合计 31 架 helper + 主线 = 32 ✓ 没有余量给向日葵（电量实测漂移很小，可接受）
#
# ============ 纪律（血泪）============
#  * **只认 Entities.Pumpkin**：clear() 后整盘是草原、草永远可割，`can_harvest()`
#    恒为真 ⇒ 不翻土/不认实体就会把空地当成成熟南瓜（v2 实测全场零产出）。
#  * **死瓜的 can_harvest() 永远是 False**（文档）⇒ 只以 can_harvest 为判据的循环会卡死
#    （probe_pump 实测踩到）⇒ 必须**同时看实体**。
#  * **时间戳调度（DUE）在这里没用**：实测轮次间隔约 2 秒 ≫ 生长 0.14 秒
#    ⇒ 每轮所有格子都"到点" ⇒ 跳过永远不触发。所以本版**不用 DUE**，老老实实每轮扫。
#  * **目标必须相对开局库存**（绝对目标已连栽两次）。
#  * 没有三元表达式；LF + 制表符；一律用完整原文锚点改代码。
# ============================================================

VERSION = 3
BOARD = get_world_size()
REG = 7
GAP = 1
PITCH = REG + GAP
GRID = BOARD // PITCH
NBLOCK = GRID * GRID
TILES = REG * REG
HALF = (TILES + 1) // 2            # 25（0 号半块 25 格，1 号半块 24 格）
PUMPKIN_GAIN = 80000000
WATER_THRESHOLD = 0.9
WATER_FLOOR = 20000
CYCLE_CAP = 600
SPAWN_COST = 211                   # 实测：用来把 spawn 开销折算成报告里的秒数

WOK = [1]                          # 本轮允不允许浇水（每轮算一次，别放进逐格循环）
HARV = [0]


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


def bx(b, i):
	return (b % GRID) * PITCH + (i % REG)


def by(b, i):
	return (b // GRID) * PITCH + (i // REG)


def tend(b, h, sib, closer):
	# 只管第 b 块的第 h 个半块，长驻到"我这半块全部存活且成熟"才结束。
	px = []
	py = []
	i = h * HALF
	stop = (h + 1) * HALF
	if stop > TILES:
		stop = TILES
	while i < stop:
		append(px, bx(b, i))
		append(py, by(b, i))
		i = i + 1
	n = len(px)
	st = []
	i = 0
	while i < n:
		append(st, 0)
		i = i + 1
	p = n
	while p > 0:
		# 水量下限与开关**每轮算一次**（逐格算就是 49 倍的浪费）
		WOK[0] = 0
		if num_items(Items.Water) > WATER_FLOOR:
			WOK[0] = 1
		i = 0
		while i < n:
			if st[i] == 0:
				goto(px[i], py[i])
				# **先翻土再读实体**（草原上草永远可割，不翻土会误判 —— v2 的大坑）
				if get_ground_type() != Grounds.Soil:
					till()
				t = get_entity_type()
				if t == Entities.Pumpkin:
					if can_harvest():
						st[i] = 1          # 活着且成熟；成熟后不会再枯死 ⇒ 单调收敛
				else:
					if t != None:
						harvest()          # 死瓜 / 别的东西，清掉重种
					plant(Entities.Pumpkin)
				if WOK[0] == 1:
					if get_water() < WATER_THRESHOLD:
						use_item(Items.Water)
			i = i + 1
		p = 0
		i = 0
		while i < n:
			if st[i] == 0:
				p = p + 1
			i = i + 1
	# ---- 后半块：等兄弟，两个半块都全熟就自己收割 ----
	if closer == 1:
		# 轮询（4 tick/次，实测几乎免费）——**别用硬屏障**：谁先好谁先走
		while has_finished(sib) == False:
			pass
		r = wait_for(sib)
		if r == 0:
			# 兄弟那半块也全熟 ⇒ 整块 7x7 已合并 ⇒ 收任意一格都拿整块的钱
			goto(bx(b, 0), by(b, 0))
			harvest()
			HARV[0] = HARV[0] + 1
	return 0


def main():
	print("=== pumpkin_farm3 v", VERSION, "start ===")
	print("board", BOARD, "reg", REG, "gap", GAP, "pitch", PITCH,
		"blocks", NBLOCK, "tiles", TILES, "half", HALF,
		"max_drones", max_drones(), "lv_pumpkins", num_unlocked(Unlocks.Pumpkins),
		"water", num_items(Items.Water), "carrot", num_items(Items.Carrot))
	if NBLOCK * 2 > max_drones():
		# 16 块 x 2 半块 = 32 个槽，正好等于 cap（含主线）；主线占 1 个 ⇒ helper 需 31 个
		print("[p3] 半块数", NBLOCK * 2, "cap", max_drones(), "⇒ helper 需要", NBLOCK * 2 - 1)
	if NBLOCK * 2 - 1 > max_drones() - 1:
		print("[p3] ERROR: 无人机不够（需要", NBLOCK * 2 - 1, "架 helper）")
		return
	TARGET = num_items(Items.Pumpkin) + PUMPKIN_GAIN
	print("[p3] 目标 =", num_items(Items.Pumpkin), "+", PUMPKIN_GAIN, "=", TARGET)
	clear()
	G0 = num_items(Items.Pumpkin)
	GT0 = get_time()
	cycle = 0
	while cycle < CYCLE_CAP:
		cycle = cycle + 1
		T0 = get_time()
		# ---- 阶段一：其余 15 块的 anchor（主线自己也算一个 anchor 的父机）----
		anchors = []
		b = 1
		while b < NBLOCK:
			d = spawn_drone(tend, b, 0, None, 0)
			if d != None:
				append(anchors, d)
			b = b + 1
		# block 0 的 anchor（主线的 closer 要轮询它）
		a0 = spawn_drone(tend, 0, 0, None, 0)
		# ---- 阶段二：closer 带上各自 anchor 的句柄 ----
		closers = []
		i = 0
		while i < len(anchors):
			b = i + 1
			d = spawn_drone(tend, b, 1, anchors[i], 1)
			if d != None:
				append(closers, d)
			i = i + 1
		# ---- 主线自己当 block 0 的 closer（这样 32 架正好用满）----
		tend(0, 1, a0, 1)
		# ---- 收尾：等其余人都结束 ----
		i = 0
		while i < len(closers):
			wait_for(closers[i])
			i = i + 1
		i = 0
		while i < len(anchors):
			wait_for(anchors[i])
			i = i + 1
		DT = get_time() - T0
		GN = num_items(Items.Pumpkin)
		TT = get_time() - GT0
		RATE = 0
		if TT > 0:
			RATE = (GN - G0) / TT
		print("[p3] cycle", cycle, "cycle_s", DT, "harvests", HARV[0],
			"spawns", 2 * NBLOCK, "spawn_s", 2 * NBLOCK * SPAWN_COST / 6075,
			"pumpkin", GN, "per_min_M", RATE * 60 / 1000000, "(目标 20)",
			"water", num_items(Items.Water))
		if num_items(Items.Pumpkin) >= TARGET:
			break
	GN = num_items(Items.Pumpkin)
	TT = get_time() - GT0
	RATE = 0
	if TT > 0:
		RATE = (GN - G0) / TT
	print("=== pumpkin_farm3 end ===", "cycles", cycle, "harvests", HARV[0],
		"gained", GN - G0, "elapsed_s", TT,
		"pumpkin_per_s", RATE, "pumpkin_per_min", RATE * 60,
		"per_cycle_s", TT / cycle)


main()
