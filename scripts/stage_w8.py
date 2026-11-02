# ============================================================
# stage_w8.py —— 档位 W = 8x8（Expand lv5）· **第一个带向日葵带的档**
#
# 地块规划（本档自带，唯一事实来源。8x8 = 64 格）：
#   +---+---+---+---+
#   | 南瓜方块 4x4  | 向日葵带 4x4 |   y=0..3：x=0..3 方块、x=4..7 向日葵
#   +---+---+---+---+
#   | 轮作 8 列 x 4 行（32 格）    |   y=4..7：x=0..7 全部轮作
#   +---+---+---+---+
#   16 + 16 + 32 = 64 ✓（util.check_lands() 逐格验）
#
# 这一档的两个新东西：
#   * **方块边长 4**（block_size = min(ws//2, 6) = 4）⇒ 一刀 64 个南瓜（4^3）
#   * **向日葵带 16 格**：场上 >= 10 株才有 8 倍 power，而 power = 全局 2 倍速
#     （真机到 world 8 用了 2991 秒，2 倍速等于把这 50 分钟砍掉一半）
#
# 轮作配比仍按 1:1:1（见 stage_w6 的推导：种一株胡萝卜要 wood 1 + hay 1）：
#   8 列 x 4 行 = 32 格，拆成 **2 列胡萝卜 / 3 列草 / 3 列木**
#   （胡萝卜 8 格是这一档的吞吐上限；草与木各 12 格，够它消耗且有富余）
#
# 下一级 Expand（lv5->6）要 **pumpkin 8000** ⇒ 本档就是攒它（一刀 64 个 ⇒ 约 125 刀；
#   南瓜等级每升一级翻倍，buy(1) 会自己买，所以实际刀数会更少 ✓）
# ============================================================

SIDE = 8
SHAPE = "square"
VERSION = 1
BLOCK = 4              # 方块边长，必须与 block_farm.block_size() 同口径（enter 里会核对）
SUN_W = 4              # 向日葵带：x=4..7
SUN_H = 4              # y=0..3
MAZE = 4               # 迷宫区 4x4 = 16 格（金币/物质 = 4）：让金币线从 w8 就开跑 ✓
WORKER_CYCLES = 12     # 迷宫副机一个班次建几座
ROT_CYCLES = 40        # 轮作副机一个班次扫几遍（20 → 40：单列片每遍只 4 格，
                       #   拉长班次才能覆盖一个 wave（~250~500s），否则副机死后区域空窗 ✗）
SUN_CYCLES = 24
# ⚠ 2026-11-02 利用率优化（Lead：cap=4 时 49.4%、cap=8 更低 ✗）：
#   **旧版 w8 的 assign() 只派 1 个任务（迷宫）** ⇒ cap=4 天花板 50%、cap=8 只有 25% ✗
#   而 sun / pumpkin / 轮作 **全由主机自己干** ⇒ 副机名额空着、主机累死 ✗✗
#   ⇒ 现在拆成 **7 个独立副机任务**（见 assign）：maze / pumpkin / rot0..3 / sun
#     区域全部取自 lands() 里已有的 4 块地（两两不相交 ✓，不改地块分配 ✓）
#   ⚠ 每架副机的班次长度必须 < full_run 的 ACTIVE_TTL（非迷宫 200 秒 / 迷宫 620 秒），
#     否则「无人机还活着、标记却被清掉」⇒ 同区会被派第二架（R5 违规 ✗）
#     · pumpkin: PK_CYCLES=2 ⇒ 每轮最长 45s 等待 ⇒ 班次 ≤ ~120s < 200 ✓
#     · sun:     SUN_CYCLES=24，但 sun_simple_worker 内部有 SUN_SHIFT_SEC=200s 硬上限 ✓
#     · rot:     40 遍 × 4 格 ≈ 60~200s < 620（cycles≥6 ⇒ TTL 走迷宫档）✓
#     · maze:    MZ_SHIFT_SEC=520s < 620 ✓（原样不动）
PK_CYCLES = 2          # 南瓜副机一个班次几轮
ROT_SLICES = 4         # farm_low 切几片（每片 1 列 x 4 行 = 4 格，两两不相交 ✓）
                       #   farm_low 共 4 列 ⇒ 4 片；任务数 1 → 7 ⇒ cap=8 也能飞满 ✓
HAY_FLOOR = 40         # 草见底就把一条胡萝卜列借给它（策略常数）
WOOD_FLOOR = 40
CARROT_WANT = 60       # 胡萝卜低于这个数就把一条木列借给它（南瓜方块的种子钱）
import util
import budget
import jobs

ROLES_TOP = ["wood", "wood", "wood", "wood"]      # x=0..3 的 y=4..7（4 列）
ROLES_BOT = ["carrot", "carrot", "hay", "hay"]    # x=4..7 的 y=4..7（4 列）


def enter():
	# 配比机械自检（进档即验）：**草格 >= 胡萝卜格**（每株胡萝卜要 1 草 + 1 木）
	a0 = allocation()
	if util.check_ratio("w8", [("farm_low", SIDE - BLOCK, a0)]) == 0:
		return 0
	side = jobs.pumpkin_block_side()
	if side != BLOCK:
		print("[s8] !! 方块边长口径不一致：block_farm 给", side, "，本档规划", BLOCK)
		return 0
	print("[s8] 档位 8x8 | 规划：方块(0,0) 4x4 | 向日葵带 x=4..7,y=0..3（16 格）",
		"| 轮作 32 格 = 2 列胡萝卜 / 3 列草 / 3 列木 | 下一级 Expand 要 pumpkin 8000")
	return 1


def lands():
	n = BLOCK
	return [("block", 0, 0, n, n),
		("sun", n, 0, SUN_W, SUN_H),
		("maze", 0, n, MAZE, MAZE),
		("farm_low", MAZE, n, SIDE - MAZE, SIDE - n)]


def verify_lands():
	ws = get_world_size()
	if ws != SIDE:
		print("[s8] !! 本档只服务 world", SIDE, "，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	print("[s8] 地块自检通过：方块", BLOCK * BLOCK, "格 + 向日葵", SUN_W * SUN_H,
		"格 + 轮作", ws * ws - BLOCK * BLOCK - SUN_W * SUN_H, "格 =", ws * ws, "格")
	return 1


def allocation():
	# ⚠⚠ 真机教训（2026-10-08）：这块地**只剩 4 列**（另一半已划给迷宫区），
	#   而旧的 8 项配比表还在文件里被重复定义、最后生效 ✗ ⇒ 这块地拿到的是
	#   上表前四项 ['hay','hay','hay','wood'] ⇒ **一格胡萝卜都没有** ✗✗
	#   真机日志实录：`矩形里 胡萝卜 0 草 12 木 4 | 库存 carrot 0` ✓✓
	#   ⇒ 4 列必须**三样齐备**（草和木是胡萝卜的原料，少一样整条线断 ✓）
	r = ["carrot", "hay", "wood", "hay"]
	if num_unlocked(Unlocks.Plant) <= 0:
		return ["hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Carrots) <= 0:
		return ["hay", "hay", "wood", "hay"]
	# 借列纪律：**草/木之间互借，绝不动胡萝卜列**（否则胡萝卜线自断 ✓）
	if num_items(Items.Hay) < HAY_FLOOR:
		r[2] = "hay"
	if num_items(Items.Wood) < WOOD_FLOOR:
		r[1] = "wood"
	# ⚠⚠ **不许把草/木列借给胡萝卜**（真机停机实录 2026-10-08）：
	#   `[ut] !! 配比违反不变量：草 28 < 胡萝卜 32` ⇒ 档位自检不通过 ⇒ 停机 ✗
	#   固定表本身是合规的，是这条**运行时调整**把不变量破坏了 ✗
	#   ⇒ 配比是**硬约束**，运行时只允许在草/木之间互借（草>=胡萝卜恒成立 ✓）；
	#     胡萝卜不够时由南瓜方块的补种底线去等（block_farm 的 floor ✓），不是靠改配比 ✓
	return r


ACTIVE = []              # 每个任务是否有无人机在飞（full_run 每轮填 ✓）


def set_active(mask):
	# 接收 full_run 的"谁在飞"（列表按值拷贝 ✓ 跨机安全 ✓）
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	i = 0
	while i < len(mask):
		append(ACTIVE, mask[i])
		i = i + 1


def busy_ok(idx):
	# 主机要不要自己干第 idx 个任务：**没人做我才接手** ✓
	#   真机缺陷（2026-10-08）：旧版用「有副机在飞 ⇒ 让位」的乐观假设 ✗
	#   ⇒ 副机实际没在飞时那块地**两不管** ✓（实测 farm_b 88 格全草 ✗）
	if idx < len(ACTIVE):
		if ACTIVE[idx] == 1:
			return 0
	return 1


def assign(drones):
	# 【名单顺序 = 优先级】full_run 从轮换起点开始按顺序放飞，名额用完就停。
	#   2026-11-02 扩容：旧版只有 1 个迷宫任务 ⇒ cap=4 天花板 50%、cap=8 只有 25% ✗
	#   现在 **7 个任务**，**区域全部两两不相交**（都在 lands() 已有的 4 块地里 ✓）：
	#     maze   @(0,4) 4x4   = "maze" 区
	#     pumpkin@(0,0) 4x4   = "block" 区（block_farm 的固定方块）
	#     rot0   @(4,4) 1x4   = "farm_low" 第 1 列
	#     rot1   @(5,4) 1x4   = "farm_low" 第 2 列
	#     rot2   @(6,4) 1x4   = "farm_low" 第 3 列
	#     rot3   @(7,4) 1x4   = "farm_low" 第 4 列
	#     sun    @(4,0) 4x4   = "sun" 区
	#   ⇒ w8 在 cap=2/4/8/16 下可派任务数 = 7，可放飞 = min(7, cap-1) = 1/3/7/7 ✓
	if drones < 2:
		return []
	js = []
	# ① 迷宫（金币线）：保持原优先级第 1 ✓
	if num_unlocked(Unlocks.Mazes) > 0:
		append(js, {"name": "maze", "entry": jobs.maze_worker,
			"x0": 0, "y0": BLOCK, "w": MAZE, "h": MAZE,
			"cycles": WORKER_CYCLES, "roles": 0})
	# ② 南瓜方块（Expand 的货币）：旧版一直是主机干 ⇒ 现在给副机
	if num_unlocked(Unlocks.Pumpkins) > 0:
		append(js, {"name": "pumpkin", "entry": jobs.pumpkin_worker,
			"x0": 0, "y0": 0, "w": BLOCK, "h": BLOCK,
			"cycles": PK_CYCLES, "roles": 0})
	# ③ 轮作：farm_low 按列切 ROT_SLICES 片（每片 1 列，角色表内容不变，只是按列切开 ✓）
	a = allocation()
	sw = (SIDE - MAZE) // ROT_SLICES
	s = 0
	while s < ROT_SLICES:
		rr = []
		k = 0
		while k < sw:
			append(rr, a[s * sw + k])
			k = k + 1
		append(js, {"name": "rot" + str(s), "entry": jobs.rotation_worker,
			"x0": MAZE + s * sw, "y0": BLOCK, "w": sw, "h": SIDE - BLOCK,
			"cycles": ROT_CYCLES, "roles": rr})
		s = s + 1
	# ④ 向日葵带（power = 全局 2 倍速）：副机版会自己 till + 按生长节奏配速 ✓
	if num_unlocked(Unlocks.Sunflowers) > 0:
		append(js, {"name": "sun", "entry": jobs.sun_simple_worker,
			"x0": BLOCK, "y0": 0, "w": SUN_W, "h": SUN_H,
			"cycles": SUN_CYCLES, "roles": 0})
	return js


S8_DIAG = [0]
RECT = [4, 4, 4, 4]        # 本档唯一的轮作矩形 = (MAZE, BLOCK, SIDE-MAZE, SIDE-BLOCK)


def s8_report(a):
	# 诊断（真机症状：hay/wood 堆积而 carrot 恒 0 ✗）：本档配比 + **矩形里实际长着什么**
	S8_DIAG[0] = S8_DIAG[0] + 1
	if S8_DIAG[0] % 10 != 1:
		return
	i = 0
	n_carrot = 0
	n_hay = 0
	n_wood = 0
	n_other = 0
	while i < 4:
		j = 0
		while j < 4:
			util.go_to(RECT[0] + i, RECT[1] + j)
			e = get_entity_type()
			if e == Entities.Carrot:
				n_carrot = n_carrot + 1
			elif e == Entities.Tree or e == Entities.Bush:
				n_wood = n_wood + 1
			elif e == Entities.Grass or e == None:
				n_hay = n_hay + 1
			else:
				n_other = n_other + 1
			j = j + 1
		i = i + 1
	print("[s8] 第", S8_DIAG[0], "轮 | 配比", a,
		"| 矩形里 胡萝卜", n_carrot, "草", n_hay, "木", n_wood, "其它", n_other,
		"| 库存 hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot), "pumpkin", num_items(Items.Pumpkin),
		"| 付得起胡萝卜吗", util.can_afford(Entities.Carrot))


def run():
	a = allocation()
	i = 0
	while i < 4:
		ROLES_BOT[i] = a[i]
		i = i + 1
	s8_report(a)
	# ---- 任务下标映射：**必须与 assign() 的 append 顺序严格一致** ----
	#   顺序：maze → pumpkin → rot0 → rot1 → sun（见 assign 的注释）
	ni = 0
	maze_i = -1
	if num_unlocked(Unlocks.Mazes) > 0:
		maze_i = ni
		ni = ni + 1
	pk_i = -1
	if num_unlocked(Unlocks.Pumpkins) > 0:
		pk_i = ni
		ni = ni + 1
	rot0_i = ni
	ni = ni + ROT_SLICES
	sun_i = -1
	if num_unlocked(Unlocks.Sunflowers) > 0:
		sun_i = ni
		ni = ni + 1
	# 1) 轮作：**按片判断** —— 只有该片没有副机时主机才扫那 1 列（R5：一区一 owner ✓）
	#   ⚠ 旧版无条件整片扫 ⇒ 副机在飞时会与副机抢地 ✗
	sw = (SIDE - MAZE) // ROT_SLICES
	s = 0
	while s < ROT_SLICES:
		if busy_ok(rot0_i + s) == 1:
			rr = []
			k = 0
			while k < sw:
				append(rr, a[s * sw + k])
				k = k + 1
			jobs.sweep_columns(MAZE + s * sw, BLOCK, sw, SIDE - BLOCK, rr)
		s = s + 1
	# 2) 向日葵带：有太阳副机且它在飞 ⇒ 那一区归副机（R5）
	if sun_i < 0:
		# 没有太阳任务（未解锁）⇒ 老行为：主机自己割（sun_shift 内部会判解锁 ✓）
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
	else:
		if busy_ok(sun_i) == 1:
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
			jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
	# 3) 南瓜方块：有副机时归副机；没有/不在飞时主机自己干
	if pk_i < 0:
		jobs.pumpkin_shift(1, budget.pumpkin_keep())
	else:
		if busy_ok(pk_i) == 1:
			jobs.pumpkin_shift(1, budget.pumpkin_keep())
	# 4) 迷宫（金币）：有副机时归副机（R5），独自在飞时自己跑 ✓
	if util.drone_count() <= 1:
		jobs.maze_shift(0, BLOCK, MAZE, 1)
	util.go_to(0, 0)
	return "w8"
