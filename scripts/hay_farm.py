# ============================================================
# hay_farm.py —— **高速产草（Hay）v2：伴生自适应布局 + 瘦身循环**
#
# 目标：`Leaderboards.Hay` 的 `num_items(Items.Hay) >= 2000000000`（= 2000M 草）。
#
# ============ v2 相对 v1 的两处（都由实测数据驱动）============
#
# 【一】伴生布局 —— 草产量最大的杠杆（实测约 x13.8）
#   CALIB 实测（本存档）：
#     草基础值（Grass lv10）= **512**（= 2^9，又是 `2^(lv-1)` 那个模式）
#     满足伴生之后        = **81,920** = 512 x 160（Polyculture lv5）
#     再生时间            = **0.47 秒** ⇒ 上限 2,179 次/秒，**不是瓶颈**
#   **致命事实**（docs/game/unlocks/polyculture.md）：
#     "Each plant chooses this randomly, but it will **always choose a different plant than itself**."
#     ⇒ 一片纯草田里每株的请求都是"灌木/树/胡萝卜"，而周围**全是草**
#       ⇒ **一格都满足不了** ⇒ 纯草田拿到 x1，把 x160 整个丢掉。
#   **好消息**：同一份文档写着 "**The growth stage of the carrot doesn't matter.**"
#     ⇒ 只要那格**有那个物种**就行；而**草不用播种**（割完自己长回来）⇒ 请求不变
#     ⇒ **布局是一次性的、永久生效**。
#
#   v2 的做法（**两遍扫描、自适应选物种**，比盲铺棋盘更好）：
#     第 1 遍：走遍全盘，对每一株草读 `get_companion()`，把"谁点名了哪个格子的哪个物种"
#              记进 TALLY[格*3+物种]。
#     第 2 遍：某格只要被 >= MIN_REQ 株草点名，就改成**被点名最多的那个物种**
#              （那些草从此永久吃 x160）。
#     然后才开始收草（只收草格，伴生格不动）。
#   ⇒ 脚本会先打印**物种分布**和**预计被满足的草株数**，跑之前就能算出该期待多少。
#
# 【二】循环瘦身（实测每格 437 tick -> 目标约 200 tick）
#   实测 v1：13 圈 x 32 格用了 30 秒 ⇒ **每格 437 tick**，而动作本身只要 188 tick
#   （move 94 + harvest 94）。差在**每格都调用了 `num_items()` 和 `get_time()`** ——
#   这两个都是函数调用。v2 把它们移到**每圈一次**，内循环只剩
#   「查草格标记 -> can_harvest -> harvest -> move」。
#
# ---------- 纪律（血泪，改这个项目的脚本之前先读）----------
#   * **没有三元表达式**（`A if C else B`）：实测让脚本在校验阶段就 Error、零输出，
#     而 py_compile（校验 Python 语法）与 audit_save0.py **都抓不到**。
#     ⇒ 用 `tools/gamelang.py` 扫这类"Python 有、本语言没有"的写法。
#   * `num_items()` 是**全局库存**：多架同时收割时差值是脏的（污染倍数 ≈ 并行机数），
#     所以任何"单次产量"都必须**单机单格**量（CALIB 就是这么做的）。
# ============================================================

SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD
HAY_TARGET = 2000000000            # 排行榜目标（docs/game/unlocks/leaderboard.md）
CALIB = 1                          # 1 = 开局先做单机标定（推荐开着）
MIN_REQ = 2                        # 一个格子至少被这么多株草点名，才改成伴生格
REPORT_LAPS = 20                   # 每几圈打印一行
GOAL_LAPS = 4                      # 每几圈查一次目标（**不要每格查**，那是 v1 变慢的主因之一）

# ---- 全盘布局（只有主机用得到）----
IS_COMP = []                       # 1024：1 = 伴生格
TALLY = []                         # 1024 x 3：TALLY[格*3+物种] = 被点名次数
WANT = []                          # 1024：该格被点名最多的物种编码
_i = 0
while _i < CELLS:
	append(IS_COMP, 0)
	append(WANT, -1)
	_i = _i + 1
# **必须留余量**：`TALLY[k*3+sp]` 里 k 最大是 CELLS-1、sp 最大是 3
# ⇒ 最大下标 = (CELLS-1)*3+3 = CELLS*3 **恰好等于长度** ⇒ 越界一格。
# 实测：第一次跑 v2 就崩在这里（`索引 3072 超出列表范围 In: main <- place_pass`），
# 而 `audit_save0.py` **抓不到** —— 它只查字面量下标，这种动态下标它管不了。
# ⇒ 规矩：**扁平多下标数组一律多留几个，并在启动时做一次边界自检**（见 main）。
TALLY_N = CELLS * 3 + 4
_i = 0
while _i < TALLY_N:
	append(TALLY, 0)
	_i = _i + 1

# ---- 每架无人机自己的状态（模块全局 = 每架一份）----
ISG = []                           # 本机那一行里"哪些格子是草格"
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


def ecode(t):
	# print 不支持枚举对象：0=草 1=灌木 2=树 3=胡萝卜 -1=其它/空
	if t == Entities.Grass:
		return 0
	if t == Entities.Bush:
		return 1
	if t == Entities.Tree:
		return 2
	if t == Entities.Carrot:
		return 3
	return -1


def wait_grown(max_sec):
	t0 = get_time()
	while get_time() - t0 < max_sec:
		if can_harvest():
			return get_time() - t0
	return -1


def cut():
	g0 = num_items(Items.Hay)
	harvest()
	return num_items(Items.Hay) - g0


# ------------------------------------------------------------
# 开局标定（单机单格，干净读数）
# ------------------------------------------------------------
def calib():
	clear()
	goto(0, 0)
	wait_grown(60)
	cut()
	regrow = wait_grown(60)
	print("[hay] CALIB regrow_s =", regrow, "(割掉到又能割)")
	base = cut()
	print("[hay] CALIB base_yield(no companion) =", base)
	wait_grown(60)
	c = get_companion()
	if c == None:
		print("[hay] CALIB WARNING: get_companion() 返回 None")
		return
	pt, (px, py) = c
	print("[hay] CALIB companion wants code", ecode(pt), "at", px, py, "(1=灌木 2=树 3=胡萝卜)")
	goto(px, py)
	if pt == Entities.Carrot:
		if get_ground_type() != Grounds.Soil:
			till()
	plant(pt)
	goto(0, 0)
	wait_grown(60)
	comp = cut()
	print("[hay] CALIB with_companion =", comp)
	if base > 0:
		print("[hay] CALIB multiplier =", comp / base, "(Polyculture lv5 的文档值 = 160)")
	print("[hay] CALIB 参考：内循环瘦身后每格约 200 tick ⇒ 约 970 次收割/秒；",
		"2000M/分(33,333,333/秒) 需要每次 >=", 33333333 / 970)


# ------------------------------------------------------------
# 第一遍：统计"谁点名了哪个格子的哪个物种"
# ------------------------------------------------------------
def tally_pass():
	i = 0
	while i < CELLS:
		IS_COMP[i] = 0
		WANT[i] = -1
		i = i + 1
	i = 0
	while i < CELLS * 3:
		TALLY[i] = 0
		i = i + 1
	y = 0
	while y < SIZE_OF_BOARD:
		x = 0
		while x < SIZE_OF_BOARD:
			goto(x, y)
			if get_entity_type() == Entities.Grass:
				c = get_companion()
				if c != None:
					pt, (px, py) = c
					sp = ecode(pt)
					# **只关心"非草"的请求**：草的伴生永远不是草（always a different plant）
					if sp >= 1:
						k = py * SIZE_OF_BOARD + px
						TALLY[k * 3 + sp] = TALLY[k * 3 + sp] + 1
			x = x + 1
		y = y + 1


# ------------------------------------------------------------
# 第二遍：被点名 >= MIN_REQ 的格子改成"被点名最多的那个物种"
# ------------------------------------------------------------
def place_pass():
	ncomp = 0
	y = 0
	while y < SIZE_OF_BOARD:
		x = 0
		while x < SIZE_OF_BOARD:
			k = y * SIZE_OF_BOARD + x
			best = -1
			bestn = 0
			sp = 1
			while sp <= 3:
				n = TALLY[k * 3 + sp]
				if n > bestn:
					bestn = n
					best = sp
				sp = sp + 1
			# ================= v3：改成**棋盘格 50/50** ===================
			# 实测（第 25 节）：自适应布局**完全没生效** —— 命中率 3.5%，而随机基线是 3.9%。
			# 根因：**收割 = 换了一株新草，伴生偏好会重抽**（polyculture.md 说的是
			# "different for each individual plant"；我只看到"growth stage 不影响"，
			# 漏了"收割即换株"）。所以预排的伴生对不上，统计出来的 TALLY 是噪声。
			#
			# ⇒ 布局不再依赖任何预测，直接铺棋盘，把**随机命中率稳定抬到 f/3**：
			#     平均每刀 = 512 x (1 + 159 x f/3)；速率 ∝ (1-f) x (1 + 53f)
			#     这条曲线在 **f = 0.49** 取最大值 13.75
			#     f=0.116（旧 MIN_REQ=2）-> 6.33 -> 96.2M/分（实测）
			#     **f=0.50（棋盘格）      -> 13.75 -> 约 209M/分**  ✓ 过 200M/分
			# 棋盘格与"偏好是否会重抽"这个假设**无关**：即使布局本来有效，
			# 50/50 也就是随机命中的那个值；所以这个改动是稳的。
			# **整行条带**：伴生格只在奇数行，草独占偶数行。
			# 比棋盘格更好的两处：
			#   1. **每走一格就是一刀** —— 棋盘格里一半的走路花在伴生格上；
			#   2. **命中率更高**：草株 3 步内的 7x7 候选里，奇数行占 4 行
			#      ⇒ P(落点有伴生) = 28/48 = 0.583（棋盘格只有 0.5）
			#      ⇒ 命中 = 0.583/3 = 19.4% ⇒ 平均每刀 16,333。
			if y % 2 == 1:
				IS_COMP[k] = 1
				WANT[k] = best
				ncomp = ncomp + 1
			x = x + 1
		y = y + 1
	y = 0
	while y < SIZE_OF_BOARD:
		x = 0
		while x < SIZE_OF_BOARD:
			k = y * SIZE_OF_BOARD + x
			if IS_COMP[k] == 1:
				goto(x, y)
				sp = WANT[k]
				if sp == 3:
					if get_ground_type() != Grounds.Soil:
						till()
					plant(Entities.Carrot)
				elif sp == 2:
					plant(Entities.Tree)
				else:
					plant(Entities.Bush)
			x = x + 1
		y = y + 1
	print("[hay] layout: companion_tiles", ncomp, " grass_tiles", CELLS - ncomp)
	return ncomp


def layout_report():
	# 物种分布 + 预计被满足的草株数 —— **跑之前就能算出该期待多少**
	s1 = 0
	s2 = 0
	s3 = 0
	sat = 0
	ncomp = 0
	i = 0
	while i < CELLS:
		s1 = s1 + TALLY[i * 3 + 1]
		s2 = s2 + TALLY[i * 3 + 2]
		s3 = s3 + TALLY[i * 3 + 3]
		if IS_COMP[i] == 1:
			ncomp = ncomp + 1
			sat = sat + TALLY[i * 3 + WANT[i]]
		i = i + 1
	grass = CELLS - ncomp
	print("[hay] 请求物种分布: bush", s1, " tree", s2, " carrot", s3,
		"(均匀的话三者应接近)")
	print("[hay] **预计被满足的草株数 =", sat, " / 草株总数", grass, "** (满足的永久 x160)")
	# **v3 的正确预测口径**：偏好每收割一次就重抽 ⇒ 只认**随机命中率 = f/3**，
	# 不再用"预排满足数"去预测（那个口径已经实测证伪：预测 39.7 倍、实际 6.8 倍）。
	fcomp = ncomp / CELLS
	match = fcomp / 3
	print("[hay] **随机命中率 = f/3 =", match, "** → 平均每刀 = 512 x (1+159x", match,
		") =", 512 * (1 + 159 * match))
	print("[hay] 速率相对纯草田 = (1-f) x (1+53f) =", (1 - fcomp) * (1 + 53 * fcomp),
		"（纯草田实测 14.1M/分；这条曲线在 f≈0.49 取最大 13.75）")
	print("[hay] 旧口径的 sat =", sat, "已不可信（保留只为对照）")


# ------------------------------------------------------------
# 收割工：只割草格；**目标/报表检查移到每圈一次**
# ------------------------------------------------------------
def worker(row, target, comp):
	# **`comp` 必须当参数传进来**（实测差点踩的坑）：副机是「重新执行一次本文件」的
	# 独立内存，它们的 `IS_COMP` 全是初始值 0 —— 那样它们会把**伴生格也当草格割掉**，
	# 布局当场报废（而且不报错、只是产量上不去，属于最难查的一类）。
	# 跨机只能走 `spawn_drone(…, 参数)`：官方文档保证参数是**复制**语义。
	goto(0, row)
	i = 0
	while i < SIZE_OF_BOARD:
		if comp[row * SIZE_OF_BOARD + i] == 0:
			append(ISG, 1)
		else:
			append(ISG, 0)
		i = i + 1
	# **必须是草行**：条带布局下偶数行才是草，派到奇数行会一刀都收不到（空转）。
	if row % 2 == 1:
		print("[hay] row", row, "是伴生行，不该派工 —— 检查 spawn 的步长")
		return 0
	h0 = num_items(Items.Hay)
	t0 = get_time()
	tprev = t0
	hprev = h0
	laps = 0
	while True:
		i = 0
		while i < SIZE_OF_BOARD:
			if ISG[i] == 1:
				if can_harvest():
					harvest()
					HARV[0] = HARV[0] + 1
			move(East)
			i = i + 1
		laps = laps + 1
		if laps % REPORT_LAPS == 0:
			now = get_time()
			dt = now - tprev
			hnow = num_items(Items.Hay)
			if dt > 0:
				print("[hay] row", row, "laps", laps, "harv", HARV[0],
					"gain_per_s", (hnow - hprev) / dt, "hay", hnow)
			tprev = now
			hprev = hnow
		if laps % GOAL_LAPS == 0:
			if num_items(Items.Hay) >= target:
				break
	print("[hay] row", row, "DONE laps", laps, "harv", HARV[0],
		"gained", num_items(Items.Hay) - h0, "elapsed_s", get_time() - t0)
	return HARV[0]


def main():
	print("=== hay_farm v2 start ===")
	print("world_size", SIZE_OF_BOARD,
		"target", HAY_TARGET,
		"have", num_items(Items.Hay),
		"max_drones", max_drones(),
		"lv_grass", num_unlocked(Unlocks.Grass),
		"lv_poly", num_unlocked(Unlocks.Polyculture),
		"water", num_items(Items.Water),
		"fertilizer", num_items(Items.Fertilizer))
	# ---- 启动边界自检（扁平数组最容易 off-by-one，而静态体检看不见动态下标）----
	if len(IS_COMP) < CELLS or len(WANT) < CELLS or len(TALLY) < CELLS * 3 + 4:
		print("[hay] ERROR: 布局数组太小", len(IS_COMP), len(WANT), len(TALLY))
		return
	print("[hay] bounds ok: IS_COMP", len(IS_COMP), "WANT", len(WANT), "TALLY", len(TALLY))
	if CALIB == 1:
		calib()
	if num_items(Items.Hay) >= HAY_TARGET:
		print("[hay] 已经够了，收工。")
		return
	clear()
	print("[hay] tally pass: 读全盘每一株草的 get_companion() ...")
	tally_pass()
	print("[hay] place pass: 把被点名 >=", MIN_REQ, "的格子改成被点名最多的物种 ...")
	place_pass()
	layout_report()
	cap = max_drones()
	drones = []
	# **一条草行一架**：伴生行占了一半的行，所以只有 SIZE/2 条草行要人。
	# 行号 = i*2（偶数行才是草）。闲置的无人机不耗电，不用勉强派出去。
	n = SIZE_OF_BOARD // 2
	if n > cap:
		n = cap
	i = 1
	while i < n:
		d = spawn_drone(worker, i * 2, HAY_TARGET, IS_COMP)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[hay] launched", len(drones), "helpers + main on", n, "grass rows (偶数行)")
	H0 = num_items(Items.Hay)
	T0 = get_time()
	worker(0, HAY_TARGET, IS_COMP)
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	H1 = num_items(Items.Hay)
	DT = get_time() - T0
	RATE = 0
	if DT > 0:
		RATE = (H1 - H0) / DT
	print("=== hay_farm end ===",
		"hay", H1, "gained", H1 - H0, "elapsed_s", DT,
		"hay_per_s", RATE, "hay_per_min", RATE * 60)


main()
