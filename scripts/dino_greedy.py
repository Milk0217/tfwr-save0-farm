# ============================================================
# dino_greedy.py —— 恐龙**贪心追苹果**版（目标：把骨头从 1.00M/分 推到 3~4M/分）
#
# ============ 基线（dino_fill.py 那一场，按它自己的"格/秒"逐段算出来的）============
#   moves 192,759 | 分段耗时 694 + 205 + 145 + 961 = **2,005 秒 = 33.4 分钟**
#   骨头 +33,488,928  ÷ 33.4 分钟 = **1,002,662 /分钟**（≈ 刚好压线 1M）
#   瓶颈：**192,759 移动 ÷ 1,023 苹果 = 188 移动/苹果** ✗
#   （沿汉密尔顿回路走永远安全，但苹果随机落点 ⇒ 平均要半圈才碰到一个）
#
# ============ 本版的思路：朝苹果直接走 ============
#   文档原文："Using `measure()` on an apple will return the position of the next apple"
#   ⇒ 站在苹果上时 `measure()` 给出**下一个苹果的坐标** ⇒ 直线逼近
#   |dx| + |dy| 平均约 32 格 ⇒ 每苹果移动数 188 -> 约 40（**约 4.7 倍**）
#
#   预期（按实测速度反推）：早期 694->约 85 秒、中期 350->约 60 秒、后期 961->约 280 秒
#   ⇒ 合计约 430~600 秒 ⇒ **约 3.3~4.7M 骨头/分**
#
# ============ 为什么贪心在这里是安全的（关键，别删）============
#   1. **不需要自己记录尾巴**：`move()` 撞到尾巴会**返回 False**（文档），
#      所以"能不能走"由游戏直接告诉你 ⇒ 四个方向依次试即可，零额外状态。
#   2. **不可能被彻底困死**：文档写 "The last segment of the tail will move out of the way
#      during the move, so you can move onto it" ⇒ **刚离开的那一格永远可以回去**
#      ⇒ 只要尾巴还没填满农场，就至少有一个方向可走 ✓
#   3. **"满了"的判定与 dino_fill 一致**：四个方向全部返回 False ⇒ 尾巴已填满整块农场
#      （文档："if the snake fills out the whole farm, you will not be able to move anymore"）
#      ⇒ 这时换帽子收割，骨头 = 长度² x 倍率（lv6 = x32）。
#   4. 脱困策略：顺序是「距离大的轴朝目标 → 另一个轴朝目标 → 两轴反向」，
#      被尾巴挡住就换下一个方向 ⇒ 最坏情况只是多绕几步，不会终止。
#
# ============ 纪律 ============
#  * `measure()` / `get_time()` / `get_pos_x(y)` / `quick_print()` **都极便宜或免费**
#    ⇒ 每次移动都 `measure()` 一次完全负担得起（对比一次移动要 33~400 tick）。
#  * **戴帽子时不能绕边**（文档）⇒ 农场是有界网格，坐标不会回绕。
#  * 摘帽子才结算骨头 ⇒ 四个方向全堵住之后立刻摘。
#  * 没有三元表达式；LF + 制表符；`clear()` 会重置无人机位置，所以顺序是
#    clear -> 走回 (0,0) -> 戴帽子（苹果落在脚下）。
# ============================================================

VERSION = 1
N = get_world_size()
CELLS = N * N
REPORT_MOVES = 20000
MAX_MOVES = CELLS * 4000           # 保险上限（正常约 4 万步就满了）
DINO_MULT = 32                     # 2^(lv-1)，lv6 = 32（实测：33,488,928 = 1023^2 x 32）


def try_h(tx):
	# 水平朝目标走一格；已经在同一列就返回 0（让调用者去试别的方向）
	if tx > get_pos_x():
		return move(East)
	if tx < get_pos_x():
		return move(West)
	return 0


def try_v(ty):
	if ty > get_pos_y():
		return move(North)
	if ty < get_pos_y():
		return move(South)
	return 0


def try_h_far(tx):
	# 水平**远离**目标（脱困用）
	if tx > get_pos_x():
		return move(West)
	if tx < get_pos_x():
		return move(East)
	return 0


def try_v_far(ty):
	if ty > get_pos_y():
		return move(South)
	if ty < get_pos_y():
		return move(North)
	return 0


def step(tx, ty):
	# 走一步。返回 1 = 走了，0 = 四个方向全堵住（= 尾巴填满了农场）
	px = get_pos_x()
	py = get_pos_y()
	adx = tx - px
	if adx < 0:
		adx = 0 - adx
	ady = ty - py
	if ady < 0:
		ady = 0 - ady
	if adx >= ady:
		if try_h(tx) == 1:
			return 1
		if try_v(ty) == 1:
			return 1
		if try_h_far(tx) == 1:
			return 1
		if try_v_far(ty) == 1:
			return 1
	else:
		if try_v(ty) == 1:
			return 1
		if try_h(tx) == 1:
			return 1
		if try_v_far(ty) == 1:
			return 1
		if try_h_far(tx) == 1:
			return 1
	# ---- **四方向兜底（必须留着）** ----
	# 上面四个 helper 在"目标就是脚下这一格"时**全部返回 0**（同轴同点 ⇒ 没有"朝向目标"的
	# 方向可走）。而这种情况真实存在：**苹果有概率直接生成在无人机脚下**（文档说
	# "a new apple will be purchased and placed in a random location"）。
	# 旧版没这个兜底 ⇒ 一站在苹果上就误判成"四个方向全被堵住"（= 农场满了）⇒ 提前摘帽收工。
	# 实测证据：第一版走 371 步、长度才 18 就停了，而长度 18 时不可能被堵死 ✗
	# 兜底逻辑：随便走一步 ⇒ 这一步就吃掉了脚下的苹果 ⇒ 拿到下一个苹果的坐标，继续追。
	if move(East) == True:
		return 1
	if move(North) == True:
		return 1
	if move(West) == True:
		return 1
	if move(South) == True:
		return 1
	return 0


def main():
	print("=== dino_greedy v", VERSION, "start ===")
	print("board", N, "cells", CELLS, "max_drones", max_drones(),
		"lv_dinosaurs", num_unlocked(Unlocks.Dinosaurs),
		"cactus", num_items(Items.Cactus), "bone", num_items(Items.Bone))
	print("[greedy] 基线：dino_fill 是 188 移动/苹果、33.4 分钟、1.00M 骨头/分")
	clear()
	# clear() 会重置无人机位置 ⇒ 先走回 (0,0)，再戴帽子（苹果落在脚下）
	while get_pos_x() != 0:
		move(West)
	while get_pos_y() != 0:
		move(South)
	B0 = num_items(Items.Bone)
	C0 = num_items(Items.Cactus)
	change_hat(Hats.Dinosaur_Hat)
	# 起点的苹果就在脚下 ⇒ 第一次 measure() 就能拿到"下一个苹果"的坐标
	tx = 0
	ty = 0
	m = measure()
	if m != None:
		tx = m[0]
		ty = m[1]
	moves = 0
	ate = 0
	t0 = get_time()
	tr = t0
	mr = 0
	while moves < MAX_MOVES:
		if step(tx, ty) == 0:
			break
		moves = moves + 1
		m = measure()              # 站在苹果上 ⇒ 返回下一个苹果坐标（否则 None）
		if m != None:
			tx = m[0]
			ty = m[1]
			ate = ate + 1
		if moves % REPORT_MOVES == 0:
			now = get_time()
			dt = now - tr
			sp = 0
			if dt > 0:
				sp = (moves - mr) / dt
			mpa = moves / (ate + 1)
			print("[greedy] moves", moves, "ate", ate, "moves_per_apple", mpa,
				"格/秒", sp, "cactus", num_items(Items.Cactus),
				"elapsed_s", now - t0)
			tr = now
			mr = moves
	DT = get_time() - t0
	# ---- 摘帽子收割（骨头只在摘帽时结算）----
	change_hat(Hats.Gray_Hat)
	B1 = num_items(Items.Bone)
	gain = B1 - B0
	print("[greedy] 停: moves", moves, "ate", ate,
		"moves_per_apple", moves / (ate + 1), "elapsed_s", DT,
		"仙人掌消耗", C0 - num_items(Items.Cactus))
	print("[greedy] 骨头 +", gain, "（= 长度^2 x", DINO_MULT, "）")
	if gain > 0:
		L = (gain / DINO_MULT) ** 0.5
		print("[greedy] 反推长度 =", L, " | **骨头/分 =", gain / DT * 60, "**")
		print("对照 dino_fill：1,002,662 /分（33.4 分钟）")
		if moves > 0:
			print("[greedy] 每苹果移动数：dino_fill 188 ->", moves / (ate + 1),
				"（倍数", 188 / (moves / (ate + 1)), "）")
	print("=== dino_greedy end ===")


main()
