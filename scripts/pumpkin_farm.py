# ============================================================
# pumpkin_farm.py —— **高速产南瓜**（独立脚本：整盘铺南瓜方阵，一块一架）
#
# 为什么要单独写：main.py 只用了 14 个 6x6 方阵（而且它同时还要种胡萝卜/向日葵/缓冲带）。
# 当前目标：**25,900,000 南瓜** = 买 `Unlocks.Cactus` lv6 ——
# 仙人掌的产量系数是 `2^(cactus_lv-1)`，lv5 -> lv6 是 **16 -> 32，整条仙人掌线翻倍**
# （cactus_farm 实测：25 块 x 10,000/轮 ≈ 1.5M/分钟 -> 约 3.0M/分钟）。
#
# ---------- 南瓜的产量口径（**这一轮刚纠正过，别再抄旧值**）----------
#   文档（docs/game/entities/pumpkin 的邻居 docs/game/unlocks/pumpkins.md）：
#     **Mega Pumpkin 按边长分两段：n<=5 时 n³，n>=6 时 n²x 6**
#   再叠加等级倍率（与 Mazes / Dinosaurs / Cactus 同一个模式 `2^(lv-1)`）：
#     6x6 一次连锁收割 = 6² x 6 x 2^(pumpkins_lv - 1) = 216 x 2^(lv-1)
#       lv7 -> 216 x 64  = **13,824**   <- BUILD 19 当年量到的那个数
#       lv9 -> 216 x 256 = **55,296**   <- BUILD 42 那批 [pump] pyield 读数
#   ⇒ 交接文档里「[pump] pyield 应为 13,824」**已经过期**，现在应是 55,296。
#   （注意：这与仙人掌那条 25x 污染不是一回事 —— 南瓜这边的 4 倍是**等级**带来的。）
#   本脚本开局会用**单机单块单轮**量一次干净值（见 CALIB），而不是照抄。
#
# ---------- 机制要点（决定这个状态机长什么样）----------
#   * 南瓜长成那一刻有 **1/5** 概率变成 Dead Pumpkin；而**成熟后不会再枯死**
#     ⇒「存活且成熟」是**单调收敛**的状态：某格一旦确认就永远成立，不必再看。
#   * 所以每格在一个种植周期里只需要访问约 1/0.8 = 1.25 次，而不是每轮 1 次。
#   * Dead Pumpkin 无法正常收割，但 harvest() 会直接把它清除 ⇒ 清掉再补种。
#   * 整阵必须**全部**存活且成熟才收割（Harvest Gate）；否则杀一刀只会收到那一小片，
#     产量按收割时的连通区域算 —— 所以「提前收割」是纯亏。
#
# ---------- 布局 ----------
#   默认 **REG_SIZE=7 + GAP=1 -> pitch 8 -> 4x4 = 16 块，覆盖 784 格**。三条约束按重要性排：
#   1. **GAP >= 1 是硬约束**（见下面 GAP 那段实测）：紧挨着铺会让相邻方阵连成一片，
#      而合并后的收割**只给一块的钱** ⇒ 那些格子的产量直接丢掉。
#   2. **产量按短边算**（文档 n<=5 -> n³、n>=6 -> n²x6，n 取短边）⇒ **正方形永远最划算**，
#      所以 REG_SIZE 取正方形边长。
#   3. **边长 >= 6**：n<=5 掉进 n³ 口径（5x5 = 125 = 5/格），n>=6 才是 n²x6（6/格）。
#      这就是玩家实测「6x6 最优」的精确原因；**再大不是更肥，而只是块更少、周期更长**
#      （整块要等最不走运的那一格，轮数 = ln(格数)/ln5）。
#   为什么最后选 7 而不是 6：pitch = 边长 + 1，而 8 能整除 32 ⇒ 4x4 = 16 块铺满，覆盖 784 格；
#   pitch 7 也是 16 块，但只覆盖 576 格。块数一样、地多 36%。
#   为什么不做「一块派 2 架」：收割门要求**整块**待确认数为 0，而每架无人机只有自己的
#   内存 —— 第 2 架不知道第 1 架那半边的状态，门永远不开。唯一解法是让某架扫全块，
#   那就等于回到 1 架。
#   模型（每周期产量 = 覆盖格数 x 6 x 2^(lv-1)；周期 = 收敛轮数 x G + 走位时间）：
#     16 块 7x7（784 格）：G=4 秒 ≈ 104k/秒 = 6.2M/分；G=0.8 秒 ≈ 19M/分
#     （16 块 6x6 只有 576 格：G=4 ≈ 86k/秒，G=0.8 ≈ 17M/分）
#   ⇒ 「20M 南瓜/分钟」的关键**不是块大小，而是把生长时间压到最低**（周期里 2/3 是等生长）。
#   方阵之间留 1 格：虽然南瓜不像仙人掌那样会被 swap 互踩，但**两块紧挨会连成 6x12
#   矩形、产量口径就变了**（BUILD 26 的教训，layout.check_squares 就是为此加的）。
#   空隙格（32x32 里 448 格）交给闲置无人机种向日葵换电量。
#
# ---------- 用法 ----------
#   在游戏里直接运行本文件。它会 clear() 整盘（别和 main.py 同时跑）。
#   产够 PUMPKIN_TARGET 就收工，收工时打印 **pumpkin_per_min**（全程口径，唯一可信的那个）。
# ============================================================

SIZE_OF_BOARD = get_world_size()

# **边长 7 + 缝 1（pitch 8）**：产量按**短边**算 ⇒ 正方形永远最划算，
# 而 pitch 8 正好 4x4 铺满 32x32 ⇒ **16 块、覆盖 784 格**（16 块 6x6 + pitch 7 只有 576 格）。
REG_SIZE = 7
# **块间空隙 GAP**：0 = 紧挨着铺满，1 = 留 1 格缝。
# 为什么默认 0：n>=6 时**每格产量恒定**（= 6 x 2^(lv-1)），所以缝就是纯浪费的地。
# 而 BUILD 26 那次「两块 6x6 紧挨连成 6x12」的实测是 **27,648 = 2 x 13,824** ——
# **正好是面积翻倍、每格不变** ⇒ 紧挨**没有惩罚**；当时说的「产量口径被改变」指的是
# 读数变了，不是每格产量掉了。（CONTEXT 里「矩形口径未验证」这条现在有数据了。）
# **实测推翻了我最初的判断（2026-09-12 夜）**：第一次实跑用 GAP=0（无缝），
# 结果 `pumpkin 8,350,478 -> 13,415,182` 只涨 5,064,704，而各机 harvests 计数合计约 525 次。
# 反推：**92 次有效收获 x 55,296 = 5,087,232 ≈ 实际涨幅** ⇒
# **合并后的连锁收割仍然只给一块的钱**（6x12 拿到的还是 55,296），
# 另外 433 次收获是 0 产出（邻居的格子已经被先手收走了）。
# ⇒ CONTEXT 里「两块紧挨会改变产量口径」是对的；
#   我从 BUILD 26 那个 27,648 推出的「面积口径、紧挨无害」是错的 ——
#   那 27,648 更可能是同一架把两次收割都算进了 num_items 差值（污染）。
# ⇒ **GAP >= 1（方阵隔离）是硬约束。**
GAP = 1
PITCH = REG_SIZE + GAP
GRID = SIZE_OF_BOARD // PITCH
if GRID < 1:
	GRID = 1
NBLOCK = GRID * GRID
TILES = REG_SIZE * REG_SIZE
REG_LIMIT = GRID * PITCH

BLOCK_OX = []
BLOCK_OY = []
_i = 0
while _i < NBLOCK:
	append(BLOCK_OX, (_i % GRID) * PITCH)
	append(BLOCK_OY, (_i // GRID) * PITCH)
	_i = _i + 1

PUMPKIN_TARGET = 25900000          # = Cactus lv6 的成本（probe7 实测）
PUMPKIN_GAIN = 80000000            # **相对增量，不是绝对值！**
								   # 绝对值目标已经连栽两次：wood 设 1e9 而开局已有 1.33B ⇒ 第 10 圈就收工；
								   # carrot 设 4e8 而开局已有 3.98e8 ⇒ 同样。两次都把"启动期"算进了平均值，
								   # 报出来 862M / 191M，而稳定段其实是 1,150M / 258M。
								   # 80M 按 ~18M/分 约 4.4 分钟 ⇒ 启动期占比降到 5% 以内。
REPORT_EVERY = 20                  # 每几轮打印一行（南瓜的"轮"很快，间隔要大一点）
FULL_EVERY = 20                    # 每多少轮强制全量复查一次（防「成熟后不会死」的假设有偏差）
STALE_LIMIT = 40                   # 连续多少轮没收到就强制全量复查
WATER_THRESHOLD = 0.9              # **已回滚（实测 0.95 是净亏）**
								   # 实测：0.95 时水库存 482 秒内从 1,117,634 掉到 1,099,336
								   # = **-38/秒**（v3 用 0.9 时几乎持平）⇒ 阈值太高等于是
								   # 「每次访问都浇水」，而浇水是**动作** ⇒ 单轮从 1.33 秒涨到 3.4 秒，
								   # 速率反而从 16.2M/分 掉到 10.1M/分。
								   # 教训：水位是"每秒衰减 1%"，门槛每抬高一点，浇水频率就翻好几倍；
								   # **浇水不是免费的**，它和收割抢同一份动作预算。
								   # **没有提到 1.0**：那会让每格每次访问都浇水，
								   # 水耗从约 19/秒 暴涨到 370/秒，把 1.13M 库存抽干。
WATER_FLOOR = 20000                # 水量下限：低于此数停止浇水。**每轮只查一次**（见 WOK），
								   # 绝不放进逐格循环 —— 那正是 wood v6 实测出的最大空转来源。
SUN_ON_SPARE = 1                   # 1 = 闲置无人机去空隙格种向日葵换电量
# ---- 肥料：只给"补种死瓜"那一步施，不给初始铺满的 49 格施 ----
# 依据：`Items.Fertilizer` = "instantly remove 2s from the plants remaining grow time"，
# 而 G 只有约 1.45 秒 < 2 秒 ⇒ **施过肥那一格当轮就熟**，补种那几代不再各等一个 G。
# 反过来，初始铺满 49 格若也施肥，消耗 = 784 格/周期 ÷ 约 2 秒 = 392/秒，而肥料收入
# 只有约 1/秒（Fertilizer 已满级，没法再升）⇒ 绝对不行。
# **风险（本版就是来量它的）**：fertilizer.md 写 "Plants grown with fertilizer will be
# infected"，而 "infected ... half of its yield is turned into Items.Weird_Substance"
# ⇒ 施肥**可能让产量腰斩**。CALIB 会同时报出单块产量与同块产出的奇怪物质，
# 若产量掉到约 75,264、奇怪物质多出约 75,264，就是确诊。
FERT_ON_REPAIR = 0                # **实测后关掉**：施肥不加速、只亏产量。
								   # 稳态 cyc_s 实测 9.24~9.83 秒（纯版 8.6~9.3）⇒ 周期没变；
								   # 但感染让单块产量从 150,528 掉到 142,848（第二轮）
								   # / 136,704（第一轮）⇒ 净亏 5~9%。
								   # 我当初从 CALIB 的"首轮 cyc_s 6.03"推出 21.8M/分是错的：
								   # 首轮不代表稳态 —— 纯版的 CALIB 也是 5.12 秒而稳态 8.9 秒。
								   # 想再验证就把这个值改回 1，但记得要拿**稳态** cyc_s 比。
FERT_FLOOR = 2000                 # 库存低于此数停止施肥（graceful 退化）
SUN_REPORT_SEC = 60

# ---- 每架无人机自己的状态（模块全局 = 每架一份，import/执行语义保证）----
MY = [0]                           # 我负责第几块
PX = []                            # 本方阵每格的 x（行主序）
PY = []
STATE = []                         # 0 = 待确认；1 = 已确认「存活且成熟」
FERT = [0]                         # 本机一共施了几次肥（只统计本机；跨机要读全局库存）
FERT_NOW = [0]                     # 本轮允不允许施肥（每轮算一次）
WOK = [1]                          # 本轮允不允许浇水（每轮算一次，见 tend_all）
DUE = []                           # 每格"下次最早值得去看"的时刻（时间戳调度，见 tend_all）
NEXT_DUE = [0]                     # 本块所有待确认格子里最早的 DUE（count_pending 顺手算出）
# ---- 阶段打点（`get_tick_count()` 免费，所以打点本身不吃 tick）----
# 用途：把"每周期 267 次动作"拆到四个阶段上，**量**出浪费在哪，而不是继续猜。
# [tend_all, count_pending, 收割, replant_block]，单位 tick；÷200 就是走了多少格。
TK = [0, 0, 0, 0]
SPIN = [0]                         # 空转等待花了多少 tick（这是嫌疑人）
# **这是本版唯一的算法改动**：原来 `STATE[i] == 0` 既表示"没长好"也表示"该补种"，
# 代码分不清，只能**每轮都重新走一遍所有未确认的格子**（含正在长的）。
# 而 `get_time()` 是**免费**的（timing.md）⇒ 补种时记下时间，没到最早成熟时刻就
# **根本不过去**，每格每代只访问一次。
# GROW_MIN 取"水量满时的生长时间"作为**下界**：预估偏小只会多跑一趟（下次会自动顺延），
# 偏大才会真的拖慢周期 ⇒ 宁可取小。实测 G 约 1.45 秒（基础约 7 秒 / 满水 x4.9）。
# ============ 时间戳调度（DUE）：已开启，但常数按**实测**重设 ============
# 背景：probe_pump 实测 —— 水位 0（1 倍速）时南瓜从播种到能收只要 **2.77 秒**，
# 按 watering.md 的 1x->5x 线性，满水时约 **0.55 秒**。而我原来的模型写的是"基础约 7 秒、
# G=1.45 秒"，错了 2.5 倍 ⇒ **周期 8.8 秒里约 7 秒根本不是等生长，是无人机自己的动作**。
# ⇒ 这条线是**动作受限**，所以"减少动作"是唯一正确的方向；而上一场我把它判为无效，
# 原因是常数用错：GROW_MIN=1.3 比真实生长(0.55)大了 2.4 倍 ⇒ 每格都被推迟一个间隔才确认，
# 还让 tend_all(0) 经常一格都不到点、直接空返回，worker 掉进空转烧轮数。
# 现在按实测取 **0.6 秒**（略高于 0.55 的下界：估小只会多跑一趟，估大才会真拖慢周期）。
GROW_MIN = 0.15                     # **按实测的生长时间重设（0.6 -> 0.15）**
								   # probe_pump v2 实测：满水（水位 1.0）时南瓜 **0.14 秒**就熟。
								   # 上一版设 0.6 是 4 倍的粗粒度 ⇒ 每格被反复复查：
								   # 打点实测 `tend_all` 每周期走 **290 格**（必需只有 49 格），
								   # 5.6 轮/周期 x 约 51 格 ≈ 286 ✓ 与实测吻合 ⇒ **白走 241 格
								   # = 48,200 tick = 7.9 秒/周期**，那就是周期里一直找不到的那 7 秒。
								   # 现在按实测调到 0.15 秒（略高于 0.14：估小只多跑一趟）。
# ---- 每架无人机自己的状态（模块全局 = 每架一份，import/执行语义保证）----
# （这两行是被我上一次切片编辑误删后补回来的：那次用 `find("\n\n")` 找注释块结尾，
#   结果跨过了后面的代码 —— **教训：一律用完整的原文锚点 + 命中次数断言，不要用位置切片**。）
TILLED = []                        # 0 = 这格还没查过地面/翻过土；1 = 已处理过
								   # 翻过之后不会变回草原 ⇒ 每格每周期只查一次
CYC = [0, 0, 0]                    # 本机 [收获次数, 本轮步数, 累计产量]（诊断用）


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


def bx(c):
	return BLOCK_OX[MY[0]] + c


def by(r):
	return BLOCK_OY[MY[0]] + r


def water_here():
	# **每格 2 次调用**（原来是 4 次：num_items / get_ground_type / get_entity_type / get_water）。
	# 水量下限改由 WOK（每轮算一次）把关，所以这里不必再调 num_items。
	# 逐格循环里的水位四连查是最大的空转来源 —— wood v6 实测：单圈 API 调用 185 -> 90，
	# 单圈耗时 2.41 -> 约 1.3 秒。这里的调用点只在「已经翻过土、且脚下有东西」时才到达，
	# 所以 get_ground_type / get_entity_type 这两个判断是多余的。
	# 水量下限那个检查也去掉：它只是安全网，而水库存 1.13M 全程稳定（实测 1,131,950 -> 1,126,427）；
	# 真的空了 use_item 也只会返回 False，不会出事。
	if WOK[0] == 0:
		return
	if get_water() < WATER_THRESHOLD:
		use_item(Items.Water)


def build_coords():
	# 本方阵每格的坐标（行主序）。**只做一次**。
	i = 0
	while i < TILES:
		append(PX, bx(i % REG_SIZE))
		append(PY, by(i // REG_SIZE))
		append(STATE, 0)
		append(TILLED, 0)
		append(DUE, 0)             # 0 = 立刻可查（首次全盘要扫一遍）
		i = i + 1


def tend_all(full):
	# **每轮只算一次的开关**：肥料够不够、允不允许浇水。
	# 这两个 num_items 原来写在逐格循环里 —— 那是 wood v6 实测出的最大空转来源
	# （单圈 API 调用 185 -> 90、耗时 2.41 -> 1.3 秒），我自己却在新加的肥料代码里又犯了一次。
	fertilize = 0
	if FERT_ON_REPAIR == 1:
		if num_items(Items.Fertilizer) > FERT_FLOOR:
			fertilize = 1
	FERT_NOW[0] = fertilize
	if num_items(Items.Water) > WATER_FLOOR:
		WOK[0] = 1
	else:
		WOK[0] = 0
	# 走一遍：full=1 时全查，否则只查待确认的格子。
	# 只查待确认的格子是这套状态机的全部价值：动作数从 ~2n/轮 降到 ~0.5n/轮，
	# 既省电（行动是耗电主因），又让轮次快得多（待确认的格子被更早复查 => 成阵更快）。
	now = get_time()
	i = 0
	while i < TILES:
		if full == 1 or STATE[i] == 0:
			if full == 0:
				# **没到最早可能成熟时刻 ⇒ 这一格根本不用走过去**（本版的核心改动）
				if now < DUE[i]:
					i = i + 1
					continue
			goto(PX[i], PY[i])
			# **必须先翻土**（实测踩过的大坑）：clear() 之后整盘是**草原**，而草原上长着草 ——
			# `get_entity_type()` 会返回 Entities.Grass 而且 `can_harvest()` 是 **True**，
			# 于是状态机会把「长着草的空地」误判成「已确认成熟的南瓜」，第 1 轮就判定整块就绪、
			# 去 harvest() 了一刀草（last_gain = 0），随后所有工人空转、整场零产出。
			if TILLED[i] == 0:
				# 地面类型一格里一个周期只查一次（翻过之后不会变回草原）
				if get_ground_type() != Grounds.Soil:
					till()
				TILLED[i] = 1
			t = get_entity_type()
			if t == None:
				plant(Entities.Pumpkin)
				STATE[i] = 0
				DUE[i] = get_time() + GROW_MIN
			elif t == Entities.Dead_Pumpkin:
				# 死瓜不能正常收，但 harvest() 会把它直接清掉
				harvest()
				plant(Entities.Pumpkin)
				# **这里是"补种"而不是"初始铺满"** ⇒ 施肥的那 2 秒正好把这一代抹掉。
				# 只在这条分支里施肥，初始铺满（走 t == None 那条）不施。
				if FERT_NOW[0] == 1:
					use_item(Items.Fertilizer)
					FERT[0] = FERT[0] + 1
				STATE[i] = 0
				DUE[i] = get_time() + GROW_MIN
			elif t == Entities.Pumpkin:
				if can_harvest():
					STATE[i] = 1
				else:
					# 还活着但没熟（或水没跟上）：排到下一个最早成熟点再看
					STATE[i] = 0
					DUE[i] = get_time() + GROW_MIN
			else:
				# **不是南瓜**（草、或上一轮留下的别的作物）⇒ 清掉重种，
				# 绝不能落进「can_harvest() 为真就算确认」那条路（那正是上面那个坑）。
				harvest()
				plant(Entities.Pumpkin)
				STATE[i] = 0
				DUE[i] = get_time() + GROW_MIN
			water_here()
		i = i + 1


def count_pending():
	# 顺手把"下一个最早可检查时刻"算出来，供 worker 用来**代替空转**
	p = 0
	nx = 0
	i = 0
	while i < TILES:
		if STATE[i] == 0:
			p = p + 1
			if nx == 0 or DUE[i] < nx:
				nx = DUE[i]
		i = i + 1
	NEXT_DUE[0] = nx
	return p


def replant_block():
	# 连锁收割一次清空整块 36 格；只补脚下那格的话其余 35 格要等下一轮才补上，
	# 而那一轮计数必然是 0 ⇒ 等于两轮才能收一次。立刻补满把周期压到一轮。
	i = 0
	while i < TILES:
		goto(PX[i], PY[i])
		# **必须先翻土**：clear() 之后整盘是草原，`get_entity_type()` 返回 Entities.Grass
		# 而不是 None ⇒ 不翻土的话这里一株都种不下去（靠紧接着的 tend_all 兜底，白慢一轮）。
		if get_ground_type() != Grounds.Soil:
			till()
		# **这一趟走位顺手把状态记全**（probe_cost 实测：get_entity_type / can_harvest
		# 各只要 **1 tick**，基本免费；而走一格要 **200 tick**）。这是本版唯一的提速点：
		# 原来这里走完 49 格却把 STATE 全部盲设为 0，导致紧接着的 tend_all(0) 又把 49 格
		# 重走一遍 —— 那一趟白走 = 49 x 200 / 6075 = **1.6 秒**，占整个周期的 18%。
		t = get_entity_type()
		if t == Entities.Pumpkin:
			if can_harvest():
				STATE[i] = 1                       # 活着且成熟 ⇒ 当场确认
			else:
				STATE[i] = 0                       # 还活着没熟 ⇒ 排下次再看
				DUE[i] = get_time() + GROW_MIN
		else:
			if t != None:
				harvest()                      # 死瓜 / 别的东西，清掉
			plant(Entities.Pumpkin)
			STATE[i] = 0
			DUE[i] = get_time() + GROW_MIN
		i = i + 1
	# **注意：这里不再把 STATE 全部盲设成 0。**
	# 上面那一趟走位已经逐格判定过了（查询免费），所以紧接着的 tend_all(0)
	# 只会去访问"确实还没确认"的那几格（约 12 格死瓜），而不是整块 49 格。
	# TILLED 也**不重置**：收割不会把土变回草原。


def worker(b, target, limit):
	# limit > 0 = **标定模式**：收到 limit 次就退出。
	# 标定必须**单独一架、不带任何别的无人机**跑 —— `num_items(Items.Pumpkin)` 是全局库存，
	# 多架同时收割时每次的差值是脏的（这条在 cactus_farm 上被实测证实过：污染倍数 = 并行块数）。
	MY[0] = b
	build_coords()
	rounds = 0
	since = 0
	harvests = 0
	while True:
		rounds = rounds + 1
		since = since + 1
		full = 0
		if rounds % FULL_EVERY == 0:
			full = 1
		if since > STALE_LIMIT:
			full = 1
		t0 = get_time()
		k = get_tick_count()
		tend_all(full)
		TK[0] = TK[0] + get_tick_count() - k
		CYC[1] = CYC[1] + 1
		k = get_tick_count()
		pend = count_pending()
		TK[1] = TK[1] + get_tick_count() - k
		if pend == 0:
			# 整块「存活且成熟」→ 从任意一格连锁收割整块，随即补满并重置状态
			goto(PX[0], PY[0])
			g0 = num_items(Items.Pumpkin)
			k = get_tick_count()
			harvest()
			TK[2] = TK[2] + get_tick_count() - k
			CYC[2] = CYC[2] + (num_items(Items.Pumpkin) - g0)
			harvests = harvests + 1
			since = 0
			k = get_tick_count()
			replant_block()
			TK[3] = TK[3] + get_tick_count() - k
			if rounds % REPORT_EVERY == 0 or limit > 0:
				print("[pump] block", b, "round", rounds,
					"harvests", harvests,
					"last_gain(污染: 约 = 并行块数 x 真值)", num_items(Items.Pumpkin) - g0,
					"cyc_s", get_time() - t0,
					"total", num_items(Items.Pumpkin),
					"water", num_items(Items.Water))
			if limit > 0:
				if harvests >= limit:
					break
			if num_items(Items.Pumpkin) >= target:
				break
		else:
			if rounds % REPORT_EVERY == 0:
				print("[pump] block", b, "round", rounds,
					"pending", pend,
					"since_harvest", since,
					"harvests", harvests,
					"total", num_items(Items.Pumpkin),
					"| tick分布 tend", TK[0], "count", TK[1],
					"harv", TK[2], "replant", TK[3],
					"| 空转", SPIN[0], "| 折算格数 tend", TK[0] / 200,
					"count", TK[1] / 200, "harv", TK[2] / 200, "replant", TK[3] / 200,
					"spin", SPIN[0] / 200)
			# **不许空转**：没活干就等到"下一个最早可检查时刻"再去干。
			# 之前这里立刻转回循环顶部，而 tend_all(0) 因为时间戳跳过瞬间返回、
			# count_pending 又非 0 ⇒ 每轮只花约 160 tick 就转一圈、38 轮/秒
			# ⇒ **把 6,075 tick/秒 的预算全烧在空转上**，周期被硬拉长。
			# `get_time()` 免费、`pass` 只要 1 tick ⇒ 这种等待每轮约 2~3 tick，便宜 50 倍。
			if NEXT_DUE[0] > 0:
				k = get_tick_count()
				while get_time() < NEXT_DUE[0]:
					pass
				SPIN[0] = SPIN[0] + get_tick_count() - k
	print("[pump] block", b, "DONE rounds", rounds, "harvests", harvests, "gained", CYC[2])
	return harvests


# ------------------------------------------------------------
# 空隙格上的向日葵（闲置无人机的副业）——与 cactus_farm 同一套做法
# ------------------------------------------------------------
def is_gap(x, y):
	# 空闲地 = 不属于任何南瓜方阵的格子。
	# GAP=1 时块之间还有缝；GAP=0 时块是紧挨着的，**没有缝** —— 空闲地只剩方阵区之外的余条
	# （32x32、REG_SIZE=6、GAP=0 时是 x/y >= 30 的 124 格）。
	if GAP > 0:
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
				goto(0, y0)
				laps = laps + 1
				# **必须能退出**：主机最后要 wait_for 全部，而这个循环本身没有终点。
				# 用共享物品栏当共同收工信号（跨机可见）。
				if num_items(Items.Pumpkin) >= target:
					print("[sun2] rows", y0, y1, "done, harv", harv, "power", num_items(Items.Power))
					break
		if get_time() - t0 > SUN_REPORT_SEC:
			t0 = get_time()
			print("[sun2] rows", y0, y1, "laps", laps, "harv", harv,
				"power", num_items(Items.Power), "pumpkin", num_items(Items.Pumpkin))
	return harv


def main():
	# **目标 = 开局库存 + 相对增量**（不是绝对值 —— 见 PUMPKIN_GAIN 那段）
	TARGET = num_items(Items.Pumpkin) + PUMPKIN_GAIN
	print("[pump] 目标 =", num_items(Items.Pumpkin), "+", PUMPKIN_GAIN, "=", TARGET,
		"（按 18M/分 约需", PUMPKIN_GAIN / 18000000, "分钟）")
	print("=== pumpkin_farm v5-async start === (v3 的异步结构 + 逐格调用微优化: water_here 4->2 次, TILLED 跳过重复地面查询, 水位门槛 0.95)")
	print("world_size", SIZE_OF_BOARD,
		"reg_size", REG_SIZE,
		"pitch", PITCH,
		"grid", GRID,
		"blocks", NBLOCK,
		"tiles_per_block", TILES,
		"target_abs", PUMPKIN_TARGET, "gain", PUMPKIN_GAIN,
		"have", num_items(Items.Pumpkin),
		"max_drones", max_drones(),
		"lv_pumpkins", num_unlocked(Unlocks.Pumpkins),
		"water", num_items(Items.Water),
		"carrot", num_items(Items.Carrot))
	if BLOCK_OX[NBLOCK - 1] + REG_SIZE > SIZE_OF_BOARD:
		print("[pump] ERROR: 布局越界，检查 REG_SIZE / GRID")
		return
	# **理论值必须按 REG_SIZE 算**：原来写死 216（= 6x6）而 REG_SIZE 早已改成 7 ⇒ 应为 294。
	# 基准错了，"产量偏低"的告警也会跟着错。
	THEORY = REG_SIZE * REG_SIZE * 6 * (2 ** (num_unlocked(Unlocks.Pumpkins) - 1))
	print("[pump] 每块理论产量 =", REG_SIZE, "x", REG_SIZE, "x 6 x 2^(lv-1) =", THEORY)
	clear()
	cap = max_drones()
	drones = []
	# ---- 开局自标定：**单机单块**跑满一次收获，量干净的单块产量 ----
	print("[pump] CALIB start: 单独一架跑一块，量干净的 per_block 产量")
	PC0 = num_items(Items.Pumpkin)
	WC0 = num_items(Items.Weird_Substance)
	FC0 = num_items(Items.Fertilizer)      # **全局库存**：FERT[0] 是每机一份，统计不到 CALIB 那架
	d = spawn_drone(worker, 0, 999999999, 1)
	if d != None:
		wait_for(d)
	PC1 = num_items(Items.Pumpkin)
	print("[pump] CALIB end: 单块干净产量 =", PC1 - PC0, "| 理论 =", THEORY)
	# ---- 感染确诊：施肥那一版如果产量腰斩、奇怪物质等量增加，就是 fertilizer.md 那条机制 ----
	print("[pump] CALIB 感染检查: 同一块产出的奇怪物质 +",
		num_items(Items.Weird_Substance) - WC0,
		"| 本次 CALIB 消耗肥料", FC0 - num_items(Items.Fertilizer),
		"| 施肥已", FERT_ON_REPAIR, "(1=开)")
	if PC1 - PC0 < THEORY:
		print("[pump] CALIB 警告: 产量低于理论值 —— 很可能就是施肥导致的感染，",
		"把 FERT_ON_REPAIR 改成 0 再跑一次对比")
	if PC1 - PC0 <= 0:
		# **别把这个当成小故障**：产量为 0 就是上面那个「草原上的草被当成可收」的坑，
		# 继续跑下去 16 架会全部空转（实测跑了一分多钟、pumpkin 一点没动）。
		print("[pump] *** CALIB 产量为 0 —— 停下来查 tend_all 的翻土那一步，别继续跑 ***")
		return
	# ---- 正式铺开 ----
	i = 0
	while i < NBLOCK and i < cap - 1:
		d = spawn_drone(worker, i, TARGET, 0)
		if d != None:
			append(drones, d)
		i = i + 1
	print("[pump] launched", len(drones), "pumpkin workers on", NBLOCK, "blocks")
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
			d = spawn_drone(sun_worker, y0, y1, TARGET)
			if d != None:
				append(drones, d)
			s = s + 1
		print("[pump] +", nsun, "sunflower workers on the gap tiles")
	P0 = num_items(Items.Pumpkin)
	T0 = get_time()
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	P1 = num_items(Items.Pumpkin)
	DT = get_time() - T0
	RATE = 0
	if DT > 0:
		RATE = (P1 - P0) / DT
	print("=== pumpkin_farm end ===",
		"pumpkin", P1,
		"gained", P1 - P0,
		"elapsed_s", DT,
		"pumpkin_per_s", RATE,
		"pumpkin_per_min", RATE * 60)


main()
