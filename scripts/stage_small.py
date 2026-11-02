# ============================================================
# stage_small.py —— world 5~8 的**完整作业模块**（模板，其余档位照此写）
#
# 用户定下的三条架构指令：
#   ① 不要中央的 zones.py（中央分区表已经证明会与各产线脱节 ✗）
#   ② 按**棋盘大小**分模块：每个模块只服务一个尺寸档位 ✓
#   ③ 每个模块**自带地块规划** —— 地块划分写在本文件里，谁都看得见 ✓
#
# 本文件必须自足：只用游戏内置函数 + util.py（公共工具）✓
#   （本项目已在 go_to / cost_line / can_afford 上各栽过一次"跨文件未定义"✗）
#
# ---- 本档位（world 5~8）的地块规划 ----
#   棋盘 5x5 ~ 8x8（25 ~ 64 格）。这一档的特点：**还没有 6x6 方块的价值**
#   （文档 pumpkins.md：n>=6 才吃满 n*n*6 的倍率 ✓），所以：
#
#   +----------------+--------------------+
#   | 南瓜方块       | 轮作（其余全部）    |
#   | (0,0) 起       | 灌木/树 -> wood     |
#   | n = ws//2 格   | 胡萝卜  -> carrot   |
#   | （3x3 或 4x4） | 草地    -> hay      |
#   |                | 向日葵  -> power    |
#   +----------------+--------------------+
#
#   分工：
#     * 主机 = 轮作（跳过南瓜方块区）
#     * 副机 = 南瓜方块区（若 max_drones() > 1）
#   这一档**不设迷宫区**（8x8 迷宫放不下 ✓ mazes.md 要求 n x n）
# ============================================================

VERSION = 1
LO = 5                 # 本模块负责的 world 下界（含）
HI = 8                 # 上界（含）
PLAN_NAME = "轮作 + 单块南瓜田"


def block_side():
	# 本档位的南瓜方块边长（文档：尽量接近 6，但不许吞掉整块棋盘）
	ws = get_world_size()
	n = ws // 2
	if n > 6:
		n = 6
	if n < 2:
		n = 0
	return n


def plan():
	# 打印本档位的地块规划与实际尺寸（每次世界变化后可调用一次 ✓）
	ws = get_world_size()
	n = block_side()
	print("[s5] world", ws, "| 档位 world", LO, "~", HI, "|", PLAN_NAME)
	if n > 0:
		print("[s5]   南瓜方块 (0,0) 起", n, "x", n, "格 ⇒ 共", n * n, "格")
		print("[s5]   轮作区   = 其余", ws * ws - n * n, "格（灌木/树、胡萝卜、草地、向日葵）")
	else:
		print("[s5]   棋盘太小 ⇒ 全部", ws * ws, "格都归轮作（不留方块）")
	return n


def owns(x, y):
	# 本档位的地块判定：南瓜方块区归副机，其余归主机
	n = block_side()
	if n > 0:
		if x < n and y < n:
			return "block"
	return "farm"


def run(helpers):
	# 执行一轮本档位的作业。helpers 是 full_run 传进来的公共工具（避免跨文件未定义 ✗）
	# 返回本轮做了什么（便于判据行打印 ✓）
	n = block_side()
	if n >= 2:
		# 有方块 ⇒ 方块交给副机（若可用），主机只做轮作
		if num_unlocked(Unlocks.Megafarm) > 0:
			if max_drones() > 1:
				helpers["ensure_block_drone"](n)
	if num_unlocked(Unlocks.Plant) <= 0:
		helpers["hay_grind"](5.0)
		return "grind"
	helpers["farm_round"](0)
	return "farm"
