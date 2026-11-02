# ============================================================
# zones.py —— **分区的唯一事实来源**（用户要求：别让多无人机抢地盘）
#
# 为什么要有这个文件：
#   在此之前，谁该在哪块地干活**没有任何一处说了算** ✗ —— 于是出现：
#     * 轮作只知道跳过 pb_size()² 那一小块，不知道迷宫区/向日葵区 ✗
#     * 南瓜专机只认 (0,0) 起 n×n，尺寸一变就对不上 ✗
#     * gold_mini 会在**整块地上找空地**建 8x8 迷宫 ⇒ 直接把别人的地在用 ✗✗
#   结果就是用户看到的「多无人机互相抢地盘」。
#
# 铁律（任何模块都必须遵守）：
#   1) **一块地只有一个 owner** —— 依据 docs/game/unlocks/megafarm.md 的 race condition 警告；
#   2) 任何 plant/harvest 之前，先问 zone_of(x, y) 是不是自己负责的区域；
#   3) 所有区域**拼满整块地且互不重叠** —— check() 会自检并打印结果 ✓。
#
# 本文件**自足**：只用游戏内置函数（go_to 之类不借用别的文件，免得再出
# 「函数从未被定义」那类错误 —— 本项目已在 go_to / cost_line / can_afford 上栽过 3 次）。
# ============================================================

VERSION = 3
BLOCK_MAX = 6          # 文档结论：至少 6x6 才吃满倍率（pumpkins.md）
MAZE_SIDE = 8          # 迷宫区边长（mazes.md：n 份奇异物质 = n x n 迷宫）
SUN_H = 2              # 向日葵带高度（sunflowers.md：场上 >=10 株才有 8 倍 power）

NAMES = []             # 区域名
X0 = []                # 左上角
Y0 = []
W = []
H = []
OWNER = []             # 谁负责：main / drone1 ... / none


def add(name, x0, y0, w, h, owner):
	NAMES.append(name)
	X0.append(x0)
	Y0.append(y0)
	W.append(w)
	H.append(h)
	OWNER.append(owner)


def build():
	# 依据当前棋盘大小重算分区（每次世界变大后调用一次即可）
	while len(NAMES) > 0:
		NAMES.pop()
		X0.pop()
		Y0.pop()
		W.pop()
		H.pop()
		OWNER.pop()
	ws = get_world_size()
	# ---- 南瓜方块：边长按文档（>=6 才吃满），但**绝不能吞掉整块棋盘** ----
	bs = BLOCK_MAX
	if bs > ws // 2:
		bs = ws // 2
	if bs < 2:
		bs = 0
	# 方块块数：留出至少一半棋盘给轮作/迷宫
	nb = 0
	if bs > 0:
		nb = (ws // 2) // bs
		if nb < 1:
			nb = 1
	k = 0
	while k < nb:
		add("block" + str(k), k * bs, 0, bs, bs, "drone" + str(k + 1))
		k = k + 1
	# ---- 迷宫区：只在棋盘够大时划出（Mazes 解锁后才真的会用）----
	mx = nb * bs
	if mx + MAZE_SIDE <= ws:
		if ws >= MAZE_SIDE * 2:
			add("maze0", mx, 0, MAZE_SIDE, MAZE_SIDE, "droneM")
	# ---- 向日葵带：贴在方块下面 ----
	if bs > 0:
		if bs + SUN_H <= ws:
			add("sun", 0, bs, nb * bs, SUN_H, "droneS")
	# ---- 其余全部归轮作（唯一不需要登记的区域）----
	return ws


def geom():
	# v3：把分区几何一次算成**常数**，供 O(1) 判定使用（用户指出：分区随地图变大没调整 ✗）
	ws = get_world_size()
	bs = BLOCK_MAX
	if bs > ws // 2:
		bs = ws // 2
	if bs < 2:
		bs = 0
	nb = 0
	if bs > 0:
		nb = (ws // 2) // bs
		if nb < 1:
			nb = 1
	has_maze = 0
	if nb * bs + MAZE_SIDE <= ws:
		if ws >= MAZE_SIDE * 2:
			has_maze = 1
	return ws, bs, nb, has_maze


def zone_of(x, y):
	# ---- v3：**O(1) 判定**（原来遍历区域表 ⇒ 轮作每格都查表 ⇒ 时间被吃光 ✗）----
	# 分区是矩形且完全由 ws 决定 ⇒ 直接用坐标算式判断 ✓
	ws, bs, nb, has_maze = geom()
	if bs > 0:
		if y < bs:
			if x < nb * bs:
				return "block" + str(x // bs)
		if y >= bs and y < bs + SUN_H:
			if x < nb * bs:
				return "sun"
	if has_maze == 1:
		if x >= nb * bs and x < nb * bs + MAZE_SIDE:
			if y < MAZE_SIDE:
				return "maze0"
	return "farm"


def owner_of(name):
	if name == "farm":
		return "main"
	i = 0
	while i < len(NAMES):
		if NAMES[i] == name:
			return OWNER[i]
		i = i + 1
	return "none"


def in_zone(name, x, y):
	if zone_of(x, y) == name:
		return 1
	return 0


def is_farm(x, y):
	# 轮作专用：只有落在 "farm" 的格子才归主机
	if zone_of(x, y) == "farm":
		return 1
	return 0


def report():
	print("[zn] world", get_world_size(), "| 专区数", len(NAMES))
	i = 0
	while i < len(NAMES):
		print("[zn]  ", NAMES[i], "x", X0[i], "y", Y0[i], "w", W[i], "h", H[i], "owner", OWNER[i])
		i = i + 1
	return len(NAMES)


def check():
	# 自检：每一格必须**恰好**属于一个专区或归 farm（互不重叠 ✓ 拼满 ✓）
	ws = get_world_size()
	farm_n = 0
	bad = 0
	y = 0
	while y < ws:
		x = 0
		while x < ws:
			hit = 0
			i = 0
			while i < len(NAMES):
				if x >= X0[i] and x < X0[i] + W[i]:
					if y >= Y0[i] and y < Y0[i] + H[i]:
						hit = hit + 1
				i = i + 1
			if hit > 1:
				bad = bad + 1
			if hit == 0:
				farm_n = farm_n + 1
			x = x + 1
		y = y + 1
	# v2 修正：**本语言不支持三元表达式**（A if C else B）✗ —— 改成 if/else 语句 ✓
	if bad == 0:
		print("[zn] 自检：重叠格", bad, "| 归轮作的格", farm_n, "| 结论 通过 ✓")
	else:
		print("[zn] 自检：重叠格", bad, "| 归轮作的格", farm_n, "| 结论 有重叠 ✗")
	if bad == 0:
		return 1
	return 0


build()
if __name__ == "__main__":
	report()
	check()
