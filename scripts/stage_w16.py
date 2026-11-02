# ============================================================
# stage_w16.py —— 档位 W = 16x16（Expand lv7）· 末档（22x22 / 32x32 本期不做）
#
# 地块规划（本档自带，唯一事实来源。16x16 = 256 格）：
#   +---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+
#   | 南瓜(0,0)6x6 | 迷宫0(6,0)8x8      | 迷宫1(6,8)8x8     | 向日葵(14,0)2x16 |  见 lands()
#   +---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+
#   | 仙人掌(0,6)6x6             | 轮作 farm_a(0,12)6x4        |                |
#   +---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+---+
#   36 + 64 + 64 + 32 + 36 + 24 = 256 ✓（util.check_lands() 逐格验）
#
# 三个「第一次」：
#   * **迷宫区**：docs/game/unlocks/mazes.md 说金币/物质 = 迷宫边长 ⇒ 8x8 区 = 8 金币/物质。
#     （满场 16x16 能给 16，但会把整盘推平、农场得重铺 ⇒ 先留专区，满场是后面的优化）
#   * **两座迷宫**（maze0/maze1）：每座有自己的宝藏 ⇒ 真并行 ✓（maze_gold2.py 的结论）
#   * 轮作只剩 farm_a 24 格（farm_b 已改成 maze1）⇒ 角色表按列 6 项
#
# ⚠⚠ 2026-11-01 真机 bug 修复：轮作切片**必须**切在 farm_a 上！
#   旧版切片指向 (6,8,8,8) = 现在的 maze1 ⇒ ①轮作副机被迷宫困住后 harvest 树篱
#   （源码 FarmObject.Harvestable=>true）⇒ 整座迷宫被抹掉 ✗②主机 sweep 被 maze0 挡住
#   （util.go_to 旧版无界）⇒ 主机永久卡死 ✗✗（同时 util.go_to 已改成有界 ✓）
# ============================================================

SIDE = 16
SHAPE = "square"
VERSION = 1
BLOCK = 6              # 方块边长，必须与 block_farm.block_size() 同口径（enter 里核对）
MAZE = 8               # 迷宫区边长（8x8 = 64 格）
SUN_W = 2              # 向日葵带：x=14..15
SUN_H = 16             # y=0..15（整条右带；凑满 32 格也顺便把右下角补上）
HAY_FLOOR = 60
WOOD_FLOOR = 60
CARROT_WANT = 150
CACTUS = 6             # 仙人掌方块 6x6 = 36 格（用户报「w16 缺仙人掌产能」）
PK_CYCLES = 3          # 南瓜副机一个班次几轮（每轮最长 45 秒等待）
CZ_CYCLES = 2          # 仙人掌副机一个班次几刀
SUN_CYCLES = 24        # 每次收割 8 点 = 240 行动的 2 倍速；16 架一起烧 ⇒ 必须多割         # 向日葵副机一个班次割几刀（power 全场共享 ⇒ 副机越多越要供）
WORKER_CYCLES = 12     # 迷宫副机一个班次建几座（策略常数：要小到让主机有机会采购）
ROT_CYCLES = 20        # 轮作副机一个班次扫几遍
ROT_MAX = 12           # 轮作最多切几片（farm_a 只有 6 列 ⇒ 实际会被 cols 钳到 <= 6）✓
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


# 轮作区只剩 farm_a = (0,12) 6 列 x 4 行 = 24 格：草 4 列(16) / 胡萝卜 1 列(4) / 木 1 列(4)
#   不变量 草 16 >= 胡萝卜 4 ✓（util.check_ratio 机械验 ✓）
ROLES_A = ["hay", "hay", "hay", "hay", "carrot", "wood"]
# ⚠ ROLES_B 已**没有地主**（原来的 farm_b (6,8,8,8) 改成了 maze1）⇒ 只为 allocation() 签名兼容保留
ROLES_B = ["hay", "hay", "hay", "hay", "hay", "hay", "carrot", "wood"]

def enter():
	a0, b0 = allocation()
	# ⚠⚠ 轮作区**只剩 farm_a (0,12,6,4)**：farm_b (6,8,8,8) 已经改成 maze1 ⇒ 不能算进配比 ✓
	#   真机 bug（2026-11-01）：旧配比表里还挂着 farm_b 的 8 列角色 ⇒ 轮作切片被派到 maze1 里，
	#   轮作副机的 work_tile 对树篱 can_harvest() 返回 true ⇒ harvest() = RemoveMaze ⇒ maze1 秒毁 ✗
	if util.check_ratio("w16", [("farm_a", SIDE - BLOCK - CACTUS, a0)]) == 0:
		return 0
	side = jobs.pumpkin_block_side()
	if side != BLOCK:
		print("[s16] !! 方块边长口径不一致：block_farm 给", side, "，本档规划", BLOCK)
		return 0
	print("[s16] 档位 16x16 | 方块(0,0)6x6 | 迷宫0(6,0)8x8 | 迷宫1(6,8)8x8",
		"| 向日葵带 x=14..15 全高 32 格 | 仙人掌(0,6)6x6 | 轮作 farm_a(0,12)6x4=24 格")
	return 1


def lands():
	# 铺满校验（mock 抓过一次洞：原来 x=0..5 的 y=6..7 与 x=14..15 的 y=12..15 没被分到）
	# ② 两座 8x8 迷宫（依据 maze_gold2.py：8x8 只有 49 面墙 ⇒ 复用会拆到全开 ⇒ 越刷越顺 ✓）
	return [("block", 0, 0, BLOCK, BLOCK),
		("maze0", BLOCK, 0, MAZE, MAZE),
		("maze1", BLOCK, MAZE, MAZE, MAZE),
		("sun", SIDE - SUN_W, 0, SUN_W, SUN_H),
		("cactus", 0, BLOCK, CACTUS, CACTUS),
		("farm_a", 0, BLOCK + CACTUS, BLOCK, SIDE - BLOCK - CACTUS)]


def verify_lands():
	ws = get_world_size()
	if ws != SIDE:
		print("[s16] !! 本档只服务 world", SIDE, "，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	print("[s16] 地块自检通过：方块", BLOCK * BLOCK, "格 + 迷宫0", MAZE * MAZE,
		"格 + 迷宫1", MAZE * MAZE,
		"格 + 向日葵", SUN_W * SUN_H, "格 + 仙人掌", CACTUS * CACTUS, "格 + 轮作",
		BLOCK * (SIDE - BLOCK - CACTUS),              # farm_a 6 列 x 4 行 = 24 ✓
		"格 =", ws * ws, "格")
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
	# 轮作任务在名单里的起始下标（必须与 assign() 的 append 顺序严格一致）：
	#   cactus? sun? maze0+maze1? pumpkin? ⇒ 之后才是 rot0..rotN
	n = 0
	if num_unlocked(Unlocks.Cactus) > 0:
		n = n + 1
	if num_unlocked(Unlocks.Sunflowers) > 0:
		n = n + 1
	if num_unlocked(Unlocks.Mazes) > 0:
		n = n + 2
	if num_unlocked(Unlocks.Pumpkins) > 0:
		n = n + 1
	return n


def rot_any_active():
	# 2026-11-02（cactus-fixer 的 test_stage_owner 抓到的同型 R5 缺口）：
	#   旧版主机**无条件**整片扫 farm_a (0,12,6,4)，而 rot 副机也被派到 farm_a 的切片上
	#   ⇒ 副机在飞时主机仍会去 harvest/plant 同一片地 ⇒ **一区两 owner 抢地** ✗
	#   （与 w12 旧写法 `busy_ok(1)` 只看第 1 片是同一类错误 ✓）
	#   ⇒ 任一轮作切片在飞 ⇒ 主机不许碰 farm_a（轮作副机合起来覆盖全部 6 列 ✓）
	i = rot_base()
	while i < len(ACTIVE):
		if ACTIVE[i] == 1:
			return 1
		i = i + 1
	return 0


def assign(drones):
	HANDED[0] = 0
	if jobs.dino_ready() == 1:
		return []          # 独占相：一架副机都不派（恐龙尾巴会挡住它们）
	if jobs.full_maze_ready() == 1:
		return []          # 满场迷宫相同样独占 ✓（整块棋盘都是树篱）
	if drones < 2:
		return []
	js = []
	# 【名单顺序 = 优先级】调度器按顺序放飞，名额用完就停。
	#   真机教训（2026-10-08）：w16 原来是 [maze, sun, pumpkin, cactus, ...]，
	#   4 架额度时名额被前三项占满 ⇒ **仙人掌 0 产能** ⇒ Dinosaurs 买不起（cactus 2000）
	#   ⇒ 整条骨头链（终点必需）永远不启动 ✗✗
	#   ⇒ 现在把**卡住终点的产线**排在名额之内：仙人掌 → 向日葵（电是全局瓶颈）→ 迷宫（金币）→ 南瓜
	if num_unlocked(Unlocks.Cactus) > 0:
		append(js, {"name": "cactus", "entry": jobs.cactus_shift,
			"x0": 0, "y0": BLOCK, "w": CACTUS, "h": CACTUS,
			"cycles": CZ_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 8
	if num_unlocked(Unlocks.Sunflowers) > 0:
		append(js, {"name": "sun", "entry": jobs.sun_simple_worker,
			"x0": SIDE - SUN_W, "y0": 0, "w": SUN_W, "h": SUN_H,
			"cycles": SUN_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 2
	if num_unlocked(Unlocks.Mazes) > 0:
		append(js, {"name": "maze0", "entry": jobs.maze_worker,
			"x0": BLOCK, "y0": 0, "w": MAZE, "h": MAZE,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
		# ② **第二座迷宫**（依据 maze_gold2.py：每座有**自己的宝藏** ⇒ 真并行 ✓；
		#   8x8 只有 49 面墙 ⇒ 复用会拆到全开、越刷越顺 ✓✓）
		append(js, {"name": "maze1", "entry": jobs.maze_worker,
			"x0": BLOCK, "y0": MAZE, "w": MAZE, "h": MAZE,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
	if num_unlocked(Unlocks.Pumpkins) > 0:
		append(js, {"name": "pumpkin", "entry": jobs.pumpkin_worker,
			"x0": 0, "y0": 0, "w": BLOCK, "h": BLOCK,
			"cycles": PK_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 4
	# ⚠⚠ **轮作切片只能在 farm_a (0,12,6,4) 里切**（真机 bug 2026-11-01）：
	#   旧版切片扫 (6,8,8,8) = 现在的 maze1 ⇒ ①轮作副机被困在迷宫里、work_tile 对树篱
	#   `can_harvest()` 返回 true（源码 FarmObject.Harvestable=>true）⇒ harvest() 会把整座
	#   迷宫抹掉 ✗②主机 sweep 走到 (6,8) 时会被 maze0 的边界**永久卡死**（util.go_to 旧版无界）✗✗
	#   ⇒ 轮作切片改到 farm_a：6 列 x 4 行，按列分角色（ROLES_A）✓
	# ⚠⚠ **删掉了旧 farm_b 切片**：farm_b 已改成 maze1 ✓
	n = drones - 5                  # 主机 + 仙人掌/向日葵/迷宫0/迷宫1/南瓜 = 5 架专职
	if drones >= 3:
		if n < 1:
			n = 1                   # **上游保护**：额度 >= 3 时至少留 1 片轮作 ✓
	if n > ROT_MAX:
		n = ROT_MAX
	cols = BLOCK                     # farm_a 的列数 = 6
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
		x0 = i * per
		w = per
		if i == n - 1:
			w = cols - i * per
		rr = []
		k = i * per
		while k < i * per + w:
			# ⚠⚠ 真机越界实录（2026-10-08）：`索引 10 超出了列表 [10 项] 的范围` ✗
			#   ⇒ 切片列数与 ROLES 表长度可能不一致（布局改过/表被改短）✗
			#   ⇒ 钳位兜底：越界一律按 "hay" 填 ✓（草是最安全的默认：只收不种 ✓）
			if k < len(ROLES_A):
				append(rr, ROLES_A[k])
			else:
				append(rr, "hay")
			k = k + 1
		append(js, {"name": "rot" + str(i), "entry": jobs.rotation_worker,
			"x0": x0, "y0": BLOCK + CACTUS, "w": w, "h": SIDE - BLOCK - CACTUS,
			"cycles": ROT_CYCLES, "roles": rr})
		HANDED[0] = HANDED[0] + 16
		seq = seq + 1
	return js


def allocation():
	# ⚠⚠ 轮作现在**只有 farm_a**（6 列 x 4 行 = 24 格）：farm_b (6,8,8,8) 已改成 maze1 ✗
	#   所以 b 返回的 ROLES_B 已经**不再被任何 sweep 使用**（保留返回值只为不改函数签名）✓
	#   调整方向沿用 stage_w8/w12 的教训：**草/木见底时在草与木之间互借，绝不动胡萝卜列**
	a = ROLES_A          # 见上面的实测依据：草为主 ✓
	b = ROLES_B
	if num_unlocked(Unlocks.Plant) <= 0:
		return ["hay", "hay", "hay", "hay", "hay", "hay"], ["hay", "hay", "hay", "hay", "hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Carrots) <= 0:
		return ["wood", "hay", "wood", "hay", "wood", "hay"], ["hay", "wood", "hay", "wood", "hay", "wood", "wood", "hay"]
	if num_items(Items.Hay) < HAY_FLOOR:
		a[2] = "hay"                 # 木 → 草
	if num_items(Items.Wood) < WOOD_FLOOR:
		a[1] = "wood"                # 草 → 木
	# ⚠⚠ **不许把草/木列借给胡萝卜**（真机停机实录 2026-10-08）：
	#   `[ut] !! 配比违反不变量：草 28 < 胡萝卜 32` ⇒ 档位自检不通过 ⇒ 停机 ✗
	#   固定表本身是合规的，是这条**运行时调整**把不变量破坏了 ✗
	#   ⇒ 配比是**硬约束**，运行时只允许在草/木之间互借（草>=胡萝卜恒成立 ✓）；
	#     胡萝卜不够时由南瓜方块的补种底线去等（block_farm 的 floor ✓），不是靠改配比 ✓
	return a, b


S16_DIAG = [0]
# farm_a 的地面类型诊断（2026-11-02，用户报 `hay` 长期贴 0）：**只统计、不改变任何行为** ✓
#   动机：hay 的唯一消耗方是胡萝卜种子（反编译 Farm.Plant：cost x 2^(yield升级-1)），
#   而 `[s16] 地里 草 16` 现在把「空土壤格」也数成草 ⇒ 看不出草列是不是已经**土壤化**
#   （土壤上草不会长 ⇒ hay 产量永久归零 ✗）。这一行把 Grassland / Soil / 其它 分开数。
S16_SOIL_A = [0, 0, 0, 0, 0, 0]     # 第 i 列有几格是 Grounds.Soil


def s16_report(a, b):
	# 诊断（真机症状 2026-10-08：`hay 15` 长期见底，而木 18 万 / 胡萝卜 5 万过剩 ✗）
	#   打印：本档配比 + **两块地实际长着什么** + 库存 ⇒ 一眼看出草是"没种"还是"种了没收到" ✓
	S16_DIAG[0] = S16_DIAG[0] + 1
	if S16_DIAG[0] % 10 != 1:
		return
	n_hay = 0
	n_carrot = 0
	n_wood = 0
	n_other = 0
	n_grassland = 0
	n_soil = 0
	n_gother = 0
	S16_SOIL_A[0] = 0
	S16_SOIL_A[1] = 0
	S16_SOIL_A[2] = 0
	S16_SOIL_A[3] = 0
	S16_SOIL_A[4] = 0
	S16_SOIL_A[5] = 0
	# a 区 (0,12) 6 列 x 4 行
	i = 0
	while i < 6:
		j = 0
		while j < 4:
			util.go_to(0 + i, 12 + j)
			e = get_entity_type()
			if e == Entities.Carrot:
				n_carrot = n_carrot + 1
			elif e == Entities.Tree or e == Entities.Bush:
				n_wood = n_wood + 1
			elif e == Entities.Grass or e == None:
				n_hay = n_hay + 1
			else:
				n_other = n_other + 1
			# 地面类型（只统计）：Soil 上长不出草 ⇒ 草列土壤化 = hay 产量永久归零 ✗
			g = get_ground_type()
			if g == Grounds.Soil:
				n_soil = n_soil + 1
				S16_SOIL_A[i] = S16_SOIL_A[i] + 1
			elif g == Grounds.Grassland:
				n_grassland = n_grassland + 1
			else:
				n_gother = n_gother + 1
			j = j + 1
		i = i + 1
	# ⚠ 原来这里还有一块 "b 区 (6,8) 8x8" 的扫描 —— 那块地**已经改成 maze1**，
	#   扫它只会把 64 格树篱数成"其它"，误导诊断 ⇒ 删掉 ✓
	print("[s16] 第", S16_DIAG[0], "轮 | A", a,
		"| 地里 胡萝卜", n_carrot, "草", n_hay, "木", n_wood, "其它", n_other,
		"| 库存 hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot), "pumpkin", num_items(Items.Pumpkin),
		"gold", num_items(Items.Gold), "weird", num_items(Items.Weird_Substance),
		"| 累计收割", jobs.HARVEST[0], "| 在飞", util.drone_count())
	# 地面类型行（只诊断）：列序 0~3=草 4=胡萝卜 5=木 ⇒ 一眼看出哪条列被土壤化 ✗
	print("[s16] farm_a 地面 | 草原", n_grassland, "土壤", n_soil, "其它", n_gother,
		"| 各列土壤", S16_SOIL_A,
		"| 草列(0-3)土壤化", S16_SOIL_A[0] + S16_SOIL_A[1] + S16_SOIL_A[2] + S16_SOIL_A[3],
		"| 胡萝卜列(4)土壤", S16_SOIL_A[4], "| wood列(5)土壤", S16_SOIL_A[5])


# ⚠⚠ **迷宫区只在没有副机在飞时由主机碰**（真机 2026-11-01）：
#   原来用 busy_ok(idx) 判断「没人管就我上」✗，而 ACTIVE 是近似的 ✗
#   ⇒ 主机与副机**同时**建/收同一座迷宫 ⇒ 互相把对方迷宫抹掉 ✗✗
#   实测：`[mzw] 副机班次结束：建了 **0** 座迷宫` ✗、`寻宝时脚下异常（Grass）` ✗、
#         `gold` 卡在 61 万不动 ✗
#   ⇒ 一块地一个 owner（R5）的**硬规则**：有副机在飞，主机绝不碰迷宫区 ✓
def run():
	# 【独占相】恐龙跑：尾巴会占满棋盘、还会挡住别的无人机 ⇒ 这一段整场归主机
	#   条件由 jobs.dino_ready() 判定（Dinosaurs 已解锁 + 仙人掌够 + 骨头还没攒够）
	# 满场迷宫相（独占；开关在 jobs.FULL_MAZE_ON ✓ —— 默认关，验证后再开 ✓）
	if util.drone_count() <= 1:
		if jobs.full_maze_ready() == 1:
			jobs.full_maze_run(get_world_size())
			util.go_to(0, 0)
			return "w16"
	if util.drone_count() <= 1:
		if jobs.dino_ready() == 1:
			jobs.dino_run(get_world_size())
			util.go_to(0, 0)
			return "w16"
	a, b = allocation()
	s16_report(a, b)
	i = 0
	while i < 6:
		ROLES_A[i] = a[i]
		i = i + 1
	i = 0
	while i < 8:
		ROLES_B[i] = b[i]
		i = i + 1
	# 1) 轮作（含产奇异物质的树列）：主机**只扫 farm_a (0,12,6,4)**
	# ⚠⚠ 真机 bug 2026-11-02（用户报「仙人掌田和混合种植冲突」）：
	#   旧参数 `sweep_columns(0, BLOCK, BLOCK, SIDE-BLOCK, ROLES_A)` = (0,6) 6x10
	#   ⇒ 矩形 y=6..15 **同时压到 cactus (0,6,6,6)=y6..11 和 farm_a (0,12,6,4)** ✗✗
	#   ⇒ 主机会去 harvest/plant 仙人掌方块 ⇒ 与仙人掌副机抢地（R5 违规）、破坏排序块 ✓
	#   现在只扫 farm_a：`sweep_columns(0, BLOCK+CACTUS, BLOCK, SIDE-BLOCK-CACTUS, ROLES_A)`
	#   （4 个参数逐一核对：x0=0 / y0=6+6=12 / w=6（= len(ROLES_A) ✓）/ h=16-6-6=4 ✓）
	# ⚠⚠ 2026-11-02（cactus-fixer 的 test_stage_owner 抓到的**同型 R5 缺口**）：
	#   这段原来是**无条件**的，而 rot 副机也被派到 farm_a 的切片上
	#   ⇒ 副机在飞时主机仍会整片扫 ⇒ 一区两 owner 抢地 ✗✗
	#   ⇒ 任一轮作切片在飞 ⇒ 主机不许碰 farm_a（rot 副机合起来覆盖全部 6 列 ✓）
	if rot_any_active() == 0:
		jobs.sweep_columns(0, BLOCK + CACTUS, BLOCK, SIDE - BLOCK - CACTUS, ROLES_A)
	# ⚠⚠ **删掉了指向 maze1 的轮作 sweep**（真机 bug 2026-11-01）：
	#   旧代码 `if busy_ok(5): sweep_columns(BLOCK, MAZE, SIDE-BLOCK-SUN_W, SIDE-MAZE, ROLES_B)`
	#   扫的是 (6,8,8,8) = **现在的 maze1** ✗ ⇒ ①轮作副机/主机走进迷宫会 harvest 树篱把整座迷宫抹掉
	#   （源码：FarmObject.Harvestable=>true，HedgePlant 未覆盖 ⇒ can_harvest() 对树篱是 true ✗✗）
	#   ②主机 `util.go_to(6,8)` 第一段就被 maze0 的边界挡死（旧版 go_to 无界 ⇒ 主机永久卡死 ✗✗✗）
	#   ⇒ 轮作切片现在改到 farm_a (0,12,6,4)（见 assign），这里不再有第二个 owner ✓
	# 2) 向日葵带（8 倍 power ⇒ 全局 2 倍速）
	if util.drone_count() <= 1:
		# 没有副机时主机自己割两刀（power 是全场共享的，供不上就会拖慢所有无人机）
		jobs.sun_shift(SIDE - SUN_W, 0, SUN_W, SUN_H)
		jobs.sun_shift(SIDE - SUN_W, 0, SUN_W, SUN_H)
		jobs.cactus_shift(0, BLOCK, CACTUS, CACTUS, 1, get_world_size(), 0)
	# 3) 南瓜方块 6x6
	if busy_ok(4):
		if num_unlocked(Unlocks.Pumpkins) > 0:
			jobs.pumpkin_shift(1, budget.pumpkin_keep())
	# 4) 迷宫区（金币）：**只有主机独自在飞时才自己跑**——有副机时那一区归副机（R5）
	#    金币够了（Megafarm 2000 之后是 Leaderboard 100 万）就不再建
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK, 0, MAZE, 1)
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK, MAZE, MAZE, 1)     # 第二座迷宫的主机兜底 ✓
	util.go_to(0, 0)
	return "w16"
