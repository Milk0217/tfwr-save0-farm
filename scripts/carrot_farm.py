# ============================================================
# carrot_farm.py —— **高速产胡萝卜（Carrot）v3**
#
# 目标：**200,000,000 胡萝卜/分钟**（= 3,333,333/秒）。
#
# ============ v1 的三处实测（都写在这里，别再猜一遍）============
#  1. **播种代价 = 512 木材 + 512 干草**（`get_cost(Entities.Carrot)` 与实测扣除完全一致）。
#     按 216-288 次/秒算 = 110-147K 木/秒 ≈ 7-9M 木/分，相对 3.5B 库存完全可承受。
#  2. **无伴生基础值 = 512**（= 1 x 2^9，Carrots lv10 已解锁）。v1 标定量到 81,920，
#     那是**满伴生**值（512 x 160）—— 因为 `clear()` 后满地是草原，胡萝卜"抢 Grass"的请求
#     当场就被满足了。⇒ 标定必须**自己按 get_companion() 摆好伴生**才能得到确定的值，
#     再除以 160 反推基础值。
#  3. **再生 5.87 秒**（土壤上、已补种）。这是胡萝卜真正的瓶颈：
#     512 格 / 5.87 秒 = **87 刀/秒** ≈ 85M/分，**不浇水永远到不了 200M**
#     ⇒ 必须浇水（watering.md：水位 0 是 1 倍、水位 1 是 5 倍，线性）。
#
# ============ v1 为什么死循环（教训记在这里）============
#  a. `till()` 写在了**圈循环**里而不是**逐格循环**里 ⇒ 一行 32 格里只有第 0 格翻了土。
#  b. 漏了 wood v6 里"空着就种"的分支。草原上 `can_harvest()` **恒为真**（草永远可割），
#     于是循环变成"割草 -> 在草原上种胡萝卜 -> 报错"重复 31 次，
#     **胡萝卜永远不增加 ⇒ 目标永不达成 ⇒ 跑到天荒地老**（实测 row 0 前 10 圈割了 310 刀）。
#     ⇒ 两条永久护栏：**只割自己那种作物** + **停滞检测**（连续 3 次报告没涨就主动退出）。
#  c. 标定把满伴生值当成基础值 ⇒ 预测虚高 160 倍，打印出 45,180M/分这种荒谬数。
#     **预测数字荒谬本身就是报警信号** —— 以后看到先怀疑标定，别怀疑世界。
#
# ============ 布局：棋盘格（v2 实测之后改的，v3 起用）============
#  胡萝卜**没有邻居惩罚**（trees.md 那条"每个树邻居生长时间翻倍"只写在 trees.md，
#  胡萝卜/南瓜/仙人掌文档里都没有）⇒ 布局只看"伴生比例"和"几架机器在干活"两件事。
#  v2 用了列条带，实测结论：
#    * 32 行都有活干、16 刀/圈 = **100% 就绪**（浇水把生长顶到 1.48 秒 < 单圈 2.22 秒）✓
#    * 但实测**平均每刀 = 14,120**，反推命中率 0.167 ⇒ **菱形窗 24 格里伴生只占 12 格**。
#  ⇒ 换成**棋盘格**：伴生占 **16/24 = 0.667**（菱形窗里交错排布，比条带的 0.5 更高！）
#     命中率 0.222 ⇒ 平均每刀 512 x 36.3 = **18,601（+32%）**
#     棋盘格每行都有胡萝卜格 ⇒ **32 架照样全部干活**，每刀动作数不变（走两格+割+种 = 4）✓
#     ⇒ **纯赚 32%，没有任何代价**。这就是 v2 -> v3 的唯一改动。
#
#  v2 的实测结论（保留，别再重新量）：
#    单机 7.2 刀/秒、单圈 2.22 秒、16 刀/圈（满就绪）、水 0.87~0.93
#    ⇒ 230 刀/秒 x 14,120 = 3.25M/秒 = **195M/分**（差目标 2.5%）
#    ⇒ 换棋盘格后预计 230 x 18,601 = 4.28M/秒 = **257M/分**（超目标 28%）✓
#
# ============ 动作预算（200M/分 靠什么撑起来）============
#  单机吞吐按 wood 实测的 77 次 API 调用/秒（tick 预算约 6,075/秒 ÷ 每次调用约 79 tick）：
#    每圈 = 32 移动 + 16 割 + 16 种 + 16 can_harvest + 少量水位查询 ≈ 84 次调用 ⇒ 单圈约 1.1 秒
#    ⇒ 单机 14.5 刀/秒 ⇒ 32 架 = 465 刀/秒 ⇒ x 16,307 = **455M/分**（上限）
#  保守按"27 个动作/秒"的老模型：864/4 = 216 刀/秒 ⇒ x 16,307 = **211M/分**（下限）
#  ⇒ 200M 可行，但**余量不厚** ⇒ 每一处空转都要省（这就是 v1 那个"每圈 185 次调用"要命的理由）。
#
# ============ 纪律 ============
#   * **标定必须量在自己造的条件下**：土壤上、割完补种再等（wood v3 量到草的 0.47 秒那次），
#     伴生自己按 get_companion() 摆（v1 量到 81,920 那次）。
#   * **不能假设 clear() 之后满地是草**，也不能假设是土壤 ⇒ 普查 + 缺啥补啥。
#   * **get_time() / get_tick_count() / quick_print() 完全免费**（timing.md）⇒ 进度行用 quick_print。
#   * **num_items() 是全局库存** ⇒ 多机同收时差值是脏的；进度只报本机刀数。
#   * **启动期要摊薄**：CARROT_GAIN（相对增量）设大，跑够 1-2 分钟。**别用绝对值当目标** ——
#     v3 设了绝对值 4 亿而开局已有 3.98 亿 ⇒ 第 10 圈就收工，平均值被启动期拖到 191M/分。
#   * **没有三元表达式**，`**` 没用过 ⇒ 一律不写。
# ============================================================

VERSION = 4
SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD
CARROT_GAIN = 500000000           # **相对增量**（不是绝对值！）跑够长把启动期摊薄：
								   # 约 118 秒 / 50 圈 ⇒ 启动期占比降到 10% 以内
CALIB = 1
REPORT_LAPS = 10
GOAL_LAPS = 5
TIMEOUT_S = 60
STALL_REPORTS = 3                  # 连续这么多次报告胡萝卜没涨 ⇒ 判定卡死，主动退出
# **伴生窗口是"曼哈顿距离 <= 3 的菱形"（25 格，去掉自己 = 24 格），不是 7x7 的 48 格！**
# polyculture.md 写的是 "within 3 moves"，而"一 move"就是走一格 ⇒ 菱形。这条 2026-09-13 用
# 两次独立实测同时校准上了：
#   棋盘格（wood）：菱形 24 格里伴生占 16 ⇒ 16/24 = 0.667 ⇒ 命中 0.222 ⇒ 树 2560x36.3 = 92,900
#                   （wood 实测平均 90,050~94,252 ✓）
#   列条带（carrot）：伴生占 12 ⇒ 0.5 ⇒ 命中 0.167 ⇒ 512x27.6 = 14,120（carrot 实测 14,120 ✓）
# ⇒ **棋盘格的伴生比例最高（0.667），比我原先以为的条带（0.583）更好** —— 之前整整反了。
MATCH = (16 / 24) / 3              # 0.222：棋盘格菱形窗里伴生占 16/24，"总是选不同物种" ⇒ 除以 3
PLANTS_PER_S_EST = 216             # 播种速率上限（动作预算），用于资源闸门
WOOD_SAFETY = 60                   # 闸门：每秒木材消耗不得高于"库存/60"
STARTUP_S = 10                     # 启动期估算：翻土 + 种满 + 等第一茬
WATER_LEVEL = 0.75                 # 低于此水位就浇（每次 +0.25 ⇒ 水位在 0.75~1.0 之间走）
WATER_EVERY = 2                    # 稳态下每 2 圈查一次水位
WARMUP_LAPS = 4                    # 开局每圈都浇：水位从 0 顶到满要 4 次浇水
CHECK_EVERY = 8                    # 每 8 圈补查一次"格子空了没有"

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


def wait_grown(max_sec):
	t0 = get_time()
	while get_time() - t0 < max_sec:
		if can_harvest():
			return get_time() - t0
	return -1


def till_here():
	if get_ground_type() != Grounds.Soil:
		till()


def calib():
	# 返回 1 = 可以开跑；0 = 有问题，别跑
	clear()
	# ---- 1) 播种代价：get_cost 字面值 + 实测扣除 ----
	goto(0, 0)
	till_here()
	cost = get_cost(Entities.Carrot)
	if cost == None:
		print("[carrot] CALIB get_cost 返回 None（异常）")
	else:
		for item in cost:
			print("[carrot] CALIB get_cost:", item, "=", cost[item])
	w0 = num_items(Items.Wood)
	h0 = num_items(Items.Hay)
	plant(Entities.Carrot)
	dw = w0 - num_items(Items.Wood)
	dh = h0 - num_items(Items.Hay)
	print("[carrot] CALIB 实播 1 棵：扣 wood", dw, " hay", dh)
	# ---- 2) 等长好，然后**自己摆伴生**，量确定的值 ----
	r = wait_grown(TIMEOUT_S)
	if r < 0:
		print("[carrot] CALIB 生长超时 >", TIMEOUT_S, "秒 ⇒ 停下来查原因")
		return 0
	print("[carrot] CALIB 长好了，用了", r, "秒；按 get_companion() 摆伴生")
	plant_type, (cx, cy) = get_companion()
	goto(cx, cy)
	if get_entity_type() != None:
		harvest()
	if plant_type == Entities.Carrot:
		till_here()
	plant(plant_type)
	goto(0, 0)
	c0 = num_items(Items.Carrot)
	harvest()
	y = num_items(Items.Carrot) - c0
	base = y / 160
	print("[carrot] CALIB 满伴生单次 =", y, "⇒ **无伴生基础值 =", base, "**")
	# ---- 3) 再生：**割完必须补种再等** ----
	till_here()
	plant(Entities.Carrot)
	r2 = wait_grown(TIMEOUT_S)
	print("[carrot] CALIB regrow_s =", r2, "(土壤上量、已补种)")
	# ---- 4) 资源闸门 ----
	print("[carrot] CALIB 库存: wood", num_items(Items.Wood), " hay", num_items(Items.Hay))
	if dw > 0:
		need = dw * PLANTS_PER_S_EST
		have = num_items(Items.Wood) / WOOD_SAFETY
		print("[carrot] 闸门：预计木材消耗", need, "/秒  vs  库存承受力", have, "/秒")
		if need > have:
			print("[carrot] ABORT: 播种代价太高，会把木材抽干。先别跑。")
			return 0
	# ---- 5) 预测（**两个上限取小**：生长 vs 动作）----
	if base > 0:
		avg = base * (1 + 159 * MATCH)
		act = 32 * 27 / 4
		print("[carrot] 预测：基础", base, " 命中率", MATCH, " 平均每刀", avg)
		print("[carrot] 预测：动作上限", act, "刀/秒 ⇒ 约", act * avg * 60 / 1000000, "M/分")
		if r2 > 0:
			dry = CELLS / 2 / r2
			wet = CELLS / 2 / (r2 / 3.9)
			print("[carrot] 预测：生长上限 不浇水", dry, "刀/秒 ⇒ 约",
				dry * avg * 60 / 1000000, "M/分 | 浇水 x3.9 后", wet, "刀/秒 ⇒ 约",
				wet * avg * 60 / 1000000, "M/分 | 目标 200")
	return 1


def worker(row, target, verbose):
	# 列条带：偶数列 x = 胡萝卜（生产格），奇数列 x = 草（伴生格）。
	# **32 行全都这么走** ⇒ 每行都有活干，没有空走的无人机（v1 的行条带白丢了一半机器）。
	goto(0, row)
	t0 = get_time()
	tprev = t0
	hprev = 0
	cprev = num_items(Items.Carrot)
	stall = 0
	laps = 0
	while True:
		# ---- 每圈只算一次的开关（放进逐格循环就是 32 倍开销）----
		water_now = 0
		if num_items(Items.Water) > 20000:
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
				# ---- 生产格 ----
				if laps == 0:
					# 翻土**必须在逐格循环里**（v1 放在圈循环里 ⇒ 一行只翻了第 0 格）
					till_here()
				if check_empty == 1:
					if get_entity_type() == None:
						plant(Entities.Carrot)
				# **只割胡萝卜**：草原上 can_harvest() 恒为真，不加这个判断就会割草、
				# 然后在草原上种胡萝卜报错 —— v1 的死循环就是这么来的。
				if get_entity_type() == Entities.Carrot:
					if can_harvest():
						harvest()
						plant(Entities.Carrot)
						HARV[0] = HARV[0] + 1
				if water_now == 1:
					if get_water() < WATER_LEVEL:
						use_item(Items.Water)
			else:
				# ---- 伴生格：必须是草。没人收它 ⇒ 只在第 0 圈查一次 ----
				if check_empty == 1:
					if get_entity_type() == None:
						plant(Entities.Grass)
			move(East)
			x = x + 1
		laps = laps + 1
		if laps % REPORT_LAPS == 0:
			now = get_time()
			dt = now - tprev
			cnow = num_items(Items.Carrot)
			if verbose == 1:
				if dt > 0:
					# quick_print 是免费的（timing.md）；普通 print 不是。32 架刷屏本身就在吃 tick。
					quick_print("[carrot] row", row, "laps", laps, "harv", HARV[0],
						"harv_per_s", (HARV[0] - hprev) / dt,
						"lap_s", dt / REPORT_LAPS,
						"carrot", cnow,
						"water_lvl", get_water())
			# ---- 停滞检测：连续 STALL_REPORTS 次胡萝卜没涨就主动退出 ----
			if cnow <= cprev:
				stall = stall + 1
			else:
				stall = 0
			if stall >= STALL_REPORTS:
				print("[carrot] ERROR: row", row, "连续", stall,
					"次报告胡萝卜没涨（收割", HARV[0], "刀）⇒ 判定卡死，退出。")
				break
			cprev = cnow
			tprev = now
			hprev = HARV[0]
		if laps % GOAL_LAPS == 0:
			if target > 0:
				if num_items(Items.Carrot) >= target:
					break
	print("[carrot] row", row, "DONE laps", laps, "harv", HARV[0],
		"elapsed_s", get_time() - t0)
	return HARV[0]


def main():
	print("=== carrot_farm v", VERSION, "start ===")
	print("world_size", SIZE_OF_BOARD,
		"have_carrot", num_items(Items.Carrot),
		"have_wood", num_items(Items.Wood),
		"have_hay", num_items(Items.Hay),
		"max_drones", max_drones(),
		"lv_carrots", num_unlocked(Unlocks.Carrots),
		"lv_poly", num_unlocked(Unlocks.Polyculture))
	if CALIB == 1:
		if calib() == 0:
			print("=== carrot_farm aborted ===")
			return
	clear()
	# ---- 场地普查（不能假设 clear() 之后满地是草，也不能假设是土壤）----
	c_s = 0
	c_g = 0
	_cy = 0
	while _cy < SIZE_OF_BOARD:
		_cx = 0
		while _cx < SIZE_OF_BOARD:
			if get_ground_type() == Grounds.Soil:
				c_s = c_s + 1
			else:
				c_g = c_g + 1
			move(East)
			_cx = _cx + 1
		move(North)
		_cy = _cy + 1
	print("[carrot] 普查: 土壤", c_s, "草地", c_g)
	goto(0, 0)
	print("[carrot] 布局: **棋盘格** (x+y)%2==0 种胡萝卜", CELLS // 2, "格 |",
		"其余", CELLS // 2, "格草地做伴生 | 命中率 =", MATCH,
		"（菱形窗 16/24 / 3 = 0.222，比列条带的 0.167 高 33%）")
	if c_s > 0:
		print("[carrot] 注意: 有", c_s, "格是裸土 —— 伴生列上的裸土不长草，worker 会补种")
	# **目标必须相对开局库存**：v3 设了绝对值 4 亿，而开局已有 3.98 亿 ⇒ 第 10 圈就收工，
	# 24 秒里前 5 圈全是启动期（翻 512 格土 + 种满 + 等第一茬 4.4 秒 + 灌水）
	# ⇒ 报出来的平均只有 191M/分，而稳定段其实是 255M/分。wood 那次也是同一个错。
	target = num_items(Items.Carrot) + CARROT_GAIN
	print("[carrot] 目标 =", num_items(Items.Carrot), "+", CARROT_GAIN, "=", target,
		"（按 255M/分 约需", CARROT_GAIN / 255000000 * 60, "秒）")
	n = SIZE_OF_BOARD
	cap = max_drones()
	if n > cap:
		n = cap
	drones = []
	i = 1
	while i < n:
		d = spawn_drone(worker, i, target, 0)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[carrot] launched", len(drones), "helpers + main on", n, "rows")
	C0 = num_items(Items.Carrot)
	W0 = num_items(Items.Wood)
	H0 = num_items(Items.Hay)
	T0 = get_time()
	worker(0, target, 1)
	total_harv = HARV[0]
	i = 0
	while i < len(drones):
		total_harv = total_harv + wait_for(drones[i])
		i = i + 1
	C1 = num_items(Items.Carrot)
	DT = get_time() - T0
	RATE = 0
	if DT > 0:
		RATE = (C1 - C0) / DT
	print("=== carrot_farm end ===",
		"carrot", C1, "gained", C1 - C0, "elapsed_s", DT,
		"carrot_per_s", RATE, "carrot_per_min", RATE * 60)
	print("[carrot] 消耗: wood", W0 - num_items(Items.Wood),
		" hay", H0 - num_items(Items.Hay))
	if total_harv > 0:
		avg = (C1 - C0) / total_harv
		steady_s = DT - STARTUP_S
		print("[carrot] 总刀数", total_harv, "平均每刀", avg)
		if steady_s > 0:
			print("[carrot] 稳定段估算(刨掉前", STARTUP_S, "秒启动):",
				total_harv / steady_s * avg * 60 / 1000000, "M/分 | 目标 200")


main()
