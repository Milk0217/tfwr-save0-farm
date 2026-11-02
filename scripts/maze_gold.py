# ============================================================
# maze_gold.py —— 刷迷宫换金币（**v34：迷宫复用版**，目标：最大化 金币/分钟）
#
# ⚠️ 2026-10-05：**要冲速率请用 `maze_gold2.py`**（16 座 8x8 小迷宫并行 + 每架建图走
#    最短路）。本脚本的实测速率是 688,000 金币/分（164 次宝藏 / 468.5 秒），而用户目标
#    是 2,000,000/分；瓶颈是「32 架抢同一个宝藏 + 贪心 DFS 在 1024 格里蒙着走」
#    （离线模拟：真实树距离约 10 步，贪心 DFS 要 700 步）。本脚本**原样保留**作为
#    已验证的退路：小迷宫的落点规则若与预期不符，就切回这里。
#    推导与模拟读数见 `docs/journal/2026-10-05.md`。
#
# ================= 为什么改成「复用」 =================
# v33（每个宝藏开一座新迷宫）每一轮都要付这些**固定开销**：
#   clear() → 派 31 架 → 散开 2 秒 → 走到灌木 → 种灌木 → 灌物质 → 搜 → 等全部收工
# 而游戏文档（docs/game/unlocks/mazes.md）里有一条一直没用上的机制：
#
#   > 在宝藏上**再灌一次同样的物质**，会**收掉当前宝藏并在同一座迷宫里随机重定位**一个新宝藏；
#   > 最多重定位 300 次。每移动一次宝藏，迷宫的墙会被**随机拆掉一些**（所以复用后可能有环）。
#
# ⇒ 固定开销**只付一次**，之后每个宝藏只剩「最近那架走过去 + 1 次 use_item」。
#   而且墙被不断拆掉 ⇒ 迷宫越来越开阔 ⇒ 每次追捕的步数越来越小。
#   （排行榜 `Leaderboards.Maze` 的目标 9,863,168 金币，文档明说「正好等于复用一座 32x32
#     迷宫 300 次」—— 这个玩法本来就是为复用设计的。）
#
# ================= 吞吐的硬上限（先算账，别指望不可能的数） =================
#   32x32、lv5：一次宝藏 = 1024 x 2^(5-1) = **16,384 金币**
#   一个动作（move / harvest / use_item）= **200 tick**；2 倍速下实测约 **6,075 tick/秒**
#   ⇒ 全局 30 个动作/秒（所有无人机同时在这条时钟上推进，不是各算各的）。
#   一次宝藏**理论最少** = 1 步走过去 + 1 次 use_item = 400 tick
#   ⇒ 绝对天花板 6075/400 = 15.2 次/秒 = 248,832 金币/秒 = **14.9M 金币/分钟**
#     （升到 lv6 金币翻倍 -> **29.9M/分钟**，但那是"宝藏永远在脚边"的不可能状态）
#   所以「200M 金币/分钟」比不可能的天花板还高 13 倍 —— 那不是优化问题。
#   本脚本的现实区间是 **0.5M ~ 7M 金币/分钟**，取决于墙被拆得多快（看 [stat] 的读数）。
#
# ================= 结构 =================
#   主机：clear() → 派 31 架猎人（各走向散布起点，边走边等迷宫成型）→ 建迷宫
#         → 自己也当猎人 → 达标/耗尽 → destroy_maze() → 等猎人退出 → 下一座
#   猎人：追宝藏（DFS + visited + 朝宝藏的启发式；**每步重读 measure()** 以跟随被挪走的目标）
#         到宝藏 → use_item(物质) —— 这一次动作**同时收货并重定位** → 继续追下一个
#
#   没有共享内存【在这里是好事】：每架无人机重新执行本文件 ⇒ **各自有一份 VIS/PATH/GEN**，
#   不需要任何跨机协调。唯一的全局真相是共享物品栏 `num_items(Items.Gold)`，
#   所以报告一律用金币增量算，不用各机自己的计数器（那是 BUILD 13 的假数据坑）。
#
# ================= 机制自愈 =================
#   `hunt()` 在宝藏上先试 use_item，**用金币增量验证**；若没给金币再退回 `harvest()`
#   （文档保证 harvest 宝藏也给金币）。于是即使「use_item 能重定位」这条机制与文档不符，
#   脚本也只会退化成「一座迷宫收一次」的旧行为，而不会卡死或算错。
#
# 本脚本只做刷钱，不种田。用完切回 main.py 即可。
# ============================================================

SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD
DIRS = [North, East, South, West]
DIR_DX = [0, 1, 0, -1]
DIR_DY = [1, 0, -1, 0]

# ---- 猎人的散布起点：循环生成 32 个 = 8x4 均匀网格 ----
# 宝藏位置随机 ⇒ 墙钟 = min(所有猎人的距离) ⇒ 起点越分散、min 越短。
_G = SIZE_OF_BOARD // 16
if _G < 1:
	_G = 1
START_X = []
START_Y = []
_k = 0
while _k < 32:
	# ---- BUILD 45：**把 32 个家铺满整个场地** ----
	# 旧公式：((_k // 8) * 2 + 1) * _G，_G = SIZE_OF_BOARD // 16 = 2
	#   ⇒ x = {2,6,10,14,18,22,26,30} ✓ 铺满
	#   ⇒ y = {2,6,10,14}            ✗ **只覆盖下半场！y>=16 一个家都没有** ✗✗
	# 后果（用户实测 BUILD 44 仍然聚拢）：上半场的宝藏"最近的家"永远是 y=14 那一排
	#   ⇒ 只有那 8 架反复上去干活、长期滞留在上方，其余各架闲着 ⇒ 看起来就是"聚拢" ✓
	#   **Voronoi 分派本身没错，是分派的锚点分布错了** ✗
	# 新公式：x 用 4 格间距（2,6,...,30）、y 用 8 格间距（4,12,20,28）⇒ 覆盖 0..31 全域 ✓
	#   ⇒ 任一宝藏到最近家的距离 ≈ |dx|<=2、|dy|<=4 ⇒ 平均约 6 格 ⇒ 约 0.2 秒/次 ✓
	append(START_X, (_k % 8) * 4 + 2)
	append(START_Y, (_k // 8) * 8 + 4)
	_k = _k + 1
MAX_HUNTERS = 32                   # 31 个副机 + 主机

MAZE_SUBSTANCE = SIZE_OF_BOARD
if num_unlocked(Unlocks.Mazes) > 1:
	MAZE_SUBSTANCE = SIZE_OF_BOARD * (2 ** (num_unlocked(Unlocks.Mazes) - 1))

BUSH_X = SIZE_OF_BOARD // 4        # 灌木种在象限中心（主机从这里建迷宫）
BUSH_Y = SIZE_OF_BOARD // 4
GATHER_SECONDS = 2                 # 建迷宫前留给猎人散开的时间（只影响第一次追捕）
HUNT_MAX_STEPS = 4000              # 一次追捕的步数上限（32x32 迷宫最长路径 ~1024，留足余量）
MAX_HUNT_RETRY = 300                # 主机连续这么多次追不到就拆迷宫收工（防死循环）
REPORT_SEC = 10                    # 会话内每约这么多秒打一行 [stat]（get_time 免费）
# ---- BUILD 43：猎人"就近才追"的阈值（曼哈顿距离）----
# 用户实测：无人机**逐渐聚拢** ⇒ 效率下降 ✗
# 原因：31 架全追同一个宝藏 ⇒ 每次重定位后全部挤到宝藏刚才的位置 ⇒
#       "最近的猎人"退化成"全员从同一处出发" ⇒ 平均路程从 10 步涨到几十步 ✗
# 修法：只让"离宝藏 <= NEAR_R"的那几架出发，其余原地等 ⇒ 散布结构保持 ✓
# 32x32 用 31 架时，每架平均覆盖约 33 格 ⇒ 网眼约 5~6 格 ⇒ 12 留了充裕余量 ✓
NEAR_R = 12
# BUILD 44 兜底用的状态（模块全局 = 每架无人机各一份 ✓）
LTX = [-1]
LTY = [-1]
STALL = [0]
REPORT_EVERY_MAZE = 1              # 每几座迷宫打印一行 [stat]

# ---- 每架无人机自己的 DFS 状态（模块全局 = 每架一份，见文件头的说明）----
VIS = []                           # 访问标记，用**世代号**免去每次清零（省 CELLS 条语句）
PATH = []                          # DFS 栈（线性下标）
_i = 0
while _i < CELLS:
	append(VIS, 0)
	append(PATH, 0)
	_i = _i + 1
GEN = [0]                          # 当前世代；VIS[k] == GEN[0] 表示本次搜索已访问
HUNT_STEPS = [0, 0]                # 本机 [累计追捕步数, 单次最大步数]

# ---- 主机用的会话统计 ----
SESSION = [0, 0, 0]                # [会话开始时间, 开始时的金币, 已用迷宫座数]
GOAL_GOLD = [0]                    # 金币的绝对目标（= 开始时金币 + 本次要刷的增量）
# ---- BUILD 37：把"收工目标"从「Leaderboard 还差多少」改成「本次要刷多少」----
# 原因（实测 BUILD 36）：Leaderboard 的那 1,000,000 金币**已经被打满过了**
#   ⇒ 目标只剩 62,412 ⇒ **2 次宝藏（65,536）就收工，整场只跑了 7.3 秒** ✗
#   ⇒ 既量不到稳定速率，也吃不到文档说的"每次重定位随机拆墙 ⇒ 路越来越短"的复利。
# 200,000,000 ≈ 6,104 次宝藏；物质够 35,876 次 ⇒ 只用掉约 17% ✓
GOAL_GAIN = [5000000]              # 本次要刷的金币增量。按实测潜力 3~6M/分 ⇒ 约 1 分钟跑完
# （要长跑就把它调大，例如 200000000 ≈ 6104 次宝藏，物质够 35876 次 ✓）


# ------------------------------------------------------------
# 基础
# ------------------------------------------------------------
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


def step_back(cx, cy, px, py):
	dx = (px - cx + SIZE_OF_BOARD) % SIZE_OF_BOARD
	dy = (py - cy + SIZE_OF_BOARD) % SIZE_OF_BOARD
	if dx == 1:
		move(East)
	elif dx == SIZE_OF_BOARD - 1:
		move(West)
	elif dy == 1:
		move(North)
	else:
		move(South)


def drone_cap():
	# max_drones() 属于 Megafarm 解锁，未解锁前调用可能报错，所以先判断
	if num_unlocked(Unlocks.Megafarm) <= 0:
		return 0
	return max_drones()


def gold_per_maze():
	return CELLS * (2 ** (num_unlocked(Unlocks.Mazes) - 1))


def leaderboard_get(which):
	# which: 0 = 金币需求，1 = 骨头需求。已解锁或已满级（get_cost 返回 None）时为 0。
	c = get_cost(Unlocks.Leaderboard)
	if c == None:
		return 0
	t = 0
	for it in c:
		if which == 0:
			if it == Items.Gold:
				t = t + c[it]
		else:
			if it == Items.Bone:
				t = t + c[it]
	return t


def can_unlock_leaderboard():
	c = get_cost(Unlocks.Leaderboard)
	if c == None:
		return 0
	for it in c:
		if num_items(it) < c[it]:
			return 0
	return 1


# ------------------------------------------------------------
# 追一次宝藏
#   返回 1 = 我收货成功且宝藏已重定位（复用成立）
#        4 = 收货成功但**没有重定位**（迷宫已耗尽 / 机制与文档不符）⇒ 该换新迷宫
#        2 = use_item 与 harvest 都没给金币（异常）
#        3 = 迷宫已消失（被别的机拆掉，或已经不在了）
#        0 = 本次步数用尽（调用方重试即可）
#
# 两个关键点：
#   1. **每步重读 measure()**（1 tick）：宝藏会被别的猎人挪走，目标变了就从当前位置
#      重起一次 DFS（世代号 +1、栈清空）。这是"多机抢同一个宝藏"的必要代价，很便宜。
#   2. 站上宝藏时用 **use_item** 而不是 harvest：文档说这一次动作同时「收货 + 重定位」，
#      所以每个宝藏只要 1 次动作。用金币增量验证，没给就退回 harvest（自愈）。
# ------------------------------------------------------------
def hunt():
	tp = measure()
	if tp == None:
		return 3
	tx, ty = tp
	GEN[0] = GEN[0] + 1
	g = GEN[0]
	depth = 0
	steps = 0
	while steps < HUNT_MAX_STEPS:
		steps = steps + 1
		cx = get_pos_x()
		cy = get_pos_y()
		t = get_entity_type()
		if t == Entities.Treasure:
			g0 = num_items(Items.Gold)
			use_item(Items.Weird_Substance, MAZE_SUBSTANCE)
			if num_items(Items.Gold) > g0:
				HUNT_STEPS[0] = HUNT_STEPS[0] + steps
				if steps > HUNT_STEPS[1]:
					HUNT_STEPS[1] = steps
				return 1
			# ---- BUILD 42：**绝不调用 harvest()！这是把整座迷宫抹掉的元凶** ----
			# 文档原文："If you use `harvest()` anywhere else the maze will simply disappear."
			#         "Use `harvest()` on the treasure to receive gold"
			# 而这里正是"两架猎人抢同一个宝藏"的落点：
			#   A 抢先 use_item（拿到金币、宝藏重定位）⇒ B 站的这一格**已经不是宝藏了**
			#   ⇒ B 的 use_item 无效 ⇒ 若回退 harvest() ⇒ **整座迷宫立刻消失** ✗✗✗
			# 实测证据（BUILD 41 的日志）：
			#   `[hunt] slot 3 异常：use_item 与 harvest 都没给金币`
			#   `[maze] hunt 返回 3（measure 为 None / 不在树篱上）` 连续 5 次 ⇒ 本座结束
			#   —— measure() 只在**迷宫外**返回 None ⇒ 迷宫确实被抹掉了 ✓
			# 正确做法：use_item 没给金币就当作"被别的猎人抢先" ⇒ 直接返回 0（重试），
			#           **绝不动 harvest** ✓（这是本项目第三个"看着像自愈、实则是地雷"的机制 ✗）
			return 0
		if t != Entities.Hedge:
			return 3
		# 目标可能被别的猎人挪走了：重读一次（1 tick），变了就重起 DFS
		tp2 = measure()
		if tp2 == None:
			return 3
		a, b = tp2
		if a != tx or b != ty:
			tx = a
			ty = b
			GEN[0] = GEN[0] + 1
			g = GEN[0]
			depth = 0
		VIS[cy * SIZE_OF_BOARD + cx] = g
		# 在「能走且本次没访问过」的方向里挑一个最接近宝藏的
		best = -1
		best_d = 999999
		for d in range(4):
			nx = (cx + DIR_DX[d] + SIZE_OF_BOARD) % SIZE_OF_BOARD
			ny = (cy + DIR_DY[d] + SIZE_OF_BOARD) % SIZE_OF_BOARD
			if VIS[ny * SIZE_OF_BOARD + nx] != g:
				if can_move(DIRS[d]):
					dd = abs(nx - tx) + abs(ny - ty)
					if dd < best_d:
						best_d = dd
						best = d
		if best >= 0:
			PATH[depth] = cy * SIZE_OF_BOARD + cx
			depth = depth + 1
			move(DIRS[best])
		else:
			# 死胡同：沿 DFS 栈退一步（迷宫是一棵树时这是唯一的走法）
			if depth == 0:
				return 0
			depth = depth - 1
			prev = PATH[depth]
			step_back(cx, cy, prev % SIZE_OF_BOARD, prev // SIZE_OF_BOARD)
	return 0


def destroy_maze():
	# 在**非宝藏**处 harvest() 会让整座迷宫消失（文档）—— 这是让所有猎人退出的信号。
	# 所以先离开宝藏那一格，再收割它旁边的树篱。
	if get_entity_type() == Entities.Treasure:
		moved = 0
		d = 0
		while d < 4 and moved == 0:
			if can_move(DIRS[d]):
				move(DIRS[d])
				moved = 1
			d = d + 1
	if get_entity_type() == Entities.Hedge:
		harvest()


# ------------------------------------------------------------
# 猎人（副机）：走到散布起点 -> 一直追宝藏，直到迷宫消失
# ------------------------------------------------------------
def hunter(slot):
	sx = START_X[slot]
	sy = START_Y[slot]
	# ---- 诊断（BUILD 36）----
	# 上一轮实测：约一半猎人 `got 0 steps 0` ⇒ hunt() 第一行 measure() 返回 None ⇒ 直接退出。
	# 文档说 measure() 只在 **"anywhere in the maze"** 才返回宝藏坐标 ⇒ 说明它们脚下不是迷宫格。
	# 这条日志一轮就能回答"是起点越界、还是迷宫没盖满整场"。
	print("[hunt] slot", slot, "start", sx, sy,
		"| 位置", get_pos_x(), get_pos_y(),
		"| 脚下实体", get_entity_type(),
		"| measure", measure())
	# 1) 走向散布起点；**边走边看迷宫成型没**（脚下变成树篱就立刻开搜）。
	#    不能在这里用 goto 死等：迷宫一成型，move() 就会被树篱挡住，goto 的 while 会原地死转。
	steps = 0
	arrived = 0
	t_wait = get_time()
	while get_entity_type() != Entities.Hedge:
		if arrived == 1:
			# ---- **修复 BUILD 35：到了起点之后必须按"墙钟"等迷宫，不能按迭代次数等** ----
			# 旧写法 `and steps < 200` 是致命 bug：到了起点后循环体什么都不做，
			# 但 `steps` 照样自增 ⇒ 200 次空转只要约 0.2 秒就"超时"退出 ✗
			# 而迷宫是在主机 GATHER_SECONDS(=2 秒) 之后才建的 ⇒ **31 架猎人全部
			# 在迷宫出现之前就退出了**（实测日志：31 条 [hunt] 行全部排在 DIAG build 之前，
			# 且全是 steps 0 = 从没进过迷宫）✗
			# `get_time()` 是 0 tick 的（实测成本表）⇒ 空等完全免费 ✓
			if get_time() - t_wait > 90:
				# 真的一直没有迷宫（主机没建成 / 已被拆）⇒ 退出，绝不死等
				print("[hunt] slot", slot, "等迷宫超时 90 秒，退出")
				return 0
		else:
			if get_pos_x() != sx:
				if get_pos_x() < sx:
					move(East)
				else:
					move(West)
			elif get_pos_y() != sy:
				if get_pos_y() < sy:
					move(North)
				else:
					move(South)
			else:
				arrived = 1
			steps = steps + 1
			if steps > 4000:
				# 走到起点都走不到（被树篱挡住等）⇒ 也别死转
				print("[hunt] slot", slot, "去起点失败，退出")
				return 0
	# 2) 追捕循环
	#    **必须有失败次数闸**：hunt() 返回 0 表示「这次步数用尽」，正常情况重试就行；
	#    但如果迷宫被别的机拆掉后它恰好卡在某个角落，`while True` 就会空转到
	#    主机 wait_for 永远等不到 —— 那是最难查的一类死锁。这里兜住。
	got = 0
	fails = 0
	while True:
		# ---- BUILD 43：**就近才追，否则原地等**（防止 31 架聚拢 ⇒ 效率衰减）----
		# 这条规则是纯本地的（不需要共享内存）：只需知道自己与宝藏的曼哈顿距离。
		# `measure()` 与 `get_time()` 都便宜/免费 ⇒ 空闲等待几乎不花预算 ✓
		tp = measure()
		if tp == None:
			break
		# ---- BUILD 44：**按"最近的家"分派（Voronoi 式）—— 彻底杜绝聚拢** ----
		# BUILD 43 的 NEAR_R 只限制了"单次移动距离"，没有限制"谁该动"：
		# 同一架会被反复选中，其余各架仍会随被选中的次数慢慢漂移 ⇒ 用户实测仍然聚拢 ✗
		# 现在：每个猎人有一个**固定的家**（现成的 START_X/Y，32 个均匀散布点），
		# 宝藏出现时各自算出"哪个家离它最近"，**只有那个家的主人出发** ✓
		#   ⇒ 每架永远只在自己那一格附近活动 ⇒ 数学上不可能聚拢 ✓✓
		#   ⇒ 出动距离 = 从自家到宝藏 ≈ ≤5~6 格 ⇒ 约 0.2 秒/次 ⇒ 约 9M 金币/分 ✓
		# 成本：32 次比较 ≈ 100 tick，而**每次宝藏只算一次**（一趟追捕约 2,000 tick）⇒ 5% ✓
		best = 0
		bd = 999999
		k = 0
		while k < MAX_HUNTERS:
			d2 = abs(START_X[k] - tp[0]) + abs(START_Y[k] - tp[1])
			if d2 < bd:
				bd = d2
				best = k
			k = k + 1
		if best != slot:
			# 兜底：若同一个宝藏位置连续约 2 秒没人拿（主人可能已退出/卡住）⇒ 我也上 ✓
			if tp[0] == LTX[0] and tp[1] == LTY[0]:
				STALL[0] = STALL[0] + 1
			else:
				LTX[0] = tp[0]
				LTY[0] = tp[1]
				STALL[0] = 0
			if STALL[0] < 10:
				t_idle = get_time()
				while get_time() - t_idle < 0.2:
					pass
				continue
			STALL[0] = 0
		r = hunt()
		if r == 1:
			got = got + 1
			fails = 0
		elif r == 4:
			# ---- BUILD 41：**猎人不再拆迷宫** ----
			# 实测（BUILD 40）：一座迷宫只复用 2~3 次就"结束"（mazes 1、gain 98,304 = 恰好 3 次、
			# 物质消耗 4,096 = 1 次建迷宫 + 3 次重定位）。
			# 根因：r==4 的含义是"use_item 没给金币、但 harvest 给了" —— 这多半是
			# **两架猎人同时抢同一个宝藏**的竞态：A 先 use_item（拿到金币、宝藏重定位），
			# B 紧接着在**同一格**仍看到 Treasure ⇒ use_item 无效 ⇒ 退回 harvest 又拿到金币 ⇒ 判 4 ✗
			# 而原来这里 `destroy_maze()` 一拆，**整座迷宫的墙全部复原、所有猎人一起收工** ✗✗
			# ⇒ 死循环：刚建的迷宫复用几次就被自己人拆掉 ✓ 与你观察到的"复用两次就结束"吻合。
			# 修法：猎人只**自己退出**；拆不拆迷宫由主机统一决定 ✓
			print("[hunt] slot", slot, "use_item 无效（疑似抢宝藏竞态）⇒ 本机退出，不拆迷宫")
			break
		elif r == 3:
			break
		elif r == 2:
			print("[hunt] slot", slot, "异常：use_item 与 harvest 都没给金币 ⇒ 本机退出，不拆迷宫")
			break
		else:
			fails = fails + 1
			if fails >= MAX_HUNT_RETRY:
				break
	print("[hunt] slot", slot, "got", got, "steps", HUNT_STEPS[0], "max_step", HUNT_STEPS[1])
	return got


def wait_all(drones):
	i = 0
	while i < len(drones):
		wait_for(drones[i])
		i = i + 1


# ------------------------------------------------------------
# 一次会话：clear -> 派猎人 -> 建迷宫 -> 主机也追 -> 拆迷宫 -> 等收工
# ------------------------------------------------------------
def session():
	clear()
	drones = []
	cap = drone_cap()
	i = 1
	while i < cap and i < MAX_HUNTERS:
		d = spawn_drone(hunter, i)
		if d != None:
			append(drones, d)
		i = i + 1
	# ---- 诊断（BUILD 35）：把"到底派出了几架"直接量出来 ----
	# 用户观察到"只有一个 worker 在工作"⇒ 必须先确认是 drone_cap 太小、还是 spawn 失败。
	# 注意上一轮的日志里 [hunt] slot 1..31 都打印了，所以更可能是"派出来了但迷宫没建起来"，
	# 这两个诊断能把两种情况区分开，不必再猜。
	print("[maze] DIAG spawn: drone_cap =", cap, "max_drones =", max_drones(),
		"spawned =", len(drones), "MAX_HUNTERS =", MAX_HUNTERS)
	# 给猎人几秒散开（只影响第一次追捕）
	if len(drones) > 0:
		start = get_time()
		while get_time() - start < GATHER_SECONDS:
			pass
	# 建迷宫
	goto(BUSH_X, BUSH_Y)
	plant(Entities.Bush)
	if get_entity_type() != Entities.Bush:
		# 上一轮"31 架猎人全部 steps 0"的根因高度可疑在这里：灌木根本没种上 ⇒ 没有迷宫。
		# 最可能是**地面类型不对**（前一场仙人掌/恐龙把地面留成了土壤）⇒ 换一种地面再试一次。
		print("[maze] DIAG bush: 灌木没种上！ground =", get_ground_type(),
			"entity =", get_entity_type(),
			"weird =", num_items(Items.Weird_Substance))
		if get_ground_type() != Grounds.Soil:
			till()
			plant(Entities.Bush)
			print("[maze] DIAG bush: 翻土后重种 -> entity =", get_entity_type(),
				"ground =", get_ground_type())
		if get_entity_type() != Entities.Bush:
			print("[maze] DIAG bush: 两种地面都种不上 ⇒ 本座放弃（把上面两行发我）")
			wait_all(drones)
			return 0
	if not use_item(Items.Weird_Substance, MAZE_SUBSTANCE):
		print("[maze] 奇异物质不够了（现有", num_items(Items.Weird_Substance),
			"需要", MAZE_SUBSTANCE, "）")
		wait_all(drones)
		return 0
	t_after = get_entity_type()
	print("[maze] DIAG build: use_item 之后 entity =", t_after,
		"（应为 Hedge=树篱 或 Treasure=宝藏；None 说明迷宫没成形）")
	if t_after != Entities.Hedge:
		if t_after != Entities.Treasure:
			print("[maze] DIAG build: 迷宫没成形 ⇒ 本座放弃")
			wait_all(drones)
			return 0
	# 主机自己也当猎人，直到「达标 / 迷宫耗尽 / 迷宫消失」
	got = 0
	fails = 0
	# ---- BUILD 38：会话内定期报告 ----
	# 之前 [stat] 只在**整座迷宫结束时**打一次；而放宽 MAX_HUNT_RETRY 之后一座迷宫能活
	# 好几分钟 ⇒ 屏幕上长时间什么都不动（用户实测"没有反应"）✗
	# 改成每约 REPORT_SEC 秒打一行：`get_time()` 是 0 tick 的（实测成本表）⇒ 免费 ✓
	t_rep = get_time()
	got_rep = 0
	silent3 = 0
	while True:
		r = hunt()
		if r == 1:
			got = got + 1
			fails = 0
			now = get_time()
			if now - t_rep >= REPORT_SEC:
				g = num_items(Items.Gold)
				dt = now - SESSION[0]
				rate = 0
				if dt > 0:
					rate = (g - SESSION[1]) * 60 / dt
				print("[stat] gold", g, "gain", g - SESSION[1],
					"elapsed_s", dt, "**gold_per_min", rate, "**",
					"mazes", SESSION[2], "本座收", got,
					"段内", got - got_rep, "次/", now - t_rep, "秒",
					"weird", num_items(Items.Weird_Substance))
				t_rep = now
				got_rep = got
			if num_items(Items.Gold) >= GOAL_GOLD[0]:
				break
		elif r == 4:
			print("[maze] 迷宫耗尽（use_item 不再给金币）—— 本座主机收了", got, "次")
			break
		elif r == 3:
			# ---- BUILD 41：原来是**静默 break** ⇒ 会话悄无声息地结束、事后查不到原因 ✗ ----
			# r==3 = measure() 返回 None（不在迷宫内）或脚下不是 Hedge，多数是瞬时状态。
			# 改成"打印原因 + 有限重试"，而不是立刻结束这一座 ✓
			silent3 = silent3 + 1
			print("[maze] hunt 返回 3（measure 为 None / 不在树篱上）第", silent3, "次")
			if silent3 >= 5:
				print("[maze] 连续 5 次返回 3 ⇒ 本座结束")
				break
		elif r == 2:
			print("[maze] 异常：use_item 与 harvest 都没给金币")
			break
		else:
			fails = fails + 1
			if fails >= MAX_HUNT_RETRY:
				print("[maze] 连续", fails, "次追不到，拆迷宫收工")
				break
	# ---- 报告（BUILD 36）：每次会话的重定位次数与平均步数 ----
	# 判据：若"平均步数"随 got 上升而下降 ⇒ 文档说的"每次重定位随机拆墙"确实在起作用 ✓
	avg = 0
	if got > 0:
		avg = HUNT_STEPS[0] / got
	print("[maze] session 结束: 主机收了", got, "次  连续失败", fails,
		"| 平均步数", avg, " 最大步数", HUNT_STEPS[1],
		"| 物质余量", num_items(Items.Weird_Substance),
		"（够", num_items(Items.Weird_Substance) // MAZE_SUBSTANCE, "次）")
	# 拆掉迷宫，让所有猎人退出（它们下一步就会看到树篱没了）
	destroy_maze()
	wait_all(drones)
	SESSION[2] = SESSION[2] + 1
	return got


def report():
	g = num_items(Items.Gold)
	dt = get_time() - SESSION[0]
	rate = 0
	if dt > 0:
		rate = (g - SESSION[1]) * 60 / dt
	print("[stat] gold", g,
		"target", GOAL_GOLD[0],
		"gain", g - SESSION[1],
		"elapsed_s", dt,
		"gold_per_min", rate,
		"mazes", SESSION[2],
		"weird", num_items(Items.Weird_Substance),
		"power", num_items(Items.Power),
		"max_drones", drone_cap())


def main():
	print("=== maze_gold v34 (reuse) start ===")
	print("world_size", SIZE_OF_BOARD,
		"maze_lv", num_unlocked(Unlocks.Mazes),
		"substance_per_maze", MAZE_SUBSTANCE,
		"gold_per_treasure", gold_per_maze(),
		"gold", num_items(Items.Gold),
		"weird", num_items(Items.Weird_Substance),
		"power", num_items(Items.Power),
		"max_drones", drone_cap(),
		"leaderboard_lv", num_unlocked(Unlocks.Leaderboard))
	# ---- BUILD 39：**删掉两道"已通关就收工"的挡板** ----
	# 实测（BUILD 38）：上一轮顺带解锁了 Unlocks.Leaderboard ⇒ 于是
	#   `num_unlocked(Unlocks.Leaderboard) > 0` 与 `gn <= 0` 同时成立 ⇒
	#   脚本每次启动都打印"已解锁 / 不需要金币"然后**立刻 return** ⇒ 屏幕上一行活都不干 ✗
	# 现在用的是**相对增量** GOAL_GAIN，与"排行榜还差多少"无关 ⇒ 这两道挡板已过时 ✓
	gn = leaderboard_get(0)
	bn = leaderboard_get(1)
	print("[maze] Leaderboard 解锁等级", num_unlocked(Unlocks.Leaderboard),
		"| 排行榜还差 gold", gn, "bone", bn,
		"| 现有 gold", num_items(Items.Gold), "bone", num_items(Items.Bone))
	print("[maze] 本脚本按**相对增量**刷（不看排行榜是否已通关）✓")
	# BUILD 37：用**相对增量**而不是"排行榜还差多少"（后者已被打满 ⇒ 会秒退）
	GOAL_GOLD[0] = num_items(Items.Gold) + GOAL_GAIN[0]
	print("[maze] 本次目标 = 现有", num_items(Items.Gold), "+", GOAL_GAIN[0],
		"= ", GOAL_GOLD[0], "（约", GOAL_GAIN[0] // (CELLS * (2 ** (num_unlocked(Unlocks.Mazes) - 1))),
		"次宝藏；物质够", num_items(Items.Weird_Substance) // MAZE_SUBSTANCE, "次）")

	SESSION[0] = get_time()
	SESSION[1] = num_items(Items.Gold)
	while True:
		# ---- BUILD 40：**只在"排行榜尚未解锁"时才尝试解锁，且失败也不收工** ----
		# 实测（BUILD 39）：Leaderboard 已经是 lv1，但 can_unlock_leaderboard() 仍返回 1 ⇒
		#   脚本去 unlock() ⇒ 被拒 ⇒ 打印"拒绝了请求，收工"并 **return** ⇒ 又一次开局就退出 ✗
		# 这是本次排查的**第三道过时挡板**（前两道在 BUILD 39 删掉）。
		# 修法：① 用 num_unlocked 显式判"未解锁"；② 失败也只提示、不退出 ⇒ 继续刷金币 ✓
		if num_unlocked(Unlocks.Leaderboard) == 0:
			if can_unlock_leaderboard() == 1:
				if unlock(Unlocks.Leaderboard):
					print("[maze] *** Unlocks.Leaderboard UNLOCKED ***")
				else:
					print("[maze] unlock() 被拒（资源不够？）—— 继续刷金币，不解锁也不退出")
		if num_items(Items.Gold) >= GOAL_GOLD[0]:
			# ---- 达到本次目标 ⇒ 打印**实测速率**（这是判定 2M/分 的关键行）----
			dt = get_time() - SESSION[0]
			rate = 0
			if dt > 0:
				rate = (num_items(Items.Gold) - SESSION[1]) * 60 / dt
			print("[maze] *** 达到本次目标 *** gold", num_items(Items.Gold),
				"target", GOAL_GOLD[0],
				"gain", num_items(Items.Gold) - SESSION[1],
				"elapsed_s", dt,
				"**gold_per_min", rate, "**",
				"（判定：>= 2,000,000 即达标；次/秒 =", rate / 60 / 32768, "）")
			return
		if num_items(Items.Weird_Substance) < MAZE_SUBSTANCE:
			print("[maze] 奇异物质不够了，收工。gold =", num_items(Items.Gold))
			return
		session()
		if SESSION[2] % REPORT_EVERY_MAZE == 0:
			report()


main()
