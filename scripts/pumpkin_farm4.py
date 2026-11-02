# ============================================================
# pumpkin_farm4.py —— 南瓜 v4：**完全独立的块主**（去掉全局屏障）
#
# 从 v3 的实测里学到的两件事（用户指出，且日志证实）：
#   1. v3 的 main 里有**全局屏障**：`wait_for` 等全部 32 架结束才开下一轮
#      ⇒ 一块早干完也要干等最慢那块 ⇒ 周期 = **最慢那块**（实测 cycle_s 9.4~12.2 秒，
#        而单架版只要 8.8 秒）。这正是我在 v2 里批评、却在 v3 里又造了一遍的东西。
#      ⇒ 本版：**每个块一个长驻"块主"，自己循环、永不等待别人**。
#   2. 报告用 `print` 要花 tick（`quick_print` 才免费）⇒ 本版全部改 `quick_print`
#      并且只在每 N 轮报一次。（注：实测这一项只占约 0.3%，顺手改掉，别指望它提速。）
#
# ============ 本版结构（16 块 7x7，pitch 8）============
#   块主 owner(b, with_helper)，**长驻无限循环**：
#     with_helper=1：派一架帮手管后半块，自己管前半块；
#                    自己那半块扫完全熟后，**轮询 has_finished(帮手)**，
#                    帮手也报 0 ⇒ 整块 7x7 已合并 ⇒ 走到块角割一刀（收一格 = 整块的钱 ✓）
#     with_helper=0：**独占整块**（两次半块扫描，自己开闸）—— 因为 cap=32，
#                    16 块 x 2 架 = 32，再加主线就超了 ⇒ 最后一块只能 1 架。
#   无人机配额：15 块 x (1 块主 + 1 帮手) + 1 块 x 1 块主 = **31 架 helper + 主线 = 32** ✓
#   主线**不参与干活**，只用免费的 quick_print 定期报速率，并等所有块主收工。
#
# ============ 依据全部是实测（probe_* 系列）============
#   move/harvest/plant = 200 tick    查询 = 1 tick    has_finished 轮询 = 4 tick
#   wait_for 取值 = 1 tick           spawn_drone = 211 tick   引擎 6,075 tick/秒
#   ⇒ 单机 30.4 动作/秒；生长：干 1.1~1.5 秒、**满水 0.14 秒**
#   v3 实测：16 块每轮都收满（每周期 +2,408,448 = 16 x 150,528 ✓），
#            但周期被屏障拉到 9.8 秒 ⇒ 14.7M/分；去掉屏障后单块自己的周期应回到 6~7 秒
#            ⇒ 预计 **20~23M/分**（180 格半块走位 ÷ 30.4 = 5.9 秒 + 2 次 spawn 0.07 秒）
#
# ============ 纪律（血泪，别踩）============
#  * **只认 Entities.Pumpkin**：clear() 后是草原、草永远可割、can_harvest() 恒真
#    ⇒ 不翻土不认实体就会把空地当成熟瓜（v2 全场零产出）。
#  * **死瓜 can_harvest() 永远 False**（文档）⇒ 判据必须同时看实体，否则循环卡死。
#  * **不要用时间戳调度（DUE）**：实测轮次间隔约 2 秒 ≫ 生长 0.14 秒 ⇒ 跳过永不触发。
#  * **不要再造全局屏障**：块与块之间必须完全独立（v3 的教训）。
#  * 没有三元表达式；LF + 制表符；一律用完整原文锚点改代码。
# ============================================================

VERSION = 4
BOARD = get_world_size()
REG = 7
GAP = 1
PITCH = REG + GAP
GRID = BOARD // PITCH
NBLOCK = GRID * GRID
TILES = REG * REG
HALF = (TILES + 1) // 2
PUMPKIN_GAIN = 80000000
WATER_THRESHOLD = 0.9
WATER_FLOOR = 20000
REPORT_SEC = 20                    # 每这么多秒报一次（用免费的时间/打印）
SPAWN_COST = 211

TARGET = [0]                       # 全局目标（模块全局 = 每架一份，但主线派工时值已定 ✓）
WOK = [1]


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


def cxx(b, i):
	return (b % GRID) * PITCH + (i % REG)


def cyy(b, i):
	return (b // GRID) * PITCH + (i // REG)


def tend_half(b, h):
	# 扫第 b 块的第 h 个半块，返回 0 = 这半块全部"存活且成熟"
	px = []
	py = []
	i = h * HALF
	stop = (h + 1) * HALF
	if stop > TILES:
		stop = TILES
	while i < stop:
		append(px, cxx(b, i))
		append(py, cyy(b, i))
		i = i + 1
	n = len(px)
	st = []
	i = 0
	while i < n:
		append(st, 0)
		i = i + 1
	p = n
	while p > 0:
		WOK[0] = 0
		if num_items(Items.Water) > WATER_FLOOR:
			WOK[0] = 1
		i = 0
		while i < n:
			if st[i] == 0:
				goto(px[i], py[i])
				if get_ground_type() != Grounds.Soil:
					till()
				t = get_entity_type()
				if t == Entities.Pumpkin:
					if can_harvest():
						st[i] = 1
				else:
					if t != None:
						harvest()
					plant(Entities.Pumpkin)
				if WOK[0] == 1:
					if get_water() < WATER_THRESHOLD:
						use_item(Items.Water)
			i = i + 1
		p = 0
		i = 0
		while i < n:
			if st[i] == 0:
				p = p + 1
			i = i + 1
	return 0


def harvest_block(b):
	goto(cxx(b, 0), cyy(b, 0))
	harvest()


def owner(b, with_helper):
	# **长驻的块主**：自己循环，绝不等待别的块 —— 这就是本版与 v3 的根本区别。
	while True:
		if num_items(Items.Pumpkin) >= TARGET[0]:
			return 0
		if with_helper == 1:
			d = spawn_drone(tend_half, b, 1)
			tend_half(b, 0)
			if d == None:
				# 帮手没派成（不该发生）⇒ 退回"独占整块"，保证这块不出废轮
				tend_half(b, 1)
				harvest_block(b)
			else:
				while has_finished(d) == False:
					pass
				r = wait_for(d)
				if r == 0:
					harvest_block(b)
		else:
			# 独占整块（cap 不够，只能这样）：两次半块扫描，自己开闸
			tend_half(b, 0)
			tend_half(b, 1)
			harvest_block(b)
	return 0


def main():
	print("=== pumpkin_farm4 v", VERSION, "start ===")
	print("board", BOARD, "reg", REG, "pitch", PITCH, "blocks", NBLOCK,
		"max_drones", max_drones(), "lv_pumpkins", num_unlocked(Unlocks.Pumpkins),
		"water", num_items(Items.Water), "carrot", num_items(Items.Carrot))
	need = (NBLOCK - 1) * 2 + 1
	print("[p4] 块主配额 =", need, "架 helper（含 1 块独占）| cap =", max_drones())
	if need > max_drones() - 1:
		print("[p4] ERROR: 无人机不够")
		return
	TARGET[0] = num_items(Items.Pumpkin) + PUMPKIN_GAIN
	print("[p4] 目标 =", num_items(Items.Pumpkin), "+", PUMPKIN_GAIN, "=", TARGET[0],
		"| 预计单块周期 180 格 / 30.4 = 5.9 秒 + 2 次 spawn 0.07 秒")
	clear()
	G0 = num_items(Items.Pumpkin)
	T0 = get_time()
	owners = []
	b = 0
	while b < NBLOCK - 1:
		d = spawn_drone(owner, b, 1)
		if d != None:
			append(owners, d)
		b = b + 1
	d = spawn_drone(owner, NBLOCK - 1, 0)
	if d != None:
		append(owners, d)
	print("[p4] launched", len(owners), "块主（前", len(owners) - 1, "个各带 1 架帮手）")
	# ---- 主线只做监控（quick_print 免费；什么都不干，也就不占用任何一块的进度）----
	tprev = get_time()
	while True:
		allf = 1
		i = 0
		while i < len(owners):
			if has_finished(owners[i]) == False:
				allf = 0
			i = i + 1
		now = get_time()
		if now - tprev >= REPORT_SEC:
			GN = num_items(Items.Pumpkin)
			DT = now - T0
			R = 0
			if DT > 0:
				R = (GN - G0) / DT
			quick_print("[p4] t", DT, "s pumpkin", GN, "per_min_M", R * 60 / 1000000,
				"(目标 20) water", num_items(Items.Water), "all_done", allf)
			tprev = now
		if allf == 1:
			break
	GN = num_items(Items.Pumpkin)
	DT = get_time() - T0
	R = 0
	if DT > 0:
		R = (GN - G0) / DT
	print("=== pumpkin_farm4 end ===", "gained", GN - G0, "elapsed_s", DT,
		"pumpkin_per_s", R, "pumpkin_per_min", R * 60)


main()
