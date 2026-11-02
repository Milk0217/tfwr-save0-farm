# ============================================================
# stage_row.py —— 档位 W = 「一行」（Expand lv1）
#
# 为什么单独一个档：docs/game/unlocks/expand_2.md（权威）说下一级才
#   「no longer in a nice row」⇒ **Expand lv1 的农场是一行**，而
#   get_world_size() 在「一行」和「3x3」下**都是 3** ⇒ 只看 world 分不出档 ✗
#   （旧 full_run 的 farm_round 把它当 3x3 走：move(North) 在只有一行时绕回原行，
#     于是同一格被走三遍、k 值每遍都不同 —— 日志里那点零零碎碎的 wood 就是这么来的。）
#
# 地块规划（本档自带）：
#   一行 N 格（N = get_world_size()）：
#     [0] = 灌木 → wood      （第 0 格）
#     [1..N-1] = 草  → hay   （其余全部，只收不种）
#   目标：wood 20 ⇒ Expand lv2（世界变成方块）。haw 也顺路在涨 ✓
#
# 长轴方向由 enter() 实测（x 有长度就往 East 走，否则往 North 走）——
#   这就是 r4 那条「几何一律每调用现算、不许在顶层读棋盘」的落地方式。
# ============================================================

SIDE = 3
SHAPE = "row"
VERSION = 1
import util
import jobs

AXIS = [0, 0, 0]      # [world, x 有长度?, y 有长度?]，进档时探一次


def step_fwd():
	if AXIS[1] == 1:
		move(East)
	else:
		move(North)


def enter():
	ws = get_world_size()
	xm, ym = util.board_shape()
	if xm == 1 and ym == 1:
		print("[sr] !! 探测到的是方块，不是一行 ⇒ 拒绝进入本档（交由 stage_w3）")
		return 0
	if xm == 0 and ym == 0:
		print("[sr] !! 两条轴都没有长度 ⇒ 不是行档")
		return 0
	AXIS[0] = ws
	AXIS[1] = xm
	AXIS[2] = ym
	print("[sr] 档位 world", ws, "= 一行（x 有长度", xm, "/ y 有长度", ym, "）",
		"| 规划：第 0 格产 wood，其余割草 | 目标 wood 20 ⇒ Expand lv2")
	return 1


def lands():
	ws = get_world_size()
	if AXIS[1] == 1:
		return [("row", 0, 0, ws, 1)]
	return [("row", 0, 0, 1, ws)]


def verify_lands():
	ls = lands()
	l = ls[0]
	if l[3] * l[4] != get_world_size():
		print("[sr] !! 地块没铺满：", l[3], "x", l[4], "≠ world", get_world_size())
		return 0
	if AXIS[0] != get_world_size():
		print("[sr] !! 进档时记的 world", AXIS[0], "≠ 现在", get_world_size())
		return 0
	print("[sr] 地块自检通过：", l[3] * l[4], "格 = 一整行")
	return 1


def assign(drones):
	# D = 1 ⇒ 无副机可分。将来 Megafarm 到手后，行档早已毕业，不必补
	return []


ACTIVE = []              # 统一契约：所有档位都有 set_active ✓（本档无副机 ⇒ 空实现）


def set_active(mask):
	# 真机报错实录：`Error: stage_w1.set_active 不存在` ✗（整轮中止）
	#   ⇒ full_run 对所有档位都会调它 ✓ ⇒ **接口必须统一** ✓（本档 d=1，没有副机 ⇒ 空实现 ✓）
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	return 0


def run():
	util.go_to(0, 0)
	n = get_world_size()
	i = 0
	while i < n:
		if i == 0:
			jobs.work_wood_tile()
		else:
			jobs.work_hay_tile()
		step_fwd()          # 走满 N 步正好绕回起点 ✓
		i = i + 1
	return "row"
