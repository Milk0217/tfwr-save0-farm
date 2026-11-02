# ============================================================
# stage_w6.py —— 档位 W = 6x6（Expand lv4）· **第一个带南瓜方块的档**
#
# 地块规划（本档自带，唯一事实来源）：
#   +---+---+---+---+---+---+
#   | 南瓜方块  | 木 | 木 | 胡 |     y=0..2：x=0..2 是方块，x=3/4 木、x=5 胡萝卜
#   |  3 x 3    |   |   |   |
#   +---+---+---+---+---+---+
#   | 草 | 草 | 草 | 木 | 木 | 胡 |  y=3..5：x=0..2 草（过剩时让给木）
#   +---+---+---+---+---+---+
#
#   方块占 9 格，轮作占 27 格 —— 两边**恰好铺满 36 格**，由 util.check_lands() 逐格验 ✓
#
# 为什么这一档才开南瓜：
#   * block_farm 的边长口径是 min(ws//2, 6) ⇒ 6x6 给 **3x3**（一刀 27 个，每格 3 个）；
#   * 这一档的下一级 Expand（lv4->5）**正好要 pumpkin 1000** ⇒ 南瓜终于有了买家 ✓
#   * 胡萝卜是南瓜的种子钱（种一株 1 个胡萝卜，3x3 补一轮 9 个）⇒ 胡萝卜列不能停
#
# 门槛（关键，见 block_farm v17 注释）：南瓜补种用的胡萝卜底线来自
#   budget.carrot_keep()（= 下一个目标的胡萝卜需求），**不是** block_farm 内部那个
#   写死的 carrot_floor() ≈ 684 —— 后者会让 6x6 一颗南瓜都种不下去 ✗
# ============================================================

SIDE = 6
SHAPE = "square"
VERSION = 1
BLOCK = 3              # 方块边长，必须与 block_farm.block_size() 同口径（run() 里会核对）
HAY_FLOOR = 40         # 草见底就把一条胡萝卜列借给它（策略常数）
WOOD_FLOOR = 40        # 木见底同理
import util
import budget
import jobs

ROLES_A = ["wood", "wood", "carrot"]      # x=3,4,5（全高 6 行）
ROLES_B = ["hay", "hay", "hay"]           # x=0,1,2 的 y=3..5 三行


def enter():
	print("[s6] 档位 6x6 | 规划：方块(0,0) 3x3 | x=3/4 木、x=5 胡萝卜",
		"| 底排 x=0..2 草（过剩时让给木）| 下一级 Expand 要 pumpkin 1000")
	return 1


def lands():
	n = BLOCK
	return [("block", 0, 0, n, n),
		("bands_top", n, 0, SIDE - n, SIDE),
		("bands_low", 0, n, n, SIDE - n)]


def verify_lands():
	ws = get_world_size()
	if ws != SIDE:
		print("[s6] !! 本档只服务 world", SIDE, "，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	side = jobs.pumpkin_block_side()
	if side != BLOCK:
		print("[s6] !! 方块边长口径不一致：block_farm 给", side, "，本档规划", BLOCK)
		return 0
	print("[s6] 地块自检通过：方块", BLOCK * BLOCK, "格 + 轮作",
		ws * ws - BLOCK * BLOCK, "格 =", ws * ws, "格")
	return 1


def assign(drones):
	return []


def carrot_goal():
	# 南瓜方块的「种子钱」：方块面积 x 3（约够三代补种）+ 下一个目标的胡萝卜需求
	return BLOCK * BLOCK * 3 + budget.carrot_keep()


def allocation():
	# 6 个轮作列（A 三列各 6 格 = x3/x4/x5 | B 三列各 3 格 = 底排 x0/x1/x2），共 27 格。
	#
	# **配比由种植成本决定，不是拍脑袋**：真机实测「种一株 Carrot 要 wood 1 + hay 1」
	#   ⇒ 每产 1 个胡萝卜就净消耗 1 wood 与 1 hay
	#   ⇒ 一列每轮大约产「格数」个 ⇒ **可持续配比恒等于 1:1:1（按格数算）**
	#   ⇒ 27 格拆成 9 胡萝卜 / 9 草 / 9 木 = 每样「一条 A 列 + 一条 B 列」✓
	#
	# 两轮 mock 长跑换来的（都是偏离 1:1:1 的后果）：
	#   * 1 胡 / 5 木 ⇒ 木 27117、胡萝卜 5 ⇒ 南瓜补种全饿死 ✗
	#   * 3 胡 / 1 草 / 2 木 ⇒ 草被吃光（hay 3）⇒ 胡萝卜自己都种不下去 ✗
	# 偏离只能靠缓冲撑一会儿，迟早被上下游掐断 ✓
	#
	# ⚠ 别指望「木列顺路产草」：work_wood_tile 收完灌木立刻补种，
	#   只有**第一次**遇到草地时才顺带收一份 hay（一次性），不是稳定来源 ✗
	r = ["carrot", "hay", "wood", "carrot", "hay", "wood"]
	if num_unlocked(Unlocks.Plant) <= 0:
		return ["hay", "hay", "hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Carrots) <= 0:
		return ["wood", "hay", "wood", "hay", "wood", "hay"]
	# 草或木见底 ⇒ 把一条胡萝卜列借给它（否则胡萝卜同样种不下去，等于三输）
	if num_items(Items.Hay) < HAY_FLOOR:
		r[0] = "hay"
	if num_items(Items.Wood) < WOOD_FLOOR:
		r[3] = "wood"
	return r


ACTIVE = []              # 统一契约：所有档位都有 set_active ✓（本档无副机 ⇒ 空实现）


def set_active(mask):
	# 真机报错实录：`Error: stage_w1.set_active 不存在` ✗（整轮中止）
	#   ⇒ full_run 对所有档位都会调它 ✓ ⇒ **接口必须统一** ✓（本档 d=1，没有副机 ⇒ 空实现 ✓）
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	return 0


def run():
	# ---- 1) 轮作（先干活：胡萝卜列要先产出，南瓜才有种子钱）----
	a = allocation()
	ROLES_A[0] = a[0]
	ROLES_A[1] = a[1]
	ROLES_A[2] = a[2]
	ROLES_B[0] = a[3]
	ROLES_B[1] = a[4]
	ROLES_B[2] = a[5]
	jobs.sweep_columns(3, 0, 3, SIDE, ROLES_A)
	jobs.sweep_columns(0, 3, 3, 3, ROLES_B)
	# ---- 2) 南瓜方块：跑一轮（种 → 等熟 → 补死株 → 收割门满足就一刀收）----
	if num_unlocked(Unlocks.Pumpkins) > 0:
		jobs.pumpkin_shift(1, budget.pumpkin_keep())
	util.go_to(0, 0)
	return "w6"
