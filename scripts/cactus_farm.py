# ============================================================
# cactus_farm.py —— **高速刷仙人掌**（独立脚本：整盘铺仙人掌方阵，一块一架）
#
# 为什么要单独写：main.py 里的 `cactus_push` 是「开局补课」用的 —— 它借用南瓜方阵
# （只有 14 个 6x6），而且**每轮都多跑一遍冗余的清地遍**（上一轮的连锁收割已经把整片收空了，
# 那一遍只是当初为了清掉南瓜而留的）。
# 当前目标：**15,600,000 个** = 买 `Unlocks.Mazes` lv6（金币/宝藏 16,384 -> 32,768，
# 等于把 maze_gold 的金币产量直接翻倍）。
#
# ---------- 实测口径（标定自 BUILD 41/42 的实跑，别推翻它）----------
#   一块 n 格的连通区排好序收割一次 = **4n²** 个（实测 6x6 = 36 格 -> 5,184；文档的 n² 是它的 1/4）
#   一轮 = 播种 + 生长 + **排序** + 收割，排序约占 2/3：
#     排序步数 ≈ 逆序数 ≈ 0.075 n²（实测 6x6 = **97 次**），每次 = swap(200) + move(200) = **400 tick**
#     => 6x6 排序 ≈ 38,800 tick ≈ 6.5 秒（2 倍速约 6,075 tick/秒）
#   其它动作（move/plant/harvest）实测约 **94 tick/个**
#   ⇒ main.py 现在是 14 块 x 5,184 / 约 12 秒 ≈ **6,000 个/秒**
#
# ---------- 本脚本的三处提速 ----------
#   1. **整盘铺满**：按 (REG_SIZE+1) 的间距平铺，一块一架（region 之间必须留 1 格间隔，
#      否则两块相邻会被 swap 互踩）。REG_SIZE=5 -> 25 块；REG_SIZE=6 -> 16 块。
#   2. **省掉冗余的清地遍**：首次 `till` 之后每轮只播种 —— 连锁收割已经收空了整片。
#   3. **播种时浇水**（带存量下限保护，见 WATER_FLOOR）：含水量越高生长越快（最多 5 倍）。
#
# ---------- 实测核对（2026-09-12 第一次实跑，**口径已确认**）----------
#   跑了一小段时间后：cactus 153,542 -> 1,153,542，正好 **+1,000,000**
#   = 16 轮 x 25 块 x **2,500**，而 2,500 = 4 x 25² ⇒ **「4n²」对 n=25 也成立** ✓
#   （原先只在 6x6 上验过，所以 REG_SIZE=5 是带风险的推断；现在不用再怀疑了。）
#   模型吞吐：REG_SIZE=5（25 块）≈ **14,000 个/秒** -> 15.6M 约 19 分钟；
#            REG_SIZE=6（16 块）≈ 10,000 个/秒（现在的 main.py cactus_push 只有 ~6,000/秒）。

# ---------- 闲置无人机去收空隙格上的向日葵（SUN_ON_SPARE）----------
#   25 块方阵只用掉 25 架，cap=32 ⇒ **有 6~7 架闲置**。为什么不让它们也去开方阵：
#   算过了 —— REG_SIZE=4（16 格）能塞 31 块，但模型吞吐只比现在高约 1%
#   （14,600 vs 14,500 个/秒），**换来的是 +140 电/秒，明显更划算**。
#   空隙格共 **419 格**（块间的竖缝/横缝 295 + 余条 124），种向日葵**不会破坏方阵隔离**：
#   仙人掌连锁只往「相邻的仙人掌」扩散，而 push_value 的 L 形路径永远在 [0,REG_SIZE) 内，
#   绝不会 swap 到缝里去。副机不浇水（水要留给仙人掌）。
#   看 [sun2] 那行核对；仙人掌刷够时它们用同一个共享物品栏信号自动收工。
#
# ---------- 用法 ----------
#   在游戏里直接运行本文件。它会 `clear()` 整盘（所以别和 main.py 同时跑）。
#   刷够 `CACTUS_TARGET` 就自动收工；之后用 main.py 的 `try_upgrade()` 或手动买 Mazes lv6。
#   想看阶段耗时（到底是生长贵还是排序贵），看 [cact] phase 那行。
# ============================================================

SIZE_OF_BOARD = get_world_size()

REG_SIZE = 5                       # 每块方阵的边长（改这里就能切 5/6 两种配置）
PITCH = REG_SIZE + 1               # 块间距：**必须 >= REG_SIZE+1**，否则两块相邻会被 swap 互踩
GRID = SIZE_OF_BOARD // PITCH      # 每维几块
if GRID < 1:
	GRID = 1
NREG = GRID * GRID

REG_OX = []
REG_OY = []
_i = 0
while _i < NREG:
	append(REG_OX, (_i % GRID) * PITCH)
	append(REG_OY, (_i // GRID) * PITCH)
	_i = _i + 1
REG_LIMIT = GRID * PITCH           # 方阵区之外的余条（32 - 30 = 2 行/列）也算空隙

TILES = REG_SIZE * REG_SIZE
CACTUS_TARGET = 15600000           # = Mazes lv6 的成本（早买完了）。
# 2026-10-05 更正：**别用这支脚本刷高顶礼帽**！它把小方块并行，n 被锁在 25，
# 实测只有 0.84M/分；整片方案 cactus_big.py 实测 34.84M/分（41 倍）。
MAX_ROUNDS = 0                     # 0 = 一直刷到够为止
REPORT_EVERY = 5                   # 每几轮打印一行 [cact]
WATER_THRESHOLD = 0.9              # 含水量低于此数就浇水（1 罐 = 0.25，所以 >=0.75 就补满）
WATER_FLOOR = 20000                # **水量下限**：库存低于此数就停止浇水。
								   # 水是**产水速率受限**的资源（watering 满级也只有几十罐/秒），
								   # 铺满整盘的浇水量远大于产水速率 ⇒ 必须设下限，否则会把水抽干
								   # 然后被动地退回"不浇水"的更慢状态。
VERIFY_EVERY = 10                  # 每几轮做一次**真实的**重读自检（平时只查内存快照）
WAIT_SEC = 90                      # 等成熟的单次上限
SUN_ON_SPARE = 1                   # 1 = 把闲置无人机派去收**空隙格**上的向日葵换电量
SUN_REPORT_SEC = 60                # 向日葵副机每多少秒打印一行

# ---- 每架无人机自己的状态（模块全局 = 每架一份，import/执行的语义保证）----
MY = [0]                           # 我负责第几块
SOIL_DONE = [0]                    # 本方阵是否已经翻成土壤（只做一次）
GRID_V = []                        # 尺寸快照（行主序）
SORTED = []
_i = 0
while _i < TILES:
	append(GRID_V, 0)
	append(SORTED, 0)
	_i = _i + 1
SWAPS = [0]                        # 本轮交换次数
PHASE = [0.0, 0.0, 0.0, 0.0]       # 累计秒数：[播种, 等成熟, 排序, 收割]
# ---- 把"播种"那 4.57 秒再拆开（它内部是 plant_region + fix_missing 两遍）----
# 动机：实测 plant 阶段 = 4.57 秒 = 约 139 个动作，而"25 格 x (move+plant)"只要 50 个
# ⇒ 必须知道这 139 个落在哪一遍里，才能判断是"两遍扫描合理但某遍多走路"还是别的。
# **我上一轮猜"两遍冗余、可以合并"是错的**：fix_missing 跑在 wait_mature 之后，
# 专门抓"种了没长成"的，它不可省。所以这里只量、不猜。
SUBP = [0, 0]                      # [plant_region 的 tick, fix_missing 的 tick]
FIXN = [0, 0]                      # [fix_missing 补种次数, plant_region 播种次数]


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


def rx(c):
	return REG_OX[MY[0]] + c


def ry(r):
	return REG_OY[MY[0]] + r


def water_here():
	# 只给"已经种了东西的土壤"浇水，并且**只在存量高于下限时**浇（见 WATER_FLOOR 的说明）
	if num_items(Items.Water) < WATER_FLOOR:
		return
	if get_ground_type() == Grounds.Soil:
		if get_entity_type() != None:
			if get_water() < WATER_THRESHOLD:
				use_item(Items.Water)


def till_region():
	# 只在第一轮做：把本方阵翻成土壤（till 是"切换"，所以必须先判地面类型）
	for row in range(REG_SIZE):
		for col in range(REG_SIZE):
			c = col
			if row % 2 == 1:
				c = REG_SIZE - 1 - col
			goto(rx(c), ry(row))
			if get_ground_type() != Grounds.Soil:
				till()


def plant_region():
	# 蛇形播种：行与行之间只花 1 次移动
	k0 = get_tick_count()              # 打点（get_tick_count 免费，不吃 tick）
	for row in range(REG_SIZE):
		for col in range(REG_SIZE):
			c = col
			if row % 2 == 1:
				c = REG_SIZE - 1 - col
			goto(rx(c), ry(row))
			if get_entity_type() == None:
				plant(Entities.Cactus)
				FIXN[1] = FIXN[1] + 1
			water_here()
	SUBP[0] = SUBP[0] + get_tick_count() - k0


def fix_missing():
	# 盯一格等到成熟之后，再全阵核对一次并补种没熟的
	k0 = get_tick_count()              # 打点（免费）
	missing = 0
	for row in range(REG_SIZE):
		for col in range(REG_SIZE):
			c = col
			if row % 2 == 1:
				c = REG_SIZE - 1 - col
			goto(rx(c), ry(row))
			if get_entity_type() == None:
				plant(Entities.Cactus)
				missing = missing + 1
				FIXN[0] = FIXN[0] + 1
			elif not can_harvest():
				missing = missing + 1
	SUBP[1] = SUBP[1] + get_tick_count() - k0
	return missing


def wait_mature(max_sec):
	# 只盯一格轮询到成熟（get_time 是 0 tick 的），比反复全阵扫描便宜得多
	goto(rx(0), ry(0))
	start = get_time()
	while get_time() - start < max_sec:
		if can_harvest():
			return 1
		pass
	return 0


def read_grid():
	# 蛇形读一遍，把 TILES 格尺寸读进内存。返回读不到尺寸的格数（>0 说明有空位/未熟）
	empty = 0
	for row in range(REG_SIZE):
		for col in range(REG_SIZE):
			c = col
			if row % 2 == 1:
				c = REG_SIZE - 1 - col
			goto(rx(c), ry(row))
			v = measure()
			if v == None:
				empty = empty + 1
				v = 0
			GRID_V[row * REG_SIZE + c] = v
	return empty


def mem_swap(a, b):
	t = GRID_V[a]
	GRID_V[a] = GRID_V[b]
	GRID_V[b] = t


# `push_value` 已删除：它是旧"目标驱动"排序的执行器，第一步 `goto` 回源格
# 造成每轮 135 次白走（4.4 秒）。现在由 bubble_row/bubble_col 的
# "先行后列"两阶段排序完成，且不需要它（也不需要预先算目标顺序）。
# 保留这段注释是为了记住：**别再用跨行的路径驱动排序**（我试过，全废）。


def push_value(src, dst):
	# 用相邻交换把 src 处的值推到 dst：先沿行对齐列、再沿列对齐行。
	# 这条 L 形路径是安全的：途中经过的格子行主序下标都 >= dst，不会碰到已归位的前半段。
	# **swap() 只交换、不移动无人机** —— 必须 swap 之后紧跟同方向的 move，
	# 否则无人机会停在原地把同一对来回换（实测过：交换 94 次、违规数仍是 27 = 什么都没做）。
	# **不要再试图替换它**：三种实现的实测对比见 sort_region 里的注释（push_value 最省）。
	sx = src % REG_SIZE
	sy = src // REG_SIZE
	dx = dst % REG_SIZE
	dy = dst // REG_SIZE
	goto(rx(sx), ry(sy))
	while sx != dx:
		if sx < dx:
			swap(East)
			move(East)
			mem_swap(sy * REG_SIZE + sx, sy * REG_SIZE + sx + 1)
			sx = sx + 1
		else:
			swap(West)
			move(West)
			mem_swap(sy * REG_SIZE + sx, sy * REG_SIZE + sx - 1)
			sx = sx - 1
		SWAPS[0] = SWAPS[0] + 1
	while sy != dy:
		if sy < dy:
			swap(North)
			move(North)
			mem_swap(sy * REG_SIZE + sx, (sy + 1) * REG_SIZE + sx)
			sy = sy + 1
		else:
			swap(South)
			move(South)
			mem_swap(sy * REG_SIZE + sx, (sy - 1) * REG_SIZE + sx)
			sy = sy - 1
		SWAPS[0] = SWAPS[0] + 1


def sort_region():
	# 读一遍 -> 纯内存插入排序算出升序目标 -> 只执行必要的相邻交换（把"看"和"动"分开）
	if read_grid() > 0:
		return 0
	k = 0
	while k < TILES:
		SORTED[k] = GRID_V[k]
		k = k + 1
	i = 1
	while i < TILES:
		v = SORTED[i]
		j = i - 1
		done = 0
		while j >= 0 and done == 0:
			if SORTED[j] > v:
				SORTED[j + 1] = SORTED[j]
				j = j - 1
			else:
				done = 1
		SORTED[j + 1] = v
		i = i + 1
	# ---- 执行：**目标驱动** —— 对每个目标位，找最近的持有者，用 push_value 推过去 ----
	# **这里是回退**：我一度把它换成"路径驱动的单趟 gnome"，实测**失败**：
	#   swaps 46 -> 101、sort 7.49 -> 21.39 秒、单块产量 10,000 -> **32**（几乎全废）。
	# 原因见 docs/game/unlocks/cactus.md 的 Hint 1：
	#   "If the rows are already sorted, sorting the columns will not unsort the rows."
	#   ⇒ 正确姿势是**先行后列**的两阶段排序；而"沿行主序 gnome"在**行末横穿**时
	#     会反复穿过整行、把已排好的行内顺序打乱 ⇒ 既多换又收敛不了。
	# `push_value` 之所以对，是因为它**把每个值直接送到确切的目标下标**，
	#   路径怎么走都不影响最终排列（L 形路径保证不碰已归位的前半段）。
	# ---- 执行：**目标驱动** —— 对每个目标位找最近的持有者，用 push_value 推过去 ----
	# 试过的两种替代方案（都实测过，都更差或直接坏掉）：
	#  * 跨行主序的单趟 gnome：swaps 46->101、sort 7.49->21.39 秒、产量 10,000->**32**（没收敛）
	#  * 文档 Hint 1 的"先行后列"两阶段冒泡（bubble_row/bubble_col）：
	#    **正确**（bad 0、per_round 10,000 ✓）但 sort **7.49 -> 11.63~12.67 秒** ✗
	#    原因：两次交换次数几乎一样（46~51 vs 38~61），但走位从 181 个动作涨到 373 个
	#    —— 逐列阶段等于把整块再走一遍。
	# ⇒ **push_value 的"把每个值沿 L 形路径直接送到确切目标下标"是三者里最省的**：
	#    它的交换次数 = 各值的曼哈顿推送距离之和（实测 46~51），远低于冒泡的逆序数。
	#    （我一度以为"46 = 逆序数下界" ⇒ 这是错的，gnome 对同一块田做了 101 次交换就是反证。）
	for idx in range(TILES):
		want = SORTED[idx]
		if GRID_V[idx] != want:
			best = -1
			best_d = 999
			scan = idx + 1
			while scan < TILES:
				if GRID_V[scan] == want:
					d = abs(scan // REG_SIZE - idx // REG_SIZE) + abs(scan % REG_SIZE - idx % REG_SIZE)
					if d < best_d:
						best_d = d
						best = scan
				scan = scan + 1
			if best >= 0:
				push_value(best, idx)
	return 1


def violations_mem():
	# 用**内存快照**数违规（0 次移动，免费）。push_value 一直同步维护 GRID_V，
	# 所以排完序它就该是 0。真实的"重读一遍再数"每 VERIFY_EVERY 轮做一次（防模型漂移）。
	bad = 0
	for y in range(REG_SIZE):
		for x in range(REG_SIZE):
			me = GRID_V[y * REG_SIZE + x]
			if x + 1 < REG_SIZE:
				if GRID_V[y * REG_SIZE + x + 1] < me:
					bad = bad + 1
			if y + 1 < REG_SIZE:
				if GRID_V[(y + 1) * REG_SIZE + x] < me:
					bad = bad + 1
	return bad


def violations_real():
	read_grid()
	return violations_mem()


def is_gap(x, y):
	# 空隙格 = 不属于任何仙人掌方阵的格子：块之间的竖缝/横缝（% PITCH == REG_SIZE），
	# 或者方阵区之外的余条（x/y >= REG_LIMIT）。32x32、REG_SIZE=5 时共 **419 格**。
	# **在这些格子上种向日葵不会破坏方阵隔离**：仙人掌的连锁收割只往「相邻的仙人掌」
	# 扩散（文档用的词就是相邻的 cacti），而 push_value 的 L 形路径永远在
	# [0, REG_SIZE) 之内，绝不会 swap 到缝里去。
	if x % PITCH == REG_SIZE:
		return 1
	if y % PITCH == REG_SIZE:
		return 1
	if x >= REG_LIMIT:
		return 1
	if y >= REG_LIMIT:
		return 1
	return 0


def sun_worker(y0, y1, target):
	# 闲置无人机的副业：在自己负责的**行带**里只对空隙格动手，收向日葵换电量。
	# 为什么不直接把空闲无人机也派去开仙人掌方阵：算过了，REG_SIZE=4（16 格）能塞 31 块，
	# 但模型吞吐只比现在的 25 块 x 25 格高约 1%（14,600 vs 14,500 个/秒）——
	# **把 6 架换成 +140 电/秒要划算得多**。
	# 不浇水：水是产水速率受限的资源，要留给仙人掌（那边浇水直接缩短每轮周期）。
	goto(0, y0)
	laps = 0
	tiles = 0
	harv = 0
	t0 = get_time()
	while True:
		x = get_pos_x()
		y = get_pos_y()
		if is_gap(x, y) == 1:
			if laps == 0:
				if get_ground_type() != Grounds.Soil:
					till()
			t = get_entity_type()
			if t == None:
				plant(Entities.Sunflower)
			elif can_harvest():
				harvest()
				plant(Entities.Sunflower)
				harv = harv + 1
		move(East)
		tiles = tiles + 1
		if tiles >= SIZE_OF_BOARD:
			tiles = 0
			move(North)
			y2 = get_pos_y()
			if y2 < y0 or y2 >= y1:
				# 行带走完一圈（棋盘是环形的，North 会从 31 绕回 0）
				goto(0, y0)
				laps = laps + 1
				# **必须能退出**：主机最后要 wait_for 所有无人机，而这个循环本身没有终点。
				# 用「仙人掌刷够了」当共同收工信号 —— Items.Cactus 是共享物品栏，跨机可见，
				# 所以这正是那个天然的全局完成条件（和 cactus worker 用的是同一个）。
				if num_items(Items.Cactus) >= target:
					print("[sun2] rows", y0, y1, "done: cactus target reached, harv", harv)
					break
		if get_time() - t0 > SUN_REPORT_SEC:
			t0 = get_time()
			print("[sun2] rows", y0, y1, "laps", laps, "harv", harv,
				"power", num_items(Items.Power), "cactus", num_items(Items.Cactus))
	return harv


def worker(idx, target, limit):
	# limit > 0 = **标定模式**：只跑 limit 轮就退出。
	# 标定必须**单独一架、不带任何别的无人机**跑，量到的库存增量才是干净的（见 main 的注释）。
	MY[0] = idx
	rounds = 0
	gained = 0
	while True:
		rounds = rounds + 1
		if MAX_ROUNDS > 0:
			if rounds > MAX_ROUNDS:
				break
		if limit > 0:
			if rounds > limit:
				break
		before = num_items(Items.Cactus)
		t0 = get_time()
		if SOIL_DONE[0] == 0:
			till_region()
			SOIL_DONE[0] = 1
		plant_region()
		t1 = get_time()
		if wait_mature(WAIT_SEC) == 0:
			print("[cact] region", idx, "wait timeout")
			return rounds
		t2 = get_time()
		# 排序。**不预先跑一遍全阵 fix_missing**：read_grid 本来就要走一遍全阵、
		# 并且会数出「读不到的格子数」，所以只在真的读不到时才补种+重试。
		# 白跑那一遍全阵要 25 次移动 ≈ 一轮的 9%，而生长是均匀的，绝大多数轮次没有空格。
		SWAPS[0] = 0
		ok = sort_region()
		tries = 0
		while ok == 0 and tries < 3:
			tries = tries + 1
			fix_missing()
			if wait_mature(WAIT_SEC) == 0:
				break
			ok = sort_region()
		t3 = get_time()
		bad = 0
		if ok == 0:
			# **排不好就不收割**：未排序时连锁不会扩散，收一刀只有 1 个（而不是 4n²）。
			# 宁可白等一轮，也不要拿一个「1」去污染产量统计。
			print("[cact] region", idx, "unreadable after", tries, "retries -> skip harvest")
		else:
			bad = violations_mem()
			goto(rx(0), ry(0))
			harvest()
		t4 = get_time()
		PHASE[0] = PHASE[0] + (t1 - t0)
		PHASE[1] = PHASE[1] + (t2 - t1)
		PHASE[2] = PHASE[2] + (t3 - t2)
		PHASE[3] = PHASE[3] + (t4 - t3)
		gained = gained + (num_items(Items.Cactus) - before)
		if rounds % VERIFY_EVERY == 0:
			real = violations_real()
			if real > 0:
				print("[cact] region", idx, "**REAL violations", real, "** (mem said", bad, ")")
		if rounds % REPORT_EVERY == 0 or limit == 1:
			cyc = t4 - t0
			rate = 0
			if cyc > 0:
				rate = (num_items(Items.Cactus) - before) / cyc
			print("[cact] region", idx, "round", rounds,
				"yield_raw(污染: 约 = 并行块数 x 真值)", num_items(Items.Cactus) - before,
				"cyc_s", cyc,
				"rate_raw", rate,
				"swaps", SWAPS[0],
				"bad", bad,
				"phase plant/grow/sort/harv", PHASE[0] / rounds, PHASE[1] / rounds, PHASE[2] / rounds, PHASE[3] / rounds,
				"| 播种两遍: plant_region", SUBP[0] / 6075 / rounds,
				"fix_missing", SUBP[1] / 6075 / rounds,
				"秒(动作数", SUBP[0] / 200 / rounds, SUBP[1] / 200 / rounds, ")",
				"补种", FIXN[0] / rounds, "播种", FIXN[1] / rounds,
				"total", num_items(Items.Cactus))
		if num_items(Items.Cactus) >= target:
			break
	print("[cact] region", idx, "DONE rounds", rounds, "gained", gained, "per_round", gained / rounds)
	return rounds


def main():
	print("=== cactus_farm start ===")
	print("world_size", SIZE_OF_BOARD,
		"reg_size", REG_SIZE,
		"pitch", PITCH,
		"grid", GRID,
		"regions", NREG,
		"tiles_per_region", TILES,
		"target", CACTUS_TARGET,
		"have", num_items(Items.Cactus),
		"max_drones", max_drones(),
		"water", num_items(Items.Water))
	if REG_OX[NREG - 1] + REG_SIZE > SIZE_OF_BOARD:
		print("[cact] ERROR: 布局越界，检查 REG_SIZE / GRID")
		return
	print("[cact] region pitch", PITCH, "-> gaps are 1 tile (必留，否则两块相邻会 swap 互踩)")
	clear()
	drones = []
	cap = max_drones()
	# ---- 开局自标定（**必须先做**）----
	# `num_items(Items.Cactus)` 是**全局库存**，而每个副机的 `yield` 取的是它的差值。
	# 25 架同时收割时，每个副机都会把别机的收获算进自己那一轮 ⇒ **每轮 yield 是脏的**
	# （倍数约等于同时收割的机数）。这正是当初 `[pump] pyield` 读出 55,296 = 4 x 13,824
	# 的同一个坑；而「6x6 = 5,184」也是 4 架并行期间量的 ⇒ **那个 4 倍很可能就是污染**。
	# 所以：先只派 **1 架、只跑 1 轮**，那一行 `[cact] CALIB` 里的 per_round 才是真产量口径。
	print("[cact] CALIB start: 单独一架跑一轮，用来量干净的 per_region yield")
	d = spawn_drone(worker, 0, 999999999, 1)
	if d != None:
		wait_for(d)
	print("[cact] CALIB end: 上面的 per_round 就是**一块", REG_SIZE, "x", REG_SIZE,
		"方阵一次连锁收割的真实产量**；乘", NREG, "块才是每轮总产出")
	i = 0
	while i < NREG and i < cap - 1:
		d = spawn_drone(worker, i, CACTUS_TARGET, 0)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[cact] launched", len(drones), "cactus workers on", NREG, "regions")
	# **闲置的无人机去收空隙格上的向日葵换电量**（见 is_gap / sun_worker 的注释）。
	nsun = cap - 1 - len(drones)
	if SUN_ON_SPARE == 0:
		nsun = 0
	if nsun < 0:
		nsun = 0
	if nsun > 0:
		s = 0
		while s < nsun:
			y0 = (SIZE_OF_BOARD * s) // nsun
			y1 = (SIZE_OF_BOARD * (s + 1)) // nsun
			d = spawn_drone(sun_worker, y0, y1, CACTUS_TARGET)
			if d != None:
				append(drones, d)
			s = s + 1
		print("[cact] +", nsun, "sunflower workers on the gap tiles")
	C0 = num_items(Items.Cactus)
	T0 = get_time()
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	# **这是唯一干净的速率读数**：全程库存增量 / 全程墙钟（每颗仙人掌只被算一次）
	C1 = num_items(Items.Cactus)
	DT = get_time() - T0
	RATE = 0
	if DT > 0:
		RATE = (C1 - C0) / DT
	print("=== cactus_farm end === cactus", C1,
		"gained", C1 - C0,
		"elapsed_s", DT,
		"cactus_per_s", RATE,
		"cactus_per_min", RATE * 60)


main()
