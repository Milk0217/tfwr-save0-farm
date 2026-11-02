# ============================================================
# dino_greedy2.py —— 恐龙贪心 v2：**自己记尾巴 + 防死胡同**
#
# ============ v1 为什么死（实测两次）============
#   第一次 moves 371  ate 17 长度 18 ✗     第二次 moves 977 ate 41 长度 42 ✗
#   而 moves_per_apple = 20.6~23.3（dino_fill 是 188）⇒ **追苹果本身没问题，8 倍** ✓
#   死因：**被自己的尾巴围死**。长度 42 就能在 1024 格里围出一个封闭圈（4x4 的环只要 12 格）。
#
#   **我上一轮判断错了一次**：我以为文档那句 "The last segment of the tail will move out of
#   the way during the move, so you can move onto it" 意味着不会被围死 —— 它只保证
#   "刚腾出来的那一格能走"，**不保证不形成闭环** ✗
#
#   还有个硬约束：`measure()` 在恐龙田里**只读得出苹果**（站在苹果上返回下一个苹果坐标，
#   否则 None）⇒ **尾巴是感知不到的** ⇒ 必须自己记录路径 ✓
#
# ============ v2 的两件新东西 ============
#   ① **路径记录**：`PATH` 按时间存下走过的每一格，`OCC[1024]` 标记被尾巴占着的格。
#      不变式：占用格数 = 长度 + 1（头自己也算一格）—— 实测佐证：填满农场时长度 1023、
#      占用 1024 ✓ 每走一步只改 2 格（新增头、释放最老的尾）⇒ 几乎免费。
#   ② **防死胡同**：候选方向先在内存里筛一遍 —— 走过去之后那格还剩几个自由邻居？
#      **少于 2 个就不选**（这正是蛇类经典死法：钻进一格宽的通道 / 收紧成环）。
#      成本约 32 tick/步，而一步移动要 33~400 tick ⇒ 完全划得来。
#   ③ 兜底顺序：先"靠近苹果且不是死胡同" → 再"靠近苹果" → 再"远离苹果但能活" → 四方向硬试。
#
# ============ 纪律 ============
#  * `measure()` / `get_time()` / `get_pos_x(y)` / `quick_print()` 都免费或 1 tick
#    ⇒ 每步都 `measure()` 完全负担得起。
#  * 苹果有概率生成在**脚下** ⇒ 目标 = 当前格时也要走一步（吃掉它）⇒ 四方向硬试兜底。
#  * 戴帽子时不能绕边 ⇒ 有界网格，坐标不回绕。
#  * 摘帽才结算骨头；骨头 = 长度^2 x 32（lv6）。
#  * 没有三元表达式；LF + 制表符。
# ============================================================

VERSION = 2
N = get_world_size()
CELLS = N * N
REPORT_MOVES = 20000
MAX_MOVES = CELLS * 4000
DINO_MULT = 32

OCC = []                           # CELLS 个 0/1
PATH = []                          # 走过的位置（按时间追加）
HEAD = [0]
LEN = [0]                          # 长度 = 吃到的苹果数
SELFCHK = [0]


def build_occ():
	i = 0
	while i < CELLS:
		append(OCC, 0)
		i = i + 1


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
	# 走到 (nx,ny) 之后的路径记录：新增头、按当前长度释放最老的尾
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
	# 朝 (dx,dy) 走一格。avoid_dead=1 时先做死胡同检查
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


def step(tx, ty):
	# 返回 1 = 走了；0 = 四个方向全走不了（真的没路了）
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
	# 第一遍：靠近苹果的两个方向 + 防死胡同
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
	# 第二遍：放宽死胡同要求（可能有"唯一的活路"本身是个死胡同口）
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
	# 第三遍：四方向硬试（苹果在脚下时必须走一步吃掉它）
	if go(1, 0, 0) == 1:
		return 1
	if go(-1, 0, 0) == 1:
		return 1
	if go(0, 1, 0) == 1:
		return 1
	if go(0, -1, 0) == 1:
		return 1
	return 0


def main():
	print("=== dino_greedy2 v", VERSION, "start ===")
	print("board", N, "cells", CELLS, "lv_dinosaurs", num_unlocked(Unlocks.Dinosaurs),
		"cactus", num_items(Items.Cactus), "bone", num_items(Items.Bone))
	print("[g2] v1 实测：8 倍效率但被自己围死（长度 18 / 42 就停）")
	clear()
	build_occ()
	while get_pos_x() != 0:
		move(West)
	while get_pos_y() != 0:
		move(South)
	# 记录起点（此时还没尾巴）
	append(PATH, ix(0, 0))
	OCC[0] = 1
	B0 = num_items(Items.Bone)
	C0 = num_items(Items.Cactus)
	change_hat(Hats.Dinosaur_Hat)
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
		m = measure()
		if m != None:
			tx = m[0]
			ty = m[1]
			ate = ate + 1
			LEN[0] = ate
		if moves % REPORT_MOVES == 0:
			now = get_time()
			dt = now - tr
			sp = 0
			if dt > 0:
				sp = (moves - mr) / dt
			# 自检：OCC 里标记的格数 应等于 长度+1
			c = 0
			i = 0
			while i < CELLS:
				if OCC[i] == 1:
					c = c + 1
				i = i + 1
			print("[g2] moves", moves, "ate", ate, "len", LEN[0],
				"occ_marked", c, "(应 =", LEN[0] + 1, ")",
				"moves_per_apple", moves / (ate + 1), "格/秒", sp,
				"elapsed_s", now - t0)
			tr = now
			mr = moves
	DT = get_time() - t0
	change_hat(Hats.Gray_Hat)
	B1 = num_items(Items.Bone)
	gain = B1 - B0
	print("[g2] 停: moves", moves, "ate", ate, "len", LEN[0], "elapsed_s", DT,
		"moves_per_apple", moves / (ate + 1), "仙人掌消耗", C0 - num_items(Items.Cactus))
	print("[g2] 骨头 +", gain, "（= 长度^2 x", DINO_MULT, "）")
	if gain > 0:
		print("[g2] 反推长度 =", (gain / DINO_MULT) ** 0.5,
			"| **骨头/分 =", gain / DT * 60, "**",
			"| 对照 dino_fill 1,002,662/分")
	print("=== dino_greedy2 end ===")


main()
