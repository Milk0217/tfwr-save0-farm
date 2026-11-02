# ============================================================
# wood_hay.py —— 专用高速木材 / 干草生产
#
# 与 main.py 的分工：main.py 跑的是「胡萝卜 → 南瓜 → 仙人掌」产业链，
# 本脚本则把除向日葵之外的全部土地投入木材与干草，用于买基础升级。
#
# 布局（12x12 = 144 格）：
#   左半区 x < 6，全部 12 行 ......... 72 格  木草混合区（默认草 = 干草）
#   右半区 y 0~3（4 行） ............. 24 格  木草混合区（默认棋盘式 Tree/Bush = 木材）
#   右半区 y 4~5（2 行） ............. 12 格  胡萝卜，只为给向日葵供种（1 胡萝卜/株）
#   右半区 y 6~11（6 行） ............ 36 格  向日葵 —— **保留**，维持 Power 的 2 倍速
#
# 木草混合区（96 格）的物种不是固定的，而是由**伴生投票**决定：
#   每次访问一格，读它脚下植物的 get_companion()；请求的坐标若落在混合区内，
#   就给那一格投一票。下一轮访问那一格时按票种下对应物种。
#   没有票就退回默认（左半区草、右半区棋盘式树/灌木）。
#
# 为什么值得这么做：混合种植已升到 10 倍，而它作用的正好是 草/灌木/树/胡萝卜
#   —— 也就是干草和木材本身。10 倍远大于任何产量升级，所以让物种去迁就请求，
#   比固定种植划算得多。
#
# 代价：树木之间有正交相邻时生长时间翻倍（棋盘式本来是为了避开它）。
#   但一次全盘扫描要十几秒，而树 7 秒就能长好，生长从来不是瓶颈，
#   所以为了 10 倍而放弃棋盘式是划算的 —— 只是每格可能不是每次扫描都能收。
#
# 坐标约定：x = 东西（东为 +x），y = 南北（北为 +y）。
# ============================================================

SIZE_OF_BOARD = get_world_size()
HALF = SIZE_OF_BOARD // 2                      # 左右半区分界

SUN_ROWS = 6                                   # 右半区上方 6 行给向日葵
CARROT_ROWS = 2                                # 接下来 2 行给胡萝卜
MIX_ROWS = SIZE_OF_BOARD - SUN_ROWS - CARROT_ROWS   # 12x12 -> 4，右半区剩余给木草
SUN_START = SIZE_OF_BOARD - SUN_ROWS           # 12x12 -> 6，向日葵从这里往北
SUNFLOWER_W = SIZE_OF_BOARD - HALF             # 12x12 -> 6 列
SUNFLOWER_H = SUN_ROWS                         # 12x12 -> 6 行

# --- 状态门控阈值 ---
MIN_SUNFLOWERS = 10                # Petal Gate：场上不足 10 株时只补种、不收割
WATER_THRESHOLD = 0.6             # 含水量低于此数就浇水（1 罐 = 0.25）；0.6 是按 watering_6 的 3.2 罐/秒算出的可持续上限
REPORT_EVERY = 20                  # 每多少轮扫描打印一行状态
COMPANION_STEP = 3                 # 伴生抽样的步长（木草混合区每 N 格抽 1 格）

# 上报用的可变容器（写入列表元素，不需要 global）
SUNFLOWER_STATS = [0, 0]           # [场上株数, 本轮最大花瓣]
MIX_STATS = [0, 0, 0]              # [抽样株数, 已满足株数, 本轮生效的指派格数]

# --- 伴生指派表：每格被指派去种什么，以及是哪一轮投的票 ---
PLAN = []
PLAN_AGE = []
_plan_i = 0
while _plan_i < SIZE_OF_BOARD * SIZE_OF_BOARD:
	append(PLAN, None)
	append(PLAN_AGE, -1)
	_plan_i = _plan_i + 1


# ------------------------------------------------------------
# 区域判定
# ------------------------------------------------------------
def in_hay_zone(x, y):
	# 左半区全部 12 行：默认草
	return x < HALF


def in_wood_zone(x, y):
	# 右半区下方 MIX_ROWS 行：默认棋盘式 Tree/Bush
	return x >= HALF and y < MIX_ROWS


def in_mix_zone(x, y):
	return in_hay_zone(x, y) or in_wood_zone(x, y)


def in_carrot_zone(x, y):
	return x >= HALF and y >= MIX_ROWS and y < MIX_ROWS + CARROT_ROWS


def in_sun_zone(x, y):
	return x >= HALF and y >= SUN_START


def needs_soil(x, y):
	return in_carrot_zone(x, y) or in_sun_zone(x, y)


def sunflower_tile_x(row, col):
	# 蛇形走位：偶数行自西向东、奇数行自东向西。
	# 必须显式算坐标 —— 环形棋盘上从最右列再往东会绕回最左列，连走 move(East)
	# 会让整行错位到左半区去（在 main.py 上真的踩过一次，踩掉 18 格胡萝卜）。
	if row % 2 == 0:
		return HALF + col
	return HALF + SUNFLOWER_W - 1 - col


def has_companion_preference(t):
	return t == Entities.Grass or t == Entities.Bush or t == Entities.Tree or t == Entities.Carrot


# ------------------------------------------------------------
# 伴生指派表读写
# ------------------------------------------------------------
def plan_index(x, y):
	return y * SIZE_OF_BOARD + x


def plan_at(x, y, sweep):
	# 采用「最新一票」，即本轮或上一轮投的都认。
	# 这样无论目标格在扫描顺序里排在投票者的前面还是后面，都能在
	# 「投票者的下一株被收割之前」把物种摆好。
	k = plan_index(x, y)
	if PLAN_AGE[k] >= sweep - 1:
		return PLAN[k]
	return None


def set_plan(x, y, species, sweep):
	k = plan_index(x, y)
	PLAN[k] = species
	PLAN_AGE[k] = sweep


def vote_from(x, y, sweep):
	# 读脚下植物的伴生请求；目标落在木草混合区内才投票（1 tick，不移动）
	t = get_entity_type()
	if t == None:
		return
	if not has_companion_preference(t):
		return
	c = get_companion()
	if c == None:
		return
	ptype, (px, py) = c
	if in_mix_zone(px, py):
		set_plan(px, py, ptype, sweep)


# ------------------------------------------------------------
# 移动辅助
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# 单格作业
# ------------------------------------------------------------
def make_soil_if_needed():
	# till() 是「切换」而不是「设为土壤」，土壤再翻一次会变回草原
	if get_ground_type() != Grounds.Soil:
		till()


def plant_bush_or_tree():
	# 默认模式：棋盘式相间，保证任意两棵 Tree 都不正交相邻
	if (get_pos_x() + get_pos_y()) % 2 == 0:
		plant(Entities.Tree)
	else:
		plant(Entities.Bush)


def water_if_needed():
	if get_ground_type() == Grounds.Soil:
		if get_entity_type() != None and get_water() < WATER_THRESHOLD:
			use_item(Items.Water)


def tend_mix_tile(x, y, sweep):
	# 木草混合区的一格：收割 → 按票种下 → 读新苗请求再投一票。
	# 返回本格是否有生效的指派（供上报统计）。
	#
	# 收割前也投一次票：万一某种植物的伴生偏好是绑在格子上而不是绑在植株上，
	# 这一票就有价值；成本只有 1 tick，不移动。
	if can_harvest():
		vote_from(x, y, sweep)
		harvest()

	want = plan_at(x, y, sweep)
	if want == None:
		# 没有票 → 退回默认
		if in_wood_zone(x, y):
			plant_bush_or_tree()
		else:
			plant(Entities.Grass)
	elif want == Entities.Grass:
		plant(Entities.Grass)
	else:
		plant(want)

	# 种下之后再投一票：这是主路径 —— 新苗的请求比它被收割早整整一轮
	vote_from(x, y, sweep)

	if want == None:
		return 0
	return 1


def tend_carrot_tile():
	# 胡萝卜：这里只为给向日葵供种（每株向日葵要 1 胡萝卜）。
	# 不施肥 —— 施肥会把一半胡萝卜变成奇异物质，而这个脚本要的就是胡萝卜。
	if can_harvest():
		harvest()
	plant(Entities.Carrot)


def tend_sunflowers():
	# 向日葵带的两遍扫描（**保留**：它是无人机 2 倍速的来源）
	#
	# 第一遍求全场最大花瓣 M（未成熟的也算），第二遍只割「成熟且 measure() == M」。
	# 为什么不用硬编码 15：实测花瓣从 7 缓慢生长，300 轮都没到过 15，
	# 硬等 15 会让 Power 永远是 0。
	alive = 0
	max_petals = 0

	for row in range(SUNFLOWER_H):
		y = SUN_START + row
		for col in range(SUNFLOWER_W):
			goto(sunflower_tile_x(row, col), y)
			t = get_entity_type()
			if t == Entities.Sunflower:
				alive = alive + 1
				p = measure()
				if p != None and p > max_petals:
					max_petals = p

	gate_open = max_petals > 0 and alive >= MIN_SUNFLOWERS

	for row in range(SUNFLOWER_H):
		y = SUN_START + row
		for col in range(SUNFLOWER_W):
			goto(sunflower_tile_x(row, col), y)
			t = get_entity_type()
			if t == Entities.Sunflower:
				if gate_open and can_harvest() and measure() == max_petals:
					harvest()
					plant(Entities.Sunflower)
			elif t == None:
				plant(Entities.Sunflower)
			else:
				harvest()
				plant(Entities.Sunflower)
			water_if_needed()

	SUNFLOWER_STATS[0] = alive
	SUNFLOWER_STATS[1] = max_petals


# ------------------------------------------------------------
# 自动升级：用 unlock() 把富余资源换成升级
#
# 注意「auto_unlock」这个解锁只是**授予 unlock() 函数本身**，并不会自动买东西，
# 所以必须自己判断「买得起」再调用。get_cost() 返回 {物品: 数量}，
# 买之前逐个物品比对库存，并为农场的耗材预留一点底。
# ------------------------------------------------------------
def upgrade_reserve(item):
	if item == Items.Wood:
		return 1500
	if item == Items.Hay:
		return 1500
	if item == Items.Carrot:
		return 500
	return 0


def can_afford(cost):
	if cost == None:
		return False
	if len(cost) == 0:
		# 空成本 = 免费或已满级。照样让它去试 unlock()：失败只花 1 tick，成功就白拿一个升级。
		return True
	for item in cost:
		if num_items(item) < cost[item] + upgrade_reserve(item):
			return False
	return True


# 想买的升级，按优先级从高到低。每轮只买一个，买完下一轮重新判断，
# 这样不会把资源一次性抽干（多个升级常常抢同一批木材/干草）。
UPGRADE_TARGETS = [Unlocks.Grass, Unlocks.Trees, Unlocks.Speed, Unlocks.Watering, Unlocks.Sunflowers, Unlocks.Carrots, Unlocks.Fertilizer, Unlocks.Polyculture, Unlocks.Pumpkins]


def try_upgrade():
	# 返回买到的下标，没买返回 -1。用下标打日志，避免 print 不支持枚举对象。
	i = 0
	for target in UPGRADE_TARGETS:
		if can_afford(get_cost(target)):
			if unlock(target):
				print("[upgrade] bought target_index", i)
				return i
		i = i + 1
	return -1


# ------------------------------------------------------------
# 伴生抽样的命中统计
# ------------------------------------------------------------
def companion_survey():
	tested = 0
	hit = 0
	idx = 0
	for row in range(SIZE_OF_BOARD):
		for col in range(SIZE_OF_BOARD):
			x = col
			y = row
			if in_mix_zone(x, y):
				if idx % COMPANION_STEP == 0:
					goto(x, y)
					t = get_entity_type()
					if has_companion_preference(t):
						c = get_companion()
						if c != None:
							ptype, (px, py) = c
							goto(px, py)
							if get_entity_type() == ptype:
								hit = hit + 1
							tested = tested + 1
				idx = idx + 1
	MIX_STATS[0] = tested
	MIX_STATS[1] = hit


# ------------------------------------------------------------
# 初始化
# ------------------------------------------------------------
def init_board():
	clear()
	for row in range(SIZE_OF_BOARD):
		y = get_pos_y()
		for col in range(SIZE_OF_BOARD):
			x = get_pos_x()
			if needs_soil(x, y):
				make_soil_if_needed()
			if in_sun_zone(x, y):
				plant(Entities.Sunflower)
			elif in_carrot_zone(x, y):
				plant(Entities.Carrot)
			# 木草混合区保持草原：草会自长，树/灌木也能在草原上长
			move(East)
		move(North)


# ------------------------------------------------------------
# 状态上报
# ------------------------------------------------------------
def report(sweep, sec_per_sweep, ticks_per_sweep):
	print("[stat] sweep", sweep,
		"sec/sweep", sec_per_sweep,
		"ticks/sweep", ticks_per_sweep,
		"sunflowers", SUNFLOWER_STATS[0],
		"max_petal", SUNFLOWER_STATS[1],
		"power", num_items(Items.Power),
		"poly_lv", num_unlocked(Unlocks.Polyculture),
		"mix_hit", MIX_STATS[1], "/", MIX_STATS[0],
		"mix_plan", MIX_STATS[2],
		"hay", num_items(Items.Hay),
		"wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot))


# ------------------------------------------------------------
# 主扫描：逐行扫过全盘，处理木草混合区与胡萝卜带
# （向日葵带由 tend_sunflowers() 单独负责）
# ------------------------------------------------------------
def game_loop(sweep):
	plan_count = 0
	for row in range(SIZE_OF_BOARD):
		y = get_pos_y()
		for col in range(SIZE_OF_BOARD):
			x = get_pos_x()

			if in_mix_zone(x, y):
				plan_count = plan_count + tend_mix_tile(x, y, sweep)
			elif in_carrot_zone(x, y):
				tend_carrot_tile()
			# SUNFLOWER 带不在这里处理
			move(East)
		move(North)
	MIX_STATS[2] = plan_count


def main():
	init_board()
	sweep = 0
	mark_time = get_time()
	mark_ticks = get_tick_count()
	while True:
		tend_sunflowers()
		sweep = sweep + 1
		game_loop(sweep)
		if sweep % REPORT_EVERY == 0:
			now_time = get_time()
			now_ticks = get_tick_count()
			sec_avg = (now_time - mark_time) / REPORT_EVERY
			ticks_avg = (now_ticks - mark_ticks) / REPORT_EVERY
			# 抽样与升级都放在计时区间之外，免得污染 sec/sweep
			companion_survey()
			report(sweep, sec_avg, ticks_avg)
			try_upgrade()
			mark_time = get_time()
			mark_ticks = get_tick_count()


main()
