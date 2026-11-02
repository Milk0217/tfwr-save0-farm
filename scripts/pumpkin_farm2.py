# ============================================================
# pumpkin_farm2.py —— 南瓜 **v4 架构**：每块 2 架（各管半块）+ 主机当收割门仲裁者
#
# 目标 20M/分。基线是 pumpkin_farm.py v3（1 架/块）：**实测 16.2M/分、cyc_s 8.9 秒**
#   （output.txt：CALIB 单块 150,528 = 294 x 512 ✓ lv_pumpkins 是 **10** 不是 9，
#     所以基础值是 512、全盘一轮 = 784 x 6 x 512 = 2,408,448）
#   ⇒ 要 20M/分 就必须 16 x 150,528 / T >= 333,333 ⇒ **T <= 7.22 秒**（现在 8.9）
#
# 周期拆解（实测反推）：**~4 代生长 x ~1.5 秒 + 扫描 ~3.1 秒**
#   1) 生长那 6 秒：水位门槛 0.9 ⇒ 水位约 0.95 ⇒ x4.8，而 watering.md 的上限就是 x5
#      ⇒ **快到头了**，只把门槛提到 0.95 再拿一点点（不提 1.0：那会让每格每次访问都浇水，水耗暴涨）
#   2) 扫描那 3.1 秒：**只有这块能砍** ⇒ 两块并行 ⇒ 3.1 -> 约 1.7 秒
#
# ============ 死结与它的解法 ============
# v3 里我判过「每块 2 架」无解：收割门要求**整块**待确认数为 0，而每架无人机只有自己的内存，
# 第 2 架不知道第 1 架那半边的状态。**那个判定漏了 `wait_for`**：
#   无人机之间确实不能共享内存，但**返回值是一条可靠信道**（wood/carrot 那 32 架汇总刀数就是靠它）。
# ⇒ 本版的角色分工：
#   * **tender(b, h)**：只管半块（25 / 24 格），**长驻**到自己那半块全部确认才返回。
#     长驻是关键 —— `STATE` 记忆（只复查待确认的格子）是 v3 的核心优化，
#     如果每轮重新 spawn，记忆就没了，扫描会退回「每轮全扫 49 格」。
#   * **主机 = 仲裁者**：收齐 32 个半块的返回值，按块相加；**两边都是 0** 才派一架去收那块。
#     每个数字都是那一架自己数出来的，没有任何猜测 ✓
#   * 收割：合并后的 7x7 收任意一格都拿整块的钱（v3 实测 92 次有效收获 x 55,296 = 总涨幅 ✓）
#     ⇒ 派一架走到块中心割一刀即可，不必每格都割。
#
# ============ 为什么这一版没有向日葵工人 ============
# 16 块 x 2 = **32 个半块，正好等于全部无人机数**（主机也算一架）⇒ 没有空闲机器。
# 电量实测不是问题：carrot_farm 跑了 40 万刀、全场没有向日葵，power 只从 26,256 漂到 24,796
# ⇒ 移动耗电小到可以忽略；而 v3 那 15 架向日葵整场也只贡献 +3.4/秒。若将来 power 真的见底，
# 症状是「所有动作突然慢一倍」，那时再把一个块降为单架去顶向日葵。
#
# ============ 纪律（血泪，别再踩）============
#  * **必须先 `till()` 再读 `get_entity_type()`**：clear() 后整盘是草原、草永远可割，
#    `can_harvest()` 恒真 ⇒ 会把「长草的空地」误判成「已确认成熟的南瓜」，第 1 轮就开闸割草，
#    随后全场空转、零产出（v2 实测踩过）。所以白名单是「只认 Entities.Pumpkin」。
#  * **合并后的巨型南瓜仍报 `Entities.Pumpkin`**（存根里只有 Pumpkin / Dead_Pumpkin 两个实体，
#    没有独立的 Mega 实体）⇒ 白名单不会误伤刚合并好的瓜 ✓
#  * **`GAP >= 1` 是硬约束**：紧挨着铺会让相邻方阵连片，而合并矩形按**短边**算产量
#    ⇒ 7x14 只给 7x7 的钱（v3 实测：433 次收获是 0 产出）。
#  * **不能提前收割**：整块全部存活且成熟才开闸，早割是纯亏。
#  * **目标必须是相对增量**（`num_items + GAIN`）：绝对值目标已经连栽两次
#    （wood 设 1e9 而开局 1.33B、carrot 设 4e8 而开局 3.98e8 ⇒ 都是第 10 圈收工、
#     平均值被启动期拖成 862M/191M，而稳定段其实是 1,150M/258M）。
#  * **没有三元表达式**，`**` 没用过 ⇒ 一律不写。
# ============================================================

VERSION = 5
SIZE_OF_BOARD = get_world_size()
REG_SIZE = 7                       # 边长（>=6 才落到 n*n*6 的口径，= 6 格/格）
GAP = 1                            # 硬约束
PITCH = REG_SIZE + GAP             # 8，正好整除 32
GRID = SIZE_OF_BOARD // PITCH      # 4
NBLOCK = GRID * GRID               # 16
TILES = REG_SIZE * REG_SIZE        # 49
HALF = (TILES + 1) // 2            # 25（第 0 半块 25 格，第 1 半块 24 格）
NSLOT = NBLOCK * 2                 # 32 个半块 = 全部无人机数

PUMPKIN_GAIN = 80000000            # **相对增量**（不是绝对值！见纪律那段）
CYCLE_CAP = 400                    # 大循环上限（保险）
ROUND_CAP = 200                    # 单个半块内部的轮数上限（保险）
REPORT_EVERY = 1                   # 每几轮打一行（一轮已经是整盘一次，够慢了）
WATER_THRESHOLD = 0.95             # 0.9 -> 0.95：拿生长那一档（上限 x5 就是水位 1.0）
WATER_FLOOR = 20000
# ---- 下面两个开关是"把逐格开销搬出逐格循环"用的（wood v6 实测这是最大的空转来源）----
# 旧写法 `water_here()` 每访问一格要发 4 次调用（num_items / get_ground_type /
# get_entity_type / get_water），而它 99% 的情况什么都不做。
# 每个半块一个周期只访问约 31 格 ⇒ 155 次调用 ÷ 77 次/秒 ≈ 2.0 秒，占整个周期的四分之一。
WATER_EVERY = 2                    # 稳态下每 2 轮才查一次水位
WARMUP_ROUNDS = 2                  # 开局头两轮每轮都查（水位从 0 顶上去）
CALIB = 1

BLOCK_OX = []
BLOCK_OY = []
_i = 0
while _i < NBLOCK:
	append(BLOCK_OX, (_i % GRID) * PITCH)
	append(BLOCK_OY, (_i // GRID) * PITCH)
	_i = _i + 1


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


def tender(b, h):
	# 只管第 b 块的第 h 个半块，长驻到「我这半块全部存活且成熟」才返回 0。
	# 撞到 ROUND_CAP 还没齐就返回"还剩几格"（>0），主机据此判该块未就绪。
	px = []
	py = []
	i = h * HALF
	stop = (h + 1) * HALF
	if stop > TILES:
		stop = TILES
	while i < stop:
		append(px, BLOCK_OX[b] + (i % REG_SIZE))
		append(py, BLOCK_OY[b] + (i // REG_SIZE))
		i = i + 1
	n = len(px)
	st = []
	td = []
	i = 0
	while i < n:
		append(st, 0)              # 0 = 待确认；1 = 已确认「存活且成熟」
		append(td, 0)              # 0 = 这一格还没查过地面/翻过土；1 = 已处理过
		i = i + 1
	rounds = 0
	p = n
	while rounds < ROUND_CAP:
		# **每轮只算一次**的开关（放进逐格循环就是每格 4 次调用的空转，见文件头那段）
		water_now = 0
		if num_items(Items.Water) > WATER_FLOOR:
			if rounds < WARMUP_ROUNDS:
				water_now = 1
			else:
				if rounds % WATER_EVERY == 0:
					water_now = 1
		i = 0
		while i < n:
			if st[i] == 0:
				goto(px[i], py[i])
				if td[i] == 0:
					# 地面类型**一格里一个周期只查一次**：翻过之后不会变回草原
					# （仍然是"先翻土再读实体"那条纪律：草原上草永远可割，不翻土会误判）
					if get_ground_type() != Grounds.Soil:
						till()
					td[i] = 1
				t = get_entity_type()
				if t == Entities.Pumpkin:
					if can_harvest():
						st[i] = 1      # 一旦确认就永远成立（成熟后不会再枯死）
				else:
					# 空格 / Dead_Pumpkin / 别的东西：清掉重种
					if t != None:
						harvest()
					plant(Entities.Pumpkin)
				# 只给**还没确认**的格子浇水（已确认的成熟瓜不需要水，而且它也不会再被访问）
				if st[i] == 0:
					if water_now == 1:
						if get_water() < WATER_THRESHOLD:
							use_item(Items.Water)
			i = i + 1
		p = 0
		i = 0
		while i < n:
			if st[i] == 0:
				p = p + 1
			i = i + 1
		if p == 0:
			return 0
		rounds = rounds + 1
	return p


def harvest_block(b):
	# 合并且整块成熟的 7x7：收任意一格都拿整块的钱 ⇒ 走到块中心割一刀
	goto(BLOCK_OX[b] + REG_SIZE // 2, BLOCK_OY[b] + REG_SIZE // 2)
	harvest()


def main():
	print("=== pumpkin_farm2 v", VERSION, "start ===")
	print("board", SIZE_OF_BOARD, "reg", REG_SIZE, "gap", GAP, "pitch", PITCH,
		"blocks", NBLOCK, "tiles/block", TILES, "slots", NSLOT,
		"max_drones", max_drones(), "lv_pumpkins", num_unlocked(Unlocks.Pumpkins),
		"water", num_items(Items.Water), "carrot", num_items(Items.Carrot))
	TARGET = num_items(Items.Pumpkin) + PUMPKIN_GAIN
	print("[p2] 目标 =", num_items(Items.Pumpkin), "+", PUMPKIN_GAIN, "=", TARGET,
		"（按 20M/分 约需", PUMPKIN_GAIN / 20000000, "分钟）")
	if NSLOT > max_drones():
		print("[p2] ERROR: 半块数", NSLOT, "超过无人机数", max_drones(), "⇒ 停下")
		return
	clear()
	cap = max_drones()
	# ---- 开局自标定：主机单独按两半顺序跑一次 block 0，量干净的单块产量 ----
	if CALIB == 1:
		print("[p2] CALIB start: 主机单机跑 block 0 的两个半块，量干净的单块产量")
		C0 = num_items(Items.Pumpkin)
		T0 = get_time()
		r1 = tender(0, 0)
		r2 = tender(0, 1)
		harvest_block(0)
		PC = num_items(Items.Pumpkin) - C0
		print("[p2] CALIB end: 单块干净产量 =", PC,
			"| 理论 7x7 = 294 x 2^(lv-1) =", 294 * (2 ** (num_unlocked(Unlocks.Pumpkins) - 1)),
			"| 单机跑两个半块用了", get_time() - T0, "秒 | 残留待确认", r1, r2)
		if PC <= 0:
			print("[p2] *** CALIB 产量为 0 ⇒ 停下来查 tender 的翻土那一步，别继续跑 ***")
			return
	# ---- 正式开跑：每轮 = 派满 32 个半块 ⇒ 收齐 ⇒ 收割就绪的块 ----
	G0 = num_items(Items.Pumpkin)
	GT0 = get_time()
	cycle = 0
	ready_n = 0
	while cycle < CYCLE_CAP:
		cycle = cycle + 1
		T0 = get_time()
		# 槽 0 由主机自己跑，槽 1..31 派出去
		drones = []
		slots = []
		s = 1
		while s < NSLOT:
			d = spawn_drone(tender, s // 2, s % 2)
			if d != None:
				append(drones, d)
				append(slots, s)
			s = s + 1
		pend = []
		i = 0
		while i < NSLOT:
			append(pend, 1)
			i = i + 1
		# 主机自己也管半个块（没有空闲机器可用，见文件头那段）
		pend[0] = tender(0, 0)
		i = 0
		while i < len(drones):
			pend[slots[i]] = wait_for(drones[i])
			i = i + 1
		# 按块汇总：两边都是 0 才算整块就绪
		ready = []
		b = 0
		while b < NBLOCK:
			if pend[b * 2] == 0:
				if pend[b * 2 + 1] == 0:
					append(ready, b)
			b = b + 1
		notready = NBLOCK - len(ready)
		# 就绪的块各派一架去收（并行走，别让主机一趟趟跑）
		hs = []
		i = 0
		while i < len(ready):
			d = spawn_drone(harvest_block, ready[i])
			if d != None:
				append(hs, d)
			i = i + 1
		i = 0
		while i < len(hs):
			wait_for(hs[i])
			i = i + 1
		ready_n = ready_n + len(ready)
		DT = get_time() - T0
		GN = num_items(Items.Pumpkin)
		TT = get_time() - GT0
		RATE = 0
		if TT > 0:
			RATE = (GN - G0) / TT
		if cycle % REPORT_EVERY == 0:
			print("[p2] cycle", cycle, "cycle_s", DT, "ready", len(ready), "/", NBLOCK,
				"harvests_total", ready_n, "pumpkin", GN,
				"water", num_items(Items.Water),
				"per_min_M", RATE * 60 / 1000000, "(目标 20)")
		if notready > 0:
			print("[p2] 注意: 有", notready, "块这一轮没收（待确认数没归零），下一轮会接着长")
		if num_items(Items.Pumpkin) >= TARGET:
			break
	GN = num_items(Items.Pumpkin)
	TT = get_time() - GT0
	RATE = 0
	if TT > 0:
		RATE = (GN - G0) / TT
	print("=== pumpkin_farm2 end ===", "cycles", cycle, "harvests", ready_n,
		"gained", GN - G0, "elapsed_s", TT,
		"pumpkin_per_s", RATE, "pumpkin_per_min", RATE * 60,
		"per_block_cycle_s", TT / cycle)


main()
