# ============================================================
# stage_w4.py —— 档位 W = 4x4（Expand lv3）
#
# 地块规划（本档自带，唯一事实来源）：
#   x=0 列：wood     x=1 列：wood
#   x=2 列：carrot（wood 不够时让给 wood）
#   x=3 列：hay（草过剩时也让给 wood）
#
# **本档不设南瓜方块**，理由（不是省事，是算过）：
#   * 4x4 的方块边长只能是 2（block_farm 口径 min(ws//2, 6)）⇒ 一刀只有 8 个南瓜；
#   * 而这一档的要务是 **wood 100 + carrot 50**（Expand lv3->4）；
#   * Pumpkins 解锁本身要 wood 500 + carrot 200 —— 在 4x4 攒这些之前，
#     Expand 早就被硬优先买走了 ⇒ 本档几乎必然 **Pumpkins 还没解锁**，
#     拿 4 格去等一个开不了工的方块纯属浪费 ✓
#   ⇒ 南瓜线统一交给 stage_w6（那边方块边长 3、Pumpkins 大概率已解锁）
#
# 与 stage_w3 的关系：同一套「按列分物种 + 需求驱动让位」的骨架，
#   只是列数从 3 变 4、且走位改用 jobs.sweep_columns（不再逐格手写）。
# ============================================================

SIDE = 4
SHAPE = "square"
VERSION = 1
HAY_SURPLUS = 3        # 草超过保留线这么多倍就把草列让给木（策略常数）
import util
import budget
import jobs

ROLES = ["hay", "hay", "hay", "hay"]


def enter():
	print("[s4] 档位 4x4 | 规划：x=0/1 木 | x=2 胡萝卜（木不够时让给木）| x=3 草（过剩时让给木）",
		"| 本档不设南瓜方块（见文件头）")
	return 1


def lands():
	ws = get_world_size()
	return [("wood0", 0, 0, 1, ws), ("wood1", 1, 0, 1, ws),
		("carrot", 2, 0, 1, ws), ("hay", 3, 0, 1, ws)]


def verify_lands():
	ws = get_world_size()
	if ws != 4:
		print("[s4] !! 本档只服务 world 4，当前", ws)
		return 0
	if util.check_lands(lands(), ws) == 0:
		return 0
	print("[s4] 地块自检通过：", ws * ws, "格 =", len(lands()), "条竖带")
	return 1


def assign(drones):
	return []


def roles():
	r = ["hay", "hay", "hay", "hay"]
	if num_unlocked(Unlocks.Plant) > 0:
		r[0] = "wood"
		r[1] = "wood"
		r[3] = "hay"
	if num_unlocked(Unlocks.Carrots) > 0:
		if num_items(Items.Wood) > budget.wood_keep():
			r[2] = "carrot"
	if num_items(Items.Hay) > budget.hay_keep() * HAY_SURPLUS:
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
	r = roles()
	ROLES[0] = r[0]
	ROLES[1] = r[1]
	ROLES[2] = r[2]
	ROLES[3] = r[3]
	jobs.sweep_columns(0, 0, 4, 4, ROLES)
	util.go_to(0, 0)
	return "w4"
