# ============================================================
# util.py —— 各档位共用的公共工具（**工具层**：纯工具、无地块知识、无跨档状态）
#
# 为什么不把 go_to / can_afford / cost_of 抄进每个档位文件：
#   本项目已在 go_to / cost_line / can_afford 上各栽过一次「跨文件未定义」✗
#   ⇒ 集中在一处定义，谁 import 谁用 ✓
# 本文件自足：只用游戏内置函数。
#
# ---- v2（P0）新增 board_shape() ----
# 为什么需要它：docs/game/unlocks/expand_1.md 的农场是「a nice row」（一行），
#   expand_2.md 才说「no longer in a nice row」⇒ **行档与方块档的走位完全不同**，
#   而两者的 get_world_size() 都可能是 3 ⇒ 只看 world 分不出档 ✗
#   判法：走一步看坐标变没变 —— 变了说明那条轴有长度；绕回原格说明那条轴只有 1 格。
#   （与 full_run v58 的教训同源：坐标计数器一旦与实际格子错位，整片区域会被静默跳过。）
# 缓存按 world 键控（R4：模块顶层不许读棋盘，读到就会被 import 缓存冻住）。
# ============================================================

VERSION = 2

SHAPE = [0, -1, 0, 0]      # [world, expand 等级, x 轴有长度?, y 轴有长度?]


def go_to(tx, ty):
	# 走到 (tx,ty)。返回 1 = 到达，0 = 走不到/被挡后放弃。
	# ⚠⚠⚠ 真机致命隐患（2026-11-01 反编译 + 日志确认）：**旧版是无界 while**：
	#     `while get_pos_x() != tx: move(East/West)` —— 而 move() 撞墙只返回 False、**不报错** ✗
	#     一旦路径被迷宫边界挡住（例如 w16 的 maze0 横在 (0,0) 与东边地块之间），
	#     这架副机就**永久卡死**；而 full_run 的 ACTIVEB 只在"全体副机死光"时才清零
	#     ⇒ **一架卡死 = 所有副机永远不再放飞** ⇒ 整台机器停摆 ✗✗✗
	#   ⇒ 必须**有界**：上限 = 曼哈顿距离 x 4 + 40（够绕小障碍，也不至于磨）；
	#     另加"连续 8 步位置没变 ⇒ 判定被挡"的快判（即使上限给大也不会空转）✓
	#   ⇒ 另：棋盘是**环形**的 ⇒ 每个轴都**先走"环绕更近"的那一边**，被挡再换另一边；
	#     这样 (0,0) → (14,0) 会走 West 两步（15→14）而**不是**穿过 maze0 走 14 步 ✓✓
	#   兼容：原来没有返回值（None），调用方全都忽略 ⇒ 现在返回 1/0 是向后兼容的 ✓
	ws = get_world_size()
	sx = get_pos_x()
	sy = get_pos_y()
	dist = abs(tx - sx) + abs(ty - sy)
	limit = dist * 4 + 40
	# 每个轴的优先方向：先按"环绕更近"选，撞墙后**永久换边**（避免来回振荡）✓
	xeast = 1
	if (sx - tx + ws) % ws < (tx - sx + ws) % ws:
		xeast = 0
	ynorth = 1
	if (sy - ty + ws) % ws < (ty - sy + ws) % ws:
		ynorth = 0
	steps = 0
	stuck = 0
	while steps < limit:
		cx = get_pos_x()
		cy = get_pos_y()
		if cx == tx and cy == ty:
			return 1
		moved = 0
		if cx != tx:
			if xeast == 1:
				move(East)
			else:
				move(West)
			if get_pos_x() != cx:
				moved = 1
			else:
				xeast = 1 - xeast      # 撞墙 ⇒ 换另一边绕行
				if xeast == 1:
					move(East)
				else:
					move(West)
				if get_pos_x() != cx:
					moved = 1
		if moved == 0:
			if cy != ty:
				if ynorth == 1:
					move(North)
				else:
					move(South)
				if get_pos_y() != cy:
					moved = 1
				else:
					ynorth = 1 - ynorth
					if ynorth == 1:
						move(North)
					else:
						move(South)
					if get_pos_y() != cy:
						moved = 1
		if moved == 0:
			stuck = stuck + 1
			if stuck >= 8:
				print("[ut] !! go_to 走不到", tx, ty, "（从", sx, sy, "，卡在",
					get_pos_x(), get_pos_y(), "）⇒ 放弃")
				return 0
		else:
			stuck = 0
		steps = steps + 1
	print("[ut] !! go_to 走不到", tx, ty, "（从", sx, sy, "，现在",
		get_pos_x(), get_pos_y(), "）⇒ 放弃")
	return 0


def hay_grind(seconds):
	# 早期最快的干草来源：站在一格上原地割（草 0.47 秒长回来，harvest 免费）
	go_to(0, 0)
	t0 = get_time()
	got = 0
	while get_time() - t0 < seconds:
		if can_harvest():
			harvest()
			got = got + 1
	return got


def cost_of(t, it):
	# 从 get_cost(t) 的字典里取某一项；没有该项 / 已满级（None）都返回 0
	c = get_cost(t)
	if c == None:
		return 0
	for k in c:
		if k == it:
			return c[k]
	return 0


def can_afford(t):
	# 依据 docs/game/unlocks/costs.md：get_cost(t) 返回 {物品: 数量}；已满级返回 None
	c = get_cost(t)
	if c == None:
		return 0
	for it in c:
		if num_items(it) < c[it]:
			return 0
	return 1


# ============================================================
# **南瓜区规划口径**（跨文件约定，改动前先读这里）
#
#   位置：左上角 (0,0) 起
#   边长：n = min(world // 2, 6)
#         world 6  -> 3x3（9/36 格，给 hay/wood/carrot 留 27 格）
#         world 12 -> 6x6（吃满 pumpkins.md 说的 n>=6 倍率 n*n*6）
#   归属：**block_farm 独占**；轮作档一律跳过（档位文件里的 lands() 必须与它同一口径）
#
#   为什么这么定：
#     * 世界从 1x1 长起来 ⇒ 区域必须随世界自适应，**不能照抄 layout.py 的 32x32 坐标**
#     * 6x6 时这块地很可能已被轮作占着 ⇒ 必须先初始化再种，否则 plant 落不下去
#     * 收割门要求每格都是活且成熟的南瓜 ⇒ 区内不能被别的系统种/收
# ============================================================


def drone_cap():
	# 无人机档 D 的取值来源。max_drones 属于 Megafarm 解锁 ⇒ 未解锁前不许调（会报错）
	if num_unlocked(Unlocks.Megafarm) <= 0:
		return 1
	return max_drones()


def drone_count():
	# 当前实际在飞的架数（含主机）。num_drones 同样属于 Megafarm 解锁 ⇒ 先判解锁
	if num_unlocked(Unlocks.Megafarm) <= 0:
		return 1
	return num_drones()


def check_lands(rects, side):
	# 地块自检：矩形表是否**恰好铺满 side x side 且两两不重叠**。
	# 放在工具层是因为 4 个档位都要用同一套判据 —— 抄四遍迟早抄漏一遍（本项目的老毛病 ✗）。
	# 依据 BUILD 26 的事故：两块方阵挨在一起会连成矩形、产量口径被悄悄改变，
	#   而人眼在坐标表里看不出来 ⇒ 这种检查必须机械做 ✓
	seen = []
	i = 0
	while i < side * side:
		append(seen, 0)
		i = i + 1
	i = 0
	while i < len(rects):
		l = rects[i]
		y = 0
		while y < l[4]:
			x = 0
			while x < l[3]:
				px = l[1] + x
				py = l[2] + y
				if px >= side or py >= side:
					print("[ut] !! 地块越界:", px, py, "（side", side, "）")
					return 0
				idx = py * side + px
				if seen[idx] == 1:
					print("[ut] !! 地块重叠于", px, py)
					return 0
				seen[idx] = 1
				x = x + 1
			y = y + 1
		i = i + 1
	i = 0
	while i < side * side:
		if seen[i] == 0:
			print("[ut] !! 有格子没被分到，行主序下标", i)
			return 0
		i = i + 1
	return 1


def board_shape():
	# 返回 (x 轴有长度?, y 轴有长度?)：1 = 那条轴不止一格
	# ⚠ move() 属于 Expand 解锁 ⇒ **world 1 时不许调用**（调用方负责）
	# ⚠ 调用后无人机会离开原点 ⇒ 调用方要自己 go_to(0, 0)
	# 缓存键 = (world, Expand 等级)：**形状会在 world 不变的情况下变**——
	#   实测 Expand lv1 是「一行」而 lv2 是 3x3，两者 get_world_size() 都是 3 ✗
	#   只按 world 缓存会把行档的形状冻住 ⇒ 档位分派永远切不过去
	ws = get_world_size()
	lv = num_unlocked(Unlocks.Expand)
	if SHAPE[0] == ws:
		if SHAPE[1] == lv:
			return SHAPE[2], SHAPE[3]
	go_to(0, 0)
	x0 = get_pos_x()
	move(East)
	xm = 0
	if get_pos_x() != x0:
		xm = 1
	y0 = get_pos_y()
	move(North)
	ym = 0
	if get_pos_y() != y0:
		ym = 1
	go_to(0, 0)
	SHAPE[0] = ws
	SHAPE[1] = lv
	SHAPE[2] = xm
	SHAPE[3] = ym
	return xm, ym


def check_ratio(label, rects):
	# rects = [(说明, h, roles)]：h = 该矩形的行数（roles 是逐列的物种，列数 = len(roles)）
	# 机械校验配比不变量：**草的格数必须 >= 胡萝卜的格数** ✓
	#   依据：每株胡萝卜要 1 草 + 1 木 ⇒ 草不够 ⇒ 草周期性见底 ⇒ 胡萝卜线自断 ✓
	#   （木不用管：一棵树给 5 木 —— docs/game/unlocks/trees.md ✓）
	# 与 check_lands() 同一思路：**铺满/配比这类硬约束一律机械验** ✓
	n_hay = 0
	n_carrot = 0
	n_wood = 0
	i = 0
	while i < len(rects):
		r = rects[i]
		roles = r[2]
		k = 0
		while k < len(roles):
			if roles[k] == "hay":
				n_hay = n_hay + r[1]
			elif roles[k] == "carrot":
				n_carrot = n_carrot + r[1]
			elif roles[k] == "wood":
				n_wood = n_wood + r[1]
			k = k + 1
		i = i + 1
	print("[ut] 配比自检", label, "：草", n_hay, "格 / 胡萝卜", n_carrot,
		"格 / 木", n_wood, "格")
	if n_carrot > n_hay:
		print("[ut] !! 配比违反不变量：草", n_hay, "< 胡萝卜", n_carrot,
			"⇒ 草会周期性见底、胡萝卜线自断（每株胡萝卜要 1 草 + 1 木）")
		return 0
	return 1
