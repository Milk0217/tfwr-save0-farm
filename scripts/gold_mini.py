# ============================================================
# gold_mini.py —— 极简挣金币：一座 8x8 迷宫、单机、只求 2000 金买 Megafarm
#
# 依据 docs/game/unlocks/mazes.md（权威）：
#   * 在**灌木**上用 `use_item(Items.Weird_Substance, n)` 长成一座 n×n 迷宫 ✓
#   * 每升一级：宝藏翻倍，但需要的奇异物质也翻倍 ⇒ 8x8 在 lv6 = 8×2^5 = **256** ✓
#   * 宝藏产量 = 迷宫面积 × 等级倍率 ⇒ 8x8 在 lv6 = 64×32 = **2048 金** ✓
#   * Hint 2：**无环迷宫的墙是连通的，顺着墙走就能遍历全部通道**（约 10 行代码 ✓）
#   * "Reusing a maze doesn't give you more gold" ⇒ 每次直接重建，省掉环的麻烦 ✓
#
# 为什么现在做这个（而不是继续磨南瓜）：
#   `Megafarm` 只要 gold 2000（探针实测）✓，而它解锁**多无人机** ⇒ 所有产线并行 ✓✓ ——
#   这比 Expand(8000 起、最高 410 万南瓜) 划算得多 ✓
#
# 用法：在**排行榜模拟里**（lb_enter 的 WHICH = 2，把参赛文件名临时改成 gold_mini）
#       或直接在真实存档里跑（真实存档同样能验证逻辑，且地块本来就大）。
# ============================================================

VERSION = 11
# v11：接上分区事实来源 —— **只在迷宫区内建迷宫**（用户指出：分区没随地图调整 ✗）
import zones
MAZE_N = 8                     # 棋盘 = 8x8 ⇒ 一座迷宫正好铺满
TARGET_GOLD = 2000             # Megafarm 的价格（probe_expand 实测 gold=2000）
DIRS = [North, East, South, West]
MAX_STEPS = 4000               # 单座迷宫的步数上限（8x8 最多几百步）


def go_to(tx, ty):
	# v5：**本文件必须自足** —— go_to 原来是 full_run 的，独立跑时不存在 ⇒ NameError ✗
	# （audit 点名：main() 第 100 行用到未定义的 go_to）
	while get_pos_x() != tx:
		move(East)
	while get_pos_y() != ty:
		move(North)


def can_afford(t):
	# v10：本文件必须自足（游戏报错：can_afford 从未被定义，但似乎在 full_run 里有 ✗）
	# 依据 docs/game/unlocks/costs.md：get_cost(t) 给出 {Item: 数量}，已满级返回 None ✓
	c = get_cost(t)
	if c == None:
		return 0
	for it in c:
		if num_items(it) < c[it]:
			return 0
	return 1


def substance_needed():
	# 文档：n 格迷宫要 n 份；每升一级翻倍。**不用 `**`**（本项目没用过这个运算符）
	amt = MAZE_N
	lv = num_unlocked(Unlocks.Mazes)
	i = 1
	while i < lv:
		amt = amt * 2
		i = i + 1
	return amt


def solve_maze():
	# 右手法则：能右转就右转，否则直行，否则左转，否则回头。
	# 文档保证（无环时）这样会遍历整座迷宫 ⇒ 一定会踩到宝藏 ✓
	idx = 1                    # 初始朝向 East
	steps = 0
	while steps < MAX_STEPS:
		if get_entity_type() == Entities.Treasure:
			return 1
		r = (idx + 1) % 4
		if can_move(DIRS[r]):
			idx = r
			move(DIRS[idx])
		elif can_move(DIRS[idx]):
			move(DIRS[idx])
		else:
			idx = (idx - 1) % 4
			if can_move(DIRS[idx]):
				move(DIRS[idx])
			else:
				idx = (idx + 2) % 4
				move(DIRS[idx])
		steps = steps + 1
	if get_entity_type() == Entities.Treasure:
		return 1
	return 0


def main():
	print("[gm] === gold_mini v", VERSION, "start ===")
	print("[gm] world", get_world_size(), "| gold", num_items(Items.Gold),
		"| weird", num_items(Items.Weird_Substance), "| power", num_items(Items.Power),
		"| Mazes lv", num_unlocked(Unlocks.Mazes))
	if num_unlocked(Unlocks.Mazes) <= 0:
		print("[gm] Mazes 还没解锁 ⇒ 什么都不做（纪律：动词先问解锁）")
		return
	sub = substance_needed()
	print("[gm] 每次建迷宫需要奇异物质", sub, "| 目标金币", TARGET_GOLD)
	# v3：轮数上限**派生**出来 —— 实测每座迷宫 36 金（world 6 ⇒ 6x6），
	# 原写死 40 轮 ⇒ 40x36 = 1440 < 2000 ⇒ 永远买不起 Megafarm ✗
	side = MAZE_N
	if side > get_world_size():
		side = get_world_size()
	per = side * side
	lv = num_unlocked(Unlocks.Mazes)
	i = 1
	while i < lv:
		per = per * 2
		i = i + 1
	cap = TARGET_GOLD // per + 20
	print("[gm] 每座预计", per, "金 ⇒ 轮数上限", cap)
	rounds = 0
	while num_items(Items.Gold) < TARGET_GOLD:
		rounds = rounds + 1
		if rounds > cap:
			print("[gm] 轮数上限到了还没够 ⇒ 收工（看读数）")
			return
		if num_items(Items.Weird_Substance) < sub:
			print("[gm] 奇异物质不足", sub, "⇒ 先回去施肥产奇异物质")
			return
		# ---- v4：**绝不 clear()** ----
		# 实测事故：clear() 会把整块地清成草 ⇒ wood/carrot/向日葵/树全没，
		#   农场收入断档数分钟（用户报告：某一时间点起没有草、木和胡萝卜收入 ✗）
		# 文档只要求在**灌木**上使用奇异物质（迷宫会自己占据 n×n 区域）⇒ 清场是多余的 ✗
		# ---- v6：**先找一格空地再建迷宫** ----
		# 实测：原来固定在 (0,0) 种灌木，而那格常被轮作占着（树/胡萝卜）⇒ plant 失败 ⇒
		#   迷宫长不出来 ⇒ 本函数每次都直接 return ⇒ 金币永远 0 ⇒ Megafarm 永远买不起 ✗
		#   依据 mazes.md：只要在**灌木**上用奇异物质就能长出迷宫 ⇒ 找一格草/空地即可 ✓
		# ---- v11：**只在迷宫区内建** ----
		# 用户指出：南瓜田随地图变大后，分区没跟着调整 ⇒ 迷宫（8x8）会推平农场或方块 ✗
		# 依据 docs/game/unlocks/mazes.md：在灌木上用奇异物质即长出 n x n 迷宫 ⇒
		#   只要站在**迷宫区原点**种下灌木即可，迷宫会占满它自己的 8x8 ✓
		ws2, bs2, nb2, has_maze = zones.geom()
		if has_maze == 0:
			print("[gm] 当前棋盘没有迷宫区 ⇒ 跳过（避免推平农场）")
			return
		zx = nb2 * bs2
		go_to(zx, 0)
		if can_harvest():
			harvest()
		plant(Entities.Bush)             # 文档：必须在灌木上使用奇异物质
		use_item(Items.Weird_Substance, sub)
		e = get_entity_type()
		if e != Entities.Hedge:
			if e != Entities.Treasure:
				print("[gm] 迷宫没长出来（脚下不是 Hedge/Treasure）⇒ 退出")
				return
		if solve_maze() == 0:
			print("[gm] ", MAX_STEPS, "步没找到宝藏 ⇒ 退出")
			return
		harvest()
		print("[gm] 第", rounds, "座迷宫收到 | gold", num_items(Items.Gold),
			"| weird", num_items(Items.Weird_Substance))
	# ---- v7：解锁失败时**把游戏的回答全部打出来**（不许猜 ✗）----
	# 实测：gold 2040 够、也没被扣，却返回 False ⇒ 是游戏拒绝了这次解锁 ⇒ 必须问清原因 ✓
	print("[gm] 试图解锁 Megafarm | gold", num_items(Items.Gold),
		"| gold", num_items(Items.Gold),
		"| can_afford", can_afford(Unlocks.Megafarm),
		"| 当前等级", num_unlocked(Unlocks.Megafarm))
	ok = unlock(Unlocks.Megafarm)
	if ok:
		print("[gm] Megafarm 解锁成功 ⇒ max_drones", max_drones(), "num_drones", num_drones())
	else:
		print("[gm] unlock 返回 False ⇒ 游戏拒绝。诊断：",
			"gold", num_items(Items.Gold),
			"can_afford", can_afford(Unlocks.Megafarm),
			"等级", num_unlocked(Unlocks.Megafarm),
			"Mazes 等级", num_unlocked(Unlocks.Mazes),
			"Dinosaurs", num_unlocked(Unlocks.Dinosaurs),
			"Leaderboard", num_unlocked(Unlocks.Leaderboard))
	print("[gm] === gold_mini end === rounds", rounds, "| gold", num_items(Items.Gold))


if __name__ == "__main__":
	main()
