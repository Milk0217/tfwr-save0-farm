# ============================================================
# dino_fast.py —— 恐龙跑（当前 v8）：**问路直走 + 哈密顿回路兜底 + 廉价安全检查**
#
# 权威文档（docs/unlocks/dinosaurs.md）里两条 v1 没用上的关键信息：
#   1. **站在苹果上时 `measure()` 返回「下一颗苹果」的坐标**（实测确认：`first target 8 4 from 0 0`）
#   2. **`move()` 撞到自己尾巴只是返回 False，没有任何惩罚** → 试错免费
# 所以不必像 v1 那样沿回路瞎撞（22x22 平均 242 步/颗），可以直接走过去（曼哈顿 ~14 步）。
#
# —— 移动策略（三级，永远有出路）——
#   1. **直走**：已知目标 + 尾巴不到 3/4 + 不在冷却里 + 未被判定不安全 →
#      贪心先走差距大的轴 → 被挡就 BFS 求第一步（都带安全检查）。
#   2. **哈密顿回路搜索**：沿回路走下一格，被挡就走上一格。回路覆盖全场 ⇒ **一定能踩到苹果**。
#   3. **跟尾巴**：朝尾尖走（尾尖移动时一定让开 = 蛇类经典脱困）。
#   最后四向挑「不是回头路」的；真四向都动不了 = 蛇填满农场 → 收工结算。
#
# —— 迭代史（都是实测踩出来的，改代码前先读）——
#   v2 卡死：目标不可达/过期时退化成「四向乱试」→ 原地随机漂移。**乱试是错的**。
#   v3 卡死：贪心直走把身体卷成圈，**尾巴仅 29 节就把自己围死**（476 步只吃 29 颗）。
#   v4 更糟：加的洪水填充检查用 `not (A and B)` 混写 → 疑似恒真 → 每步都判死胡同 →
#            再加上「一次失败就永久切回路」，直接退回 v1 速度。
#   v5 加固：改纯嵌套 if；安全检查**开局自检**，不符合预期就自动关掉；连续 5 次失败才切回路。
#   v6 提速：**删掉洪水填充**（长尾巴时每步 1000+ 条语句，实测「特别慢」）→
#            换成 O(4~16) 次查询的「两步活路」+「窄缝」检查；
#            BFS 访问标记改世代号（省掉每次 484 条清零）、展开格数封顶；
#            **直走失败后冷却 20 步**（否则尾巴一长就每步重付检查+BFS+回路走位，越到后面越卡）；
#            空格 < 64 直接常驻回路。
#
# 尾巴模型：占位表 OCC + 环形轨迹 TAIL，O(1) 查询；尾尖可进入（会让开）。
# 模型不准也无所谓 —— 最终以 `move()` 返回值为准，而且有第 2/3 级兜底。
# 成本/产量（**probe8 实测，2026-09-12**，dino_lv5）：
#   一颗苹果 = 2 仙人掌 × 2^(dino_lv-1)   —— lv5 时 **32 仙人掌**
#   骨头     = 尾巴长度² × 2^(dino_lv-1)  —— lv5 时 **×16**（420 颗 = 282 万骨头）
#   两个倍率同源：升级描述就是「Increases the yield **and cost** of dinosaurs」。
#   ⇒ 单位仙人掌换到的骨头**不变**，升级买到的是**单位时间的骨头翻倍**。

# —— v9 改了三处，都是实测推出来的，改前先读 ——
#   0. **进紧循环前必须先判一次行进方向**（v10 修）。v9 第一次实跑就死在这里：
#      B1 的 cycle_step 在前向被挡时会**反向走一格**，于是无人机可能一直在**倒着**
#      遍历回路；紧循环只走正向 ⇒ 进循环后第 1 步就被自己的身体挡住，整场白跑。
#      实测证据：`v10 direction flip`（v9 时是 `cycle blocked at step 1743 eaten 28
#      pos 14 1`）。旧版 bare_cycle_move 也只走正向，是个一直潜伏的坑。
#   1. **B2 单独写成紧循环** `cycle_phase()`。v8 进入 B2 之后，每「步」仍然要回外层
#      循环跑完整套逻辑（量目标 + 清冷却 + 四层兜底阶梯的 false 判断 + 吃苹果记账）
#      ≈ **75 条语句/步**，而 move() 的成本 400×0.97^k 在吃够 ~85 颗后就降到地板价。
#      实测口径：38,338 步 / 480 秒 ≈ 80 步/秒；2 倍速下约 6000 tick/秒
#      ⇒ **≈71~75 tick/步**。扣掉 move（长尾阶段 ~15 tick）后 ≈56 tick 对 ~75 条语句
#      ⇒ **约 0.8 tick/语句**（不是早先以为的 5~15）。紧循环把它压到 ~25 条语句/步
#      ⇒ 约 **2 倍**（不是拍脑袋的 3~7 倍；按 164,000 步估，约 34 分钟 → 约 16 分钟）。
#   2. **MAX_APPLES / MAX_STEPS 不再写死**：420 与 200000 都是 22×22 时代的常数，
#      放到 32×32（1024 格）上分别只填 41%、且会把长跑**静默截断**。
#   3. **吃的颗数由「还差多少骨头」反算**：target = ceil(sqrt(need / 倍率))，
#      骨头够了自动收工，不再固定跑 420 颗（那会白烧仙人掌和时间）。
# ============================================================

SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD

# 单次最多吃几颗：**按棋盘格数标定，不要写死**。420 是 22x22（484 格）时代的常数
# （当时 ≈87% 填充率），而 32x32 有 1024 格 —— 写死 420 只填 41%，白丢 (896/420)² = 4.55 倍骨头。
# 骨头 = 尾巴²×倍率 ⇒「填得越满越值」；上限只受「蛇不能把自己堵死」约束：
# 走哈密顿回路时身体一定是回路上的一段连续弧，长度 < 总格数就一定能继续走。
MAX_APPLES = CELLS - CELLS // 8    # 32x32 -> 896；22x22 -> 424（与旧值 420 几乎一致）
# 直走阶段的苹果上限。实测「直走」会在 **29 / 34 / 40 颗**附近把自己盘死（v3/v6/v7 三次），
# 而廉价守卫挡不住「比两步更深的死口袋」（要挡住就得做洪水填充，那正是实测「特别慢」的那版）。
# 所以只在**最贵的前几颗**用直走（移动成本 400×0.97^k，k<26 时占全轮耗时的绝大部分），
# 其余交给**哈密顿回路**：v1 已在 16x16 证明它能安全吃到 198/256 —— 这才是可证明安全的那条路。
DIRECT_MAX = 26
CACTUS_PER_APPLE = 2               # probe6: cost(Apple) = 2 仙人掌
CACTUS_KEEP = 20                   # 留一点仙人掌底
# 防死循环。**必须随棋盘放大**：32x32 上跑满一场的步数量级是 CELLS²/4 ≈ 26 万，
# 写死 200000 会在长跑里静默截断（表现是骨头数对不上，很难查）。
MAX_STEPS = CELLS * CELLS // 4 + 20000

DIRS = [North, East, South, West]
DDX = [0, 1, 0, -1]
DDY = [1, 0, -1, 0]

# --- 尾巴轨迹（环形缓冲）：TAIL[(ST[0]-i) % TAIL_MAX] = 倒数第 i 步离开的格子 ---
TAIL_MAX = CELLS + 8
TAIL = []
OCC = []                           # 尾巴占位表（每格一个计数器，同一格重复走过也不误清）
_i = 0
while _i < TAIL_MAX:
	append(TAIL, -1)
	_i = _i + 1
_i = 0
while _i < CELLS:
	append(OCC, 0)
	_i = _i + 1

# --- 哈密顿回路（构造与 dino_bones.py 相同，尺寸无关）---
CYCLE = []
CYCLE_IDX = []
# CYCLE_DIR[i] = 从 CYCLE[i] 走到 CYCLE[i+1] 的方向下标（预先算好）。
# 这是 v9 紧循环能把每步压到 ~6 条语句的关键：原来每步都要
# get_pos_y/x → 算线性下标 → 查 CYCLE_IDX → CYCLE[(i+1)%CELLS] → dir_to() 里再算一遍坐标。
CYCLE_DIR = []
_i = 0
while _i < CELLS:
	append(CYCLE, 0)
	append(CYCLE_IDX, 0)
	append(CYCLE_DIR, 0)
	_i = _i + 1

# --- BFS 数组。访问标记用「世代号」代替每次清零（原先每次 BFS 都要写 484 条语句清零）---
BFS_PREV = []
BFS_GEN = []
BFS_Q = []
BGEN = [0]
_i = 0
while _i < CELLS:
	append(BFS_PREV, -2)
	append(BFS_GEN, -1)
	append(BFS_Q, 0)
	_i = _i + 1
BFS_CAP = CELLS + 4                # 一次 BFS 最多展开多少格。**不要小于 CELLS**：v6 设成 260，
								   # 结果 484 格的棋盘上 BFS 经常没搜到就先被截断 → 误判「苹果不可达」
								   # → 直走被放弃、无人机被推进兜底里乱走 → 反而盘死。
								   # 调用频率由「直走失败冷却 20 步」控制，不必靠这个上限省钱。
TIGHT_FREE = 64                    # 空格少于这个数就不再直走（空间太紧，直走只会白烧语句）

# 检查开关：[0]=两步活路检查 [1]=窄缝检查 [2]=空间过紧就常驻回路。
# 开局会**自检**：在明显开阔的起点上，前两道检查必须都判「安全」；任何一道不符合预期就关掉它，
# 宁可冒险也不能让整轮退回 v1 速度（v4 就是栽在「检查写错 → 直走全废」上）。
CHECK = [1, 1, 1]

# 可变状态（写列表元素即可在函数间共享）：
#   [0]=轨迹游标 [1]=尾巴长度 [2]=目标x [3]=目标y [4]=有没有目标 [5]=上一步的方向
#   [6]=1 表示「已判定直走不安全，之后只走回路」 [7]=连续直走失败次数 [8]=直走冷却剩余步数
#   [9]=回路游标（**只在 cycle_phase 的紧循环里用**：当前所在格的回路下标）
ST = [0, 0, -1, -1, 0, -1, 0, 0, 0, 0]
# 诊断计数：[0]=直走步数 [1]=回路步数 [2]=跟尾巴步数 [3]=BFS失败次数 [4]=丢弃目标的次数
#           [5]=检查1拦下的次数（没有两步活路） [6]=检查2拦下的次数（窄缝）
DIAG = [0, 0, 0, 0, 0, 0, 0]


def build_cycle():
	n = 0
	x = 0
	while x < SIZE_OF_BOARD:
		CYCLE[n] = x
		n = n + 1
		x = x + 1
	y = 1
	while y < SIZE_OF_BOARD:
		if y % 2 == 1:
			x = SIZE_OF_BOARD - 1
			while x >= 1:
				CYCLE[n] = y * SIZE_OF_BOARD + x
				n = n + 1
				x = x - 1
		else:
			x = 1
			while x <= SIZE_OF_BOARD - 1:
				CYCLE[n] = y * SIZE_OF_BOARD + x
				n = n + 1
				x = x + 1
		y = y + 1
	CYCLE[n] = (SIZE_OF_BOARD - 1) * SIZE_OF_BOARD
	n = n + 1
	y = SIZE_OF_BOARD - 2
	while y >= 1:
		CYCLE[n] = y * SIZE_OF_BOARD
		n = n + 1
		y = y - 1
	i = 0
	while i < CELLS:
		CYCLE_IDX[CYCLE[i]] = i
		i = i + 1
	# 预计算「回路每一步的方向」。构造保证 i 与 i+1 相邻，正常情况下不该出现 -1；
	# 出现个数直接打出来当自检（有 -1 会让紧循环走不动，那样一眼能看出来）。
	i = 0
	bad = 0
	while i < CELLS:
		j = i + 1
		if j >= CELLS:
			j = 0
		CYCLE_DIR[i] = cycle_dir_of(CYCLE[i], CYCLE[j])
		if CYCLE_DIR[i] < 0:
			bad = bad + 1
		i = i + 1
	print("[dino] cycle built, cells", n, "of", CELLS, "bad_dirs", bad)


def tail_append(p, grew):
	# p = 刚离开的格子。占位 = 最近 ST[1] 个「离开过的格子」。
	# grew=1（这一步吃到苹果）时尾巴长一节 → 窗口左端往后挪，**不扣除**尾尖。
	ST[0] = ST[0] + 1
	k = ST[0]
	TAIL[k % TAIL_MAX] = p
	OCC[p] = OCC[p] + 1
	if grew == 1:
		ST[1] = ST[1] + 1
	else:
		q = k - ST[1]
		if q >= 0:
			oldp = TAIL[q % TAIL_MAX]
			if OCC[oldp] > 0:
				OCC[oldp] = OCC[oldp] - 1


def tail_blocked(p):
	# 尾巴占用 = 最近 ST[1] 步离开的格子。最老的那一段是尾尖，移动时会让开 → 可以进去。
	if OCC[p] == 0:
		return 0
	if ST[1] > 0:
		if p == TAIL[(ST[0] - ST[1] + 1) % TAIL_MAX]:
			return 0
	return 1


def dir_to(t):
	# t 与当前格相邻时返回方向下标，否则 -1（戴帽时不能绕边，所以只认严格相邻）
	cx = get_pos_x()
	cy = get_pos_y()
	nx = t % SIZE_OF_BOARD
	ny = t // SIZE_OF_BOARD
	if nx == cx and ny == cy + 1:
		return 0
	if nx == cx + 1 and ny == cy:
		return 1
	if nx == cx and ny == cy - 1:
		return 2
	if nx == cx - 1 and ny == cy:
		return 3
	return -1


def try_move(d, grew):
	cx = get_pos_x()
	cy = get_pos_y()
	nx = cx + DDX[d]
	ny = cy + DDY[d]
	if nx < 0 or nx >= SIZE_OF_BOARD or ny < 0 or ny >= SIZE_OF_BOARD:
		return 0
	if tail_blocked(ny * SIZE_OF_BOARD + nx) == 1:
		return 0
	if move(DIRS[d]):
		tail_append(cy * SIZE_OF_BOARD + cx, grew)
		ST[5] = d
		return 1
	return 0


def body_neighbors(nx, ny):
	# 数 (nx,ny) 四邻里被身体占掉的格数
	n = 0
	k = 0
	while k < 4:
		ax = nx + DDX[k]
		ay = ny + DDY[k]
		if ax >= 0 and ax < SIZE_OF_BOARD and ay >= 0 and ay < SIZE_OF_BOARD:
			if tail_blocked(ay * SIZE_OF_BOARD + ax) == 1:
				n = n + 1
		k = k + 1
	return n


def escape2(nx, ny, cx, cy):
	# 「两步活路」检查：新位置 (nx,ny) 要有一个空邻居，而那个空邻居自己还要有一个空邻居
	# （排除 (nx,ny) 本身）。(cx,cy) 是要排除的旧位置 —— 它下一步就变成身体。
	# **全用嵌套 if**：不写 `not (A and B)` 这类混合表达式（解释器优先级没有先例）。
	k = 0
	while k < 4:
		ax = nx + DDX[k]
		ay = ny + DDY[k]
		is_old = 0
		if ax == cx:
			if ay == cy:
				is_old = 1
		if is_old == 0:
			if ax >= 0 and ax < SIZE_OF_BOARD and ay >= 0 and ay < SIZE_OF_BOARD:
				if tail_blocked(ay * SIZE_OF_BOARD + ax) == 0:
					m = 0
					while m < 4:
						bx = ax + DDX[m]
						by = ay + DDY[m]
						same = 0
						if bx == nx:
							if by == ny:
								same = 1
						if same == 0:
							if bx >= 0 and bx < SIZE_OF_BOARD and by >= 0 and by < SIZE_OF_BOARD:
								if tail_blocked(by * SIZE_OF_BOARD + bx) == 0:
									return 1
						m = m + 1
		k = k + 1
	return 0


def safe_try_move(d, grew):
	# 带安全检查的一步。返回：1=走了 / 0=物理走不了 / 2=被安全规则否决
	# 这里全部是 O(4~16) 次占位查询的廉价检查 —— v5 的洪水填充在长尾巴时每步要花上千条语句，
	# 实测「特别慢」，已删除。
	cx = get_pos_x()
	cy = get_pos_y()
	nx = cx + DDX[d]
	ny = cy + DDY[d]
	if nx < 0 or nx >= SIZE_OF_BOARD or ny < 0 or ny >= SIZE_OF_BOARD:
		return 0
	if tail_blocked(ny * SIZE_OF_BOARD + nx) == 1:
		return 0
	# 检查 1：走完之后要留「两步活路」（挡掉 1 格与 2 格深的死口袋 —— v3 就是死在这种口袋里）
	if CHECK[0] == 1:
		if escape2(nx, ny, cx, cy) == 0:
			DIAG[5] = DIAG[5] + 1
			return 2
	# 检查 2：别钻窄缝（新位置四邻被身体占掉的格数）。
	# 尾巴一长（>= 24 节）就把门槛收紧到 2 —— 实测尾巴三十几节就能被盘死，
	# 而「两侧都是身体」的格子正是盘死的入口。
	if CHECK[1] == 1:
		lim = 3
		if ST[1] >= 24:
			lim = 2
		if body_neighbors(nx, ny) >= lim:
			DIAG[6] = DIAG[6] + 1
			return 2
	return try_move(d, grew)


def move_or(d, grew, safe):
	# 统一入口：safe=1 走带守卫的那条路，safe=0 走不带守卫的（最后手段）。
	# v6 的教训：守卫只管「直走」，兜底的回路/跟尾巴走位用的是不带守卫的 try_move，
	# 于是苹果不可达、长时间在兜底里走的时候就在那里盘死了（guard 计数全程 0）。
	if safe == 1:
		return safe_try_move(d, grew)
	return try_move(d, grew)


def direct_step(tx, ty, grew):
	# 直走一步（带安全规则）。返回 1=走成 / 0=两条轴都不行
	cx = get_pos_x()
	cy = get_pos_y()
	ax = -1
	ay = -1
	if cx < tx:
		ax = 1
	elif cx > tx:
		ax = 3
	if cy < ty:
		ay = 0
	elif cy > ty:
		ay = 2
	dx = tx - cx
	if dx < 0:
		dx = -dx
	dy = ty - cy
	if dy < 0:
		dy = -dy
	d1 = ax
	d2 = ay
	if dy > dx:
		d1 = ay
		d2 = ax
	if d1 >= 0:
		if safe_try_move(d1, grew) == 1:
			return 1
	if d2 >= 0:
		if safe_try_move(d2, grew) == 1:
			return 1
	return 0


def greedy_step(tx, ty, grew, safe):
	# 朝目标迈一步：先走「差距大的那个轴」，被挡就换另一个轴
	cx = get_pos_x()
	cy = get_pos_y()
	ax = -1
	ay = -1
	if cx < tx:
		ax = 1
	elif cx > tx:
		ax = 3
	if cy < ty:
		ay = 0
	elif cy > ty:
		ay = 2
	dx = tx - cx
	if dx < 0:
		dx = -dx
	dy = ty - cy
	if dy < 0:
		dy = -dy
	d1 = ax
	d2 = ay
	if dy > dx:
		d1 = ay
		d2 = ax
	if d1 >= 0:
		if move_or(d1, grew, safe) == 1:
			return 1
	if d2 >= 0:
		if move_or(d2, grew, safe) == 1:
			return 1
	return 0


def bfs_first_step(tx, ty):
	# 在「没被尾巴占用」的格子上 BFS 到目标，返回第一步方向；走不通返回 -1
	head = get_pos_y() * SIZE_OF_BOARD + get_pos_x()
	tgt = ty * SIZE_OF_BOARD + tx
	if tgt < 0 or tgt >= CELLS:
		return -1
	if head == tgt:
		return -1
	# 世代号标记访问，避免每次 BFS 都写 484 条语句清零（长尾巴时这一步每轮都在跑）
	BGEN[0] = BGEN[0] + 1
	g = BGEN[0]
	BFS_GEN[head] = g
	BFS_PREV[head] = -1
	qh = 0
	qt = 0
	BFS_Q[qt] = head
	qt = qt + 1
	found = 0
	while qh < qt and found == 0:
		if qh > BFS_CAP:
			# 展开格数封顶：宁可这一轮说「找不到」，也不要在这里烧掉几千条语句
			return -1
		cur = BFS_Q[qh]
		qh = qh + 1
		if cur == tgt:
			found = 1
		else:
			cxx = cur % SIZE_OF_BOARD
			cyy = cur // SIZE_OF_BOARD
			d = 0
			while d < 4:
				nx = cxx + DDX[d]
				ny = cyy + DDY[d]
				if nx >= 0 and nx < SIZE_OF_BOARD and ny >= 0 and ny < SIZE_OF_BOARD:
					np = ny * SIZE_OF_BOARD + nx
					if BFS_GEN[np] != g:
						if np == tgt or tail_blocked(np) == 0:
							BFS_GEN[np] = g
							BFS_PREV[np] = cur
							BFS_Q[qt] = np
							qt = qt + 1
				d = d + 1
	if found == 0:
		return -1
	cur = tgt
	while BFS_PREV[cur] != head:
		cur = BFS_PREV[cur]
	return dir_to(cur)


def cycle_step(grew, safe):
	# 模式 2：沿哈密顿回路走。下一格被挡就走上一格 —— 回路覆盖全场，走它一定能踩到苹果
	cur = get_pos_y() * SIZE_OF_BOARD + get_pos_x()
	i = CYCLE_IDX[cur]
	d = dir_to(CYCLE[(i + 1) % CELLS])
	if d >= 0:
		if move_or(d, grew, safe) == 1:
			DIAG[1] = DIAG[1] + 1
			return 1
	d = dir_to(CYCLE[(i - 1 + CELLS) % CELLS])
	if d >= 0:
		if move_or(d, grew, safe) == 1:
			DIAG[1] = DIAG[1] + 1
			return 1
	return 0


def tail_step(grew, safe):
	# 模式 3：朝尾尖走（尾尖移动时一定让开，蛇类游戏的经典脱困手段）
	if ST[1] <= 0:
		return 0
	tip = TAIL[(ST[0] - ST[1] + 1) % TAIL_MAX]
	if tip < 0:
		return 0
	tx = tip % SIZE_OF_BOARD
	ty = tip // SIZE_OF_BOARD
	if greedy_step(tx, ty, grew, safe) == 1:
		DIAG[2] = DIAG[2] + 1
		return 1
	return 0


def any_step(grew):
	# 最后手段：四向里挑一个「不是回头路」的方向（不带守卫 —— 到这里已经无路可走了）
	d = 0
	while d < 4:
		if d != (ST[5] + 2) % 4:
			if try_move(d, grew) == 1:
				return 1
		d = d + 1
	d = 0
	while d < 4:
		if try_move(d, grew) == 1:
			return 1
		d = d + 1
	return 0


def cycle_dir_of(a, b):
	# a、b 是相邻两格的线性下标 → 方向下标；不相邻返回 -1
	ax = a % SIZE_OF_BOARD
	ay = a // SIZE_OF_BOARD
	bx = b % SIZE_OF_BOARD
	by = b // SIZE_OF_BOARD
	if bx == ax:
		if by == ay + 1:
			return 0
		if by == ay - 1:
			return 2
	if by == ay:
		if bx == ax + 1:
			return 1
		if bx == ax - 1:
			return 3
	return -1


def cactus_per_apple():
	# 一颗苹果现在要多少仙人掌。**不要写死 2**：probe8 实测 lv5 时已经涨到 32。
	c = get_cost(Entities.Apple)
	if c == None:
		return CACTUS_PER_APPLE
	for it in c:
		if it == Items.Cactus:
			return c[it]
	return CACTUS_PER_APPLE


def bone_multiplier(per):
	# 骨头 = 尾巴² × 倍率，倍率 = 成本倍率 = per / 2（升级描述：产量与成本同时翻倍）。
	# 用**可测的苹果成本**反推，比按等级硬算 2^(lv-1) 更不容易过时。
	m = per // 2
	if m < 1:
		m = 1
	return m


def bone_goal():
	# 骨头要花在哪：Leaderboard 的 200 万（还没解锁时）+ Polyculture 下一级的骨头成本。
	# 这样**骨头一够就自动收工**，不会为了凑一个写死的颗数白烧仙人掌和时间。
	g = 0
	if num_unlocked(Unlocks.Leaderboard) <= 0:
		g = g + 2000000
	pc = get_cost(Unlocks.Polyculture)
	if pc != None:
		for it in pc:
			if it == Items.Bone:
				g = g + pc[it]
	return g


def cycle_phase(target, eaten, steps):
	# 阶段 B2（v9）：**极简回路紧循环** —— 每步只做「查脚下 + 走一步 + 记数」。
	#
	# 安全性：身体是回路上**一段连续的弧**（每步沿回路前进一格，并让出 ST[1] 步前那一格），
	# 所以「回路下一格」必然不在身上 —— 只要尾巴长度 < 总格数就一定能继续走。
	# 这条由 v1 在 16x16 实测（安全吃到 198/256）与 v8 在 22x22 实测（回路 38,338 步、
	# 0 次卡死）共同背书；本函数只是把同样的走法从「每步 ~75 条语句」压到 ~25 条
	# （每步 71~75 tick 里 move 只占 ~15，其余全是样板语句，约 0.8 tick/语句）。
	#
	# 尾巴模型在这里**故意不维护**（省掉每步 ~10 条语句）：紧循环不需要它，
	# 只在吃到苹果时把长度 +1 —— 因为尾巴只在吃苹果的那一步变长。
	no_eat = 0
	ST[9] = CYCLE_IDX[get_pos_y() * SIZE_OF_BOARD + get_pos_x()]
	# 行进方向必须**先判一次**，不能假定是「正向」。理由见下面 flips 分支的注释。
	fwd = 1
	flips = 0
	print("[dino] v10 tight cycle mode at eaten", eaten, "steps", steps, "tail", ST[1])
	while eaten < target and steps < MAX_STEPS:
		steps = steps + 1
		on_apple = 0
		if get_entity_type() == Entities.Apple:
			on_apple = 1
		if fwd == 1:
			d = CYCLE_DIR[ST[9]]
			nxt = ST[9] + 1
			if nxt >= CELLS:
				nxt = 0
		else:
			nxt = ST[9] - 1
			if nxt < 0:
				nxt = CELLS - 1
			# 反向走 CYCLE[nxt] → CYCLE[ST[9]]，方向就是正向表那一项的反向
			#（DIRS = [N, E, S, W]，反向 = 下标 +2 取模）
			d = (CYCLE_DIR[nxt] + 2) % 4
		if move(DIRS[d]):
			ST[9] = nxt
			DIAG[1] = DIAG[1] + 1
			if on_apple == 1:
				eaten = eaten + 1
				ST[1] = ST[1] + 1
				no_eat = 0
				if eaten % 40 == 0:
					print("[dino] eaten", eaten, "steps", steps, "cactus", num_items(Items.Cactus),
						"mode d/c/t", DIAG[0], DIAG[1], DIAG[2], "guard d/n", DIAG[5], DIAG[6])
			else:
				no_eat = no_eat + 1
				if no_eat > CELLS * 4:
					# 仙人掌不够 ⇒ 不再刷新苹果 ⇒ 别空转
					print("[dino] no apple for", no_eat, "steps, stopping at", eaten,
						"cactus", num_items(Items.Cactus))
					out = []
					append(out, eaten)
					append(out, steps)
					return out
		else:
			if flips == 0:
				# **只允许翻一次方向**。进紧循环的那一刻，身体完全可能正挡在「回路正向」
				# 那条路上：B1 的 cycle_step 在前向被挡时会**反向走一格**，所以无人机
				# 可能一直在**倒着**遍历回路。
				# 实测（v9 第一次实跑，2026-09-12）：进循环后**第 1 步**就被自己的身体挡住
				# ——`v9 cycle blocked at step 1743 eaten 28 pos 14 1`，整场白跑（28 颗 /
				# 12,544 骨头，而目标是 445 颗）。旧版 bare_cycle_move 同样只走正向，
				# 所以这是个一直潜伏的坑，只是 22x22 那次运气好没踩上。
				# 沿回路反向走同样是「回路上的一段弧」，安全性证明不变。
				flips = 1
				fwd = 1 - fwd
				print("[dino] v10 direction flip at step", steps, "eaten", eaten,
					"pos", get_pos_x(), get_pos_y(), "tail", ST[1])
			else:
				# 两个方向都走不动 = 蛇几乎填满农场 → 正常收工结算
				print("[dino] v10 cycle blocked at step", steps, "eaten", eaten,
					"pos", get_pos_x(), get_pos_y(), "tail", ST[1])
				out = []
				append(out, eaten)
				append(out, steps)
				return out
	out = []
	append(out, eaten)
	append(out, steps)
	return out


def dino_run(target):
	clear()
	change_hat(Hats.Dinosaur_Hat)
	ST[0] = 0
	ST[1] = 0
	ST[2] = -1
	ST[3] = -1
	ST[4] = 0
	ST[5] = -1
	ST[6] = 0
	ST[7] = 0
	ST[8] = 0
	i = 0
	while i < CELLS:
		OCC[i] = 0
		i = i + 1
	checked = 0
	eaten = 0
	steps = 0
	no_eat = 0
	# 安全检查自检：起点 (0,0) 周围明显是开阔地，两道检查都必须说「安全」。
	# 任何一道报不安全 ⇒ 该检查在这个解释器上求值不符合预期 ⇒ 关掉它（宁可冒险也别退回 v1 速度）。
	CHECK[0] = 1
	CHECK[1] = 1
	if escape2(1, 0, 0, 0) == 0:
		CHECK[0] = 0
		print("[dino] v8 self-test: guard1 disabled (escape2 says dead end at open start)")
	if body_neighbors(1, 0) >= 3:
		CHECK[1] = 0
		print("[dino] v8 self-test: guard2 disabled (body_neighbors wrong at open start)")
	print("[dino] v10 guards on:", CHECK[0], CHECK[1], CHECK[2])
	while eaten < target and steps < MAX_STEPS:
		steps = steps + 1
		on_apple = 0
		if get_entity_type() == Entities.Apple:
			on_apple = 1
			np = measure()
			if np == None:
				if checked == 0:
					print("[dino] measure() 没给出下一颗苹果的位置 —— 文档口径不符，请改用 dino_bones.py")
					change_hat(Hats.Straw_Hat)
					return eaten
			else:
				a, b = np
				ST[2] = a
				ST[3] = b
				ST[4] = 1
				if checked == 0:
					checked = 1
					print("[dino] first target", a, b, "from", get_pos_x(), get_pos_y())
		else:
			# 走到目标坐标却没有苹果 ⇒ 目标过期，丢弃（改由回路搜索重新撞上）
			if ST[4] == 1:
				if get_pos_x() == ST[2] and get_pos_y() == ST[3]:
					ST[4] = 0
					DIAG[4] = DIAG[4] + 1
					print("[dino] stale target at", ST[2], ST[3], "eaten", eaten, "steps", steps)

		moved = 0
		# ---- 阶段 B2 交接（v9）：身体已对齐回路，交给紧循环一次跑完 ----
		# 切过来的时机与 v8 相同：直走只在前 DIRECT_MAX 颗用，之后再走 2 颗带守卫的回路。
		# 对齐所需的最少步数 = 切换那一刻的尾巴长度；2 颗苹果的回路步数远大于它，所以
		# 「身体只剩回路上的一段连续弧」这个前提一定成立。
		# **直接 return**：原来在这里进入 B2 之后，每步仍要回到本循环跑完整套兜底阶梯，
		# 那正是实测「80 步/秒」的元凶。注意返回的是**真实吃到的颗数**（旧版撞墙时会把它
		# 改写成 target，日志上分不出「跑满」和「提前收工」）。
		if eaten >= DIRECT_MAX + 2:
			r = cycle_phase(target, eaten, steps)
			change_hat(Hats.Straw_Hat)
			return r[0]
		# ---- 阶段 A/B1：直走（只在前 DIRECT_MAX 颗）→ 带守卫的兜底阶梯 ----
		# 空格太少（尾巴几乎填满）→ 直走没有意义：直接常驻回路，省掉每步的检查与 BFS 开销
		if CHECK[2] == 1:
			if CELLS - ST[1] < TIGHT_FREE:
				if ST[6] == 0:
					ST[6] = 1
					ST[4] = 0
					print("[dino] v8 tight space -> cycle mode at eaten", eaten, "tail", ST[1])
		if ST[8] > 0:
			ST[8] = ST[8] - 1
		# 模式 1：直走 —— **只在前 DIRECT_MAX 颗**用（实测直走会在 30~40 颗附近盘死自己，
		# 而它省下的时间几乎全在前几颗：移动成本 400×0.97^k 衰减得很快）。
		if moved == 0 and ST[4] == 1 and ST[6] == 0 and ST[8] == 0 and eaten < DIRECT_MAX:
			moved = direct_step(ST[2], ST[3], on_apple)
			if moved == 0:
				d = bfs_first_step(ST[2], ST[3])
				if d >= 0:
					moved = safe_try_move(d, on_apple)
				else:
					DIAG[3] = DIAG[3] + 1
			if moved == 1:
				DIAG[0] = DIAG[0] + 1
				ST[7] = 0
			else:
				# 直走失败：不立刻切换（可能只是这一步被挡），而且**冷却 20 步**再试
				ST[7] = ST[7] + 1
				ST[8] = 20
				if ST[7] >= 5:
					ST[6] = 1
					ST[4] = 0
					DIAG[4] = DIAG[4] + 1
					print("[dino] v8 switch to cycle mode at eaten", eaten, "steps", steps,
						"deadend", DIAG[5], "narrow", DIAG[6], "bfs_fail", DIAG[3])
				else:
					print("[dino] v8 direct rejected at eaten", eaten, "steps", steps,
						"deadend", DIAG[5], "narrow", DIAG[6], "bfs_fail", DIAG[3],
						"pos", get_pos_x(), get_pos_y(), "tail", ST[1])
		# ---- 兜底阶梯（v7 关键改动：**带守卫的走法优先**）----
		# v6 的坑：守卫只管直走，兜底用的是不带守卫的 try_move，于是「苹果不可达 →
		# 长时间在兜底里走」那一段就把自己盘死了（guard 计数全程 0 就是证据）。
		# 顺序：跟尾巴（带守卫）→ 回路（带守卫）→ 跟尾巴（裸）→ 回路（裸）→ 任意方向。
		# 跟尾巴排在回路前面：尾尖一定会让开，是「保命优先」的走法。
		# 顺序分两种情形：直走期「保命优先」（跟尾巴在前），对齐期「回路优先」
		# （回路才是把身体拉回回路上的动作；跟尾巴只维持现状，不推进对齐）。
		if moved == 0:
			if eaten >= DIRECT_MAX:
				moved = cycle_step(on_apple, 1)
				if moved == 0:
					moved = tail_step(on_apple, 1)
			else:
				moved = tail_step(on_apple, 1)
				if moved == 0:
					moved = cycle_step(on_apple, 1)
		if moved == 0:
			moved = tail_step(on_apple, 0)
		if moved == 0:
			moved = cycle_step(on_apple, 0)
		if moved == 0:
			moved = any_step(on_apple)

		if moved == 0:
			print("[dino] stuck at step", steps, "eaten", eaten,
				"pos", get_pos_x(), get_pos_y(), "cactus", num_items(Items.Cactus))
			eaten = target
		else:
			if on_apple == 1:
				eaten = eaten + 1
				no_eat = 0
				ST[8] = 0          # 拿到新目标了，立刻允许再试直走
				ST[7] = 0
				if eaten % 40 == 0:
					print("[dino] eaten", eaten, "steps", steps, "cactus", num_items(Items.Cactus),
						"mode d/c/t", DIAG[0], DIAG[1], DIAG[2], "guard d/n", DIAG[5], DIAG[6])
			else:
				no_eat = no_eat + 1
				if no_eat > CELLS * 4:
					print("[dino] no apple for", no_eat, "steps, stopping at", eaten,
						"mode d/c/t", DIAG[0], DIAG[1], DIAG[2], "stale", DIAG[4])
					eaten = target
	change_hat(Hats.Straw_Hat)
	return eaten


def bone_buy_polyculture():
	# 骨头到手后把买得起的 Polyculture 级别一次买完（每级翻倍：x20 -> x40 -> x80 -> x160）
	bought = 0
	while bought < 3:
		cost = get_cost(Unlocks.Polyculture)
		if cost == None:
			return
		if len(cost) == 0:
			return
		ok = 1
		for item in cost:
			if num_items(item) < cost[item]:
				ok = 0
		if ok == 0:
			return
		if unlock(Unlocks.Polyculture):
			print("[dino] Polyculture upgraded -> lv", num_unlocked(Unlocks.Polyculture),
				"bone left", num_items(Items.Bone))
			bought = bought + 1
		else:
			return


def main():
	print("=== dino_fast v10 start ===")
	print("world_size", SIZE_OF_BOARD, "cells", CELLS, "max_cells_fill", MAX_APPLES,
		"max_steps", MAX_STEPS, "max_drones", max_drones())
	print("cactus", num_items(Items.Cactus), "bone", num_items(Items.Bone),
		"gold", num_items(Items.Gold), "dino_lv", num_unlocked(Unlocks.Dinosaurs))
	build_cycle()
	cactus = num_items(Items.Cactus)
	per = cactus_per_apple()
	mult = bone_multiplier(per)
	goal = bone_goal()
	need = goal - num_items(Items.Bone)
	if need < 0:
		need = 0
	# target = 最小的 t 使得 t² × mult ≥ need（不用 ** 运算符，本项目没验证过它）
	target = 10
	if need > 0:
		target = 1
		while target * target * mult < need:
			target = target + 1
	print("[dino] per_apple", per, "mult", mult, "bone_goal", goal,
		"need", need, "-> target_apples", target)
	if target > MAX_APPLES:
		print("[dino] WARNING: target", target, "over board limit -> capped", MAX_APPLES)
		target = MAX_APPLES
	affordable = (cactus - CACTUS_KEEP) // per
	if target > affordable:
		print("[dino] WARNING: cactus", cactus, "only affords", affordable, "apples -> target", affordable)
		target = affordable
	if target < 10:
		print("[dino] nothing to do: bone_goal", goal, "bone", num_items(Items.Bone),
			"cactus", cactus, "per_apple", per)
		return
	print("[dino] target_apples", target, "cactus_cost", target * per,
		"expected_bones", target * target * mult)
	b0 = num_items(Items.Bone)
	eaten = dino_run(target)
	b1 = num_items(Items.Bone)
	print("[dino] eaten", eaten, "bones_gained", b1 - b0, "total_bones", b1,
		"mode direct/cycle/tail", DIAG[0], DIAG[1], DIAG[2],
		"bfs_fail", DIAG[3], "dropped_targets", DIAG[4],
		"guard deadend/narrow", DIAG[5], DIAG[6])
	bone_buy_polyculture()
	print("=== dino_fast end ===")


if __name__ == "__main__":
	main()
