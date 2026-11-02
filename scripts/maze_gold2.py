# ============================================================
# maze_gold2.py —— **16 座 8x8 小迷宫并行刷金币**（目标 >= 2,000,000 金币/分钟）
#   v2（2026-10-05）：按实跑日志 + tick 级体检重写了走位与分派，见文件末尾的 v2 说明。
#
# ── 为什么（先读这段，否则会以为"多开几座迷宫"是拍脑袋）──
# 现状 `maze_gold.py`（32x32 单座满场迷宫 + 复用，31 架抢同一个宝藏）
#   实测 2026-10-05：164 次宝藏 / 468.5 秒 = **688,000 金币/分**（2.86 秒/宝藏）
#   要 2,000,000/分 ⇒ 每次宝藏 0.98 秒 ⇒ **还要快 2.9 倍**。
#
# 瓶颈是**走路**，不是收割：`measure()` 全场给出宝藏坐标（1 tick，免费），
# `use_item` 一次动作同时"收货 + 重定位"（200 tick）。离线模拟
# （`tools/maze_sim.py` / `maze_sim2.py` / `maze_sim3.py`）给出两条硬事实：
#
#   1. 32x32 生成树里，宝藏到「最近的家」的**真实树距离平均只有约 10 步**，
#      而现行的**贪心 DFS** 平均要走约 700 步（模拟）、实测反推约 87~185 步
#      ⇒ 现行算法浪费 4~70 倍，而且**迷宫越大浪费越狠**（搜索量 ∝ 迷宫面积）。
#   2. 一座 k x k 迷宫的内部墙数 = `(k-1)^2`：k=32 是 **961 面**，而"每次重定位
#      随机拆几面墙"在 300 次生命周期里**拆不完** ⇒ 大迷宫永远绕；
#      k=8 只有 **49 面** ⇒ 会被拆到全开，越刷越顺（小迷宫的结构性复利）。
#
# ── 本脚本的两条结构性改动 ──
#   A. 把棋盘切成 **16 座 8x8 小迷宫**，每座 **2 架**无人机（32 架正好）。
#      每座迷宫有**自己的宝藏** ⇒ 16 个宝藏同时推进（真并行，而不是 32 架抢 1 个）。
#   B. 每架**自己探一遍自己的迷宫**（64 格）**并建图**，用 BFS 距离场**走最短路**。
#      探测一次约 5 秒，而一座迷宫的寿命 = 301 次宝藏（复用上限 300）
#      ⇒ 摊销掉可以忽略。
#
# ── 金币账（lv6：`gold = 面积 x 2^(lv-1)` = 面积 x 32）──
#   8x8 一次宝藏 = 64 x 32 = **2,048 金币**；16 座 ⇒ 全场一轮 = 32,768 金币，
#   与满场迷宫一次宝藏**同值**，但一轮的墙钟是"一次最短路"（12~18 步 = 0.4~0.6 秒），
#   而不是"一次满场搜索"（2.86 秒）。
#   目标 2,000,000/分 = 976 次宝藏/分 = 每座每 0.98 秒一次 ⇒ 在预算内 ✓
#
# ── 小迷宫的落点规则是未知数 ⇒ 开局用探针实测，不猜 ──
#   `use_item(Items.Weird_Substance, k * 2^(lv-1))` 长出 k x k 迷宫，但**它落在
#   以无人机为中心还是以脚下为左上角**，这个存档从来没测过。所以：
#   在**两个不同锚点**各建一座 4x4 探针迷宫，沿墙走遍 16 格量出包围盒，
#   反推平移量 (ox, oy)；两次结果不一致（说明被棋盘边界裁剪了）就**不跑**，
#   只打印诊断。锚点公式对任何"固定平移"规则都成立，不需要知道是哪一种。
#
# ── 自愈（都是本项目踩过的坑）──
#   * `move()` 失败 ⇒ 把那一面记成墙 + 重做距离场（地图自愈，绝不空转）。
#   * 宝藏在脚下但 `use_item` 不给金币 ⇒ 判"迷宫耗尽"（复用 300 次上限）⇒ 拆掉重建。
#   * `use_item` 不给金币但宝藏**已经不在这格** ⇒ 被同区另一架抢先 ⇒ **绝不 harvest**
#     （在非宝藏处 harvest() 会把整座迷宫抹掉 —— maze_gold.py 踩过两次）。
#   * 一副无人机不共享内存 ⇒ 所有跨机信息只走 `spawn_drone` 的参数 ✓
#     （模块全局在副机里是"初始值"，所以探针结果必须当参数传过去）。
#
# 本脚本只刷钱，不种田。跑完切回 main.py 即可。
#
# ============================================================
# v2 优化（依据 2026-10-05 的实跑日志 + tick 级体检）
#
# 实跑读数（`output.txt`，lv6，16 座）：`gold_per_min` 从 398k 爬到 **947k** 就压住了，
# 而 power 从 35,332 掉到 30,873 = **32.3 点/秒**。按"1 点 = 30 个动作 = 6,000 tick"
# 折算 ⇒ **32 架无人机都在 100% 烧自己的 tick 预算**（6,060 tick/秒/架）。
# 也就是说：产量不是被"走位"卡住的，是被**空转的语句**吃掉的。
#
# `tools/maze_profile.py`（settrace 数语句 + 标定过的 tick 成本表）量出：
#   * hunter 追一次宝藏 = 3,741 条语句 + 15.7 次 move = **6,401 tick = 1.05 秒**
#     ⇒ 单座上限 0.95 次/秒 ⇒ 16 座 1.87M/分；而实测只有 0.54 次/秒（1.07M/分），
#     差的 0.8 秒就是下面第 1、2 条开销。
#   * 空轮询一圈只要 **9.8 tick**（620 次/秒）⇒ "等"从来不贵，**贵的是 BFS**。
#
# 四处改动（代码里都标了 `v2`）：
#   1. **距离场按目标缓存**（`FTX/FTY` + `ensure_field`）：宝藏没换就**不再重算**。
#      旧版每圈都重算，而且 hunter 追一次要算两次（分派一次 + chase 一次）✗✗
#   2. **分派改用"两家的距离场"**（`DH`/`DO`，每 20 秒刷新）：判据 `DH[宝藏]` vs
#      `DO[宝藏]` 是 **O(1)**，而且两架的规则**完全对称** ⇒ 不会出现"两架都不去"
#      的 0.8 秒空档（旧版要靠 MAX_KEEP_S 兜底，实测那 0.8 秒就是速率的天花板）。
#   3. **邻居表 `NB`**：一次算好"这格的四个邻居是谁"，BFS/走位里省掉两次取模。
#   4. **空轮询不再带 `wait_s`**：一圈 10 tick，反应延迟从约 0.33 秒降到毫秒级。
# ============================================================

SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD
DIRS = [North, East, South, West]
DIR_DX = [0, 1, 0, -1]
DIR_DY = [1, 0, -1, 0]
BIT = [1, 2, 4, 8]

# ---- 布局：16 座 8x8（32 = 4 x 8）----
# 约束：N_MAZE * PER_REG 必须 <= 32（无人机上限，含主机），否则有迷宫没人管。
#   REG=8  ⇒ 16 座 x 2 架 = 32 ✓（默认）
#   REG=16 ⇒  4 座 x 8 架 = 32 ✓（但 BFS 距离场要 256 格，每次宝藏多花约 0.27 秒）
#   REG=4  ⇒ 64 座，32 架不够（每架得管 2 座）⇒ 本布局公式不支持
REG = 8
NREG = SIZE_OF_BOARD // REG
PER_REG = 2
N_MAZE = NREG * NREG
N_WORKER = N_MAZE * PER_REG          # 32 = 主机 + 31 架副机

MAZE_LV = num_unlocked(Unlocks.Mazes)
MULT = 1
if MAZE_LV > 1:
	MULT = 2 ** (MAZE_LV - 1)
SUB_PER = REG * MULT                 # 建迷宫 = 每次重定位 = 这么多物质
GOLD_PER = REG * REG * MULT          # 一次宝藏的金币

# ---- 参数 ----
# GOAL_GAIN：本次要刷的金币**增量**（相对开局库存）。10M 是为了让"速率"有意义 ——
# 目标 2M/分 ⇒ 约 5 分钟；若实测有 4M/分 ⇒ 约 2.5 分钟。
# 想短跑就改小（例如 2000000 = 约 1 分钟），想长跑改大（库存物质够 36M/256 ≈ 14 万次）。
GOAL_GAIN = 10000000
WINDOW_S = 8.0                       # 派完副机到"同时建迷宫"的窗口（留给走位）
REPORT_SEC = 10                      # 主机每这么多秒打一行 [stat]
MAX_HUNT_STEPS = 400                 # 单次追捕步数上限（8x8 迷宫最长路径 63）
MAX_CHASE_ROUNDS = 16                # 一次追捕里重做距离场的次数上限
MAX_KEEP_S = 0.8                     # 兜底：宝藏这么久没人拿 ⇒ 我也上（v2 起几乎不会触发）
REFIELD_S = 20.0                     # 两家的距离场每这么多秒重建一次（兜底）
REFIELD_DIRTY_S = 4.0                # 地图发现新通道后，最快这么久重建一次距离场
WAIT_MAZE_S = 25.0                   # pair 1 等队友重建迷宫的上限（之后自己上）
STALL_S = 3.0                        # 让位兜底：同一个宝藏这么久没人拿 ⇒ 我去（防队友失联）
# WALL_REPORT：每座迷宫寿命结束时探一次图数"拆了多少墙"。这是纯诊断（要 5~6 秒），
# 数据已经够了（实测每 14 次重定位拆 1 面）⇒ **默认关闭**，要看就改 1。
WALL_REPORT = 0
# ---- 探针必须用**和正式区域一样的边长** ----
# 平移量 (ox,oy) 只有在"落点规则对尺寸一致"时才能跨尺寸套用：
#   * 以脚下为左上角 ⇒ 平移量恒为 0 ✓ 与尺寸无关
#   * 以无人机为中心 ⇒ 平移量 = -k/2 ✗ **与尺寸有关**（4x4 是 -2、8x8 是 -4）
# 用 4x4 探针去推 8x8 的布局会**整体偏移 2 格**，16 座就拼不满了。
# 所以探针直接用 REG（8x8，64 格，探测约 4~5 秒，物质 256 个）。
PROBE_K = 8
PROBE_ONLY = 0                       # 1 = 只探针 + 打印布局，不跑
PROBE_AT_X = [16, 4]
PROBE_AT_Y = [16, 4]

# ---- 每机一份的状态（模块全局 = 每架无人机各一份）----
OPEN = []                            # 每格已知可通方向的 4 位掩码
PROBED = []                          # 每格是否已经量过四向
VIS = []                             # 探测 DFS 的访问标记（世代号）
PATH = []                            # 探测 DFS 的路径栈
DIST = []                            # BFS 距离场（**以宝藏为源**，按目标缓存）
DSTAMP = []                          # 距离场的世代戳
BFSQ = []                            # BFS 队列（预分配，按下标写）
# ---- v2：邻居表 + 两家的距离场 ----
# NBT：几何邻居（开局一次算好，永不改变）；NB：**已知可通**的邻居（-1 = 墙/未知）。
# 有了 NB，BFS 内层不用再算两次取模 + 比 OPEN 的位，省掉一大半语句。
NBT = []
NB = []
DH = []                              # 我家的 BFS 距离（长期存在，每 REFIELD_S 秒刷新）
PH = []                              # 我家的 BFS **父指针**（指向家）⇒ 用来拉"家 → 宝藏"的链
DO = []                              # 队友家的 BFS 距离
CHAIN = []                           # 路径缓冲（父链，倒着填）
MARK = []                            # v2：某格的祖先链是否已被"本世代"标记（找 LCA 用）
RGX = [0]                            # 本机负责的区域左上角（诊断用）
RGY = [0]
EDGES = [0]                          # 本座迷宫建好时的通道数（用来量复用拆了多少墙）
MAPDIRTY = [0]                       # 地图发现了新通道（复用拆墙）⇒ 距离场要重建
MGEN = [0]
FTX = [-1]                           # 当前 DIST 距离场是按哪个宝藏目标建的（v2 缓存）
FTY = [-1]
DFIELD = [0]                         # DH/DO 是否已经建好
GEN = [0]
BGEN = [0]
STAT = [0, 0, 0, 0]                  # [收到几次, 累计步数, 重建次数, 单次最大步数]
HOMEX = [0]
HOMEY = [0]
OTHX = [0]
OTHY = [0]
SESSION = [0.0, 0, 0]                # 主机用：[会话开始时间, 开始时金币, 上次报告时间]

_i = 0
while _i < CELLS:
	append(OPEN, 0)
	append(PROBED, 0)
	append(VIS, 0)
	append(PATH, 0)
	append(DIST, 0)
	append(DSTAMP, 0)
	append(BFSQ, 0)
	append(DH, -1)
	append(PH, -1)
	append(DO, -1)
	append(MARK, 0)
	_ix = _i % SIZE_OF_BOARD
	_iy = _i // SIZE_OF_BOARD
	_d = 0
	while _d < 4:
		append(NBT, ((_iy + DIR_DY[_d] + SIZE_OF_BOARD) % SIZE_OF_BOARD) * SIZE_OF_BOARD
			+ (_ix + DIR_DX[_d] + SIZE_OF_BOARD) % SIZE_OF_BOARD)
		append(NB, -1)
		_d = _d + 1
	_i = _i + 1
_i = 0
while _i < 256:
	append(CHAIN, -1)
	_i = _i + 1


# ------------------------------------------------------------
# 基础
# ------------------------------------------------------------
def cell_of(x, y):
	return (y % SIZE_OF_BOARD) * SIZE_OF_BOARD + (x % SIZE_OF_BOARD)


def goto_free(tx, ty, limit):
	# 空地上走直线（会检查 can_move，所以不会被别的迷宫卡死成死循环）
	tx = tx % SIZE_OF_BOARD
	ty = ty % SIZE_OF_BOARD
	steps = 0
	while steps < limit:
		x = get_pos_x()
		y = get_pos_y()
		if x == tx and y == ty:
			return steps
		moved = 0
		if x != tx:
			if get_pos_x() < tx:
				if can_move(East):
					move(East)
					moved = 1
			else:
				if can_move(West):
					move(West)
					moved = 1
		if moved == 0:
			if y != ty:
				if get_pos_y() < ty:
					if can_move(North):
						move(North)
						moved = 1
				else:
					if can_move(South):
						move(South)
						moved = 1
		if moved == 0:
			return -1
		steps = steps + 1
	return -1


def step_to(tx, ty):
	# 朝"相邻的一格"走一步（环形棋盘用模运算）
	x = get_pos_x()
	y = get_pos_y()
	dx = (tx - x + SIZE_OF_BOARD) % SIZE_OF_BOARD
	dy = (ty - y + SIZE_OF_BOARD) % SIZE_OF_BOARD
	if dx == 1:
		move(East)
	elif dx == SIZE_OF_BOARD - 1:
		move(West)
	elif dy == 1:
		move(North)
	else:
		move(South)


def scan_walls(c):
	# 量当前格四向的墙并写进地图（v2：同时维护 NB 邻居表）
	m = 0
	d = 0
	base = c * 4
	while d < 4:
		# ---- v2.5：**双向写**！----
		# 只写单向会造出"单向通道"：墙被复用拆掉后，只有路过的那一格会重新扫描，
		# 邻居那格还记着"墙" ⇒ BFS 能过来、沿场下坡回不去 ⇒ 原地来回震荡 ✗✗
		nb = NBT[base + d] * 4 + ((d + 2) % 4)
		if can_move(DIRS[d]):
			m = m + BIT[d]
			NB[base + d] = NBT[base + d]
			NB[nb] = c
		else:
			NB[base + d] = -1
			NB[nb] = -1
		d = d + 1
	if OPEN[c] != m:
		# 墙被"复用的重定位"拆掉了 ⇒ 地图变了，距离场要重建（实测每次重定位拆约 0.07 面）
		MAPDIRTY[0] = 1
	OPEN[c] = m
	PROBED[c] = 1
	return m


def probe_here():
	# 就地量一次四向（4 个 can_move = 4 tick，几乎免费）⇒ 复用拆掉的墙会在路过时被发现
	scan_walls(cell_of(get_pos_x(), get_pos_y()))


def count_open_in():
	# 数一遍本区域里"已知可通"的边数（每条边两端各数一次 ⇒ 除以 2）。
	# 生成树 = REG*REG-1 条边；棋盘全开 = 2*REG*(REG-1) 条边 ⇒ 两者之差就是内墙数。
	t = 0
	yy = 0
	while yy < REG:
		xx = 0
		while xx < REG:
			c = cell_of(RGX[0] + xx, RGY[0] + yy)
			if PROBED[c] == 1:
				m = OPEN[c]
				d = 0
				while d < 4:
					if (m // BIT[d]) % 2 == 1:
						t = t + 1
					d = d + 1
			xx = xx + 1
		yy = yy + 1
	return t // 2


def farthest_in_region(ax, ay, rx, ry):
	# 区域内离 (ax,ay) 最远的那一格（决定同区第二架的家）。确定性 ⇒ 两架算出来一样。
	bx = rx
	by = ry
	bd = -1
	yy = 0
	while yy < REG:
		xx = 0
		while xx < REG:
			cx = (rx + xx) % SIZE_OF_BOARD
			cy = (ry + yy) % SIZE_OF_BOARD
			dx = abs(cx - ax)
			if dx > SIZE_OF_BOARD // 2:
				dx = SIZE_OF_BOARD - dx
			dy = abs(cy - ay)
			if dy > SIZE_OF_BOARD // 2:
				dy = SIZE_OF_BOARD - dy
			if dx + dy > bd:
				bd = dx + dy
				bx = cx
				by = cy
			xx = xx + 1
		yy = yy + 1
	out = [bx, by]
	return out


# ------------------------------------------------------------
# 迷宫：建 / 拆 / 探（建图）
# ------------------------------------------------------------
def build_maze(ax, ay, tries):
	# 站在 (ax,ay)：种灌木 + 灌物质 ⇒ 迷宫在脚下长出来。返回 1 = 成功
	t = 0
	while t < tries:
		t = t + 1
		# ---- v2.3：**幂等化** ----
		# 实测事故：pair 1 等超时后先建好了迷宫，pair 0 随后也来种 ⇒ 锚点已经是树篱
		# ⇒ `plant()` 连续 8 次失败、再退避重试 ⇒ 那一区卡十几秒 ✗（日志里 `build 失败 ×7`）
		# 迷宫已经在就直接算"建好"，调用方随后会重新对齐地图 ✓
		e_now = get_entity_type()
		if e_now == Entities.Hedge:
			print("[maze2] build: 迷宫已经在（树篱）⇒ 视为建好")
			return 1
		if e_now == Entities.Treasure:
			print("[maze2] build: 迷宫已经在（宝藏）⇒ 视为建好")
			return 1
		if measure() != None:
			print("[maze2] build: measure 有值 ⇒ 迷宫已经在 ⇒ 视为建好")
			return 1
		plant(Entities.Bush)
		if get_entity_type() != Entities.Bush:
			# 地面类型不对时的兜底（maze_gold.py 的老办法：翻土再试一次）
			if get_ground_type() != Grounds.Soil:
				till()
				plant(Entities.Bush)
		if get_entity_type() == Entities.Bush:
			if use_item(Items.Weird_Substance, SUB_PER):
				e = get_entity_type()
				if e == Entities.Hedge:
					return 1
				if e == Entities.Treasure:
					return 1
		print("[maze2] build 失败 t", t, "| ground", get_ground_type(),
			"| entity", get_entity_type(),
			"| weird", num_items(Items.Weird_Substance),
			"| 需要", SUB_PER)
		wait_s(0.5)
	return 0


def wait_s(sec):
	t = get_time()
	while get_time() - t < sec:
		pass


def destroy_maze():
	# 在**非宝藏**格 harvest() 会让整座迷宫消失（文档）⇒ 先离开宝藏那一格
	if get_entity_type() == Entities.Treasure:
		d = 0
		moved = 0
		while d < 4:
			if moved == 0:
				if can_move(DIRS[d]):
					move(DIRS[d])
					moved = 1
			d = d + 1
	if get_entity_type() == Entities.Hedge:
		harvest()


def explore(k):
	# 站在迷宫内：走遍 k*k 格、逐格记下四向的墙。返回 [ok, cells, minx, miny, maxx, maxy, steps]
	GEN[0] = GEN[0] + 1
	g = GEN[0]
	depth = 0
	cnt = 0
	minx = 999
	miny = 999
	maxx = -1
	maxy = -1
	steps = 0
	limit = k * k * 8
	while cnt < k * k:
		if steps > limit:
			break
		steps = steps + 1
		x = get_pos_x()
		y = get_pos_y()
		c = y * SIZE_OF_BOARD + x
		if VIS[c] != g:
			VIS[c] = g
			cnt = cnt + 1
			if x < minx:
				minx = x
			if x > maxx:
				maxx = x
			if y < miny:
				miny = y
			if y > maxy:
				maxy = y
		m = scan_walls(c)
		pick = -1
		d = 0
		while d < 4:
			if (m // BIT[d]) % 2 == 1:
				nx = (x + DIR_DX[d] + SIZE_OF_BOARD) % SIZE_OF_BOARD
				ny = (y + DIR_DY[d] + SIZE_OF_BOARD) % SIZE_OF_BOARD
				if VIS[ny * SIZE_OF_BOARD + nx] != g:
					pick = d
					d = 4
			d = d + 1
		if pick >= 0:
			# 注意：**先确认走成功、且还在迷宫里，再压栈** —— 否则 PATH 的
			# 不变式（PATH[0..depth-1] = 从起点到当前格的路径）会被破坏，
			# 回退时会退到错误的格子上去。
			if not move(DIRS[pick]):
				OPEN[c] = OPEN[c] - BIT[pick]
				NB[c * 4 + pick] = -1
				NB[NBT[c * 4 + pick] * 4 + ((pick + 2) % 4)] = -1
				continue
			t = get_entity_type()
			if t != Entities.Hedge:
				if t != Entities.Treasure:
					# 这一步走出了迷宫（边界上其实有个口子）⇒ 退回并记成墙（v2.5：双向）
					move(DIRS[(pick + 2) % 4])
					OPEN[c] = OPEN[c] - BIT[pick]
					NB[c * 4 + pick] = -1
					NB[NBT[c * 4 + pick] * 4 + ((pick + 2) % 4)] = -1
					steps = steps + 1
					continue
			PATH[depth] = c
			depth = depth + 1
		else:
			if depth == 0:
				break
			depth = depth - 1
			prev = PATH[depth]
			step_to(prev % SIZE_OF_BOARD, prev // SIZE_OF_BOARD)
			steps = steps + 1
	ok = 0
	if cnt >= k * k:
		ok = 1
	out = [ok, cnt, minx, miny, maxx, maxy, steps]
	return out


# ------------------------------------------------------------
# 距离场（BFS）与沿场走位
# ------------------------------------------------------------
def invalidate_fields():
	# ---- 地图一变（探测/重建完），**两个缓存都必须作废** ----
	# FTX/FTY 是"宝藏距离场"的缓存键：不作废的话，新宝藏恰好是旧目标时
	# `ensure_field` 会以为场还有效，于是拿**旧迷宫的距离场**去走位 ⇒ 原地打转（实测踩过）。
	FTX[0] = -1
	FTY[0] = -1
	DFIELD[0] = 0


def field_to(tx, ty, ox, oy):
	# ---- v2.4：从**宝藏**做 BFS，但**标到 (ox,oy) 就停** ----
	# 我们要的只是"我脚下 → 宝藏"这一条路，不需要整张场：
	# 早停把一次 BFS 从 64 格降到 20~40 格，而且给出的是**图上的真最短路**
	# （LCA 走的是"家的 BFS 树"上的路径，迷宫有环之后就比最短路长近一倍 ✗）。
	# 返回 1 = (ox,oy) 可达（DIST/DSTAMP 里已经有它的距离，可以直接沿场下坡走）
	BGEN[0] = BGEN[0] + 1
	g = BGEN[0]
	s = cell_of(tx, ty)
	tgt = cell_of(ox, oy)
	BFSQ[0] = s
	qh = 0
	qt = 1
	DSTAMP[s] = g
	DIST[s] = 0
	FTX[0] = tx % SIZE_OF_BOARD
	FTY[0] = ty % SIZE_OF_BOARD
	found = 0
	while qh < qt:
		c = BFSQ[qh]
		qh = qh + 1
		if c == tgt:
			found = 1
			break
		nd = DIST[c] + 1
		base = c * 4
		d = 0
		while d < 4:
			n = NB[base + d]
			if n >= 0:
				if DSTAMP[n] != g:
					DSTAMP[n] = g
					DIST[n] = nd
					BFSQ[qt] = n
					qt = qt + 1
			d = d + 1
	return found


def bfs_fill(sx, sy, ARR):
	# 从 (sx,sy) 做 BFS，把距离写进 ARR（不可达 = -1）。只给"两家的距离场"用（每 20 秒一次）
	i = 0
	while i < CELLS:
		ARR[i] = -1
		i = i + 1
	s = cell_of(sx, sy)
	ARR[s] = 0
	BFSQ[0] = s
	qh = 0
	qt = 1
	while qh < qt:
		c = BFSQ[qh]
		qh = qh + 1
		nd = ARR[c] + 1
		base = c * 4
		d = 0
		while d < 4:
			n = NB[base + d]
			if n >= 0:
				if ARR[n] < 0:
					ARR[n] = nd
					BFSQ[qt] = n
					qt = qt + 1
			d = d + 1
	return qt


def home_field():
	# ---- v2 的核心：从**我家**出发做一次 BFS，同时留下距离 DH 与**父指针 PH** ----
	# PH[格] = 这一格朝家走的下一格。有了它，"家 → 任意宝藏"这条链可以在**内存里**
	# 直接拉出来倒着走（约 dist 条语句），**每次宝藏就不用再算 BFS 了**。
	# 实测：一次 64 格 BFS 要 1,815 行，占了 hunter 全部开销的 71% ✗✗
	i = 0
	while i < CELLS:
		DH[i] = -1
		PH[i] = -1
		i = i + 1
	s = cell_of(HOMEX[0], HOMEY[0])
	DH[s] = 0
	BFSQ[0] = s
	qh = 0
	qt = 1
	while qh < qt:
		c = BFSQ[qh]
		qh = qh + 1
		nd = DH[c] + 1
		base = c * 4
		d = 0
		while d < 4:
			n = NB[base + d]
			if n >= 0:
				if DH[n] < 0:
					DH[n] = nd
					PH[n] = c
					BFSQ[qt] = n
					qt = qt + 1
			d = d + 1
	return qt


def home_fields():
	# ---- v2：建/刷新"我家的距离场+父指针"（DH/PH）与"队友家的距离场"（DO）----
	# 分派（谁去）与回家（沿 DH 下坡）都靠它：判据 O(1)、两架规则**完全对称**
	# ⇒ 不会出现"两架都不去、白等 0.8 秒"（旧版靠 MAX_KEEP_S 兜底）。
	home_field()
	bfs_fill(OTHX[0], OTHY[0], DO)
	DFIELD[0] = 1
	MAPDIRTY[0] = 0        # 场刚按当前地图重建过 ⇒ 不再是脏的


def step_dir(x, y, nx, ny):
	# 朝"相邻的一格"走一步；返回 1 = 成功
	dx = (nx - x + SIZE_OF_BOARD) % SIZE_OF_BOARD
	dy = (ny - y + SIZE_OF_BOARD) % SIZE_OF_BOARD
	if dx == 1:
		return move(East)
	if dx == SIZE_OF_BOARD - 1:
		return move(West)
	if dy == 1:
		return move(North)
	if dy == SIZE_OF_BOARD - 1:
		return move(South)
	return 0


def check_target(tx, ty):
	# 走一步之后的例行检查：0 = 继续 | 1 = 站上宝藏 | 2 = 宝藏被挪走 | 3 = 迷宫没了
	t = get_entity_type()
	if t == Entities.Treasure:
		return 1
	if t != Entities.Hedge:
		return 3
	tp = measure()
	if tp == None:
		return 3
	a, b = tp
	if a != tx or b != ty:
		return 2
	return 0


def route_to(tx, ty, limit):
	# ---- v2 的核心：**从当前位置**走到宝藏，全程零 BFS ----
	# 迷宫本身是一棵树，而 PH 是"以我家为根的 BFS 父指针"⇒ 任意两点之间的唯一路径 =
	# 它们到 **LCA（最近公共祖先）** 的两段。于是：
	#   1) 沿 PH 把宝藏 T 的祖先链打上标记（内存操作，约 dist 条语句）；
	#   2) 从当前位置**朝家走**，第一个踩到的标记格就是 LCA —— 这段是物理走位，
	#      而且**本来就是必经之路**，一点不浪费；
	#   3) 把 T → LCA 的链拉出来倒着走 ⇒ 到达宝藏。
	# 对比旧版：算一整张 64 格 BFS 要 1,815 行（占 hunter 全部开销的 71%），而本函数只要约 300 行。
	# 返回 [状态, 步数]：1 到宝藏 | 2 宝藏被挪走 | 3 迷宫没了 | 4 走不通（调用方退化）
	tc = cell_of(tx, ty)
	if DH[tc] < 0:
		return [4, 0]                     # 地图里到不了它 ⇒ 交给退化路径
	# 注意：**不能用 `PH[tc] < 0` 当判据** —— 宝藏正好落在我家那一格时 PH[根] = -1，
	# 那是"距离 0、已经到了"，不是"到不了"（实测踩过：宝藏在 (0,0) 时 chase 空转 16 轮）。
	MGEN[0] = MGEN[0] + 1
	mg = MGEN[0]
	n = 0
	c = tc
	while n < 256:
		if MARK[c] == mg:
			break
		MARK[c] = mg
		n = n + 1
		c = PH[c]
		if c < 0:
			# PH 为 -1 说明上一格就是**我家的根**，而它已经被标记过了 ⇒ 正常收尾
			break
	steps = 0
	# 2) 朝家走，直到踩到 T 的祖先（= LCA）
	while MARK[cell_of(get_pos_x(), get_pos_y())] != mg:
		if steps >= limit:
			return [4, steps]
		x = get_pos_x()
		y = get_pos_y()
		pc = PH[y * SIZE_OF_BOARD + x]
		if pc < 0:
			return [4, steps]
		if step_dir(x, y, pc % SIZE_OF_BOARD, pc // SIZE_OF_BOARD) == 0:
			return [4, steps]
		steps = steps + 1
		r = check_target(tx, ty)
		if r != 0:
			return [r, steps]
	# 3) 从 LCA 沿 T 的链倒着走到 T
	lca = cell_of(get_pos_x(), get_pos_y())
	n = 0
	c = tc
	while n < 256:
		if c == lca:
			break
		CHAIN[n] = c
		n = n + 1
		c = PH[c]
		if c < 0:
			return [4, steps]
	i = n - 1
	while i >= 0:
		if steps >= limit:
			return [4, steps]
		x = get_pos_x()
		y = get_pos_y()
		nx = CHAIN[i] % SIZE_OF_BOARD
		ny = CHAIN[i] // SIZE_OF_BOARD
		if x != nx or y != ny:
			if step_dir(x, y, nx, ny) == 0:
				return [4, steps]
			steps = steps + 1
			# v2.7：**hunter 的路一步都不探** —— 探测改到让位那架的回家路上做（见 walk_home），
			# 这样学习成本完全落在闲机上，关键路径只剩"走路 + 收货" ✓
			r = check_target(tx, ty)
			if r != 0:
				return [r, steps]
		else:
			i = i - 1
	return [1, steps]


def walk_home(limit):
	# 沿 DH 下坡走回自己的家。返回 1 = 到家
	steps = 0
	while steps < limit:
		x = get_pos_x()
		y = get_pos_y()
		c = y * SIZE_OF_BOARD + x
		if DH[c] == 0:
			return 1
		if DH[c] < 0:
			return 0
		best = -1
		bd = DH[c]
		base = c * 4
		d = 0
		while d < 4:
			n = NB[base + d]
			if n >= 0:
				if DH[n] >= 0:
					if DH[n] < bd:
						bd = DH[n]
						best = d
			d = d + 1
		if best < 0:
			return 0
		if not move(DIRS[best]):
			NB[c * 4 + best] = -1
			NB[NBT[c * 4 + best] * 4 + ((best + 2) % 4)] = -1
			return 0
		steps = steps + 1
		# ---- v2.7：**让位那架的回家路 = 免费的学习时间** ----
		# 这条路不在关键路径上（同区另一架正在追宝藏），所以每步都探也不亏：
		# 探测会把"被复用拆掉的墙"记进地图，随后重建的距离场就带上了新捷径 ✓
		probe_here()
	return 0


def walk_field(tx, ty, limit):
	# 沿距离场走向宝藏。返回 [状态, 步数]
	#   1 = 站上宝藏了 | 2 = 宝藏被挪走 | 3 = 迷宫没了 | 4 = 走不动（要重做距离场）
	steps = 0
	while steps < limit:
		x = get_pos_x()
		y = get_pos_y()
		t = get_entity_type()
		if t == Entities.Treasure:
			return [1, steps]
		if t != Entities.Hedge:
			return [3, steps]
		c = y * SIZE_OF_BOARD + x
		if DIST[c] == 0:
			return [4, steps]
		tp = measure()
		if tp == None:
			return [3, steps]
		a, b = tp
		if a != tx or b != ty:
			return [2, steps]
		best = -1
		bd = 999999
		base = c * 4
		d = 0
		while d < 4:
			n = NB[base + d]
			if n >= 0:
				if DSTAMP[n] == BGEN[0]:
					if DIST[n] < bd:
						bd = DIST[n]
						best = d
			d = d + 1
		if best < 0:
			return [4, steps]
		if not move(DIRS[best]):
			# 地图与现实不符：记下这面墙（v2.5：**双向**都要记），交给调用方重做距离场
			NB[c * 4 + best] = -1
			NB[NBT[c * 4 + best] * 4 + ((best + 2) % 4)] = -1
			OPEN[c] = OPEN[c] - BIT[best]
			return [4, steps]
		steps = steps + 1
	return [4, steps]


def chase(tx, ty):
	# 追一次宝藏。返回 1 = 收到并重定位 | 0 = 重试用尽 | 3 = 迷宫没了 | 4 = 迷宫耗尽
	rnd = 0
	while rnd < MAX_CHASE_ROUNDS:
		rnd = rnd + 1
		# ---- v2.6 的路线选择（用虚拟时钟台架量过，别凭直觉改回来）----
		# 1) 优先：**LCA 父链** —— 规划几乎免费（只拉一条链），走位约 8~10 步；
		# 2) 兜底：**早停 BFS** —— 给出真最短路，但一次要吃 20~64 格（约 0.24 秒规划），
		#    实测"省下的走位"抵不过"多出来的规划"（0.751 秒 vs 0.652 秒）✗
		#    ⇒ 只在父链走不通时才用它 ✓
		r = route_to(tx, ty, MAX_HUNT_STEPS)
		if r[0] == 4:
			f = 0
			if FTX[0] == tx and FTY[0] == ty:
				if DSTAMP[cell_of(get_pos_x(), get_pos_y())] == BGEN[0]:
					f = 1                    # 缓存还有效（目标没换、我在场里）
			if f == 0:
				f = field_to(tx, ty, get_pos_x(), get_pos_y())
			if f == 1:
				r = walk_field(tx, ty, MAX_HUNT_STEPS)
		STAT[1] = STAT[1] + r[1]
		if r[1] > STAT[3]:
			STAT[3] = r[1]
		st = r[0]
		if st == 1:
			# 站上宝藏：**一次 use_item 同时收货 + 重定位**（文档）
			g0 = num_items(Items.Gold)
			use_item(Items.Weird_Substance, SUB_PER)
			if num_items(Items.Gold) > g0:
				STAT[0] = STAT[0] + 1
				return 1
			# 没给金币：是被同区另一架抢先，还是迷宫耗尽？**绝不用 harvest 兜底**
			tp = measure()
			if tp == None:
				return 3
			a, b = tp
			if a != tx or b != ty:
				tx = a
				ty = b
				continue
			return 4
		if st == 2:
			tp = measure()
			if tp == None:
				return 3
			a, b = tp
			tx = a
			ty = b
			continue
		if st == 3:
			return 3
	return 0


# ------------------------------------------------------------
# 一架无人机的完整生命周期
#   slot: 0..31（含主机）；每 2 个 slot 一座迷宫，pair 0 = 建迷宫的那架
# ------------------------------------------------------------
def worker(slot, go_time, goal, ox, oy):
	i = slot // PER_REG
	pair = slot % PER_REG
	rx = REG * (i % NREG)
	ry = REG * (i // NREG)
	ax = (rx - ox + SIZE_OF_BOARD) % SIZE_OF_BOARD
	ay = (ry - oy + SIZE_OF_BOARD) % SIZE_OF_BOARD
	RGX[0] = rx
	RGY[0] = ry
	far = farthest_in_region(ax, ay, rx, ry)
	if pair == 0:
		HOMEX[0] = ax
		HOMEY[0] = ay
		OTHX[0] = far[0]
		OTHY[0] = far[1]
	else:
		HOMEX[0] = far[0]
		HOMEY[0] = far[1]
		OTHX[0] = ax
		OTHY[0] = ay
	# 1) 到自己那一格（此时全盘还是空地，直线走得到）
	got_home = goto_free(HOMEX[0], HOMEY[0], 400)
	# 2) 等到约定的时刻再一起建迷宫（否则先建的树篱会把后到的挡在外面）
	while get_time() < go_time:
		pass
	# 3) 建迷宫：pair 0 负责建，pair 1 等它出现（等不到就自己来）
	ok = 0
	if pair == 0:
		ok = build_maze(ax, ay, 6)
	else:
		t_wait = get_time()
		while get_time() - t_wait < 12:
			e = get_entity_type()
			if e == Entities.Hedge:
				ok = 2
				break
			if e == Entities.Treasure:
				ok = 2
				break
		if ok == 0:
			# 队友没建成（它可能走错了 / 灌木种不上）⇒ 我自己来
			goto_free(ax, ay, 200)
			ok = build_maze(ax, ay, 6)
	print("[maze2] slot", slot, "reg", i, "pair", pair,
		"| 家", HOMEX[0], HOMEY[0], "| 队友家", OTHX[0], OTHY[0],
		"| 建迷宫", ok, "(0=失败 1=我建的 2=队友建的)",
		"| 到家的步数", got_home,
		"| 脚下", get_entity_type(), "| measure", measure())
	# 4) 探一遍自己的迷宫并建图（64 格），再走回自己那一格
	t_ex = get_time()
	ex = explore(REG)
	print("[maze2] slot", slot, "explore ok", ex[0], "cells", ex[1],
		"bbox", ex[2], ex[3], ex[4], ex[5], "steps", ex[6],
		"耗时", get_time() - t_ex)
	if ex[0] == 0:
		print("[maze2] slot", slot, "探测失败 ⇒ 本机退出")
		return 0
	invalidate_fields()      # v2：地图变了 ⇒ 两个缓存都要作废
	home_fields()
	back = walk_home(200)
	EDGES[0] = count_open_in()
	print("[maze2] slot", slot, "回位步数", back,
		"| 本座初始通道数", EDGES[0], "（生成树", REG * REG - 1,
		"，全开", 2 * REG * (REG - 1), "）")
	# 5) 追捕循环（v2 重写）
	#    * 分派判据 = `DH[宝藏]` vs `DO[宝藏]`（两家的距离场，O(1)、**两架规则对称**）
	#      ⇒ 不会出现"两架都不去"的空档；也不需要在等待里做任何 BFS。
	#    * 空轮询一圈只要约 10 tick（实测 620 次/秒）⇒ 反应延迟是毫秒级。
	lastx = -1
	lasty = -1
	mine = 0
	ref_t = get_time()
	keep_t = get_time()
	bad = 0
	while True:
		if num_items(Items.Gold) >= goal:
			break
		if slot == 0:
			report()
		tp = measure()
		if tp == None:
			# ---- 迷宫没了：**只有 pair 0 有权重建**（v2.1 修的 bug）----
			# 实测事故：一座迷宫耗尽时同区两架**同时**发现（一架 r==4、另一架 measure 变 None）
			# ⇒ 两架都去拆+种+灌 ⇒ 互相抹掉对方刚建好的迷宫 ⇒ 11 架接连"重建失败"退出 ✗✗
			if handle_lost(ax, ay, pair, slot) == 0:
				break
			continue
		tx = tp[0]
		ty = tp[1]
		if tx != lastx or ty != lasty:
			# 换了宝藏 ⇒ 重新分派（这一步是 O(1)，不碰 BFS）
			lastx = tx
			lasty = ty
			keep_t = get_time()
			# ---- v2.7：hunter 这边**只在场缺失时兜底建一次** ----
			# 平时的"脏了重建"挪到让位分支（闲机）去做 ⇒ 不占关键路径 ✓
			if DFIELD[0] == 0:
				ref_t = get_time()
				MAPDIRTY[0] = 0
				home_fields()
			dm = DH[ty * SIZE_OF_BOARD + tx]
			dq = DO[ty * SIZE_OF_BOARD + tx]
			mine = 0
			if dm < 0:
				mine = 1                      # 我的场到不了它 ⇒ 自己去（别干等）
			elif dq < 0:
				mine = 1
			elif dm < dq:
				mine = 1
			elif dm == dq:
				if pair == 0:
					mine = 1                  # 平手时 pair 0 去（两架算法一致 ⇒ 恰好一架去）
		if mine == 0:
			# ---- 让位兜底（v2.1d）：队友可能已经退出了 ⇒ 不能无限等 ----
			# 实测：11 架"重建失败⇒本机退出"之后，剩下那架会在"该队友去"的宝藏上永远让位 ✗
			if get_time() - keep_t > STALL_S:
				mine = 1
				keep_t = get_time()
			else:
				# ---- v2.7：**让位分支 = 干学习活的地方**（这些都是闲机时间，不占关键路径）----
				# ① 地图脏了（复用拆了墙）就重建两家的距离场 ⇒ hunter 随后走的就是新捷径
				if DFIELD[0] == 1:
					if MAPDIRTY[0] == 1:
						if get_time() - ref_t > REFIELD_DIRTY_S:
							ref_t = get_time()
							MAPDIRTY[0] = 0
							home_fields()
					elif get_time() - ref_t > REFIELD_S:
						ref_t = get_time()
						home_fields()
				# ② 回自己的家待命（路上每步都探测，顺手把新通道记进地图）
				if get_pos_x() != HOMEX[0] or get_pos_y() != HOMEY[0]:
					if walk_home(200) == 0:
						# 走不回去（地图不一致）⇒ 退化：自己去追
						mine = 1
						continue
				continue
		# 我是 hunter：直接出发（v2 的 route_to 从**当前位置**就能算路，不需要先回家）
		r = chase(tx, ty)
		if r == 1:
			bad = 0
		if r == 3:
			# r==3 = 迷宫没了（多半是队友正在重建）⇒ 走统一协调，**绝不自己乱拆**
			if handle_lost(ax, ay, pair, slot) == 0:
				break
		elif r == 4:
			print("[maze2] slot", slot, "迷宫耗尽（复用 300 次上限）")
			if pair == 0:
				# ---- 量一下"复用 300 次到底拆掉了多少墙"----
				# 这是回答"要不要改用 32x32 大迷宫"的关键实测：拆墙按**每次重定位**发生，
				# 与迷宫大小无关；但 k=8 只有 49 面内墙、k=32 有 961 面。
				# v2.2：这次探图要 5~6 秒 ⇒ 每 2 座寿命量一次就够（省约 2% 的墙钟）。
				if WALL_REPORT == 1:
					ex3 = explore(REG)
					e1 = count_open_in()
					print("[maze2] slot", slot, "本座寿命内通道数", EDGES[0], "->", e1,
						"（复用 300 次新增", e1 - EDGES[0], "条通道 = 拆掉约",
						e1 - EDGES[0], "面墙）")
			if handle_lost(ax, ay, pair, slot) == 0:
				break
		elif r == 0:
			# 连续追不到 ⇒ 地图可能已经不适用（例如迷宫被别人的脚本重建过）
			# ⇒ 强制重新探一遍，绝不允许在这里无限空转
			bad = bad + 1
			if bad >= 5:
				print("[maze2] slot", slot, "连续", bad, "次追不到 ⇒ 重新探测建图")
				bad = 0
				ex2 = explore(REG)
				invalidate_fields()
				home_fields()
				if ex2[0] == 0:
					if not rebuild_with_retry(ax, ay):
						print("[maze2] slot", slot, "重建连续失败 ⇒ 本机退出")
						break
	# 收工：把自己的迷宫拆掉（省得留下树篱挡住下一份脚本）
	destroy_maze()
	print("[maze2] slot", slot, "收工 | 收到", STAT[0], "次 | 累计步数", STAT[1],
		"| 单次最多", STAT[3], "| 重建", STAT[2], "次")
	return STAT[0]


def resync_maze():
	# 地图与距离场全部重新对齐：重新探一遍 -> 作废距离场缓存 -> 重建两家的场 -> 回家
	# 用在"队友重建了新迷宫"之后（那时手里的地图还是上一座的，直接用会走错路）
	# v2.2：探图前**先确认我确实在这座迷宫里面** —— 站在迷宫外面探图会一直在外面打转 ✗
	t = 0
	while t < 3:
		t = t + 1
		e = get_entity_type()
		if e == Entities.Hedge:
			break
		if e == Entities.Treasure:
			break
		print("[maze2] resync: 不在迷宫里（脚下", e, "位置", get_pos_x(), get_pos_y(),
			"家", HOMEX[0], HOMEY[0], "measure", measure(), "）⇒ 先回家")
		goto_free(HOMEX[0], HOMEY[0], 200)
		wait_s(0.5)
	if get_entity_type() != Entities.Hedge:
		if get_entity_type() != Entities.Treasure:
			return 0
	ex = explore(REG)
	invalidate_fields()
	home_fields()
	walk_home(200)
	EDGES[0] = count_open_in()
	return ex[0]


def resync_with_retry():
	# 重新对齐失败**不再一次就永久退出**（实测 7 架就是这么没的 ✗）⇒ 退避重试 3 次
	t = 0
	while t < 3:
		t = t + 1
		if resync_maze() == 1:
			return 1
		print("[maze2] resync 第", t, "次失败，等 2 秒再试")
		wait_s(2)
	return 0


def handle_lost(ax, ay, pair, slot):
	# ---- "迷宫没了 / 耗尽"时的**唯一**处理入口（v2.1c）----
	# 铁律：**只有 pair 0 有权拆和建**。pair 1 一律先回家等队友重建；
	# 等到就重新对齐地图，等不到（队友退出了）才自己上。
	# 为什么：一座迷宫耗尽时同区两架会**同时**发现（一架 r==4、另一架 measure 变 None
	# 或 r==3）⇒ 两架都拆都建 ⇒ 互相抹掉对方刚建好的迷宫 ⇒ 实测 11 架接连失败退出 ✗✗
	if pair == 0:
		if rebuild_with_retry(ax, ay) == 0:
			print("[maze2] slot", slot, "重建连续失败 ⇒ 本机退出")
			return 0
		return 1
	if wait_maze(WAIT_MAZE_S) == 0:
		print("[maze2] slot", slot, "等不到队友重建 ⇒ 我自己来")
		if rebuild_with_retry(ax, ay) == 0:
			print("[maze2] slot", slot, "重建连续失败 ⇒ 本机退出")
			return 0
		return 1
	print("[maze2] slot", slot, "队友重建好了 ⇒ 重新探图对齐")
	if resync_with_retry() == 0:
		print("[maze2] slot", slot, "重新探图连续失败 ⇒ 本机退出")
		return 0
	return 1


def wait_maze(sec):
	# ---- 两阶段握手（v2.2 修的 bug）----
	# 事故：pair 0 收到"耗尽"后要**先探图数墙**（5~6 秒）才拆迷宫，那几秒里旧迷宫还在、
	# `measure()` 仍有值 ⇒ 旧版这里**立刻返回** ⇒ pair 1 在**旧迷宫**上开始探图，
	# 而 pair 0 紧接着把它拆掉 ⇒ 探图走到迷宫外 ⇒ 收不满 64 格 ⇒ "重新探图失败"（实测 7 架）✗✗
	# 正确握手：**先等旧迷宫消失，再等新迷宫出现**。
	t0 = get_time()
	gone = 0
	while get_time() - t0 < 15.0:
		if measure() == None:
			gone = 1
			break
		if get_pos_x() != HOMEX[0] or get_pos_y() != HOMEY[0]:
			goto_free(HOMEX[0], HOMEY[0], 200)
	if gone == 0:
		return 0                      # 旧迷宫一直没消失（队友卡住了）⇒ 让调用方接管
	while get_time() - t0 < sec:
		if measure() != None:
			return 1                  # 新迷宫回来了
		if get_pos_x() != HOMEX[0] or get_pos_y() != HOMEY[0]:
			goto_free(HOMEX[0], HOMEY[0], 200)
	return 0


def rebuild_with_retry(ax, ay):
	# 重建失败**不再直接退出**（实测：11 架接连退出 ⇒ 农场产能永久缩水 ✗）
	# 改成退避重试 3 次，真的不成才交回调用方
	t = 0
	while t < 3:
		t = t + 1
		if do_rebuild(ax, ay) == 1:
			return 1
		print("[maze2] rebuild 第", t, "次失败，等 3 秒再试")
		wait_s(3)
	return 0


def do_rebuild(ax, ay):
	# 拆掉自己的迷宫 -> 走回建迷宫的格子 -> 重新种 + 灌 -> 重新探测建图 -> 回位
	# 闸门：正常一轮 10M 金币只需每座重建**一次左右**（一座迷宫寿命 301 次宝藏）。
	# 若重建 60 次还在重建，说明迷宫在反复消失（例如"同时只能存在 N 座迷宫"这类
	# 没预料到的限制）⇒ 停手并打印诊断，而不是刷屏空转。
	if STAT[2] >= 60:
		print("[maze2] 重建次数", STAT[2], "过多 ⇒ 本机停手（迷宫可能在反复消失）")
		return 0
	destroy_maze()
	if goto_free(ax, ay, 400) < 0:
		print("[maze2] rebuild: 走不回锚点", ax, ay)
		return 0
	# v2.2：走到锚点后先看一眼 —— 迷宫**已经在**就说明队友抢先建好了（我再种就是"你建我拆"）✗
	e0 = get_entity_type()
	if e0 == Entities.Hedge:
		print("[maze2] rebuild: 迷宫已经在（队友抢先建好）⇒ 直接重新对齐")
		STAT[2] = STAT[2] + 1
		if resync_with_retry() == 1:
			return 1
		return 0
	if e0 == Entities.Treasure:
		print("[maze2] rebuild: 迷宫已经在（宝藏就在锚点上）⇒ 直接重新对齐")
		STAT[2] = STAT[2] + 1
		if resync_with_retry() == 1:
			return 1
		return 0
	if build_maze(ax, ay, 8) == 0:
		return 0
	STAT[2] = STAT[2] + 1
	ex = explore(REG)
	if ex[0] == 0:
		return 0
	invalidate_fields()      # v2：新迷宫 ⇒ 两个缓存都要作废
	home_fields()
	walk_home(200)
	EDGES[0] = count_open_in()
	return 1


# ------------------------------------------------------------
# 探针：小迷宫到底落在哪（决定 16 座能不能拼满整盘）
# ------------------------------------------------------------
def probe_at(px, py):
	# 在 (px,py) 建一座 PROBE_K x PROBE_K 迷宫，走遍它量包围盒，然后拆掉
	goto_free(px, py, 400)
	if build_maze(px, py, 3) == 0:
		print("[probe] 在", px, py, "建不起迷宫")
		return None
	ex = explore(PROBE_K)
	out = [ex[0], ex[1], ex[2], ex[3], ex[4], ex[5]]
	destroy_maze()
	return out


def probe_layout():
	# 返回 [ok, ox, oy]：迷宫包围盒左上角相对"无人机所在格"的平移量
	r1 = probe_at(PROBE_AT_X[0], PROBE_AT_Y[0])
	r2 = probe_at(PROBE_AT_X[1], PROBE_AT_Y[1])
	if r1 == None:
		return [0, 0, 0]
	if r2 == None:
		return [0, 0, 0]
	# 注意：字符串里**不要出现 '#'** —— 本项目的静态检查工具按 '#' 切注释，
	# 多行 print 里的 '#' 会把后面半行当成注释，从而误报"未定义名字"。
	print("[probe] first at", PROBE_AT_X[0], PROBE_AT_Y[0],
		"ok", r1[0], "cells", r1[1], "bbox", r1[2], r1[3], "..", r1[4], r1[5])
	print("[probe] second at", PROBE_AT_X[1], PROBE_AT_Y[1],
		"ok", r2[0], "cells", r2[1], "bbox", r2[2], r2[3], "..", r2[4], r2[5])
	if r1[0] == 0:
		return [0, 0, 0]
	if r2[0] == 0:
		return [0, 0, 0]
	if r1[1] != PROBE_K * PROBE_K:
		print("[probe] 格子数不是", PROBE_K * PROBE_K, "⇒ 物质数与面积的口径不符，停止")
		return [0, 0, 0]
	ox1 = (r1[2] - PROBE_AT_X[0] + SIZE_OF_BOARD) % SIZE_OF_BOARD
	oy1 = (r1[3] - PROBE_AT_Y[0] + SIZE_OF_BOARD) % SIZE_OF_BOARD
	ox2 = (r2[2] - PROBE_AT_X[1] + SIZE_OF_BOARD) % SIZE_OF_BOARD
	oy2 = (r2[3] - PROBE_AT_Y[1] + SIZE_OF_BOARD) % SIZE_OF_BOARD
	print("[probe] 平移量 A =", ox1, oy1, " B =", ox2, oy2)
	if ox1 != ox2 or oy1 != oy2:
		print("[probe] 两次不一致 ⇒ 落点不是固定平移（可能被棋盘边界裁剪）")
		return [0, 0, 0]
	return [1, ox1, oy1]


# ------------------------------------------------------------
# 报告
# ------------------------------------------------------------
def report():
	now = get_time()
	if now - SESSION[2] < REPORT_SEC:
		return
	SESSION[2] = now
	g = num_items(Items.Gold)
	dt = now - SESSION[0]
	rate = 0
	if dt > 0:
		rate = (g - SESSION[1]) * 60 / dt
	print("[stat] gold", g, "gain", g - SESSION[1],
		"elapsed_s", dt, "**gold_per_min", rate, "**",
		"weird", num_items(Items.Weird_Substance),
		"power", num_items(Items.Power))


def main():
	print("=== maze_gold2 v2 (16 x 8x8 并行 + 零 BFS 走位) start ===")
	print("world_size", SIZE_OF_BOARD, "maze_lv", MAZE_LV,
		"reg", REG, "座数", N_MAZE, "每座", PER_REG, "架",
		"substance_per_treasure", SUB_PER, "gold_per_treasure", GOLD_PER)
	print("[maze2] 目标：现有 gold", num_items(Items.Gold),
		"+", GOAL_GAIN, "= ", num_items(Items.Gold) + GOAL_GAIN,
		"（≈", GOAL_GAIN // GOLD_PER, "次宝藏 = 每座", GOAL_GAIN // GOLD_PER // N_MAZE, "次）")
	print("[maze2] 物质", num_items(Items.Weird_Substance),
		"够", num_items(Items.Weird_Substance) // SUB_PER, "次")
	print("[maze2] power", num_items(Items.Power),
		"（2 倍速；32 架同时动会很快耗电）")
	clear()
	t0 = get_time()
	pl = probe_layout()
	if pl[0] == 0:
		print("[maze2] *** 探针失败 ⇒ 不跑（宁可不动，也不要一堆互相重叠的迷宫）***")
		print("[maze2] 把上面 [probe] 的几行发我，我按实测的落点规则改布局公式")
		return
	ox = pl[1]
	oy = pl[2]
	print("[maze2] 落点平移量 ox", ox, "oy", oy,
		"⇒ 建迷宫的锚点 = 区域左上角 - (ox,oy)")
	k = 0
	while k < N_MAZE:
		rx = REG * (k % NREG)
		ry = REG * (k // NREG)
		print("[maze2] reg", k, "区域", rx, ry, "..", rx + REG - 1, ry + REG - 1,
			"| 建迷宫锚点", (rx - ox + SIZE_OF_BOARD) % SIZE_OF_BOARD,
			(ry - oy + SIZE_OF_BOARD) % SIZE_OF_BOARD)
		k = k + 1
	if PROBE_ONLY == 1:
		print("[maze2] PROBE_ONLY=1 ⇒ 只探针，收工")
		return
	goal = num_items(Items.Gold) + GOAL_GAIN
	go_time = get_time() + WINDOW_S
	print("[maze2] 派", N_WORKER - 1, "架副机，", WINDOW_S, "秒后同时建迷宫")
	drones = []
	slot = 1
	while slot < N_WORKER:
		d = spawn_drone(worker, slot, go_time, goal, ox, oy)
		if d != None:
			append(drones, d)
		slot = slot + 1
	print("[maze2] DIAG spawn: cap", max_drones(), "num_drones", num_drones(),
		"spawned", len(drones), "N_WORKER", N_WORKER)
	SESSION[0] = get_time()
	SESSION[1] = num_items(Items.Gold)
	SESSION[2] = SESSION[0]
	worker(0, go_time, goal, ox, oy)
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1
	dt = get_time() - t0
	g = num_items(Items.Gold)
	rate = 0
	if dt > 0:
		rate = (g - SESSION[1]) * 60 / dt
	print("[maze2] === end === gold", g,
		"gain", g - SESSION[1],
		"elapsed_s", dt,
		"**gold_per_min", rate, "**",
		"（判定：>= 2,000,000 即达标）",
		"weird", num_items(Items.Weird_Substance),
		"power", num_items(Items.Power))


main()
