# ============================================================
# stage_w12.py —— 档位 W = 12x12（Expand lv6）· **完全复位榜的主战场**
#
# 地块规划（本档自带，唯一事实来源。12x12 = 144 格）：
#   +---+---+---+---+---+---+---+---+---+---+---+---+
#   |               |        向日葵带 6x3 (18)      |  y=0..2
#   |  南瓜方块      +-------------------------------+
#   |   6x6 (36)    |        轮作 farm_top 6x9 (54)  |  y=3..8
#   +---+---+---+---+---+---+---+---+---+---+---+---+
#   |  迷宫区 6x6 (36)  |                           |  y=6..11
#   +---+---+---+---+---+---+---+---+---+---+---+---+
#   36 + 18 + 36 + 54 = 144 ✓（util.check_lands() 逐格验）
#   ⚠ 迷宫区与 farm_top 的 y 区间**不重叠**（迷宫 y=6..11，farm_top y=3..11 但 x=6..11）✓
#     迷宫在 x=0..5、farm_top 在 x=6..11 ⇒ 两列互不相干 ✓
#
# 这一版新增（用户 2026-10-07 报的两个问题）：
#   * **向日葵副机**：w12 电量实测不够（一轮 3 刀 = 24 点，主机一轮约 700 个行动要烧 23 点，
#     刚好差一点）⇒ 给带子配一架专职副机，主机就不用每轮花 200+ 个行动去扫带子 ✓
#   * **迷宫区 6x6**：原先 w12 根本没有迷宫 ⇒ 金币要到 w16 才开始产 ✗
#     现在从轮作里划出 36 格 ⇒ 金币线提前三个档位启动 ✓（金币/物质 = 6）
#   ⚠ 迷宫自带「复用」（每座连吃 30 刀，见 jobs.MZ_REUSE_MAX）—— 文档说明复用不给更多金币，
#     但省掉拆+建+重建图的整轮开销，实测金币产率约 4 倍 ✓
# ============================================================

SIDE = 12
MAZE = 6               # 迷宫区 6x6 = 36 格（金币/物质 = 6）
WORKER_CYCLES = 12     # 迷宫副机一个班次建几座
ROT_CYCLES = 40        # 轮作副机一个班次扫几遍
#   2026-11-02：20 → 40。切片 1 列 x 9 格，一遍只 9 格 ⇒ 20 遍的班次只有 ~30~90s，
#   而一个 wave（sun+maze 班次）约 300~500s ⇒ 副机死后整片空窗 ✗
#   40 遍 ≈ 60~180s（仍 < ACTIVE_TTL_MAZE 620s ✓ 不会"还活着被重派"）✓
SUN_CYCLES = 24        # 向日葵副机一个班次割几刀
ROT_MAX = 6            # 轮作最多切几片
# ⚠ 2026-11-02 利用率优化（Lead：cap=8 时 30.6% ✗）：
#   旧值 4 ⇒ cap=8 时任务数 = 1(sun+maze) + 4 = 5 ⇒ 可放飞 min(5, 7) = 5
#   ⇒ 最多 1+5=6/8 架在飞（天花板 75%，实测 30.6%）✗
#   farm_top 正好 **6 列** ⇒ 把上限提到 6：每片 1 列 x 9 格，区域两两不相交 ✓
#   ⇒ cap=8 时任务数 7、可放飞 7 ⇒ 天花板 100% ✓
#   ⚠ 每片班次 = ROT_CYCLES(20) x 9 格 ≈ 60~150s < ACTIVE_TTL_MAZE 620s ✓
#     （cycles>=6 ⇒ full_run 按迷宫档 620s 回收，不会出现「还活着却重派」✗）
SHAPE = "square"
VERSION = 2
BLOCK = 6              # 方块边长，必须与 block_farm.block_size() 同口径（enter 里核对）
SUN_W = 6
SUN_H = 3
HAY_FLOOR = 60         # 草见底 ⇒ 从木列借（绝不动胡萝卜列，见 stage_w8 的教训）
WOOD_FLOOR = 60
CARROT_WANT = 120      # 胡萝卜低于这个数、且草木都宽裕 ⇒ 多给一列胡萝卜
import util
import budget
import jobs
HANDED = [0]           # 位掩码：1=迷宫 2=向日葵 4=南瓜 8=仙人掌（assign 里登记）


def handed(name):
	# 游戏语言**不支持 dict.get()**（真机报错：Error: get 从未被定义 ✗）
	#   ⇒ 一律用显式分支，不要依赖任何字典方法 ✓
	if name == "maze":
		b = 1
	elif name == "sun":
		b = 2
	elif name == "pumpkin":
		b = 4
	elif name == "cactus":
		b = 8
	elif name == "rot":
		b = 16
	else:
		b = 0
	if b == 0:
		return 0
	if HANDED[0] // b % 2 == 1:
		return 1
	return 0


# farm_top = x=6..11, y=3..11（6 列 x 9 格 = 54）⇒ 草为主（每株胡萝卜要 1 草 ✓）
# 不变量 草 27 >= 胡萝卜 18 ✓（util.check_ratio 会验 ✓）
ROLES_TOP = ["carrot", "carrot", "hay", "hay", "hay", "wood"]

def enter():
	a0 = allocation()
	if util.check_ratio("w12", [("farm_top", SIDE - SUN_H, a0)]) == 0:
		return 0
	side = jobs.pumpkin_block_side()
	if side != BLOCK:
		print("[s12] !! 方块边长口径不一致：block_farm 给", side, "，本档规划", BLOCK)
		return 0
	print("[s12] 档位 12x12 | 方块(0,0) 6x6（一刀 216 个，满倍率）",
		"| 向日葵带 x=6..11,y=0..2（18 株）| 迷宫区 x=0..5,y=6..11（6x6）",
		"| 轮作 54 格 = 每样 18 格 | 副机：向日葵优先、其次迷宫、再切轮作")
	return 1


def lands():
	return [("block", 0, 0, BLOCK, BLOCK),
		("sun", BLOCK, 0, SUN_W, SUN_H),
		("maze", 0, BLOCK, MAZE, MAZE),
		("farm_top", BLOCK, SUN_H, SIDE - BLOCK, SIDE - SUN_H)]


def verify_lands():
	ws = get_world_size()
	if ws != SIDE:
		print("[s12] !! 本档只服务 world", SIDE, "，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	print("[s12] 地块自检通过：方块", BLOCK * BLOCK, "格 + 向日葵", SUN_W * SUN_H,
		"格 + 迷宫", MAZE * MAZE, "格 + 轮作",
		ws * ws - BLOCK * BLOCK - SUN_W * SUN_H - MAZE * MAZE, "格 =", ws * ws, "格")
	return 1


ROT_TURN = [0]         # 轮作切片起点轮换（真机实测 rot0:21 / rot1:1 ✗ ⇒ 要轮流当第一 ✓）

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


def rot_base():
	# 轮作任务在名单里的**起始下标**：0 号是 sun+maze（或 maze）——两者最多出现一个
	#   ⇒ 只要太阳/迷宫任一解锁，轮作就从 1 开始；都没解锁才从 0 开始 ✓
	if num_unlocked(Unlocks.Sunflowers) > 0:
		return 1
	if num_unlocked(Unlocks.Mazes) > 0:
		return 1
	return 0


def rot_any_active():
	# 任一轮作切片在飞 ⇒ 主机**不许**碰 farm_top（R5：一区一 owner ✓）
	# ⚠ 旧写法 `busy_ok(1)` 只查了第 1 片 ⇒ 其它片在飞时主机会整片扫、与副机抢地 ✗✗
	#   切片上限提到 6 之后这个缺口必须堵上 ✓
	i = rot_base()
	while i < len(ACTIVE):
		if ACTIVE[i] == 1:
			return 1
		i = i + 1
	return 0


def assign(drones):
	HANDED[0] = 0
	# 【顺序即优先级】调度器按列表顺序放飞，名额用完就停 ⇒ 电量是实测瓶颈，向日葵排第一 ✓
	js = []
	if drones < 2:
		return js
	# ⚠ w12 只有 **1 个副机位**（2 架 = 主机 + 1）⇒ 名单 [sun, maze] 会被 sun 占满：
	#   真机实测 `sun: 97 次 / maze: 12 次`（迷宫只跑到 11% 的时间）✗✗
	#   ⇒ 改成一个名额做**组合班次**（每轮割太阳 + 每 MAZE_EVERY 轮建一座迷宫 ✓）
	#   roles 里带太阳带坐标（统一契约 7 参；参数按值拷贝 ⇒ 跨机安全 ✓）
	if num_unlocked(Unlocks.Sunflowers) > 0:
		append(js, {"name": "sun+maze", "entry": jobs.sun_maze_worker,
			"x0": 0, "y0": BLOCK, "w": MAZE, "h": MAZE,
			"cycles": SUN_CYCLES, "roles": [BLOCK, 0, SUN_W, SUN_H]})
		HANDED[0] = HANDED[0] + 3
	elif num_unlocked(Unlocks.Mazes) > 0:
		append(js, {"name": "maze", "entry": jobs.maze_worker,
			"x0": 0, "y0": BLOCK, "w": MAZE, "h": MAZE,
			"cycles": WORKER_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 1
	n = drones - 2
	if n > ROT_MAX:
		n = ROT_MAX
	cols = SIDE - BLOCK                  # farm_top 的列数 = 6
	if n > cols:
		n = cols
	if n < 1:
		return js
	per = cols // n
	# **轮换起点**：否则永远从 rot0 开始、后面的切片饿死 ✗（实测 rot0:21 / rot1:1 ✓）
	start = ROT_TURN[0] % n
	ROT_TURN[0] = ROT_TURN[0] + 1
	seq = 0
	while seq < n:
		i = (start + seq) % n
		x0 = BLOCK + i * per
		w = per
		if i == n - 1:
			w = cols - i * per
		rr = []
		k = i * per
		while k < i * per + w:
			# 越界钳位（同 w16/w22：真机实录 `索引 10 超出范围` ✗）⇒ 默认填 hay ✓
			if k < len(ROLES_TOP):
				append(rr, ROLES_TOP[k])
			else:
				append(rr, "hay")
			k = k + 1
		append(js, {"name": "rot" + str(i), "entry": jobs.rotation_worker,
			"x0": x0, "y0": SUN_H, "w": w, "h": SIDE - SUN_H,
			"cycles": ROT_CYCLES, "roles": rr})
		HANDED[0] = HANDED[0] + 16
		seq = seq + 1
	return js


def allocation():
	# 6 列 x 9 格 = 54 ⇒ 每样两列 = 各 18 格（1:1:1 ✓，可持续轮作口径）
	# 调整方向与 stage_w8 同一条教训：**草/木见底时在草与木之间互借，绝不动胡萝卜列**
	a = ["carrot", "carrot", "hay", "hay", "hay", "wood"]
	if num_unlocked(Unlocks.Plant) <= 0:
		return ["hay", "hay", "hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Carrots) <= 0:
		return ["wood", "hay", "wood", "hay", "wood", "hay"]
	if num_items(Items.Hay) < HAY_FLOOR:
		a[4] = "hay"                 # 木 → 草
	if num_items(Items.Wood) < WOOD_FLOOR:
		a[2] = "wood"                # 草 → 木
	# ⚠⚠ **不许把草/木列借给胡萝卜**（真机停机实录 2026-10-08）：
	#   `[ut] !! 配比违反不变量：草 28 < 胡萝卜 32` ⇒ 档位自检不通过 ⇒ 停机 ✗
	#   固定表本身是合规的，是这条**运行时调整**把不变量破坏了 ✗
	#   ⇒ 配比是**硬约束**，运行时只允许在草/木之间互借（草>=胡萝卜恒成立 ✓）；
	#     胡萝卜不够时由南瓜方块的补种底线去等（block_farm 的 floor ✓），不是靠改配比 ✓
	return a


S12_DIAG = [0]


def s12_report(a):
	# 诊断（真机症状：`harv` 四次读数不变、hay 3 / carrot 0 ⇒ 全场卡死 ✗）
	S12_DIAG[0] = S12_DIAG[0] + 1
	if S12_DIAG[0] % 10 != 1:
		return
	i = 0
	n_carrot = 0
	n_hay = 0
	n_wood = 0
	n_other = 0
	while i < 6:
		j = 0
		while j < 9:
			util.go_to(BLOCK + i, SUN_H + j)
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
	print("[s12] 第", S12_DIAG[0], "轮 | 配比", a,
		"| 轮作里 胡萝卜", n_carrot, "草", n_hay, "木", n_wood, "其它", n_other,
		"| 库存 hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot), "pumpkin", num_items(Items.Pumpkin),
		"gold", num_items(Items.Gold), "| 累计收割", jobs.HARVEST[0])


def run():
	# 【独占相】恐龙跑：整场归主机（尾巴会占满棋盘并挡住副机）
	if util.drone_count() <= 1:
		if jobs.dino_ready() == 1:
			jobs.dino_run(get_world_size())
			util.go_to(0, 0)
			return "w12"
	a = allocation()
	i = 0
	while i < 6:
		ROLES_TOP[i] = a[i]
		i = i + 1
	s12_report(a)
	# 1) 轮作（先干活：胡萝卜要先产出，南瓜与向日葵都要种子钱）
	# ⚠ 2026-11-02：**任一轮作片在飞 ⇒ 主机不扫 farm_top**（R5 一区一 owner）
	#   旧写法 `busy_ok(1) or hay < HAY_FLOOR` 只查第 1 片 ⇒ 其它片在飞时主机会整片扫
	#   ⇒ 与副机抢地（违反 R5）✗。切片提到 6 片后必须用 any() 语义 ✓
	#   （草见底时的"紧急覆盖"不再由主机做：由 rot 副机的 work_hay_tile 自愈 + hay 保留线兜底 ✓）
	if rot_any_active() == 0:
		jobs.sweep_columns(BLOCK, SUN_H, SIDE - BLOCK, SIDE - SUN_H, ROLES_TOP)
	# 2) 向日葵带：主机独自在飞时多割几刀（有副机时那一区归副机 —— R5 一块地一个 owner）
	if busy_ok(0):
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
		jobs.sun_shift(BLOCK, 0, SUN_W, SUN_H)
	# 3) 南瓜方块 6x6（一刀 216 个）
	if busy_ok(9):        # 南瓜不在 w12 名单里 ⇒ 永远归主机 ✓
		if num_unlocked(Unlocks.Pumpkins) > 0:
			jobs.pumpkin_shift(1, budget.pumpkin_keep())
	# 4) 迷宫（有副机时归副机）
	if busy_ok(0):
		jobs.maze_shift(0, BLOCK, MAZE, 1)
	util.go_to(0, 0)
	return "w12"
