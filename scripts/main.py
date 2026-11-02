# ============================================================
# The Farmer Was Replaced - Save0 主脚本（单无人机自动化农场）
#
# 棋盘上下左右环形相连。各带边界全部由 SIZE_OF_BOARD 推出，16x16 时切成五条功能带（共 256 格）：
#   WOOD       24 格  左半区下方 SIZE/5 行（16x16 时 3 行 x 8 列）
#                     Bush/Tree 相间，产 Wood（种植免费）；兼作伴生缓冲带
#   HAY        40 格  左半区接下来 SIZE/3 行（16x16 时 5 行），草原，草自生长，只收不种；兼作伴生缓冲带
#   CARROT     64 格  左半区剩下的 8 行，土壤；种 1 株耗 8 干草 + 8 木材
#   PUMPKIN    36 格  右半区左下 6x6 方阵（6 是实测最优，不要撑大），土壤；种 1 株耗 8 胡萝卜
#   SUNFLOWER  92 格  右半区去掉南瓜方阵后的全部格子（L 形），土壤；产 Power（2 倍速）
#
# 混合种植：胡萝卜的伴生请求会变成对 WOOD/HAY 缓冲带的「指派」（详见 game_loop）。
# 仙人掌：一次性补课，临时征用 PUMPKIN 带（详见 cactus_push）。
#
# 坐标约定：x = 东西（东为 +x），y = 南北（北为 +y）。
# 术语与决策见 CONTEXT.md 与 docs/adr/。
# ============================================================

import layout                      # **布局的唯一事实来源**（几何常数全在 layout.py）
import w_pumpkin                   # 南瓜工人（14 方阵的状态机已整块搬过去，自包含）

LAYOUT_VERSION = layout.LAYOUT_VERSION
SIZE_OF_BOARD = layout.SIZE_OF_BOARD
HALF = layout.HALF
PUMPKIN_SIZE = layout.PUMPKIN_SIZE
PUMPKIN_TILE_COUNT = layout.PUMPKIN_TILE_COUNT
PUMPKIN_SQUARES = layout.PUMPKIN_SQUARES
PUMPKIN_OX = layout.PUMPKIN_OX
PUMPKIN_OY = layout.PUMPKIN_OY
SUN_ROWS = layout.SUN_ROWS
CARROT_END = layout.CARROT_END
WOOD_ROWS = layout.WOOD_ROWS
HAY_ROWS = layout.HAY_ROWS
# 开机自检方阵间距（BUILD 26 的教训：两块紧挨就会连成矩形、产量口径被改变）
if layout.check_squares() > 0:
	print("[main] ERROR: pumpkin squares overlap - fix layout.py")


# --- 状态门控阈值：所有「要不要动手」的判断都来自实测状态 ---
MIN_SUNFLOWERS = 10                # Petal Gate：场上不足 10 株时只补种、不收割
FERTILIZER_RESERVE = 100           # 肥料存量低于此数就不再施肥
CARROT_RESERVE = 999999              # 胡萝卜低于此数不再施肥：现在要攒 25.6 万胡萝卜升南瓜，而奇异物质已够用
WATER_THRESHOLD = 0.7             # 含水量低于此数就浇水。1 罐 = 0.25，所以 0.75 是理论上限；
								# 但阈值越高越耗水：按 watering_6 的 3.2 罐/秒算，0.6 是保守值；实测 water 库存在 0.6 下持续上涨（4413 -> 11350），有余量，抬到 0.7 换更快的生长
CACTUS_PUMPKIN_RESERVE = 300       # 南瓜低于此数就不启动仙人掌补课（1 株仙人掌 = 2 南瓜）
CACTUS_MAX_CYCLES = 16             # 补课最多跑几轮（**实测一轮满序 6x6 = 5,184 个**，不是文档的 1296）
CACTUS_PUSH_ENABLED = 1            # 1 = 开局先跑仙人掌补课（进度存在物品栏，可跨重启续跑）
# ---- 补课目标与预算（probe7 实测，2026-09-12，**别再靠猜**）----
# 全场只有两个解锁吃仙人掌，价格差 6 倍：
#   Dinosaurs lv4→5 = 2,590,000        Mazes lv5→6 = 15,600,000
# 其它还买得动的下一级：Cactus lv6 = 25,900,000 南瓜、Trees 10 = 19,700,000 干草、
#   Carrots 10 = 97,700,000 木材、Pumpkins 10 = 65,500,000 胡萝卜、
#   Polyculture lv5 = 1,250,000 骨头、Leaderboard = 2,000,000 骨头 + 1,000,000 金币。
# **金币线早已过剩**：32×32 一次满场迷宫 = 16,384 金币，Leaderboard 的 100 万金币只要
#   61 次迷宫 = 31,232 个奇异物质（库存 3,152 万）⇒ **追 Mazes lv6 没有任何回报**。
# 所以这个上限的含义是「值不值得为它堵住启动」，规则是**在预算内挑最便宜的那一档**。
CACTUS_TARGET_CAP = 3000000        # 只补 259 万这一档（恐龙 lv5）；Mazes 的 1560 万直接放弃
REPORT_EVERY = 5                   # 每多少轮扫描打印一行状态（20 → 5：主机的轮次很长，
									# 20 轮要十几分钟才出一行 [stat]，看不出胡萝卜是在涨还是在被南瓜吃掉）
SUN_REPORT_EVERY = 2               # 向日葵副机每隔几轮打印一行（它的轮次比主机慢得多）
SUN_MEASURE_EVERY = 4              # 每隔几轮才跑一次「量测遍」（只为诊断；轮转策略本身不需要它）
COMPANION_STEP = 3                 # 伴生抽样步长：左半区每 N 格抽 1 格

# 上报用的可变容器（写入列表元素，不需要 global）
# 注意：跨机**没有共享内存**，副机算出来的量必须由副机自己 print —— 主机那份永远是
# 模块初始值（BUILD 13 的「sunflowers 0」假数据就是这么来的）。所以原来那几个
# 「只写不读」的统计列表（SUNFLOWER_STATS / SUN_WORK_STATS）已经删掉，不再留陷阱。
COMPANION_STATS = [0, 0, 0]        # [抽样株数, 其中已满足的株数, 本轮生效的指派格数]
# 每格「未成熟时量到的花瓣」：同一株在「未熟」与「现在」两次量到相同值 => 花瓣在种植时定死（模型 b）
SUN_PROBE = []
# 每格「成熟株的花瓣」，-1 = 本格不是成熟向日葵；用来数「成熟且等于全场最大」的株数
SUN_MAT = []
_si = 0
while _si < SIZE_OF_BOARD * SIZE_OF_BOARD:
	append(SUN_PROBE, -1)
	append(SUN_MAT, -1)
	_si = _si + 1
# Petal Gate 兜底：连续多少轮「没有任何成熟株处在全场最大花瓣」就改用「成熟株里的最大值」
SUN_STUCK = [0]
SUN_STUCK_MAX = 5
# 花瓣分布直方图：下标 0~8 对应 7~15 瓣。用来判断「高花瓣到底有多稀有」
HIST = [0, 0, 0, 0, 0, 0, 0, 0, 0]

# --- 伴生指派表：每格被指派去种什么物种，以及是哪一轮投的票 ---
# 用两个等长列表而不是字典，避免依赖字典的 in / get 等成员方法。
PLAN = []
PLAN_AGE = []
_plan_i = 0
while _plan_i < SIZE_OF_BOARD * SIZE_OF_BOARD:
	append(PLAN, None)
	append(PLAN_AGE, -1)
	_plan_i = _plan_i + 1


# ------------------------------------------------------------
# 区域判定：所有地方共用这一组函数，是坐标的唯一事实来源
# ------------------------------------------------------------
def in_wood_zone(x, y):
	return x < HALF and y < WOOD_ROWS


def in_hay_zone(x, y):
	return x < HALF and y >= WOOD_ROWS and y < WOOD_ROWS + HAY_ROWS


def in_carrot_zone(x, y):
	# 胡萝卜带压缩到 5 行（y 11-15，55 格）：实测每格成熟约 6 秒，而两台无人机每轮要 12 秒才回访一次
	# ⇒ 原来 121 格里有一半时间在「成熟但没人收」地闲置；砍到 55 格后回访周期≈生长时间，**产量基本不变**。
	# 腾出的 6 行（y 16-21）新增第 4 个 6x6 南瓜方阵（见 in_pumpkin_zone）。
	return x < HALF and y >= WOOD_ROWS + HAY_ROWS and y < CARROT_END


def in_pumpkin_zone(x, y):
	# 4 个 6x6 方阵：右半区 x∈[HALF, HALF+6) 竖排 3 个（y 0-5 / 7-12 / 14-19），
	# 左半区 x∈[0, 6) 1 个（y 16-21）—— 这块地是从胡萝卜带压出来的（胡萝卜 11 行 → 5 行）。
	# 方阵之间留 1 行间隔，避免连成 6x12 长方形（矩形产量口径未验证）。
	# 逐方阵独立判定收割（见 work_pumpkin_smart）：0.8^36 已是 0.03%，两块合判会直接停产。
	sq = 0
	while sq < PUMPKIN_SQUARES:
		ox = PUMPKIN_OX[sq]
		oy = PUMPKIN_OY[sq]
		if x >= ox and x < ox + PUMPKIN_SIZE:
			if y >= oy and y < oy + PUMPKIN_SIZE:
				return True
		sq = sq + 1
	return False


def in_sunflower_zone(x, y):
	# 向日葵带缩到 **40 格**：右半区顶部 x∈[HALF+6, SIZE) 共 5 列 × 前 8 行。
	# 依据（实测 22x22、206 格）：毛收入 10.9/秒、耗电 3.95/秒、净 +7/秒，
	# 而**收入 = 访问速率 × 1.13**，访问速率受每步语句开销限制、与带子大小无关 ——
	# 40 格时每轮刀数少但轮次更短，每秒刀数基本不变。腾出的格子去做南瓜（单次收割 13,824 个）。
	return x >= SIZE_OF_BOARD - 3 and y < SUN_ROWS


def in_buffer_zone(x, y):
	# 伴生缓冲带 = WOOD + HAY。它们是上游产出且实测严重过剩，适合让出物种选择权
	return in_wood_zone(x, y) or in_hay_zone(x, y)


def has_companion_preference(t):
	# 有伴生偏好的只有这四种（南瓜与向日葵没有）
	return t == Entities.Grass or t == Entities.Bush or t == Entities.Tree or t == Entities.Carrot


# ------------------------------------------------------------
# 伴生指派表读写
# ------------------------------------------------------------
def plan_index(x, y):
	return y * SIZE_OF_BOARD + x


def plan_at(x, y, sweep):
	# 只有「上一轮投的票」才有效；更早的视为过期，避免陈旧指派把缓冲带锁死
	k = plan_index(x, y)
	if PLAN_AGE[k] >= sweep - 1:
		return PLAN[k]
	return None


def set_plan(x, y, species, sweep):
	k = plan_index(x, y)
	PLAN[k] = species
	PLAN_AGE[k] = sweep


# ------------------------------------------------------------
# 移动辅助
# ------------------------------------------------------------
def goto(tx, ty):
	# 环形棋盘上朝目标走；判等即可，不需要取模
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
	# till() 是「切换」而不是「设为土壤」，土壤再翻一次会变回草原，所以必须先判断
	if get_ground_type() != Grounds.Soil:
		till()


def plant_bush_or_tree():
	# (x + y) 为偶数处种 Tree、奇数处种 Bush，保证任意两棵 Tree 都不正交相邻，
	# 从而避开 Tree「旁边有树则生长时间翻倍」的惩罚
	if (get_pos_x() + get_pos_y()) % 2 == 0:
		plant(Entities.Tree)
	else:
		plant(Entities.Bush)


def water_if_needed():
	# 只给「种了作物的土壤」浇水。WOOD/HAY 带是草原且不需要水
	if get_ground_type() == Grounds.Soil:
		if get_entity_type() != None and get_water() < WATER_THRESHOLD:
			use_item(Items.Water)


def tend_carrot_tile():
	# 胡萝卜：收割后补种，补种成功的瞬间顺手施肥
	#
	# 为什么施肥：实测一次全盘扫描要十几到几十秒，而作物 2~7 秒就长好了，
	# 所以「肥料省 2 秒生长」对吞吐的贡献是 0 —— 施肥唯一真实的收益是副作用：
	# 被感染的植物收获时一半产量变成奇异物质。但奇异物质已经攒够（约 2.5 万），
	# 所以只有胡萝卜很富裕时才继续换。
	# 伴生宿主（Grass/Bush/Tree）**不要动**：它们是 work_carrot 特意留在带内、
	# 用来满足邻居请求的，收掉就等于把 ×80 的倍率拆了。
	t = get_entity_type()
	if t == Entities.Grass or t == Entities.Bush or t == Entities.Tree:
		water_if_needed()
		return
	if can_harvest():
		harvest()
	if plant(Entities.Carrot):
		if num_items(Items.Carrot) > CARROT_RESERVE and num_items(Items.Fertilizer) > FERTILIZER_RESERVE:
			use_item(Items.Fertilizer)


def vote_from(x, y, sweep):
	# 读脚下植物的伴生请求；目标落在缓冲带内才投票（1 tick，不移动）
	t = get_entity_type()
	if t == None:
		return
	if not has_companion_preference(t):
		return
	cp = get_companion()
	if cp == None:
		return
	ptype, (px, py) = cp
	# 缓冲带是草原，种不了胡萝卜 → 对 Entities.Carrot 的请求一律不投票，
	# 否则每次都会走一次注定失败的 plant() 并打出警告。
	if in_buffer_zone(px, py) and ptype != Entities.Carrot:
		set_plan(px, py, ptype, sweep)


def tend_buffer_tile(x, y, sweep):
	# 缓冲带（WOOD / HAY）的一格：收割 → 按上一轮的票决定种什么。
	# 返回本格是否被指派（供上报统计）。
	#
	# 关键：先收割再按指派补种，所以「让出物种选择权」不会丢掉产出 ——
	# 指派的灌木/树照样产木材，指派的草照样自长产干草。
	if can_harvest():
		vote_from(x, y, sweep)
		harvest()
	want = plan_at(x, y, sweep)
	if want == None:
		if in_wood_zone(x, y):
			plant_bush_or_tree()
		# HAY 带无指派时什么都不种：草会自己长回来
		return 0
	if want != Entities.Grass:
		if want == Entities.Carrot:
			# 草原上种不了胡萝卜 → 退回默认物种，别浪费一次注定失败的 plant()
			if in_wood_zone(x, y):
				plant_bush_or_tree()
		else:
			plant(want)
	vote_from(x, y, sweep)
	# want == Grass 时不用种：草原上草会自长
	return 1


# ------------------------------------------------------------
# 仙人掌：一次性的「补课」流程
#
# 规则要点：
#   - 尺寸 0~9，成熟后若「N/E 邻居 >= 自己 且 S/W 邻居 <= 自己」即为有序
#   - 收获一株有序仙人掌会递归连锁收获整片有序方形区域，产出 n^2 个（n = 收下的株数）
#   - 所以一个 s x s 方阵一次收获 s^4 个：6x6 -> 1296，每格 36 个
#   - 种 1 株耗 2 南瓜；解锁恐龙（Dinosaurs）要 2000 个仙人掌
#
# 排序用「局部修复循环」，并且保证终止：
#   定义势能 P = Σ 尺寸 × (x + y)。每次修复性交换都是把更大的值移到 x+y 更大的位置、
#   更小的移到更小的位置，所以 P 每交换一次至少 +1；而 P 有上界（尺寸 <= 9、格数有限），
#   因此交换次数有限，循环必然结束。结束时全盘无违规 = 全盘有序 = 可连锁收获。
# ------------------------------------------------------------
SUN_SPAWNED = [0]                # 1 = 向日葵副机已经派过了（补课阶段就派，避免重复派）
CACTUS_CFG = [0]                 # [0] = 本机负责第几个南瓜方阵（仙人掌田借用南瓜方阵）


def cactus_x(col):
	# 仙人掌田借用第 CACTUS_CFG[0] 个南瓜方阵（已耕好的 6x6 正方形，连 till 都不用）
	return PUMPKIN_OX[CACTUS_CFG[0]] + col


def sort_cacti():
	# 局部修复循环。每格只需查 E 与 N 两个邻居（S/W 由那些格子自己的 N/E 检查覆盖），
	# 而 measure(direction) 是原地读，不用移动 —— 所以一遍修复就是一次连续扫描。
	passes = 0
	while passes < 200:
		swaps = 0
		for row in range(PUMPKIN_SIZE):
			for col in range(PUMPKIN_SIZE):
				goto(cactus_x(col), PUMPKIN_OY[CACTUS_CFG[0]] + row)
				me = measure()
				if me != None:
					if col + 1 < PUMPKIN_SIZE:
						e = measure(East)
						if e != None:
							if e < me:
								swap(East)
								swaps = swaps + 1
								me = e
					if row + 1 < PUMPKIN_SIZE:
						n = measure(North)
						if n != None:
							if n < me:
								swap(North)
								swaps = swaps + 1
		if swaps == 0:
			return passes
		passes = passes + 1
	return passes


# ------------------------------------------------------------
# 仙人掌排序 v2：把「看」和「动」分开
#
# v1（sort_cacti）是边扫边修的局部修复循环：每收敛一遍都要把 36 格重走一次，
# 通常要十几遍，而其中绝大多数移动是白走的（只为看一眼）。
# v2 只走一遍读、再只执行必要的交换：
#   1) 蛇形读一遍，把 36 格尺寸读进内存（36 移动 + 36 measure）
#   2) 纯内存里算出目标排列与搬运路径（0 行动开销）
#   3) 只做必要的相邻交换
#
# 目标排列取「全部尺寸升序 + 行主序」，它天然满足
# 「N/E 邻居 >= 自己 且 S/W 邻居 <= 自己」。
# 归位时逐个位置把最近的持有者推过来；相邻交换次数主要由随机数据的逆序数决定，
# 这是任何正确排序都绕不开的下界，v2 省掉的是**反复扫描**的开销。
# ------------------------------------------------------------
CACTUS_GRID = []                   # 6x6 尺寸快照（行主序）
CACTUS_SORTED = []                 # 升序目标值
CACTUS_SORT_STATS = [0, 0]         # [读到的空格数, 本周期执行的交换次数]
_i4 = 0
while _i4 < PUMPKIN_TILE_COUNT:
	append(CACTUS_GRID, 0)
	append(CACTUS_SORTED, 0)
	_i4 = _i4 + 1


def cactus_read_grid():
	# 蛇形读一遍：行与行之间只花 1 次移动（v1 用 goto 每换行要横穿半行）
	empty = 0
	for row in range(PUMPKIN_SIZE):
		for col in range(PUMPKIN_SIZE):
			c = col
			if row % 2 == 1:
				c = PUMPKIN_SIZE - 1 - col
			goto(cactus_x(c), PUMPKIN_OY[CACTUS_CFG[0]] + row)
			v = measure()
			if v == None:
				empty = empty + 1
				v = 0
			CACTUS_GRID[row * PUMPKIN_SIZE + c] = v
	return empty


def cactus_mem_swap(a, b):
	t = CACTUS_GRID[a]
	CACTUS_GRID[a] = CACTUS_GRID[b]
	CACTUS_GRID[b] = t


def cactus_push_value(src, dst):
	# 把 src 处的值用相邻交换推到 dst：先沿行对齐列、再沿列对齐行。
	# 选这条 L 形路径是安全的：途中经过的格子行主序下标都 >= dst，
	# 所以不会碰到已经归位好的前半部分。内存快照同步更新。
	#
	# 关键：`swap()` **只交换、不移动无人机** —— 必须 swap 之后紧跟同方向的 move，
	# 否则无人机会停在原地把同一对来回换（实测「交换了 94 次、违规数仍是 27」= 什么都没做）。
	sx = src % PUMPKIN_SIZE
	sy = src // PUMPKIN_SIZE
	dx = dst % PUMPKIN_SIZE
	dy = dst // PUMPKIN_SIZE
	goto(cactus_x(sx), PUMPKIN_OY[CACTUS_CFG[0]] + sy)
	while sx != dx:
		if sx < dx:
			swap(East)
			move(East)
			cactus_mem_swap(sy * PUMPKIN_SIZE + sx, sy * PUMPKIN_SIZE + sx + 1)
			sx = sx + 1
		else:
			swap(West)
			move(West)
			cactus_mem_swap(sy * PUMPKIN_SIZE + sx, sy * PUMPKIN_SIZE + sx - 1)
			sx = sx - 1
		CACTUS_SORT_STATS[0] = CACTUS_SORT_STATS[0] + 1
	while sy != dy:
		if sy < dy:
			swap(North)
			move(North)
			cactus_mem_swap(sy * PUMPKIN_SIZE + sx, (sy + 1) * PUMPKIN_SIZE + sx)
			sy = sy + 1
		else:
			swap(South)
			move(South)
			cactus_mem_swap(sy * PUMPKIN_SIZE + sx, (sy - 1) * PUMPKIN_SIZE + sx)
			sy = sy - 1
		CACTUS_SORT_STATS[0] = CACTUS_SORT_STATS[0] + 1


def sort_cacti_v2():
	empty = cactus_read_grid()
	CACTUS_SORT_STATS[1] = empty
	if empty > 0:
		# 有格子读不到尺寸（空位或未成熟）→ 退回 v1 的局部修复循环，保证不会白跑
		sort_cacti()
		return

	# 插入排序（36 个元素，纯内存、零行动开销）
	k = 0
	while k < PUMPKIN_TILE_COUNT:
		CACTUS_SORTED[k] = CACTUS_GRID[k]
		k = k + 1
	i = 1
	while i < PUMPKIN_TILE_COUNT:
		v = CACTUS_SORTED[i]
		j = i - 1
		done = 0
		while j >= 0 and done == 0:
			if CACTUS_SORTED[j] > v:
				CACTUS_SORTED[j + 1] = CACTUS_SORTED[j]
				j = j - 1
			else:
				done = 1
		CACTUS_SORTED[j + 1] = v
		i = i + 1

	# 逐位置归位。只在「还没归位」的半边里找最近的持有者（scan > idx），
	# 这样已归位的前半段绝不会被推动破坏。
	for idx in range(PUMPKIN_TILE_COUNT):
		want = CACTUS_SORTED[idx]
		if CACTUS_GRID[idx] != want:
			best = -1
			best_d = 999
			scan = idx + 1
			while scan < PUMPKIN_TILE_COUNT:
				if CACTUS_GRID[scan] == want:
					d = abs(scan // PUMPKIN_SIZE - idx // PUMPKIN_SIZE) + abs(scan % PUMPKIN_SIZE - idx % PUMPKIN_SIZE)
					if d < best_d:
						best_d = d
						best = scan
				scan = scan + 1
			if best >= 0:
				cactus_push_value(best, idx)


# <<<CACTUS_SORT_V2_END>>>


# ------------------------------------------------------------
# 仙人掌补课 v2：可观测 + 便宜的等待 + 排序自检
#
# 为什么要重写：v1 的等待每试一次就要把 36 格重扫一遍，最多试 40 次，外层又最多
# 12 轮 —— 最坏情况是 480 次全阵扫描，而且**全程不打印任何东西**，看起来就像卡死。
# v2 做三件事：
#   1) 等待改成「盯住一格轮询」，验证只做一次全阵核对
#   2) 每一步都 print 到 output.txt，卡在哪一眼就能看出来
#   3) 排序后**自检违规数**；v2 没排干净就自动退回 v1 的局部修复循环再核一次
# ------------------------------------------------------------
def cactus_wait_first(max_sec):
	# 只盯一格等到成熟。用 get_time() 做上界（它是 0 tick 的）。
	goto(cactus_x(0), PUMPKIN_OY[CACTUS_CFG[0]])
	start = get_time()
	while get_time() - start < max_sec:
		if can_harvest():
			return 1
		pass
	return 0


def cactus_plant_and_wait_v2():
	for row in range(PUMPKIN_SIZE):
		for col in range(PUMPKIN_SIZE):
			goto(cactus_x(col), PUMPKIN_OY[CACTUS_CFG[0]] + row)
			if get_entity_type() == None:
				plant(Entities.Cactus)
	rounds = 0
	while rounds < 3:
		if cactus_wait_first(90) == 0:
			print("[cactus] wait timeout")
			return 0
		missing = 0
		for row in range(PUMPKIN_SIZE):
			for col in range(PUMPKIN_SIZE):
				goto(cactus_x(col), PUMPKIN_OY[CACTUS_CFG[0]] + row)
				if get_entity_type() == None:
					plant(Entities.Cactus)
					missing = missing + 1
				elif not can_harvest():
					missing = missing + 1
		if missing == 0:
			return 1
		print("[cactus] still not mature, missing", missing)
		rounds = rounds + 1
	return 0


def cactus_count_violations():
	# 读一遍，数有多少格违反「N/E 邻居 >= 自己 且 S/W 邻居 <= 自己」
	cactus_read_grid()
	bad = 0
	for y in range(PUMPKIN_SIZE):
		for x in range(PUMPKIN_SIZE):
			me = CACTUS_GRID[y * PUMPKIN_SIZE + x]
			if x + 1 < PUMPKIN_SIZE:
				if CACTUS_GRID[y * PUMPKIN_SIZE + x + 1] < me:
					bad = bad + 1
			if y + 1 < PUMPKIN_SIZE:
				if CACTUS_GRID[(y + 1) * PUMPKIN_SIZE + x] < me:
					bad = bad + 1
	return bad


def cactus_cycle_v2(n):
	before = num_items(Items.Cactus)
	# 清空这 6x6（把上面的南瓜/死瓜收掉）
	for row in range(PUMPKIN_SIZE):
		for col in range(PUMPKIN_SIZE):
			goto(cactus_x(col), PUMPKIN_OY[CACTUS_CFG[0]] + row)
			if get_entity_type() != None:
				harvest()
	print("[cactus] cycle", n, "cleared, planting and waiting")
	if cactus_plant_and_wait_v2() == 0:
		print("[cactus] cycle", n, "ABORT before sorting; have", num_items(Items.Cactus))
		return
	CACTUS_SORT_STATS[0] = 0
	sort_cacti_v2()
	bad = cactus_count_violations()
	print("[cactus] cycle", n, "swaps", CACTUS_SORT_STATS[0], "unreadable", CACTUS_SORT_STATS[1], "violations", bad)
	if bad > 0:
		# v2 没排干净 → 用 v1 的局部修复循环兜底
		sort_cacti()
		bad = cactus_count_violations()
		print("[cactus] cycle", n, "after v1 fallback violations", bad)
	goto(cactus_x(0), PUMPKIN_OY[CACTUS_CFG[0]])
	harvest()
	after = num_items(Items.Cactus)
	print("[cactus] cycle", n, "gained", after - before, "total", after)


# <<<CACTUS_CYCLE_V2_END>>>


def cactus_worker(sq, target):
	# 一架负责一个方阵：设好自己的方阵号后一直跑「清地->播种->等熟->排序->收割」，
	# 直到**全局库存**够了 —— Items.Cactus 是共享物品栏，所以这是所有副机共同的收工信号。
	CACTUS_CFG[0] = sq
	while num_items(Items.Cactus) < target:
		cactus_cycle_v2(0)


def cactus_cost_of(u):
	# 某个解锁「下一级」要多少仙人掌：已满级（get_cost 返回 None）或不吃仙人掌时为 0。
	# **只数 Items.Cactus 那一项** —— 别的成本（金币 / 骨头 / 南瓜）不由补课线负担。
	# 旧版 cactus_needed_for_dinosaurs 把 dict 里所有项都加了起来，是个定时炸弹（已修）。
	cost = get_cost(u)
	if cost == None:
		return 0
	total = 0
	for item in cost:
		if item == Items.Cactus:
			total = total + cost[item]
	return total


def cactus_needed_for_mazes():
	return cactus_cost_of(Unlocks.Mazes)


def cactus_needed_for_dinosaurs():
	return cactus_cost_of(Unlocks.Dinosaurs)


def cactus_push():
	# 欠账就补，凑够就走；南瓜不够时让位给主循环去攒。
	# 注意：必须在**派副机之前**跑完 —— 仙人掌带就是南瓜带，南瓜副机会把仙人掌当「成熟的好瓜」连锁收掉。
	if CACTUS_PUSH_ENABLED == 0:
		return
	# **目标选择（probe7 实测）**：在预算内挑最便宜的一档，理由见文件头 CACTUS_TARGET_CAP。
	# 旧写法是「先取 Mazes、超预算就截断到上限」，那会攒出一个**买不到任何东西**的数字：
	# BUILD 38~40 把 need 截成 5,000,000，而恐龙档只要 2,590,000、Mazes 要 15,600,000，
	# 于是白跑几分钟、还把南瓜线堵在启动阶段。这一次的修复就是冲它来的。
	mz = cactus_needed_for_mazes()
	dn = cactus_needed_for_dinosaurs()
	need = 0
	which = "none"
	if dn > 0:
		if dn <= CACTUS_TARGET_CAP:
			need = dn
			which = "dinosaurs"
	if mz > 0:
		if mz <= CACTUS_TARGET_CAP:
			if need == 0 or mz < need:
				need = mz
				which = "mazes"
	if need <= 0:
		print("[cactus] skip: no affordable cactus upgrade; mazes", mz, "dinosaurs", dn, "cap", CACTUS_TARGET_CAP)
		return
	have = num_items(Items.Cactus)
	if have >= need:
		print("[cactus] up to date:", which, need, "have", have)
		return
	print("[cactus] push start: need", need, which, "have", have, "pumpkin", num_items(Items.Pumpkin))
	# **补课期间也必须有人产电**：这里先把 2 架向日葵派出去占住名额（否则 7 架仙人掌机
	# 会把 8 个名额用光，长时间无电收入 ⇒ pow 被抽干、2 倍速丢失）。
	_sm = SUN_ROWS // 2
	if SUN_SPAWNED[0] == 0:
		spawn_drone(loop_sunflower, 0, _sm)
		spawn_drone(loop_sunflower, _sm, SUN_ROWS)
		SUN_SPAWNED[0] = 1
		print("[cactus] sunflower workers launched (2)")
	if drone_cap() < 4:
		# 无人机不够：退回单机顺序版
		cycles = 0
		while num_items(Items.Cactus) < need and cycles < CACTUS_MAX_CYCLES:
			if num_items(Items.Pumpkin) < CACTUS_PUMPKIN_RESERVE:
				print("[cactus] stop: pumpkin reserve low")
				return
			cactus_cycle_v2(cycles)
			cycles = cycles + 1
		print("[cactus] push done: cycles", cycles, "cactus", num_items(Items.Cactus))
		return
	# 8 架时用满：7 个副机各占一片 + 主机认领第 8 片 = 8 片同时开工。
	# 补课是开局的瓶颈，8 片并行 ⇒ 72,000 只需约 2 轮（每片一轮 5,184）。
	n = drone_cap() - 3          # 预留 2 个给向日葵、1 个给主机自己
	if n > PUMPKIN_SQUARES - 1:  # **必须留一片给主机**：主机认领第 n 片，
		n = PUMPKIN_SQUARES - 1  # n = PUMPKIN_SQUARES 会越界（BUILD 37 就崩在这里）
	if n < 2:
		n = 2
	print("[cactus] parallel push on", n, "squares")
	drones = []
	i = 0
	while i < n:
		d = spawn_drone(cactus_worker, i, need)
		if d != None:
			append(drones, d)
		i = i + 1
	CACTUS_CFG[0] = n
	while num_items(Items.Cactus) < need:
		cactus_cycle_v2(0)
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	print("[cactus] push done: cactus", num_items(Items.Cactus))


# ------------------------------------------------------------
# 伴生抽样调查：看「白拿」的命中率有多高
#
# 为什么只抽样、且每 REPORT_EVERY 轮才跑一次：
# 游戏没有读取远处格子的函数 —— get_entity_type() 只对无人机脚下有效，
# measure(direction) 只返回花瓣 / 仙人掌尺寸 / 迷宫宝藏位置，不返回物种。
# 所以确认一个伴生请求是否被满足，必须真的飞到那个坐标看一眼。
# ------------------------------------------------------------
def companion_survey():
	tested = 0
	hit = 0
	idx = 0
	# 左半区正好是 WOOD + HAY + CARROT 三条可伴生带，共 72 格
	for row in range(SIZE_OF_BOARD):
		for col in range(HALF):
			if idx % COMPANION_STEP == 0:
				goto(col, row)
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
	COMPANION_STATS[0] = tested
	COMPANION_STATS[1] = hit


# ------------------------------------------------------------
# 初始化
# ------------------------------------------------------------

# ------------------------------------------------------------
# 状态上报：用 get_time / get_tick_count / num_items / get_cost / num_unlocked
# ------------------------------------------------------------
# ------------------------------------------------------------
# 自动升级：用 unlock() 把富余资源换成升级
#
# 注意「auto_unlock」这个解锁只是**授予 unlock() 函数本身**，并不会自动买东西，
# 所以必须自己判断「买得起」再调用。get_cost() 返回 {物品: 数量}，
# 买之前逐个物品比对库存，并为农场的耗材预留一点底，别为了升级把农场饿死。
# ------------------------------------------------------------
def upgrade_reserve(item):
	# 木材 / 干草 / 胡萝卜是农场的耗材（胡萝卜补种要 8 干草 + 8 木材），留一点底
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
# **Unlocks.Dinosaurs 必须在这个表里**：仙人掌补课攒的 259 万仙人掌只有它能花掉。
# 漏了它就会变成「补课攒够了、却永远不买」的死循环 —— BUILD 40 正是这个状态。
UPGRADE_TARGETS = [Unlocks.Grass, Unlocks.Trees, Unlocks.Speed, Unlocks.Watering, Unlocks.Sunflowers, Unlocks.Carrots, Unlocks.Fertilizer, Unlocks.Polyculture, Unlocks.Pumpkins, Unlocks.Mazes, Unlocks.Dinosaurs]
UPGRADE_NAMES = ["Grass", "Trees", "Speed", "Watering", "Sunflowers", "Carrots", "Fertilizer", "Polyculture", "Pumpkins", "Mazes", "Dinosaurs"]


def try_upgrade():
	# 返回买到的下标，没买返回 -1。用下标而不是对象本身打日志，避免 print 不支持枚举。
	i = 0
	for target in UPGRADE_TARGETS:
		if can_afford(get_cost(target)):
			if unlock(target):
				print("[upgrade] bought target_index", i, UPGRADE_NAMES[i])
				return i
		i = i + 1
	return -1


# <<<UPGRADE_BLOCK_END>>>


def drone_cap():
	# max_drones() 属于 Megafarm 解锁，未解锁前调用可能报错，所以先判断
	if num_unlocked(Unlocks.Megafarm) <= 0:
		return 0
	return max_drones()


def pumpkin_needed_for_expand():
	cost = get_cost(Unlocks.Expand)
	if cost == None:
		return 0
	total = 0
	for item in cost:
		total = total + cost[item]
	return total


def sun_cost_next():
	# 向日葵升级下一级要多少（把 dict 里的数量加起来；实测各升级成本都是单一物品）。
	# 若已满级，get_cost 返回 None → 返回 -1，表示「没有升级这条路」。
	c = get_cost(Unlocks.Sunflowers)
	if c == None:
		return -1
	t = 0
	for it in c:
		t = t + c[it]
	return t


def report(sweep, sec_per_sweep, ticks_per_sweep):
	if get_world_size() != SIZE_OF_BOARD:
		# 扩张（Expand）会在运行中把棋盘换掉：本脚本的 SIZE_OF_BOARD 是启动时读的常量，
		# 于是所有带边界都错位、新棋盘又是草原 → 播种开始失败（只报警告，不报错）。
		print("[warn] board is", get_world_size(), "but this run uses", SIZE_OF_BOARD, "-> restart main.py to relayout")
	print("[stat] sweep", sweep,
		"sec/sweep", sec_per_sweep,
		"ticks/sweep", ticks_per_sweep,
		"size", SIZE_OF_BOARD,
		"world", get_world_size(),
		"max_drones", drone_cap(),
		"lv_sun", num_unlocked(Unlocks.Sunflowers),
		"sun_cost", sun_cost_next(),
		"power", num_items(Items.Power),
		"poly_lv", num_unlocked(Unlocks.Polyculture),
		"comp_hit", COMPANION_STATS[1], "/", COMPANION_STATS[0],
		"comp_plan", COMPANION_STATS[2],
		"cactus", num_items(Items.Cactus),
		"need_mazes", cactus_needed_for_mazes(),
		"need_dinos", cactus_needed_for_dinosaurs(),
		"hay", num_items(Items.Hay),
		"wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot),
		"pumpkin", num_items(Items.Pumpkin),
		"expand_needs", pumpkin_needed_for_expand(),
		"water", num_items(Items.Water),
		"cactus_swaps", CACTUS_SORT_STATS[0],
		"cactus_empty", CACTUS_SORT_STATS[1],
		"weird", num_items(Items.Weird_Substance),
		"fert", num_items(Items.Fertilizer))


# ------------------------------------------------------------
# 主扫描：逐行扫过全盘（y 从 0 往上），处理 WOOD / HAY / CARROT / PUMPKIN
#
# 混合种植 M2 的核心就在这个顺序里：
#   WOOD(y 0~2) 与 HAY(y 3~6) 排在 CARROT(y 7~11) 之前，
#   所以「先按上一轮的票改种缓冲带，再收割胡萝卜」天然成立 —— 胡萝卜被收割时
#   它要的伴生植物已经在位，10 倍直接吃到，而且全程零额外移动。
# ------------------------------------------------------------

# ------------------------------------------------------------
# 并行：把农场按【左右半区】切开，两架无人机各包一半
#
# 为什么按列切而不是按行切：文档明确写着 No Shared Memory —— 每架无人机有
# 自己的内存，读不到别人的全局变量。而混合种植的投票表（PLAN）就存在内存里，
# 所以「投票者」和「被指派的目标格」必须在同一架无人机的辖区里。
#   投票者 = 左半区的胡萝卜 / 草 / 树 / 灌木
#   目标格 = 左半区的 WOOD 与 HAY 带
# 两者同属左半区，按列切就天然满足；按行切会跨机，投票直接失效。
#
# 另外按列切正好 72 / 72 格，工作量天然均衡；向日葵与南瓜带也完整落在右半区，
# 于是「Petal Gate 的最大花瓣」和「南瓜整阵计数」都不需要跨机协调。
#
# 两个 worker 都用蛇行走位，行与行之间只花 1 次移动（不是横穿整行）。
# ------------------------------------------------------------


# <<<PARALLEL_WORKERS_END>>>


# ------------------------------------------------------------
# 南瓜整阵补种：连锁收割会一次清空 6x6 全部 36 格，
# 如果只补种脚下那一格，其余 35 格要等到下一轮扫描才补上 ——
# 而那一轮它们刚种下、计数必然是 0，于是「两轮才能收一次」。
# 这里在收割后立刻把整片补满，把周期压到一轮。
# ------------------------------------------------------------


# ------------------------------------------------------------
# 并行初始化：clear() 必须先做完（它整场重置），之后左右半区可以同时播种
# ------------------------------------------------------------


# <<<PUMPKIN_INIT_END>>>


# ------------------------------------------------------------
# 四架无人机分工 + 并行初始化
#
# 切法受 No Shared Memory 约束（每个内存状态必须整块归一架）：
#   南瓜整阵计数 / 向日葵花瓣最大值 / 伴生指派表 PLAN
# => 南瓜方阵、向日葵带、以及「投票者+目标格」都不可拆
#
# 于是：
#   主机    = WOOD+HAY 缓冲带（64 格，含伴生指派）+ 最后读胡萝卜的请求
#   副机 1  = CARROT 带（64 格）
#   副机 2  = PUMPKIN 方阵（36 格）
#   副机 3  = SUNFLOWER 带（92 格，两遍扫描）
#
# 注意投票的时序：胡萝卜的请求**必须在副机 1 收割/补种完成之后**再读，
# 否则会读到刚被割掉的旧株的请求（那株已经没了，票是废的）。
# 所以读请求被放在 wait_for 之后，由主机单独走一遍胡萝卜带。
# ------------------------------------------------------------
BUF_ROWS = WOOD_ROWS + HAY_ROWS        # 缓冲带行数（16x16 -> 8）
CARROT_START = BUF_ROWS                # 胡萝卜带起始行（16x16 -> 8）


def sun_row_x0(y):
	# 向日葵带只在上方 SUN_ROWS 行（右半区最右 5 列）；其余行没有向日葵（返回空区间）
	if y < SUN_ROWS:
		return SIZE_OF_BOARD - 3
	return SIZE_OF_BOARD


def work_buffer(sweep):
	# 主机：缓冲带每一格「收割 -> 按票改种」，票来自主机自己上一轮读到的请求
	plan_count = 0
	for y in range(BUF_ROWS):
		for i in range(HALF):
			x = i
			if y % 2 == 1:
				x = HALF - 1 - i
			goto(x, y)
			plan_count = plan_count + tend_buffer_tile(x, y, sweep)
			water_if_needed()
	COMPANION_STATS[2] = plan_count


def read_carrot_votes(sweep):
	# **备而不用**（deadcode.py 里用 --keep 明确保留）：BUILD 40 起 loop_buffer 不再调它 ——
	# 那是每轮 128 格的往返，是全场最大的一块动作/耗电开销，而它换来的伴生倍率只作用于
	# 草/灌木/树/胡萝卜（四样全都过剩 20 倍以上），对南瓜（当前唯一目标）收益为 0。
	# 哪天要把伴生投票接回来，入口就在这里（时序要求：必须在胡萝卜副机收工之后读）。
	# 主机在副机收工之后走一遍胡萝卜带，只读请求并投票（不收割、不补种）
	for row in range(CARROT_END - CARROT_START):
		y = CARROT_START + row
		for i in range(HALF):
			x = i
			if row % 2 == 1:
				x = HALF - 1 - i
			goto(x, y)
			vote_from(x, y, sweep)


def plant_host(tx, ty, ptype, cy0, ye):
	# **胡萝卜带内部伴生宿主**：把带内的目标格改种成被请求的物种（Grass/Bush/Tree）。
	# 为什么这么做：胡萝卜的请求目标落在以自己为中心 3 步内，而带子本身有 66 格 ——
	# 大量请求指向带内，原来的代码只认「缓冲带」目标，这些票**全被丢掉**（实测命中率卡在 22%）。
	# 在这里把目标格变成宿主，就等于给提出请求的那株挂上 ×Polyculture 的倍率。
	# 只做本机负责的行（两台胡萝卜机各管一半，不互相打架）；目标已经是该物种就直接跳过
	# （所以每株的请求只需要成功转换一次，之后就自然收敛，不会反复拆建）。
	if ty < cy0 or ty >= ye:
		return 0
	if not in_carrot_zone(tx, ty):
		return 0
	if ptype == Entities.Carrot:
		return 0
	goto(tx, ty)
	if get_entity_type() == ptype:
		return 0
	if can_harvest():
		harvest()
	if plant(ptype):
		water_if_needed()
		return 1
	return 0


def work_carrot(sweep, cy0, cy1):
	# 副机 1：胡萝卜带，只负责收割 + 补种 + 浇水（投票由主机读）。
	# cy0/cy1 = 本机负责的行区间（8 架时按行切成 2 段；收割/补种不需要共享状态，投票仍由主机统一读）。
	# **必须在 CARROT_END 处夹断**：下面是第 4 个南瓜方阵，tend_carrot_tile 会把南瓜收掉。
	ye = cy1
	if ye > CARROT_END:
		ye = CARROT_END
	hosts = 0
	for y in range(cy0, ye):
		row = y - CARROT_START
		for i in range(HALF):
			x = i
			if row % 2 == 1:
				x = HALF - 1 - i
			goto(x, y)
			t0 = get_entity_type()
			if t0 == Entities.Grass or t0 == Entities.Bush or t0 == Entities.Tree:
				hosts = hosts + 1
			tend_carrot_tile()
			water_if_needed()
			# 带内伴生宿主：只在宿主不足 1/3 时继续转换，免得把胡萝卜带吃成草地
			if hosts * 3 < (ye - cy0) * HALF:
				c = get_companion()
				if c != None:
					pt, (px, py) = c
					plant_host(px, py, pt, cy0, ye)


def work_sunflower(round, sy0, sy1):
	# 单遍轮转：成熟就割、割完补种（收入 = 刀数 × 1.11，实测普通 1 点 / 最大花瓣 8 点）。
	# sy0/sy1 = 本机负责的行区间（8 架时把 40 格的带子按行切成 2 段，各机独立跑，零跨机状态）。
	# 量测遍只在每 SUN_MEASURE_EVERY 轮跑一次 —— 轮转策略本身不需要知道最大花瓣，量测只为诊断。
	mrows = sy1
	if round % SUN_MEASURE_EVERY != 0:
		mrows = 0
	alive = 0
	smin = 99
	gate_max = 0
	imm = 0
	imm_max = 0
	nomeas = 0
	other = 0
	soilmis = 0
	wmin = 99
	pw_start = num_items(Items.Power)
	hsum = 0
	hmax = 0
	hmis = 0
	rot = 0
	g8 = 0
	jpet = 0
	jpow = -1
	hi = 0
	while hi < 9:
		HIST[hi] = 0
		hi = hi + 1
	for y in range(sy0, mrows):
		x0 = sun_row_x0(y)
		for x in range(x0, SIZE_OF_BOARD):
			goto(x, y)
			t = get_entity_type()
			if get_ground_type() != Grounds.Soil:
				soilmis = soilmis + 1
			if t == Entities.Sunflower:
				alive = alive + 1
				w = get_water()
				if w < wmin:
					wmin = w
				sp = measure()
				if sp == None:
					nomeas = nomeas + 1
				else:
					if sp > gate_max:
						gate_max = sp
					if sp < smin:
						smin = sp
					k = y * SIZE_OF_BOARD + x
					if sp >= 7 and sp <= 15:
						HIST[sp - 7] = HIST[sp - 7] + 1
					if can_harvest():
						SUN_MAT[k] = sp
						SUN_PROBE[k] = -1
					else:
						SUN_MAT[k] = -1
						imm = imm + 1
						if sp > imm_max:
							imm_max = sp
						SUN_PROBE[k] = sp
			else:
				other = other + 1
				SUN_MAT[y * SIZE_OF_BOARD + x] = -1

	# 第一遍走完才能定下「场上最大花瓣」，于是这里再数一次成熟株：
	#   mmax    = 成熟株里的最大花瓣
	#   matgate = 「成熟 且 等于全场最大花瓣」的株数 —— 这才是 Petal Gate 真正能不能开
	mmax = 0
	matgate = 0
	k = 0
	kmax = SIZE_OF_BOARD * SIZE_OF_BOARD
	if mrows == 0:
		kmax = 0
	while k < kmax:
		if SUN_MAT[k] != -1:
			if SUN_MAT[k] > mmax:
				mmax = SUN_MAT[k]
			if SUN_MAT[k] == gate_max:
				matgate = matgate + 1
		k = k + 1

	# Petal Gate 的目标花瓣：正常情况下就是全场最大；
	# 但若连续 SUN_STUCK_MAX 轮都「没有成熟株处在全场最大」，就退而求其次割成熟株里的最大值 ——
	# 宁可花掉一次 8 倍加成，也不能让整片向日葵长期零产出。
	sun_target = gate_max
	fbmode = 0
	if matgate == 0 and mmax > 0:
		SUN_STUCK[0] = SUN_STUCK[0] + 1
		if SUN_STUCK[0] >= SUN_STUCK_MAX:
			sun_target = mmax
			fbmode = 1
	else:
		SUN_STUCK[0] = 0

	mature = 0
	sharv = 0
	atmax = 0
	fail = 0
	fbh = 0
	grew = 0
	same = 0
	shrank = 0
	pg0 = num_items(Items.Power)
	for y in range(sy0, sy1):
		x0 = sun_row_x0(y)
		for x in range(x0, SIZE_OF_BOARD):
			goto(x, y)
			t = get_entity_type()
			if t == Entities.Sunflower:
				p = measure()
				if p != None:
					if p == gate_max:
						atmax = atmax + 1
					k = y * SIZE_OF_BOARD + x
					if SUN_PROBE[k] != -1:
						# 同一株「未熟时」与「现在」两次测量的对比：相等 => 花瓣种植即定死
						if p > SUN_PROBE[k]:
							grew = grew + 1
						elif p == SUN_PROBE[k]:
							same = same + 1
						else:
							shrank = shrank + 1
						SUN_PROBE[k] = -1
					if can_harvest():
						mature = mature + 1
						# 整片轮转：成熟就割、割完立刻补种（不再只割「最大花瓣」那 1~2 株）。
						# 每次收割都夹住 power 读数，量出「这一刀到底给了多少」。
						pw0 = num_items(Items.Power)
						harvest()
						pwd = num_items(Items.Power) - pw0
						hsum = hsum + pwd
						if pwd > hmax:
							hmax = pwd
						if pwd > 7:
							# 这一刀吃到了 8 倍（说明它是当时全场花瓣最多的那一株）
							g8 = g8 + 1
							sharv = sharv + 1
						else:
							rot = rot + 1
							if jpow == -1:
								# 本轮第一刀「普通产出」：花瓣与产出成对上报，用来标定基准值
								jpet = p
								jpow = pwd
						if pwd < 1:
							hmis = hmis + 1
						if plant(Entities.Sunflower) == False:
							fail = fail + 1
			elif t == None:
				if plant(Entities.Sunflower) == False:
					fail = fail + 1
			else:
				harvest()
				if plant(Entities.Sunflower) == False:
					fail = fail + 1
			water_if_needed()
	gain = num_items(Items.Power) - pg0
	rtot = num_items(Items.Power) - pw_start

	out = []
	append(out, alive)
	append(out, gate_max)
	append(out, sharv)
	append(out, mature)
	append(out, smin)
	append(out, atmax)
	append(out, imm)
	append(out, imm_max)
	append(out, grew)
	append(out, same)
	append(out, shrank)
	append(out, gain)
	append(out, fail)
	append(out, other)
	append(out, nomeas)
	append(out, mmax)
	append(out, matgate)
	append(out, fbh)
	append(out, SUN_STUCK[0])
	append(out, soilmis)
	append(out, wmin)
	append(out, hsum)
	append(out, hmax)
	append(out, hmis)
	append(out, rtot)
	append(out, rot)
	append(out, g8)
	append(out, jpet)
	append(out, jpow)
	return out


# ------------------------------------------------------------
# 并行初始化：clear() 之后四个区域可以同时翻土播种（初始化没有跨机状态）
# ------------------------------------------------------------
def init_region(is_left, y0, y1):
	xs = 0
	xe = HALF
	if is_left == 0:
		xs = HALF
		xe = SIZE_OF_BOARD
	for y in range(y0, y1):
		for x in range(xs, xe):
			goto(x, y)
			if in_carrot_zone(x, y):
				make_soil_if_needed()
				plant(Entities.Carrot)
			elif in_pumpkin_zone(x, y):
				make_soil_if_needed()
				plant(Entities.Pumpkin)
			elif in_sunflower_zone(x, y):
				make_soil_if_needed()
				plant(Entities.Sunflower)


def init_board_v3():
	# **这里原来是个无限递归**：`if drone_cap() < 4: init_board_v3()` —— 自己调自己，
	# cap < 4 时会直接爆栈。4 架路径删掉后入口已经挡住这种情况，但地雷要挖掉。
	clear()
	if drone_cap() < 4:
		init_region(1, 0, SIZE_OF_BOARD)
		init_region(0, 0, SIZE_OF_BOARD)
		return
	mid = SIZE_OF_BOARD // 2
	cap = drone_cap()
	if cap >= 12:
		# 工人多起来之后 init 也要跟着并行：两个半区各切 cap/2 条行带，
		# 右半区最后一条留给主机 ⇒ 副机 2*(cap/2)-1 架 + 主机 = cap 架全用上。
		per = cap // 2
		if per < 2:
			per = 2
		bw = SIZE_OF_BOARD // per
		if bw < 1:
			bw = 1
		ds = []
		i = 0
		while i < per:
			y0 = i * bw
			y1 = y0 + bw
			if i == per - 1:
				y1 = SIZE_OF_BOARD
			d = spawn_drone(init_region, 1, y0, y1)
			if d != None:
				append(ds, d)
			if i < per - 1:
				d = spawn_drone(init_region, 0, y0, y1)
				if d != None:
					append(ds, d)
			i = i + 1
		init_region(0, (per - 1) * bw, SIZE_OF_BOARD)
		i = 0
		while i < len(ds):
			wait_for(ds[i])
			i = i + 1
		return
	if drone_cap() >= 8:
		# 8 架：两个半区各切 4 条行带 → 7 个副机 + 主机，共 8 架全用上
		# （4 架时每架要翻种约 120 格；8 架降到约 60 格，铺田时间大约减半）
		q = SIZE_OF_BOARD // 4
		b0 = 0
		b1 = q
		b2 = q * 2
		b3 = q * 3
		d1 = spawn_drone(init_region, 1, b0, b1)
		d2 = spawn_drone(init_region, 1, b1, b2)
		d3 = spawn_drone(init_region, 1, b2, b3)
		d4 = spawn_drone(init_region, 1, b3, SIZE_OF_BOARD)
		d5 = spawn_drone(init_region, 0, b0, b1)
		d6 = spawn_drone(init_region, 0, b1, b2)
		d7 = spawn_drone(init_region, 0, b2, b3)
		init_region(0, b3, SIZE_OF_BOARD)
		if d1 != None:
			wait_for(d1)
		if d2 != None:
			wait_for(d2)
		if d3 != None:
			wait_for(d3)
		if d4 != None:
			wait_for(d4)
		if d5 != None:
			wait_for(d5)
		if d6 != None:
			wait_for(d6)
		if d7 != None:
			wait_for(d7)
		return
	d1 = spawn_drone(init_region, 1, 0, mid)
	d2 = spawn_drone(init_region, 1, mid, SIZE_OF_BOARD)
	d3 = spawn_drone(init_region, 0, 0, mid)
	init_region(0, mid, SIZE_OF_BOARD)
	if d1 != None:
		wait_for(d1)
	if d2 != None:
		wait_for(d2)
	if d3 != None:
		wait_for(d3)


# <<<FOUR_WORKERS_END>>>


# ------------------------------------------------------------
# 去掉全局同步栅栏：每个工人只在自己的地块上跑自己的无限循环
#
# 之前 run_one_sweep4 末尾的 wait_for 是一道栅栏：所有人都要等最慢的那个收工
# 才进入下一轮。但四块地彼此独立 —— 唯一的跨机依赖是「伴生投票」的时序，
# 而它由主机一个人完成（读胡萝卜 + 改种缓冲带），不需要别人等。
#
# 去掉栅栏的收益：
#   - 南瓜 Gate 是概率事件（整阵 6x6 同时存活成熟），访问越频繁收得越多
#     有栅栏时南瓜副机干完 144 动作要闲置约 408 动作，访问周期被拖到 ~552；
#     去掉后降到 ~144，即约 3.8 倍的成阵机会
#   - 向日葵能更早撞上「刚长到最大花瓣」的那株
# 代价：各机相位漂移，伴生抽样的命中率会略降（每轮都重读，会自我纠正）。
#
# 每个工人维护**自己的**轮次计数器：伴生指派表 PLAN 本来就在各机自己的内存里，
# 写入者（读票）与读取者（改种缓冲带）都是主机，轮次语义自洽。
# 跨机统计不再靠返回值传递 —— 由各自打印。
#
# BUILD 标记：每改一次代码就 +1，启动时打印，用来核对游戏里跑的到底是哪一版
# （游戏会用它的编辑器缓冲区覆盖外部改动，所以「版本对不对」必须能一眼看出来）。
# ------------------------------------------------------------
BUILD = 42


def loop_buffer():
	round = 0
	mark_time = get_time()
	mark_ticks = get_tick_count()
	while True:
		round = round + 1
		goto(0, 0)
		work_buffer(round)
		# 已删除 read_carrot_votes(round)：那是每轮 128 格的往返，是全场最大的一块动作/耗电开销，
		# 而它换来的伴生倍率只作用于草/灌木/树/胡萝卜 —— 四样全都过剩 20 倍以上，
		# 对南瓜（当前唯一目标）收益为 0。删掉它既省电又让主机腾出手。
		if round % REPORT_EVERY == 0:
			now_time = get_time()
			now_ticks = get_tick_count()
			sec_avg = (now_time - mark_time) / REPORT_EVERY
			ticks_avg = (now_ticks - mark_ticks) / REPORT_EVERY
			companion_survey()
			try_upgrade()
			report(round, sec_avg, ticks_avg)
			mark_time = get_time()
			mark_ticks = get_tick_count()


def loop_carrot(cy0, cy1):
	while True:
		work_carrot(0, cy0, cy1)


def loop_sunflower(sy0, sy1):
	round = 0
	mark_time = get_time()
	while True:
		round = round + 1
		st = work_sunflower(round, sy0, sy1)
		# st 只用来喂下面那两行 [sun] / [sun2] 诊断打印 —— 跨机没有共享内存，
		# 所以「副机算出来的量」只能由副机自己 print（写进本机全局是没人读的，已删）。
		if round % SUN_REPORT_EVERY == 0:
			now_time = get_time()
			sec_avg = (now_time - mark_time) / SUN_REPORT_EVERY
			mark_time = now_time
			print("[sun] build", BUILD, "round", round,
				"sec/round", sec_avg,
				"alive", st[0],
				"imm", st[6],
				"mature", st[3],
				"harv", st[2],
				"g8", st[26],
				"rot", st[25],
				"hmis", st[23],
				"hsum", st[21],
				"hmax", st[22],
				"rtot", st[24],
				"wmin", st[20],
				"size", SIZE_OF_BOARD,
				"world", get_world_size(),
				"pow", num_items(Items.Power),
				"lv_sun", num_unlocked(Unlocks.Sunflowers))
			print("[sun2] meas", round % SUN_MEASURE_EVERY,
				"jpet", st[27],
				"jpow", st[28],
				"min", st[4],
				"max_petal", st[1],
				"atmax", st[5],
				"matgate", st[16],
				"grew", st[8], "same", st[9], "shrank", st[10],
				"fail", st[12], "other", st[13], "nomeas", st[14],
				"soilmis", st[19],
				"h7", HIST[0], "h8", HIST[1], "h9", HIST[2],
				"h10", HIST[3], "h11", HIST[4], "h12", HIST[5],
				"h13", HIST[6], "h14", HIST[7], "h15", HIST[8])


# <<<LOOPS4_END>>>


# ------------------------------------------------------------
# 8 架分工（BUILD 21）：把闲置的 4 架用起来
#
# 为什么这么切：
#   - **主机（缓冲带 + 读胡萝卜投票）不可拆** —— 伴生指派表 PLAN 在每架自己的内存里，
#     投票者与目标格一旦跨机，×40 的伴生倍率就白丢了（这是农场的钱袋子）。
#   - 胡萝卜带按行切 2 段：收割/补种不需要共享状态，投票仍由主机统一读 ✓
#   - 南瓜 3 个方阵切成 2+1：状态机不跨机，各自独立结算 ✓
#   - 向日葵 40 格按行切 2 段：收入 = 访问速率 × 1.13，多一架就多一份访问速率（带的格数不是限制）
# 共 7 架（cap 8，留 1 架余量）。
# ------------------------------------------------------------
def main8():
	print("[main] BUILD", BUILD, "starting; drones cap =", drone_cap())
	init_board_v3()
	cactus_push()
	mid = CARROT_START + (CARROT_END - CARROT_START) // 2
	sunmid = SUN_ROWS // 2
	# 32 架时代的分配：一片南瓜一机（方阵数是硬上限）+ 胡萝卜 4 架 + 向日葵 4 架 + 主机。
	cap = drone_cap()
	npum = PUMPKIN_SQUARES
	if npum > cap - 9:
		npum = cap - 9
	if npum < 2:
		npum = 2
	ncar = 4
	nsun = 4
	if cap < 18:
		ncar = 2
		nsun = 2
	print("[main] dynamic split: pumpkin", npum, "carrot", ncar, "sunflower", nsun, "+ buffer(main)")
	# 南瓜 4 个方阵分给 2 架：0-1 / 2-3（右半区 3 个 + 左半区 1 个）
	psplit = PUMPKIN_SQUARES // 2
	if psplit < 1:
		psplit = 1
	_i = 0
	while _i < ncar:
		_a = CARROT_START + ((CARROT_END - CARROT_START) * _i) // ncar
		_b = CARROT_START + ((CARROT_END - CARROT_START) * (_i + 1)) // ncar
		spawn_drone(loop_carrot, _a, _b)
		_i = _i + 1
	_i = 0
	while _i < npum:            # **一片一机**：单项轮次 36 次访问 ≈ 6 秒，与成阵周期同量级
		spawn_drone(w_pumpkin.loop_pumpkin_smart, _i, _i + 1)
		_i = _i + 1
	if SUN_SPAWNED[0] == 0:              # 补课阶段已经派过就不再派（避免重复占名额）
		_i = 0
		while _i < nsun:
			_a = (SUN_ROWS * _i) // nsun
			_b = (SUN_ROWS * (_i + 1)) // nsun
			spawn_drone(loop_sunflower, _a, _b)
			_i = _i + 1
	print("[main] 6 workers launched: carrot x2 / pumpkin x2 / sunflower x2 + buffer(main)")
	loop_buffer()


# <<<LOOPS8_END>>>


# 入口：只剩「一方阵一机」这一条路径。4 架时代的三套路径（main4 / main / run_one_sweep4 /
# game_loop / work_left / work_right / 旧 work_pumpkin …）已全部删除 —— 它们不只是占行数，
# **本身就是陷阱**：旧 work_pumpkin() 只数第 0 号方阵，replant_pumpkin_band() 会把 14 片
# 一起补，误用就会出现「南瓜只收一片」这类怪象（见 docs/plans/modularize-main.md）。
# Megafarm 没解锁时没有可用的降级路径，直接报错，别静默跑半套。
# ---- 入口守卫（2026-10-05 加）----
# 为什么必须加：完全复位榜的 full_run 要**复用**本文件的函数（try_upgrade 等），
# 而原来这段是**无条件的顶层调用** ⇒ 一 import 就会把整个农场跑起来 ✗
# （和 block_farm.py 同一个坑：那里也已加守卫）
def run_main():
	if drone_cap() >= 7:
		main8()
	else:
		print("[main] ERROR: Megafarm not unlocked; drone_cap =", drone_cap())

if __name__ == "__main__":
	run_main()

