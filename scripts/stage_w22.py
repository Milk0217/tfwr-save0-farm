# ============================================================
# stage_w22.py —— 档位 W = 22x22（Expand lv8）· 【保守重写版 v3】
#
# ⚠ 为什么整份重写（2026-10-27）：
#   `lb_enter` 报 `Error: 导入的模块存在语法错误。In: import stage_w22` ✗
#   —— Python 能编译 ✓、gamelang 也放过 ✗ ⇒ 游戏解析器有一条我不认识的限制 ✓
#   而 stage_w16.py（结构相同 ✓）**导入正常** ✓
#   ⇒ 按 w16 的写法把 w22 重写成**最保守的风格** ✓：
#     不用少见构造、每个函数只做一件事、所有 print 单行或标准续行 ✓
#
# 地块规划（22x22 = 484 格，util.check_lands 逐格验 ✓）：
#   方块(0,0)6x6=36 | 迷宫0(6,0)8x8=64 | 迷宫1(6,8)8x8=64
#   迷宫2(14,0)8x8=64 | 迷宫3(14,8)8x8=64
#   向日葵(0,6)2x16=32 | 仙人掌(6,16)6x6=36 | 轮作 farm_a(2,6)4x16=64
#   轮作 farm_b(12,16)10x6=60
#   36+64+64+64+64+32+36+64+60 = 484 ✓
#
# 4 座 8x8 迷宫的依据（maze_gold2.py 实跑结论）：
#   16x16 有 225 面墙，300 次复用拆不完 ⇒ 永远绕 ✗
#   8x8 只有 49 面墙 ⇒ 会拆到全开、越刷越顺 ✓；每座有**自己的宝藏** ⇒ 真并行 ✓
# ============================================================

SIDE = 22
SHAPE = "square"
VERSION = 3
BLOCK = 6
MAZE = 16
CACTUS = 6
SUN_W = 2
SUN_H = 16
FARM_Y0 = 6
PK_CYCLES = 3
SUN_CYCLES = 24
CZ_CYCLES = 2
WORKER_CYCLES = 12
ROT_CYCLES = 20
ROT_MAX = 12
HAY_FLOOR = 80
WOOD_FLOOR = 80
CARROT_WANT = 200

import util
import budget
import jobs

HANDED = [0]
ACTIVE = []
ROT_TURN = [0]

ROLES_A = ["carrot", "hay", "hay", "wood"]
ROLES_B = ["hay", "wood", "carrot", "hay", "wood", "carrot", "hay", "wood", "carrot", "hay"]


def set_active(mask):
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	i = 0
	while i < len(mask):
		append(ACTIVE, mask[i])
		i = i + 1
	return 1


def busy_ok(idx):
	# 主机只在「没人做这个任务」时才接手 ✓
	if idx < len(ACTIVE):
		if ACTIVE[idx] == 1:
			return 0
	return 1


def lands():
	return [("block", 0, 0, BLOCK, BLOCK),
		("maze0", BLOCK, 0, 8, 8),
		("maze1", BLOCK, 8, 8, 8),
		("maze2", BLOCK + 8, 0, 8, 8),
		("maze3", BLOCK + 8, 8, 8, 8),
		("sun", 0, FARM_Y0, SUN_W, SUN_H),
		("cactus", BLOCK, MAZE, CACTUS, CACTUS),
		("farm_a", SUN_W, FARM_Y0, BLOCK - SUN_W, SIDE - FARM_Y0),
		("farm_b", BLOCK + CACTUS, MAZE, SIDE - BLOCK - CACTUS, SIDE - MAZE)]


def verify_lands():
	ws = get_world_size()
	if ws != SIDE:
		print("[s22] !! 本档只服务 world", SIDE, "，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	print("[s22] 地块自检通过：484 格 = 方块36 + 迷宫4x64 + 向日葵32 + 仙人掌36 + 轮作124")
	return 1


def allocation():
	a = ROLES_A
	b = ROLES_B
	if num_unlocked(Unlocks.Plant) <= 0:
		return ["hay", "hay", "hay", "hay"], ["hay", "hay", "hay", "hay", "hay", "hay", "hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Carrots) <= 0:
		return ["wood", "hay", "wood", "hay"], ["hay", "wood", "hay", "wood", "hay", "wood", "hay", "wood", "wood", "hay"]
	if num_items(Items.Hay) < HAY_FLOOR:
		a[2] = "hay"
	if num_items(Items.Wood) < WOOD_FLOOR:
		a[1] = "wood"
	return a, b


def enter():
	a0, b0 = allocation()
	if util.check_ratio("w22", [("farm_a", SIDE - FARM_Y0, a0), ("farm_b", SIDE - MAZE, b0)]) == 0:
		return 0
	side = jobs.pumpkin_block_side()
	if side != BLOCK:
		print("[s22] !! 方块边长口径不一致：block_farm 给", side, "，本档规划", BLOCK)
		return 0
	print("[s22] 档位 22x22 | 方块(0,0)6x6 | 4 座 8x8 迷宫 (6,0)(6,8)(14,0)(14,8) | 向日葵(0,6)2x16 | 仙人掌(6,16)6x6")
	return 1


def assign(drones):
	HANDED[0] = 0
	if jobs.dino_ready() == 1:
		return []
	if jobs.full_maze_ready() == 1:
		return []
	if drones < 2:
		return []
	js = []
	if num_unlocked(Unlocks.Cactus) > 0:
		append(js, {"name": "cactus", "entry": jobs.cactus_shift,
			"x0": BLOCK, "y0": MAZE, "w": CACTUS, "h": CACTUS,
			"cycles": CZ_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 8
	if num_unlocked(Unlocks.Sunflowers) > 0:
		append(js, {"name": "sun", "entry": jobs.sun_simple_worker,
			"x0": 0, "y0": FARM_Y0, "w": SUN_W, "h": SUN_H,
			"cycles": SUN_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 2
	if num_unlocked(Unlocks.Mazes) > 0:
		append(js, {"name": "maze0", "entry": jobs.maze_worker,
			"x0": BLOCK, "y0": 0, "w": 8, "h": 8,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
		append(js, {"name": "maze1", "entry": jobs.maze_worker,
			"x0": BLOCK, "y0": 8, "w": 8, "h": 8,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
	if num_unlocked(Unlocks.Pumpkins) > 0:
		append(js, {"name": "pumpkin", "entry": jobs.pumpkin_worker,
			"x0": 0, "y0": 0, "w": BLOCK, "h": BLOCK,
			"cycles": PK_CYCLES, "roles": 0})
		HANDED[0] = HANDED[0] + 4
	if num_unlocked(Unlocks.Mazes) > 0:
		append(js, {"name": "maze2", "entry": jobs.maze_worker,
			"x0": BLOCK + 8, "y0": 0, "w": 8, "h": 8,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
		append(js, {"name": "maze3", "entry": jobs.maze_worker,
			"x0": BLOCK + 8, "y0": 8, "w": 8, "h": 8,
			"cycles": WORKER_CYCLES, "roles": [0 - 4, 0 - 4]})
		HANDED[0] = HANDED[0] + 1
	n = drones - 7
	if drones >= 3:
		if n < 1:
			n = 1
	if n > ROT_MAX:
		n = ROT_MAX
	cols = SIDE - BLOCK - CACTUS
	if n > cols:
		n = cols
	if n < 1:
		return js
	per = cols // n
	start = ROT_TURN[0] % n
	ROT_TURN[0] = ROT_TURN[0] + 1
	seq = 0
	while seq < n:
		i = (start + seq) % n
		x0 = BLOCK + CACTUS + i * per
		w = per
		if i == n - 1:
			w = cols - i * per
		rr = []
		k = i * per
		while k < i * per + w:
			if k < len(ROLES_B):
				append(rr, ROLES_B[k])
			else:
				append(rr, "hay")
			k = k + 1
		append(js, {"name": "rot" + str(i), "entry": jobs.rotation_worker,
			"x0": x0, "y0": MAZE, "w": w, "h": SIDE - MAZE,
			"cycles": ROT_CYCLES, "roles": rr})
		HANDED[0] = HANDED[0] + 16
		seq = seq + 1
	return js


# ⚠⚠ **迷宫区只在没有副机在飞时由主机碰**（真机 2026-11-01）：
#   原来用 busy_ok(idx) 判断「没人管就我上」✗，而 ACTIVE 是近似的 ✗
#   ⇒ 主机与副机**同时**建/收同一座迷宫 ⇒ 互相把对方迷宫抹掉 ✗✗
#   实测：`[mzw] 副机班次结束：建了 **0** 座迷宫` ✗、`寻宝时脚下异常（Grass）` ✗、
#         `gold` 卡在 61 万不动 ✗
#   ⇒ 一块地一个 owner（R5）的**硬规则**：有副机在飞，主机绝不碰迷宫区 ✓
def run():
	if util.drone_count() <= 1:
		if jobs.full_maze_ready() == 1:
			jobs.full_maze_run(get_world_size())
			util.go_to(0, 0)
			return "w22"
	if util.drone_count() <= 1:
		if jobs.dino_ready() == 1:
			jobs.dino_run(get_world_size())
			util.go_to(0, 0)
			return "w22"
	a, b = allocation()
	i = 0
	while i < 4:
		ROLES_A[i] = a[i]
		i = i + 1
	i = 0
	while i < 10:
		ROLES_B[i] = b[i]
		i = i + 1
	jobs.sweep_columns(SUN_W, FARM_Y0, BLOCK - SUN_W, SIDE - FARM_Y0, ROLES_A)
	if busy_ok(0):
		jobs.cactus_shift(BLOCK, MAZE, CACTUS, CACTUS, 1, get_world_size(), 0)
	if busy_ok(1):
		jobs.sun_shift(0, FARM_Y0, SUN_W, SUN_H)
		jobs.sun_shift(0, FARM_Y0, SUN_W, SUN_H)
	if busy_ok(4):
		if num_unlocked(Unlocks.Pumpkins) > 0:
			jobs.pumpkin_shift(1, budget.pumpkin_keep())
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK, 0, 8, 1)
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK, 8, 8, 1)
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK + 8, 0, 8, 1)
	if util.drone_count() <= 1:
		jobs.maze_shift(BLOCK + 8, 8, 8, 1)
	if busy_ok(7):
		jobs.sweep_columns(BLOCK + CACTUS, MAZE, SIDE - BLOCK - CACTUS, SIDE - MAZE, ROLES_B)
	util.go_to(0, 0)
	return "w22"
