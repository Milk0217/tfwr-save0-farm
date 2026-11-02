# ============================================================
# quests.py —— 四个一次性小任务
#   1) 抚摸小猪            pet_the_piggy()
#   2) 治愈一株受感染的植物
#   3) 让无人机翻 1000 次后空翻
#   4) 制作并收获一个 32x32 的南瓜
#
# ============ 每条都来自文档/存根，不是猜的 ============
#  * `pet_the_piggy()` **不需要任何物品**。`Items.Piggy` 的说明是
#    "This item has been removed from the game but remains as a nostalgia trophy."
#    ⇒ 直接调用即可，别去找猪。
#  * `pet_the_piggy()` 和 `do_a_flip()` 都写着 **"takes 1s to execute"**，
#    并且 **"This action is not affected by speed upgrades"**
#    ⇒ 1000 次后空翻 = **1000 游戏秒 ≈ 16.7 分钟**，速度升级救不了。
#    所以本脚本把它排在**最后**做，免得挡住前三个的结果。
#    （想让 32 架分摊、约 32 秒做完？只有当游戏的计数器是全局的时候才成立；
#      如果是"每架各自计数"，那就得每架翻满 1000 次 = 还是 16.7 分钟，没有收益。
#      没法验证，所以默认用最稳的单机顺序版。）
#  * **感染与治愈**（fertilizer.md）：
#      "Plants grown with fertilizer will be infected."
#      "Weird Substance ... has the effect of toggling the infected status of the
#       plant and all adjacent plants."
#    ⇒ 治愈 = 对一个**已感染**的植物用一次 `Items.WeirdSubstance`。
#    本脚本用最稳的顺序：种下 -> 切换一次(变成感染) -> 施一次肥(文档里的感染途径)
#    -> 再切换一次(**治愈**)。两次切换净效果为零，所以邻居也回到原状 ✓
#    万一最后一步没生效，把 CURE_TOGGLE_TIMES 改成 1 再跑一次即可。
#  * **32x32 南瓜**（pumpkins.md）：
#      产量 n>=6 时是 `n*n*6` ⇒ 32x32 = 1024*6 = **6144 个**（不是 32768）。
#      "pumpkins have a 20% chance of dying once they are fully grown"
#      "Planting a new plant in its place automatically removes the dead pumpkin"
#      "can_harvest() always returns False on dead pumpkins"
#      "When all the pumpkins in a square are fully grown, they will grow together
#       to form a giant pumpkin."
#    ⇒ 1024 格**同时**活着且成熟才会合并。20% 死亡率下靠运气不可能，所以是**补种循环**：
#      每轮 32 架各扫一行、把空格/死南瓜补种上，并把"本行是否全熟"报给主线；
#      32 行全报 1 的那一轮就收。成熟只掷一次死亡（"once they are fully grown"），
#      所以轮数是收敛的（约 5-6 轮）。
#    ⇒ **中途绝对不能割**：割掉任何一格，那个方块就永远合并不起来。
#
# ============ 纪律 ============
#  * 没有三元表达式，`**` 没用过 ⇒ 一律不写。
#  * `quick_print()` 免费，普通 `print` 不免费（timing.md）⇒ 高频进度用 quick_print。
#  * 世界是环面：一路向东 32 步回到原处，所以扫完一行不用回头走。
#  * 死循环一律带上限（本脚本每处 while 都有圈数上限）。
# ============================================================

VERSION = 1
BOARD = get_world_size()
CELLS = BOARD * BOARD
FLIPS = 1000                       # 后空翻次数（每次 1 秒）
CURE_TOGGLE_TIMES = 1              # 最后"治愈"要切换几次
PUMPKIN_ROUND_CAP = 120            # 南瓜补种轮数上限（保险，正常 5-6 轮就齐）
GROW_TIMEOUT_S = 60


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


def wait_grown(max_sec):
	t0 = get_time()
	while get_time() - t0 < max_sec:
		if can_harvest():
			return 1
	return 0


# ---------------------------------------------------------------
# 1) 抚摸小猪
# ---------------------------------------------------------------
def quest_piggy():
	print("[quest] 1) 抚摸小猪 ……")
	pet_the_piggy()                # 不需要任何物品，也不消耗资源
	print("[quest] 1) 完成 ✓")


# ---------------------------------------------------------------
# 2) 治愈一株受感染的植物
# ---------------------------------------------------------------
def quest_cure():
	print("[quest] 2) 治愈一株受感染的植物 ……")
	clear()
	goto(0, 0)
	if get_ground_type() != Grounds.Soil:
		till()
	plant(Entities.Bush)
	if wait_grown(GROW_TIMEOUT_S) == 0:
		print("[quest] 2) 植物 60 秒还没长好，放弃")
		return
	print("[quest] 2) 灌木已长好")
	# 第一次切换：健康 -> 感染
	if num_items(Items.Weird_Substance) > 0:
		ok = use_item(Items.Weird_Substance)
		print("[quest] 2) 切换一次（健康->感染）返回", ok)
	else:
		print("[quest] 2) 没有 Items.Weird_Substance ⇒ 没法做，先攒这个")
		return
	# 施肥：文档里"用肥料种出来的植物会被感染"，走一遍这个途径
	if num_items(Items.Fertilizer) > 0:
		ok2 = use_item(Items.Fertilizer)
		print("[quest] 2) 施肥（文档里的感染途径）返回", ok2)
	# 第二次切换：感染 -> **治愈**
	i = 0
	while i < CURE_TOGGLE_TIMES:
		ok3 = use_item(Items.Weird_Substance)
		print("[quest] 2) 切换一次（感染->治愈）返回", ok3)
		i = i + 1
	print("[quest] 2) 完成 ✓")


# ---------------------------------------------------------------
# 4) 32x32 南瓜（先做，因为后空翻很慢）
# ---------------------------------------------------------------
def pumpkin_worker(row):
	# 扫自己那一行：把空格/死南瓜补种，数出"活着且成熟"的格数。
	# 返回 1 = 本行全熟（32/32），0 = 还没齐。
	# **绝不在这里 harvest()** —— 割掉一格，32x32 就永远合并不起来了。
	# **必须先走到自己那一行**：`spawn_drone` 只会在父机当前位置生成，不会替你移动。
	goto(0, row)
	ready = 0
	x = 0
	while x < BOARD:
		ent = get_entity_type()
		if ent == Entities.Pumpkin:
			if can_harvest():
				ready = ready + 1
		else:
			# 空格或 Dead_Pumpkin：补种会自动移除死南瓜，不用先割
			if get_ground_type() != Grounds.Soil:
				till()
			plant(Entities.Pumpkin)
		move(East)
		x = x + 1
	if ready >= BOARD:
		return 1
	return 0


def quest_pumpkin():
	print("[quest] 4) 制作并收获一个 32x32 的南瓜 ……")
	cost = get_cost(Entities.Pumpkin)
	need = 0
	if cost == None:
		print("[quest] 4) get_cost 返回 None（异常）")
	else:
		for item in cost:
			print("[quest] 4) 种一棵南瓜的代价:", item, "=", cost[item])
			if item == Items.Carrot:
				need = cost[item] * CELLS * 3      # 3 倍余量留给补种
	if need > 0:
		if num_items(Items.Carrot) < need:
			print("[quest] 4) 胡萝卜不够（需要约", need, "，只有",
				num_items(Items.Carrot), "）⇒ 跳过南瓜")
			return
	clear()
	cap = max_drones()
	n = BOARD
	if n > cap:
		n = cap
	rounds = 0
	allready = 0
	while rounds < PUMPKIN_ROUND_CAP:
		rounds = rounds + 1
		drones = []
		i = 1
		while i < n:
			d = spawn_drone(pumpkin_worker, i * (BOARD // n))
			if d != None:
				append(drones, d)
			i = i + 1
		# **按"实际扫到的行数"判定**，不要用 n：机器少于 32 架时步长 >1，会漏行
		nrows = 1 + len(drones)
		allready = pumpkin_worker(0)
		i = 0
		while i < len(drones):
			allready = allready + wait_for(drones[i])
			i = i + 1
		quick_print("[quest] 4) 第", rounds, "轮: 全熟的行数", allready, "/", nrows,
			"（本轮扫了", nrows, "行）")
		if allready >= nrows:
			break
	if allready < nrows:
		print("[quest] 4) 轮数用尽仍未全熟（可能一直有南瓜死掉），停下")
		return
	# ---- 全盘 1024 格同时活着且成熟 ⇒ 已经合并成 32x32 巨型南瓜 ⇒ 收 ----
	goto(0, 0)
	p0 = num_items(Items.Pumpkin)
	harvest()
	gain = num_items(Items.Pumpkin) - p0
	print("[quest] 4) 收获 32x32 巨型南瓜: pumpkin +", gain,
		"（文档公式 32x32 = 1024x6 = 6144 个 x 基础值）")
	print("[quest] 4) 完成 ✓ 用了", rounds, "轮")


# ---------------------------------------------------------------
# 3) 1000 次后空翻（最慢，放最后）
# ---------------------------------------------------------------
def quest_flips():
	print("[quest] 3) 后空翻 x", FLIPS, " —— 每次 1 秒且不受速度升级影响 ⇒ 约",
		FLIPS, "秒 =", FLIPS / 60, "分钟，请耐心等")
	i = 0
	while i < FLIPS:
		do_a_flip()
		i = i + 1
		if i % 100 == 0:
			quick_print("[quest] 3) 已翻", i, "/", FLIPS)
	print("[quest] 3) 完成 ✓")


def main():
	print("=== quests v", VERSION, "start ===")
	print("board", BOARD, "max_drones", max_drones(),
		"fertilizer", num_items(Items.Fertilizer),
		"weird_substance", num_items(Items.Weird_Substance),
		"carrot", num_items(Items.Carrot),
		"pumpkin", num_items(Items.Pumpkin))
	quest_piggy()
	quest_cure()
	quest_pumpkin()
	quest_flips()
	print("=== quests end === 四项都走完了")


main()
