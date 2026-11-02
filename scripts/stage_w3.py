# ============================================================
# stage_w3.py —— 档位 W = 3x3（第一个**方块**棋盘）
#
# 地块规划（本档自带，唯一事实来源）：
#   x=0 列：wood      灌木/树 → wood
#   x=1 列：carrot    胡萝卜 → carrot（**wood 不够时让给 wood**，见 roles()）
#   x=2 列：hay       草，只收不种 → hay
#
#   为什么是三条**竖带**而不是棋盘式交错：
#     * 3x3 里任何两格都在 3 步内 ⇒ 伴生（polyculture）此时还没解锁，交错没有收益
#     * 竖带让「谁占哪块地」一眼可核对，verify_lands() 能逐格验铺满/不重叠 ✓
#
# 这一档要买的四样（全部由 budget.py 按报价自己判断）：
#     Carrots(wood 50) → Expand lv3(wood 30 + carrot 20) → Trees(wood 50 + carrot 70)
#     → Speed/Grass 等级
#   ⇒ 本档是**木与胡萝卜的拉锯战**，roles() 就是那个天平。
#
# 两次死锁的教训（写进 roles() 的依据）：
#   v31：储备模式把 k==0 那格全改成胡萝卜 ⇒ wood 断供 ⇒ 胡萝卜也种不下去（互相锁死）
#   v36：所有解锁买完后 reserve(Wood) 变成 0 ⇒ 「永远不够」⇒ wood 恒为 1
#   ⇒ 判据必须是 budget.wood_keep()（待买解锁的需求 + 缓冲 + **永远为正的底**）
# ============================================================

SIDE = 3
SHAPE = "square"
VERSION = 2
HAY_SURPLUS = 3        # 草超过保留线这么多倍，就把草列也让给木（策略常数，不是游戏数据）
import util
import budget
import jobs

ROLES = ["hay", "hay", "hay"]      # 每轮开头按需求重算（roles() 的结果）


def enter():
	print("[s3] 档位 3x3 | 规划：x=0 木 | x=1 胡萝卜（木不够时让给木）| x=2 草")
	return 1


def lands():
	ws = get_world_size()
	return [("wood", 0, 0, 1, ws), ("carrot", 1, 0, 1, ws), ("hay", 2, 0, 1, ws)]


def verify_lands():
	ws = get_world_size()
	seen = []
	i = 0
	while i < ws * ws:
		append(seen, 0)
		i = i + 1
	ls = lands()
	i = 0
	while i < len(ls):
		l = ls[i]
		y = 0
		while y < l[4]:
			x = 0
			while x < l[3]:
				px = l[1] + x
				py = l[2] + y
				if px >= ws or py >= ws:
					print("[s3] !! 地块越界:", px, py)
					return 0
				idx = py * ws + px
				if seen[idx] == 1:
					print("[s3] !! 地块重叠于", px, py)
					return 0
				seen[idx] = 1
				x = x + 1
			y = y + 1
		i = i + 1
	i = 0
	while i < ws * ws:
		if seen[i] == 0:
			print("[s3] !! 有格子没被分到，行主序下标", i)
			return 0
		i = i + 1
	print("[s3] 地块自检通过：", ws * ws, "格恰好分给", len(ls), "条竖带")
	return 1


def assign(drones):
	# D = 1 ⇒ 无副机可分（Megafarm 要 gold 2000，本档远远够不着）
	return []


def roles():
	# 需求驱动：木不够就把中间那列也让给木（否则 wood 断供 ⇒ 胡萝卜也种不下去）
	# ---- 真机那一跑（2026-10-07）换来的两条 ----
	# ① 保留线口径修正后，这里的判据变成「Expand 下一级的 wood 需求」⇒ 中列能早早开工胡萝卜 ✓
	# ② 实跑收工时 hay 3894 / wood 637 ⇒ **草严重过剩、木才是瓶颈**（0.29 wood/秒）
	#    ⇒ 草一旦远超保留线，第三列也该让给木，而不是继续白产草 ✗
	#    （⚠ 别指望木列替它产草：work_wood_tile 收完灌木立刻补种，
	#      只有第一次遇到草地时才顺带收一份 hay，是一次性的，不是稳定来源）
	r = ["hay", "hay", "hay"]
	if num_unlocked(Unlocks.Plant) > 0:
		r[0] = "wood"
		r[1] = "wood"
		r[2] = "hay"
	if num_unlocked(Unlocks.Carrots) > 0:
		if num_items(Items.Wood) > budget.wood_keep():
			r[1] = "carrot"
	if num_items(Items.Hay) > budget.hay_keep() * HAY_SURPLUS:
		r[2] = "wood"
	return r


def do_col(i):
	if ROLES[i] == "wood":
		jobs.work_wood_tile()
	elif ROLES[i] == "carrot":
		jobs.work_carrot_tile()
	else:
		jobs.work_hay_tile()


ACTIVE = []              # 统一契约：所有档位都有 set_active ✓（本档无副机 ⇒ 空实现）


def set_active(mask):
	# 真机报错实录：`Error: stage_w1.set_active 不存在` ✗（整轮中止）
	#   ⇒ full_run 对所有档位都会调它 ✓ ⇒ **接口必须统一** ✓（本档 d=1，没有副机 ⇒ 空实现 ✓）
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	return 0


def run():
	r = roles()
	ROLES[0] = r[0]
	ROLES[1] = r[1]
	ROLES[2] = r[2]
	ws = get_world_size()
	util.go_to(0, 0)
	y = 0
	while y < ws:
		do_col(0)
		move(East)
		do_col(1)
		move(East)
		do_col(2)
		move(East)          # 从 x=2 走出边界 ⇒ 绕回 x=0 ✓
		move(North)         # 下一行
		y = y + 1
	return "3x3"
