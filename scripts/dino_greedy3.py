# ============================================================
# dino_greedy3.py —— **贪心开局 + 汉密尔顿回路收尾**（用户提的方案，已论证过渡安全）
#
# ============ 为什么这个混合方案成立 ============
#   * 实测：贪心每苹果只要 20~25 步（dino_fill 回路是 188 步）⇒ **8 倍效率** ✓
#   * 但贪心会**被自己的尾巴围死**（三次实测：长度 18 / 42 / 38 就停 ✗）。
#     真正能防成环的是连通性检查（洪水填充 ≈ 3,000~5,000 tick/步，贵 10~100 倍）✗ 不可用。
#   * 而**尾短的时候危险度低得多** ⇒ 前 SWITCH_AT 个苹果用贪心，之后回回路 ✓
#
# ============ 过渡安全性（我把这一步论证过了，这是本版的关键）============
#   切到回路时尾巴是"贪心散落"的、不在回路上 ⇒ 沿回路走**会撞到**那些散落段。
#   但没关系：
#     ① 头一走，尾巴跟着走 ⇒ 散落的旧格子在约 L 步内**全部被释放** ✓
#     ② 撞上时四方向绕一下即可，不必终止 ✓
#     ③ 绕完**用位置反查回路下标**（预建的 CIDX[1024]）继续沿回路走 ✓
#   ⇒ 约 L 步之后尾巴就完全落在回路上，回到标准的安全状态 ✓
#
# ============ 收益（dino_fill 自己的实测数据推的）============
#   dino_fill：前 20,000 步用 694 秒、吃了 54 个苹果 ⇒ 早期每苹果 370 步 x 211 tick
#   贪心：同样 54 个苹果只要 1,350 步 x 211 tick = **47 秒**（省 647 秒 = 整场 32%）
#   ⇒ 2,005 秒 -> 约 1,358 秒 ⇒ **约 1.48M 骨头/分**（基线 1.00M）
#
# ============ 纪律 ============
#  * `measure()` 只读得出苹果（站在苹果上给下一个苹果坐标，否则 None）⇒ 尾巴必须自己记 ✓
#  * 苹果有概率生成在**脚下** ⇒ 目标=当前格时也要走一步吃掉它（四方向硬试兜底）✓
#  * 戴帽子时不能绕边；`clear()` 会重置无人机位置（所以顺序是 clear -> 走回起点 -> 戴帽）。
#  * 摘帽才结算骨头；骨头 = 长度^2 x 32（lv6）。
#  * 没有三元表达式；LF + 制表符。
# ============================================================

VERSION = 4
N = get_world_size()
CELLS = N * N
SWITCH_AT = 30                     # 长度达到这个数就切回回路（实测死亡在 38/42）
REPORT_MOVES = 20000
MAX_MOVES = CELLS * 4000
DINO_MULT = 32

CYC = []                           # 回路方向序列
CIDX = []                          # 每个格子在回路上的下标
OCC = []
PATH = []
HEAD = [0]
LEN = [0]


def build_cycle():
	# 与 dino_fill 相同的构造：保留第 0 列当回程，其余列蛇形走完，最后闭合。
	y = 0
	while y < N:
		i = 0
		while i < N - 2:
			if y % 2 == 0:
				append(CYC, East)
			else:
				append(CYC, West)
			i = i + 1
		if y < N - 1:
			append(CYC, North)
		y = y + 1
	append(CYC, West)
	i = 0
	while i < N - 1:
		append(CYC, South)
		i = i + 1
	append(CYC, East)


def build_cidx():
	# 从 (1,0) 沿回路模拟一遍，记下每个格子对应的回路下标
	i = 0
	while i < CELLS:
		append(CIDX, 0)
		i = i + 1
	x = 1
	y = 0
	k = 0
	while k < CELLS:
		CIDX[y * N + x] = k
		if k < len(CYC):
			d = CYC[k]
			if d == East:
				x = x + 1
			if d == West:
				x = x - 1
			if d == North:
				y = y + 1
			if d == South:
				y = y - 1
		k = k + 1


def build_occ():
	i = 0
	while i < CELLS:
		append(OCC, 0)
		i = i + 1


def goto(tx, ty):
	while get_pos_x() != tx:
		if get_pos_x() < tx:
			move(East)
		else:
			move(West)
	while get_pos_y() != ty:
		if get_pos_y() < ty:
			move(North)
		else:
			move(South)


def ix(x, y):
	return y * N + x


def free(x, y):
	if x < 0 or x >= N or y < 0 or y >= N:
		return 0
	if OCC[ix(x, y)] == 1:
		return 0
	return 1


def free_neighbors(x, y):
	c = 0
	if free(x + 1, y) == 1:
		c = c + 1
	if free(x - 1, y) == 1:
		c = c + 1
	if free(x, y + 1) == 1:
		c = c + 1
	if free(x, y - 1) == 1:
		c = c + 1
	return c


def adv(nx, ny):
	p = ix(nx, ny)
	append(PATH, p)
	OCC[p] = 1
	HEAD[0] = HEAD[0] + 1
	old = HEAD[0] - (LEN[0] + 1)
	if old >= 0:
		OCC[PATH[old]] = 0


def mv(dx, dy):
	if dx == 1:
		return move(East)
	if dx == -1:
		return move(West)
	if dy == 1:
		return move(North)
	if dy == -1:
		return move(South)
	return 0


def go(dx, dy, avoid_dead):
	if dx == 0 and dy == 0:
		return 0
	nx = get_pos_x() + dx
	ny = get_pos_y() + dy
	if free(nx, ny) == 0:
		return 0
	if avoid_dead == 1:
		if free_neighbors(nx, ny) < 2:
			return 0
	if mv(dx, dy) == 1:
		adv(nx, ny)
		return 1
	return 0


def greedy_step(tx, ty):
	px = get_pos_x()
	py = get_pos_y()
	dx = 0
	if tx > px:
		dx = 1
	if tx < px:
		dx = -1
	dy = 0
	if ty > py:
		dy = 1
	if ty < py:
		dy = -1
	adx = px - tx
	if adx < 0:
		adx = 0 - adx
	ady = py - ty
	if ady < 0:
		ady = 0 - ady
	if adx >= ady:
		if go(dx, 0, 1) == 1:
			return 1
		if go(0, dy, 1) == 1:
			return 1
		if go(0 - dx, 0, 1) == 1:
			return 1
		if go(0, 0 - dy, 1) == 1:
			return 1
	else:
		if go(0, dy, 1) == 1:
			return 1
		if go(dx, 0, 1) == 1:
			return 1
		if go(0, 0 - dy, 1) == 1:
			return 1
		if go(0 - dx, 0, 1) == 1:
			return 1
	# 放宽死胡同
	if adx >= ady:
		if go(dx, 0, 0) == 1:
			return 1
		if go(0, dy, 0) == 1:
			return 1
		if go(0 - dx, 0, 0) == 1:
			return 1
		if go(0, 0 - dy, 0) == 1:
			return 1
	else:
		if go(0, dy, 0) == 1:
			return 1
		if go(dx, 0, 0) == 1:
			return 1
		if go(0, 0 - dy, 0) == 1:
			return 1
		if go(0 - dx, 0, 0) == 1:
			return 1
	# 四方向硬试（苹果在脚下时要走一步吃掉它）
	if go(1, 0, 0) == 1:
		return 1
	if go(-1, 0, 0) == 1:
		return 1
	if go(0, 1, 0) == 1:
		return 1
	if go(0, -1, 0) == 1:
		return 1
	return 0


def detour():
	# 只在"回路下一格被贪心留下的散落尾巴挡住"时调用（罕见）。
	# **刻意不做任何记账**：这里追求的是"回到极简回路"，不是安全分析。
	if move(East) == True:
		return 1
	if move(North) == True:
		return 1
	if move(West) == True:
		return 1
	if move(South) == True:
		return 1
	return 0


# `cycle_step` 已删除：它是 v3 的"带记账的回路步进"，每步约 50 条语句（get_pos x4 /
# CIDX / free / OCC / append / measure），而后期一步移动只要 33~44 tick ⇒ 把成本翻倍
# （实测同一长度下 64.4 vs dino_fill 138.07 格/秒）。v4 改成主循环里的**极简回路**
# （move + 下标自增，只在被散落尾巴挡住时才 detour 一次），不再需要它。


def main():
	print("=== dino_greedy3 v", VERSION, "start ===")
	print("board", N, "cells", CELLS, "switch_at", SWITCH_AT,
		"lv_dinosaurs", num_unlocked(Unlocks.Dinosaurs),
		"cactus", num_items(Items.Cactus), "bone", num_items(Items.Bone))
	build_cycle()
	build_cidx()
	print("[g3] 回路长度", len(CYC), "（应 =", CELLS, "）",
		"| CIDX[0] =", CIDX[0], " CIDX[N+1] =", CIDX[N + 1])
	if len(CYC) != CELLS:
		print("[g3] ERROR: 回路长度不对，先别跑")
		return
	clear()
	build_occ()
	# clear() 重置了无人机位置 ⇒ 走回 (1,0)（与 CIDX 的起点一致）再戴帽子
	goto(1, 0)
	append(PATH, ix(1, 0))
	OCC[ix(1, 0)] = 1
	B0 = num_items(Items.Bone)
	C0 = num_items(Items.Cactus)
	change_hat(Hats.Dinosaur_Hat)
	tx = get_pos_x()
	ty = get_pos_y()
	m = measure()
	if m != None:
		tx = m[0]
		ty = m[1]
	moves = 0
	ate = 0
	t0 = get_time()
	tr = t0
	mr = 0
	mode = 0                        # 0 = 贪心，1 = 回路
	while moves < MAX_MOVES:
		if mode == 0:
			if greedy_step(tx, ty) == 0:
				break
			moves = moves + 1
			m = measure()
			if m != None:
				tx = m[0]
				ty = m[1]
				ate = ate + 1
				LEN[0] = ate
				if ate >= SWITCH_AT:
					mode = 1
					print("[g3] 切到回路：长度", ate, "moves", moves,
						"elapsed_s", get_time() - t0)
		else:
			# ---- **极简回路（本版核心修复）** ----
			# 实测：旧版每步做了约 50 条语句的记账（get_pos×4 / CIDX / free / OCC / append /
			# measure），而后期一步移动只要 33~44 tick ⇒ 记账把移动成本翻了一倍多
			# （实测同一长度下 64.4 vs dino_fill 的 138.07 格/秒 = 2.14 倍）✗
			# 回路**本身**就是安全的（尾巴永远沿同一条路径在身后）⇒ 这里不需要任何记账 ✓
			ci = CIDX[ix(get_pos_x(), get_pos_y())]
			while moves < MAX_MOVES:
				if move(CYC[ci]) == False:
					# 罕见：被贪心留下的散落尾巴挡住 ⇒ 绕一下并重新定位（尾部几十步内就被吃掉）
					if detour() == 0:
						break
					ci = CIDX[ix(get_pos_x(), get_pos_y())]
				else:
					ci = ci + 1
					if ci >= CELLS:
						ci = 0
					moves = moves + 1
			break
		if moves % REPORT_MOVES == 0:
			now = get_time()
			dt = now - tr
			sp = 0
			if dt > 0:
				sp = (moves - mr) / dt
			print("[g3] moves", moves, "ate", ate, "mode", mode,
				"moves_per_apple", moves / (ate + 1), "格/秒", sp,
				"elapsed_s", now - t0)
			tr = now
			mr = moves
	DT = get_time() - t0
	change_hat(Hats.Gray_Hat)
	B1 = num_items(Items.Bone)
	gain = B1 - B0
	print("[g3] 停: moves", moves, "ate", ate, "mode", mode, "elapsed_s", DT,
		"moves_per_apple", moves / (ate + 1), "仙人掌消耗", C0 - num_items(Items.Cactus))
	print("[g3] 骨头 +", gain, "（= 长度^2 x", DINO_MULT, "）")
	if gain > 0:
		print("[g3] 反推长度 =", (gain / DINO_MULT) ** 0.5,
			"| **骨头/分 =", gain / DT * 60, "**",
			"| 对照 dino_fill 1,002,662/分")
	print("=== dino_greedy3 end ===")


main()
