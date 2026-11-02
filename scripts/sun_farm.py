# ============================================================
# sun_farm.py —— **高速刷电量（Power）**（独立脚本：整盘向日葵，一行一架）
#
# 为什么要单独写：main.py 的向日葵带只有「最右 3 列 x 26 行」= 78 格，而且实际只派了 2 架
# （补课阶段先派的 2 架让 `SUN_SPAWNED` 变 1，main8 于是整段跳过；实测 `alive 39` 就是半个带），
# 量级只有 ~10 电/秒。而**电量是"存量"资源**：它只决定后续长时间跑脚本时能不能一直吃 2 倍速，
# 所以正确的用法是"先花几分钟把电灌满，再去跑 dino/迷宫"。
#
# ---------- 实测口径（标定自 BUILD 41/42 的 [sun] 行）----------
#   * 收入 = 收割刀数 x (1 + 7 x 落在"全场最大花瓣"的比例)。实测 206 刀里 24 刀吃到 8 倍
#     ⇒ 平均 **1.68 电/刀**（不是早先以为的 1.11；`hsum 345.88 / harv 206 = 1.68`）。
#   * **访问速率受限，不是地块受限**：一个来回 = 1 次 move + 收割 + 补种 ≈ 3 个动作，
#     实测每格约 1,000 tick ⇒ 单机约 6 刀/秒 ⇒ 约 10 电/秒。加一架就多一份访问速率。
#   * 向日葵 **5 秒**长好 ⇒ 一个来回（~30 格）远长于 5 秒时，**每次经过都是熟的**。
#
# ---------- 本脚本的设计 ----------
#   **一行一架**：32x32 正好 32 行、32 架（31 副机 + 主机），每架包一整行。
#   行内循环极简（查脚下 -> 割/补种 -> 往东走一步），因为棋盘是环形的，
#   从最右列再往东会绕回最左列 ⇒ **一行天然是一个闭环，32 步一圈，零回程开销**。
#   （必须用 move(East) 连续走、不能 goto：goto 的 while 在环形棋盘上会绕远。）
#
# ---------- 模型预期 ----------
#   单机一圈 = 32 格 x (1 move + 最多 2 动作) ≈ 32 x 300~600 tick = 10k~19k tick = 1.6~3.2 秒
#   ⇒ 每格每圈都熟 ⇒ 单机 10~20 刀/秒 ⇒ **32 架合计 320~640 刀/秒**
#   ⇒ **约 540 ~ 1,070 电/秒**（乘以 1.68）。看 [sun] rate 核对真实值。
#
# ---------- 关于浇水（默认关）----------
#   浇水能把生长从 5 秒压到 1 秒，但那只有在"一圈 > 5 秒"时才划算 —— 而**水是产水速率
#   受限的资源**（watering 满级也只有几十罐/秒），整盘 1024 格每圈浇水要 300+ 罐/秒，
#   一定会把水抽干然后退回更慢的状态。所以默认 WATER=0；真要开就靠 WATER_FLOOR 兜底。
#
# ---------- 用法 ----------
#   在游戏里直接运行本文件。它会 `clear()` 整盘（别和 main.py 同时跑）。
#   刷够 POWER_TARGET 就自动收工。之后再去跑 dino_fast.py / maze_gold.py（都是 2 倍速受益者）。
# ============================================================

SIZE_OF_BOARD = get_world_size()
POWER_TARGET = 1000000             # 刷到多少电收工（0 = 不设上限，要手动停）
MAX_LAPS = 0                       # 0 = 无限圈
REPORT_EVERY = 100                 # 每几圈打印一行 [sun]（一圈才 1.6~3.2 秒，太小会刷满日志）
WATER = 0                          # 1 = 补种时浇水（见文件头"关于浇水"）
WATER_THRESHOLD = 0.9
WATER_FLOOR = 20000                # 水量下限：低于此数就停止浇水

# ---- 每架无人机自己的状态（模块全局 = 每架一份）----
HARV = [0]                         # 本机收割刀数
T0 = [0.0]                         # 本机开始时间
P0 = [0]                           # 本机开始时的电量


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


def water_here():
	if WATER == 0:
		return
	if num_items(Items.Water) < WATER_FLOOR:
		return
	if get_water() < WATER_THRESHOLD:
		use_item(Items.Water)


def worker(row):
	# 一架包一整行：先走到本行最西端，然后**靠环形棋盘**一直往东走 ——
	# 32 步回到原点，天然闭环，不需要任何回程。
	goto(0, row)
	HARV[0] = 0
	T0[0] = get_time()
	P0[0] = num_items(Items.Power)
	laps = 0
	tiles = 0
	while True:
		# 第一圈顺手把草原翻成土壤（向日葵必须种在土壤上）。
		# **必须用 laps==0 而不是"本圈走到的格数"**：格数每圈都会归零，
		# 那样这个判断会每格都成立、白白多一次 get_ground_type()（实测踩过）。
		if laps == 0:
			if get_ground_type() != Grounds.Soil:
				till()
		t = get_entity_type()
		if t == None:
			plant(Entities.Sunflower)
			water_here()
		elif can_harvest():
			harvest()
			plant(Entities.Sunflower)
			water_here()
			HARV[0] = HARV[0] + 1
		move(East)
		tiles = tiles + 1
		if tiles >= SIZE_OF_BOARD:
			tiles = 0
			laps = laps + 1
			if laps % REPORT_EVERY == 0:
				now = get_time()
				dt = now - T0[0]
				rate = 0
				if dt > 0:
					rate = (num_items(Items.Power) - P0[0]) / dt
				print("[sun] row", row, "laps", laps,
					"harv", HARV[0],
					"sec_per_lap", dt / laps,
					"power_per_s", rate,
					"power", num_items(Items.Power),
					"water", num_items(Items.Water))
			if MAX_LAPS > 0:
				if laps >= MAX_LAPS:
					break
			if POWER_TARGET > 0:
				if num_items(Items.Power) >= POWER_TARGET:
					break
	print("[sun] row", row, "DONE laps", laps, "harv", HARV[0])
	return HARV[0]


def main():
	print("=== sun_farm start ===")
	print("world_size", SIZE_OF_BOARD,
		"rows", SIZE_OF_BOARD,
		"target_power", POWER_TARGET,
		"power", num_items(Items.Power),
		"water", num_items(Items.Water),
		"max_drones", max_drones(),
		"lv_sun", num_unlocked(Unlocks.Sunflowers))
	clear()
	drones = []
	cap = max_drones()
	# 一行一架：主机认领第 0 行，副机 1..cap-1 各认领一行。
	# 行数少于无人机时后面的副机没活干（不会 spawn），所以这里按较小的那个数派。
	n = SIZE_OF_BOARD
	if n > cap:
		n = cap
	i = 1
	while i < n:
		d = spawn_drone(worker, i)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[sun] launched", len(drones), "helpers + main; rows", n, "of", SIZE_OF_BOARD)
	t_start = get_time()
	p_start = num_items(Items.Power)
	worker(0)
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	dt = get_time() - t_start
	total = num_items(Items.Power) - p_start
	rate = 0
	if dt > 0:
		rate = total / dt
	print("=== sun_farm end ===",
		"power", num_items(Items.Power),
		"gained", total,
		"elapsed_s", dt,
		"power_per_s", rate,
		"water_left", num_items(Items.Water))


main()
