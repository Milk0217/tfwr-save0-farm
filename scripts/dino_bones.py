# ============================================================
# dino_bones.py —— 养恐龙换骨头（目标：把混合种植从 10x 升到 20x）
#
# 机制（游戏内 dinosaurs 文档）：
#   - change_hat(Hats.Dinosaur_Hat) 戴上恐龙帽。帽子很重：move() 变 400 ticks，
#     但**每吃一颗苹果就 -3%（向下取整）**，所以后期移动几乎免费。
#   - 戴帽时无人机**不能绕边**，整个农场变成有界网格。
#   - 有足够仙人掌时会自动买一颗苹果放在**无人机脚下**；无人机在苹果上**再移动一次**
#     就吃掉它（尾巴长一节），并随机再生成一颗。
#   - 苹果**不能长在已种植的格子上** => 开跑前必须 clear()。
#   - 尾巴就是蛇身：移到尾巴上 move() 会失败，只有正在让开的尾尖能进。
#   - 换一顶别的帽子卸下恐龙帽 → 尾巴**立即结算：n 节 = n² 根骨头**。
#
# 策略：**沿哈密顿回路走**。
#   16x16 是偶数格，回路存在（构造见 build_cycle）。只要每步都沿回路前进 1 格，
#   蛇身就永远是头后面的一段**连续弧**，而前进的目标格必然不在身上
#   => **永不咬到自己**，不需要任何搜索、试探或回退。这是可证明安全的。
#   代价：每颗苹果平均要走半个回路（约 128 步）。
#   但因为 move() 成本按 0.97^k 衰减，跑满 256 颗的总耗时只比 100 颗多约 5%
#   —— 所以**跑满几乎免费**，没有理由中途收手。
#
# 成本：一颗苹果 = 2 个仙人掌（probe6 实测）。
# 本脚本会先 clear() 整片农场，跑完卸帽结算；之后再跑 main.py 重建农场即可。
# ============================================================

SIZE_OF_BOARD = get_world_size()
CELLS = SIZE_OF_BOARD * SIZE_OF_BOARD

MAX_APPLES = 420                   # 想吃的苹果数（受仙人掌库存会自动下调）
# 为什么从 240 抬到 420：骨头 = 尾巴节数²，**平方**意味着多吃一倍苹果 = 四倍骨头，
# 而 22x22 = 484 格，蛇身最多占满整盘（16x16 那次吃到 198/256 ≈ 77%，按此比例 22x22 约 370 颗）。
# 仙人掌现在很便宜（一块 6x6 一次收 5184 个），420 颗只要 840 个。
CACTUS_PER_APPLE = 2               # probe6: cost Apple -> Items.Cactus 2
CACTUS_KEEP = 20                   # 留一点仙人掌底
MAX_STEPS = 400000                 # 防死循环

# 哈密顿回路：CYCLE[i] = 环上第 i 个格子的编号（编号 = y*SIZE + x）
CYCLE = []
_i = 0
while _i < CELLS:
	append(CYCLE, 0)
	_i = _i + 1


def build_cycle():
	# 构造（以 16x16 为例）：
	#   行 0：自西向东走满 (0,0) -> (15,0)
	#   行 1：自东向西，只走 x=15..1
	#   行 2：自西向东，只走 x=1..15
	#   …… 交替，直到行 15（奇数行）走到 x=1
	#   收尾：西移到 (0,15)，再沿第 0 列一路北上回到 (0,0) —— 闭合
	# 这样第 0 列只在最后被用到一次，不会重复。
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
	print("[dino] cycle built, cells", n, "of", CELLS)


def step_to(dst):
	# 朝相邻的目标格走一步（不绕边 —— 戴帽时本来也绕不了）
	cx = get_pos_x()
	cy = get_pos_y()
	dx = dst % SIZE_OF_BOARD
	dy = dst // SIZE_OF_BOARD
	if dx > cx:
		return move(East)
	if dx < cx:
		return move(West)
	if dy > cy:
		return move(North)
	return move(South)


def dino_run(target):
	# clear() 让整片农场变成空草原，并把无人机放到 (0,0) —— 正好是回路起点
	clear()
	change_hat(Hats.Dinosaur_Hat)
	# 戴上帽子且仙人掌足够时，脚下会自动出现第一颗苹果
	idx = 0
	eaten = 0
	steps = 0
	on_apple = 0
	no_eat = 0
	while eaten < target and steps < MAX_STEPS:
		steps = steps + 1
		if get_entity_type() == Entities.Apple:
			on_apple = 1
		idx = (idx + 1) % CELLS
		if not step_to(CYCLE[idx]):
			print("[dino] move blocked at step", steps, "eaten", eaten)
			eaten = target
		else:
			if on_apple == 1:
				# 在苹果上又移动了一次 => 吃掉它，尾巴长一节
				on_apple = 0
				eaten = eaten + 1
				no_eat = 0
				if eaten % 40 == 0:
					print("[dino] eaten", eaten, "steps", steps, "cactus", num_items(Items.Cactus))
			else:
				# 尾巴占满棋盘后苹果长不出来 → 会一直空转，必须自己收工结算
				no_eat = no_eat + 1
				if no_eat > CELLS * 4:
					print("[dino] no apple for", no_eat, "steps, stopping at", eaten)
					eaten = target
	change_hat(Hats.Straw_Hat)
	return eaten


def bone_buy_polyculture():
	# 骨头到手后把买得起的 Polyculture 级别**一次买完**（每级翻倍：×20 -> ×40 -> ×80）
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
	print("=== dino_bones start ===")
	print("world_size", SIZE_OF_BOARD,
		"max_drones", max_drones(),
		"cactus", num_items(Items.Cactus),
		"bone", num_items(Items.Bone))
	build_cycle()

	cactus = num_items(Items.Cactus)
	target = MAX_APPLES
	if cactus < target * CACTUS_PER_APPLE + CACTUS_KEEP:
		target = (cactus - CACTUS_KEEP) // CACTUS_PER_APPLE
	if target < 10:
		print("[dino] not enough cactus:", cactus, "need", CACTUS_PER_APPLE, "per apple")
		return
	print("[dino] target_apples", target,
		"cactus_cost", target * CACTUS_PER_APPLE,
		"expected_bones", target * target)

	b0 = num_items(Items.Bone)
	eaten = dino_run(target)
	b1 = num_items(Items.Bone)
	print("[dino] eaten", eaten, "bones_gained", b1 - b0, "total_bones", b1)

	bone_buy_polyculture()
	print("=== dino_bones end ===")


main()
