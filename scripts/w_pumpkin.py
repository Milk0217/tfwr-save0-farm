# ============================================================
# w_pumpkin.py —— 南瓜工人（自包含模块，v1）
#
# 抽出来的理由：14 个方阵的状态机是整套农场里最集中、最独立的一块
# （状态表 + 逐方阵结算 + 补种都在这里），抽干净之后 main.py 会明显变薄，
# 而改南瓜逻辑不必再碰主控文件。
#
# 依据 `docs/scripting/import.md`（权威）：每次无人机执行都是独立的一次程序执行，
# `import` 会在它自己的内存里重跑 ⇒ **本文件的状态表在每架副机里各有一份**，
# 语义与「同一文件里的全局量」完全一致 ⇒ 跨模块用 spawn_drone 派副机是安全的。
# 规矩：主控用 `import w_pumpkin`（不要 `from w_pumpkin import *`）。
#
# 关键机制（别改坏）：
#   1. **逐方阵独立结算**：`pending == 0` 只数本片。0.8^36 已是 0.03%，
#      几片合判会低到几乎为零 ⇒ 南瓜直接停产。
#   2. **一片一机**：每架只盯一个方阵 ⇒ 一轮最多 36 次访问 ≈ 6 秒，
#      与成阵周期 8~10 秒同量级；2 架管 6 片时轮次要 35~45 秒，产能差一大截。
#   3. 实测一次连锁收割 = **13,824 个**（文档写的 n²*6 = 216 是错的，是它的 64 倍）。
# ============================================================

import layout

SIZE_OF_BOARD = layout.SIZE_OF_BOARD
PUMPKIN_SIZE = layout.PUMPKIN_SIZE
PUMPKIN_TILE_COUNT = layout.PUMPKIN_TILE_COUNT
PUMPKIN_SQUARES = layout.PUMPKIN_SQUARES
PUMPKIN_OX = layout.PUMPKIN_OX
PUMPKIN_OY = layout.PUMPKIN_OY

WATER_THRESHOLD = 0.7
PUMPKIN_FULL_EVERY = 20            # 每多少轮强制全量复查一次
PUMPKIN_STALE_LIMIT = 40           # 连续多少轮没收到就强制全量复查
REPORT_EVERY = 5
BUILD = 1                          # 本文件自己的版本号（启动时打印，便于核对游戏跑的是哪一版）

# 诊断：[最近一次连锁收割的产量, 收割次数, 累计产量]
PYIELD = [0, 0, 0]


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


def water_if_needed():
	if get_ground_type() == Grounds.Soil:
		if get_entity_type() != None and get_water() < WATER_THRESHOLD:
			use_item(Items.Water)


PUMPKIN_STATE = []                 # 0 = 待确认；1 = 已确认「存活且成熟」（每个方阵连续 36 格）
PUMPKIN_XS = []
PUMPKIN_YS = []
_pi = 0
while _pi < PUMPKIN_TILE_COUNT * PUMPKIN_SQUARES:
	_sq = _pi // PUMPKIN_TILE_COUNT
	_k = _pi % PUMPKIN_TILE_COUNT
	append(PUMPKIN_STATE, 0)
	append(PUMPKIN_XS, PUMPKIN_OX[_sq] + (_k % PUMPKIN_SIZE))
	append(PUMPKIN_YS, PUMPKIN_OY[_sq] + (_k // PUMPKIN_SIZE))
	_pi = _pi + 1


def pumpkin_reset_square(sq):
	base = sq * PUMPKIN_TILE_COUNT
	i = 0
	while i < PUMPKIN_TILE_COUNT:
		PUMPKIN_STATE[base + i] = 0
		i = i + 1


def replant_square(sq):
	# 只补**一个**方阵：连锁收割只会清空被收的那一片，补种也必须只补那一片。
	oy = PUMPKIN_OY[sq]
	ox = PUMPKIN_OX[sq]
	for row in range(PUMPKIN_SIZE):
		for col in range(PUMPKIN_SIZE):
			x = ox + col
			if row % 2 == 1:
				x = ox + PUMPKIN_SIZE - 1 - col
			goto(x, oy + row)
			if get_entity_type() == None:
				plant(Entities.Pumpkin)
			if col + 1 < PUMPKIN_SIZE:
				if row % 2 == 0:
					move(East)
				else:
					move(West)
		move(North)


def work_pumpkin_smart(full, sq0, sq1):
	# 只走待确认的格子；full=1 时强制全量复查。返回本轮收到的方阵数。
	got = 0
	sq = sq0
	while sq < sq1:
		base = sq * PUMPKIN_TILE_COUNT
		i = 0
		while i < PUMPKIN_TILE_COUNT:
			idx = base + i
			if full == 1 or PUMPKIN_STATE[idx] == 0:
				goto(PUMPKIN_XS[idx], PUMPKIN_YS[idx])
				t = get_entity_type()
				if t == None:
					plant(Entities.Pumpkin)
					PUMPKIN_STATE[idx] = 0
				elif t == Entities.Dead_Pumpkin:
					# 死瓜无法正常收割，但 harvest() 会把它直接清除
					harvest()
					plant(Entities.Pumpkin)
					PUMPKIN_STATE[idx] = 0
				elif can_harvest():
					PUMPKIN_STATE[idx] = 1
				else:
					PUMPKIN_STATE[idx] = 0
				water_if_needed()
			i = i + 1

		pending = 0
		i = 0
		while i < PUMPKIN_TILE_COUNT:
			if PUMPKIN_STATE[base + i] == 0:
				pending = pending + 1
			i = i + 1

		if pending == 0:
			# 本片整阵「存活且成熟」→ 从本片任意一格连锁收割本片，随即补满并重置本片状态
			goto(PUMPKIN_XS[base], PUMPKIN_YS[base])
			pp0 = num_items(Items.Pumpkin)
			harvest()
			PYIELD[0] = num_items(Items.Pumpkin) - pp0
			PYIELD[1] = PYIELD[1] + 1
			PYIELD[2] = PYIELD[2] + PYIELD[0]
			replant_square(sq)
			pumpkin_reset_square(sq)
			got = got + 1
		sq = sq + 1
	return got


def loop_pumpkin_smart(psq0, psq1):
	# 一架盯 psq0..psq1-1 这些方阵，无限循环
	print("[pump] w_pumpkin BUILD", BUILD, "squares", psq0, "-", psq1 - 1)
	round = 0
	since = 0
	harvests = 0
	while True:
		round = round + 1
		since = since + 1
		full = 0
		if round % PUMPKIN_FULL_EVERY == 0:
			full = 1
		if since > PUMPKIN_STALE_LIMIT:
			full = 1
		n = work_pumpkin_smart(full, psq0, psq1)
		if n > 0:
			since = 0
			harvests = harvests + n
		if round % REPORT_EVERY == 0:
			pending = 0
			i = 0
			while i < PUMPKIN_TILE_COUNT * PUMPKIN_SQUARES:
				if PUMPKIN_STATE[i] == 0:
					pending = pending + 1
				i = i + 1
			pavg = 0
			if PYIELD[1] > 0:
				pavg = PYIELD[2] / PYIELD[1]
			print("[pump] build", BUILD, "round", round,
				"harvests", harvests,
				"since_harvest", since,
				"pending", pending,
				"pyield", PYIELD[0],
				"pavg", pavg,
				"pumpkin", num_items(Items.Pumpkin))
