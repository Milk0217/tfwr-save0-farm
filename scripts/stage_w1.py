# ============================================================
# stage_w1.py —— 档位 W = 1x1（**只有一格**）
#
# 地块规划（本档自带，唯一事实来源）：
#   +----+
#   | 草 |   ← 唯一一格，只收不种（草自长，收一次得 1 hay）
#   +----+
#
# 依据 docs/game/unlocks/expand_1.md（权威）：Expand 之前连 move() 都没有
#   ⇒ 本档**绝对不许**调用 board_shape() / 移动类函数（会直接报错中断整轮 ✗）
# 依据 full_run v4 日志：原地割草实测 1.26 hay/秒，是本档唯一的收入来源。
#
# 本档的毕业方式不是「攒够多少」，而是**键变了自然换档**：
#   买下 Expand lv1 ⇒ world 1 -> 3 ⇒ 调度器下一轮就切到行档 ✓
# ============================================================

SIDE = 1
SHAPE = "square"
VERSION = 1
import jobs


def enter():
	print("[s1] 档位 1x1 | 规划：唯一一格 = 草（只收不种）| 目标：攒 hay 买 Speed/Expand/Plant")
	return 1


def lands():
	return [("farm", 0, 0, 1, 1)]


def verify_lands():
	ws = get_world_size()
	if ws != 1:
		print("[s1] !! 本档只服务 world 1，当前 world", ws)
		return 0
	return 1


def assign(drones):
	# 档位 D 恒为 1（Megafarm 远未解锁）⇒ 没有可分的任务，空表 = 主机自己扛
	return []


ACTIVE = []              # 统一契约：所有档位都有 set_active ✓（本档无副机 ⇒ 空实现）


def set_active(mask):
	# 真机报错实录：`Error: stage_w1.set_active 不存在` ✗（整轮中止）
	#   ⇒ full_run 对所有档位都会调它 ✓ ⇒ **接口必须统一** ✓（本档 d=1，没有副机 ⇒ 空实现 ✓）
	while len(ACTIVE) > 0:
		pop(ACTIVE)
	return 0


def run():
	jobs.grind_shift(1.0)
	return "grind"
