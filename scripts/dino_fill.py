# ============================================================
# dino_fill.py —— 一次跑完恐龙的三件事
#   任务1：让一个恐龙**填满整个农场**
#   任务2：让恐龙长度达到 **1000**
#   任务3：优化恐龙的速度
#
# ============ 事实（docs/game/unlocks/dinosaurs.md 原文，不是猜的）============
#  * 戴上 `Hats.Dinosaur_Hat` 后，**脚下会自动买一个苹果放上去**（需要仙人掌）。
#  * 无人机**在苹果上再 `move()` 一次就吃掉它、尾巴 +1**，并随机再生一个苹果。
#  * 尾巴拖在身后、占住走过的格子；`move()` 到尾巴上会**失败并返回 False**
#    （最后一节会闪开，所以能踩上去）。文档明说：**"if the snake fills out the whole
#    farm, you will not be able to move anymore"** ⇒ **动不了 = 满了**，这就是判定。
#  * 戴帽子时**不能绕边**（和平时的环面不同）⇒ 农场是有界网格。
#  * 摘帽（换任何别的帽子）时收割尾巴：**bones = 长度²**，再乘等级倍率 `2^(lv-1)`
#    （我们自己的实测：`eaten 444 bones_gained 3,154,176` = 444² x 16 ⇒ Dinosaurs lv5 = x16 ✓）
#  * 戴帽子时 `move()` 要 **400 tick**（平时 200）；**每吃一个苹果 -3%（向下取整）**，
#    一直降到底为止 ⇒ **"优化速度"的唯一杠杆就是多吃苹果**：
#        0 个苹果 400 tick/格 → 444 个已接近地板（按文档那个循环，地板是 33 tick）
#    ⇒ 所以"填满农场"（吃满 1024 个）**顺便就把速度压到了极限** ✓ 三件事是一条路。
#
# ============ 为什么用汉密尔顿回路（文档提示 1 就是这个思路）============
#  只要沿一条**固定的闭合回路**前进：尾巴永远拖在身后的回路上，**正前方永远是空格**
#  ⇒ 数学上不可能把自己困死 ✓（贪心追苹果那种写法会，这是蛇类游戏的通病。）
#  而回路覆盖全部 1024 格 ⇒ **吃掉第 1024 个苹果时，尾巴正好填满整块农场** ⇒
#  任务1 完成，此时长度 = 1024 ≥ 1000 ⇒ **任务2 同时完成** ✓
#
#  回路构造（32x32，偶数边长）：保留 **第 0 列当回程**，其余 31 列逐行蛇形走完 32 行，
#  最后沿第 0 列南到底、再向东一步回到起点闭合。步数核对：
#        32 行 x 30 步（覆盖 x=1..31 共 31 格） = 960
#        行间向北 31 步 + 收尾（西1 + 南31 + 东1）= 64
#        ---------------------------------------------------- 合计 **1024** ✓ 正好一格一步
#
# ============ 纪律 ============
#  * **`get_tick_count()` / `get_time()` / `quick_print()` 完全免费**（timing.md）⇒
#    测速度用它们，不会把被测对象本身拖慢。
#  * 内层循环要**极简**：每格只做 `取方向 -> move -> 计数`。任何额外调用（比如每格
#    都 `measure()`）都会在地板 33 tick 的移动成本上翻好几倍。
#  * **苹果吃光是会停的**：苹果要花仙人掌买，买不起就不再生成 ⇒ 尾巴停止增长。
#    所以开局打印仙人掌存量，收工打印实际消耗，别让它静默卡住。
#  * 一直动不了时**必须换帽子才能收骨头**（尾巴只在摘帽时结算）。
#  * 没有三元表达式 ⇒ 一律 if/else。
# ============================================================

VERSION = 1
SIZE_OF_BOARD = get_world_size()
N = SIZE_OF_BOARD
CELLS = N * N
REPORT_MOVES = 20000               # 每这么多步报一次速度（用免费的 tick 计数）
MAX_MOVES = CELLS * 4000           # 保险上限：远超填满所需的 1024 圈
SET_SIZE = 0                       # >0 就在开场 set_world_size 成这个值（0 = 不动）

CYCLE = []                         # 预先算好的方向序列（一步一格，长度 = CELLS）


def build_cycle():
	# 见文件头"回路构造"。只做一次，之后主循环里只查表。
	y = 0
	while y < N:
		i = 0
		while i < N - 2:
			if y % 2 == 0:
				append(CYCLE, East)
			else:
				append(CYCLE, West)
			i = i + 1
		if y < N - 1:
			append(CYCLE, North)
		y = y + 1
	# 收尾：此刻在 (1, N-1)
	append(CYCLE, West)            # -> (0, N-1)
	i = 0
	while i < N - 1:
		append(CYCLE, South)       # 沿第 0 列回到 y=0
		i = i + 1
	append(CYCLE, East)            # -> (1, 0)，闭合


def main():
	print("=== dino_fill v", VERSION, "start ===")
	if SET_SIZE > 0:
		set_world_size(SET_SIZE)
		print("[dino] set_world_size ->", SET_SIZE)
	print("board", N, "cells", CELLS,
		"lv_dinosaurs", num_unlocked(Unlocks.Dinosaurs),
		"cactus", num_items(Items.Cactus),
		"bone", num_items(Items.Bone))
	build_cycle()
	print("[dino] 回路长度 =", len(CYCLE), "（应等于", CELLS, "）")
	if len(CYCLE) != CELLS:
		print("[dino] ERROR: 回路步数不等于格数，回头查 build_cycle，先别跑")
		return
	# ---- 戴帽开跑 ----
	C0 = num_items(Items.Cactus)
	B0 = num_items(Items.Bone)
	# ---- 开跑前的两件准备工作，**顺序很关键** ----
	# 1) `clear()`：清掉地里的一切。文档说 "The apple cannot spawn if something else is
	#    planted where it wants to be" ⇒ 地里留着作物会让苹果随机落点失败。
	#    **但 clear() 会重置无人机位置**（plant.md："Call clear() to reset the farm to all
	#    grass and reset drone position"）—— 这就是它必须放在最前面的原因。
	clear()
	# 2) 走到回路的起点 (1, 0)。这一步在**戴帽子之前**做：此时 move 只要 200 tick、
	#    而且还能绕边，戴帽子之后就都不能了。
	while get_pos_x() != 1:
		move(East)
	while get_pos_y() != 0:
		move(South)
	# 3) 最后才戴帽子：戴上后**脚下会自动买一个苹果**，所以它一定落在 (1,0)，
	#    也正是回路的第一个格子 ⇒ 第一步 move 就吃掉它，尾巴从 0 变 1 ✓
	change_hat(Hats.Dinosaur_Hat)
	moves = 0
	i = 0
	tm = get_tick_count()
	t0 = get_time()
	w0 = 0
	stuck = 0
	while moves < MAX_MOVES:
		if move(CYCLE[i]) == False:
			stuck = 1
			break
		moves = moves + 1
		i = i + 1
		if i >= CELLS:
			i = 0
		if moves % REPORT_MOVES == 0:
			tk = get_tick_count() - tm
			dt = get_time() - t0
			# **本语言没有三元表达式**（`A if C else B`）⇒ 一律 if/else 语句。
			# （gamelang.py 就是为了拦这类"Python 有、这里没有"的写法而写的工具。）
			gps = 0
			if dt > 0:
				gps = (moves - w0) / dt
			print("[dino] moves", moves, "圈数", moves / CELLS,
				"ticks每格", tk / (moves - w0),
				"格/秒", gps,
				"仙人掌", num_items(Items.Cactus),
				"bone", num_items(Items.Bone))
			tm = get_tick_count()
			t0 = get_time()
			w0 = moves
	print("[dino] 停下来了: moves", moves, "stuck", stuck,
		"仙人掌消耗", C0 - num_items(Items.Cactus))
	if stuck == 0:
		print("[dino] 到达 MAX_MOVES 上限仍未卡住 —— 可能苹果买不起了（仙人掌不足），尾巴停止增长")
	# ---- 换帽子收割尾巴（**只有摘帽这一刻才结算骨头**）----
	change_hat(Hats.Gray_Hat)
	B1 = num_items(Items.Bone)
	gain = B1 - B0
	print("[dino] 收割: bones +", gain)
	if gain > 0:
		# bones = 长度² x 2^(lv-1) ⇒ 反推长度，验证"长度达到 1000"这条任务
		LV = 2 ** (num_unlocked(Unlocks.Dinosaurs) - 1)
		L = (gain / LV) ** 0.5
		print("[dino] 反推尾巴长度 =", L, "（倍率 2^(lv-1) =", LV, "）")
		if L >= 1000:
			print("[dino] 任务2 达成 ✓ 长度", L, ">= 1000")
		else:
			print("[dino] 任务2 未达成: 长度", L, "< 1000（是不是中途卡住/苹果断供了？）")
	print("=== dino_fill end ===")


main()
