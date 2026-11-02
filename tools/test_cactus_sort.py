# -*- coding: utf-8 -*-
# ============================================================
# test_cactus_sort.py —— 仙人掌排序 v2 的自测（用 farm_mock 假游戏，**不需要真机**）
#
# 为什么要单独写：真机 2026-11-01 的症状是「已种 36/36、已熟 36，但排序不收敛」
#   ⇒ 只靠静态检查（py_compile/gamelang/loop_check）**看不出排序是否真的把值排对了** ✗
#   而本项目已经栽过多次「静态全绿、跑起来什么都不干」
#   ⇒ 用一个假游戏（farm_mock）把 jobs.cactus_sort_square 真跑一遍，逐格核对 ✓
#
# 覆盖（对应任务书的三条，外加两条更狠的）：
#   (a) 随机 36 个值（size 0~9，20 个种子）
#   (b) 含重复值（全同 / 两值 / 三值随机）
#   (c) 含 0 值（合法尺寸）与 None 空洞（空位/未熟）
#   (d) 已有序的方块：必须 0 次交换（不白动）
#   (e) 端到端：cactus_shift 一刀必须 = 5184（= 6^4 x 2^2，仙人掌 lv3 的理论值）
#   (f) 兜底与闸门：局部修复从乱序必然收敛；排序后被别机改乱 ⇒ 核验拒绝；空洞 ⇒ 不半收
#
# 判据（每次都查，缺一不可）：
#   1) 行主序/二维单调：每行朝东不减、每列朝北不减（= 文档的 N/E >= 自己、S/W <= 自己）
#   2) 多重集不变：排序只换位置，不能多/少任何尺寸
#   3) 有空洞时**必须放弃**（返回 0）且不动棋盘（半排的方块比不排更糟 ✗）
#
# 用法：python tools/test_cactus_sort.py
# ============================================================
import builtins
import os
import random
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, HERE)
sys.path.insert(0, SAVE)

import farm_mock as FM

REAL_PRINT = FM.REAL_PRINT
try:
	sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
	pass

BLOCK_X = 0
BLOCK_Y = 6
N = 6
TILES = N * N
CACTUS_LV = 3                 # 真机当前等级：一刀 = 6^4 x 2^2 = 5184
WANT_KNIFE = 1296 * 4         # 6^4 = 1296，lv3 倍率 2^2 = 4


# ------------------------------------------------------------
# 假游戏世界 + 模块装配
# ------------------------------------------------------------
def make_world():
	# 16x16 棋盘（Expand lv7），仙人掌 lv3（与真机同口径）
	w = FM.World(1000000.0)
	w.lv["expand"] = 7
	w.lv["cactus"] = CACTUS_LV
	w.lv["megafarm"] = 1
	w.rebuild_board()
	return w


def fresh_modules(w):
	# 把假游戏 API 注入 builtins，再**重新导入** util/budget/jobs
	#   （R4：这些模块顶层不许读棋盘，所以 import 本身安全 ✓）
	ns = FM.make_ns(w)
	for k in ns:
		setattr(builtins, k, ns[k])
	for nm in ["util", "budget", "jobs", "block_farm"]:
		sys.modules.pop(nm, None)
	import jobs
	return ns, jobs


def plant_block(w, sizes):
	# sizes: 长度 36 的列表；元素 = 0~9 的尺寸，None = 空洞（那一格不放仙人掌）
	i = 0
	while i < TILES:
		x = BLOCK_X + i % N
		y = BLOCK_Y + i // N
		if sizes[i] == None:
			w.ent.pop((x, y), None)
			w.cactus.pop((x, y), None)
		else:
			w.ent[(x, y)] = "cactus"
			w.cactus[(x, y)] = sizes[i]
			w.planted[(x, y)] = w.clock - 100.0     # 早就成熟
		i = i + 1


def read_block(w):
	# 按行主序（idx = row * N + col）读回 36 格：尺寸 / None（空洞）
	out = []
	i = 0
	while i < TILES:
		x = BLOCK_X + i % N
		y = BLOCK_Y + i // N
		if (x, y) in w.cactus:
			out.append(w.cactus[(x, y)])
		else:
			out.append(None)
		i = i + 1
	return out


def same_multiset(a, b):
	# 只比非 None 元素的多重集（空洞单独判）
	xa = []
	xb = []
	i = 0
	while i < len(a):
		if a[i] != None:
			xa.append(a[i])
		if b[i] != None:
			xb.append(b[i])
		i = i + 1
	xa.sort()
	xb.sort()
	return xa == xb


def grid_sorted(vals):
	# 文档口径：N/E 邻居 >= 自己、S/W 邻居 <= 自己
	#   等价于：同一行朝东不减 + 同一列朝北不减
	y = 0
	while y < N:
		x = 0
		while x < N:
			here = vals[y * N + x]
			if x + 1 < N:
				east = vals[y * N + x + 1]
				if east < here:
					return False
			if y + 1 < N:
				north = vals[(y + 1) * N + x]
				if north < here:
					return False
			x = x + 1
		y = y + 1
	return True


# ------------------------------------------------------------
# 断言 / 报告
# ------------------------------------------------------------
class CaseFail(Exception):
	pass


def expect(cond, msg):
	if not cond:
		raise CaseFail(msg)


def run_case(name, fn):
	try:
		fn()
		REAL_PRINT("PASS", name)
		return 1, 0
	except CaseFail as e:
		REAL_PRINT("FAIL", name, "->", e)
		return 0, 1
	except Exception:
		REAL_PRINT("FAIL", name, "-> 抛异常（整轮中止级 ✗）：")
		REAL_PRINT(traceback.format_exc())
		return 0, 1


# ------------------------------------------------------------
# (a) 随机 36 个值：每种排列都必须排成有序 + 多重集不变
# ------------------------------------------------------------
def case_random():
	seed = 1
	while seed <= 20:
		rng = random.Random(seed)
		sizes = [rng.randrange(0, 10) for _ in range(TILES)]
		w = make_world()
		ns, jobs = fresh_modules(w)
		plant_block(w, sizes)
		ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
		expect(ok == 1, "seed %d: cactus_sort_square 返回 %d（应为 1）" % (seed, ok))
		got = read_block(w)
		expect(same_multiset(sizes, got), "seed %d: 多重集变了（换位置不能改变值集合）" % seed)
		expect(grid_sorted(got), "seed %d: 排完仍不有序 -> %s" % (seed, got))
		seed = seed + 1


# ------------------------------------------------------------
# (b) 含重复值：全同 / 两值 / 三值随机
# ------------------------------------------------------------
def case_duplicates():
	# b1：全同（36 个 5）—— 有序，且不该发生任何交换
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, [5] * TILES)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "全同方块：返回 %d" % ok)
	expect(jobs.CZ_SWAPS[0] == 0, "全同方块不该交换，实际 %d 次" % jobs.CZ_SWAPS[0])
	got = read_block(w)
	expect(got == [5] * TILES, "全同方块：值被改了 -> %s" % got)

	# b2：两值各半（18 个 1 + 18 个 9），打乱
	rng = random.Random(2026)
	two = [1] * 18 + [9] * 18
	rng.shuffle(two)
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, two)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "两值方块：返回 %d" % ok)
	got = read_block(w)
	expect(same_multiset(two, got), "两值方块：多重集变了")
	expect(grid_sorted(got), "两值方块：排完仍不有序 -> %s" % got)

	# b3：三值随机（20 个种子，大量重复 ⇒ 最容易暴露「重复值找不到持有者」的 bug）
	seed = 0
	while seed < 20:
		rng = random.Random(9000 + seed)
		vals = [rng.choice([2, 4, 7]) for _ in range(TILES)]
		w = make_world()
		ns, jobs = fresh_modules(w)
		plant_block(w, vals)
		ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
		expect(ok == 1, "三值 seed %d：返回 %d" % (seed, ok))
		got = read_block(w)
		expect(same_multiset(vals, got), "三值 seed %d：多重集变了" % seed)
		expect(grid_sorted(got), "三值 seed %d：排完仍不有序 -> %s" % (seed, got))
		seed = seed + 1


# ------------------------------------------------------------
# (c) 0 值（合法尺寸）与 None 空洞
# ------------------------------------------------------------
def case_zero_and_holes():
	# c1：全 0（合法尺寸，最容易和"空洞"混淆）⇒ 必须能排、且核验通过
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, [0] * TILES)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "全 0 方块：返回 %d（0 是合法尺寸）" % ok)
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 1, "全 0 方块：核验应通过")
	got = read_block(w)
	expect(got == [0] * TILES, "全 0 方块：值被改了")

	# c2：0 与 9 混排
	rng = random.Random(77)
	vals = [rng.choice([0, 9]) for _ in range(TILES)]
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, vals)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "0/9 混排：返回 %d" % ok)
	got = read_block(w)
	expect(same_multiset(vals, got), "0/9 混排：多重集变了")
	expect(grid_sorted(got), "0/9 混排：排完仍不有序 -> %s" % got)

	# c3：4 个空洞（None）⇒ 排序/修复都必须**放弃**（返回 0）且不动棋盘
	rng = random.Random(4242)
	holes = [rng.randrange(0, 10) for _ in range(TILES)]
	holes[0] = None
	holes[7] = None
	holes[20] = None
	holes[35] = None
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, holes)
	before = read_block(w)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 0, "有空洞时排序应返回 0（放弃），实际 %d" % ok)
	after = read_block(w)
	expect(before == after, "有空洞时棋盘被动了（半排比不排更糟 ✗）")
	ok = jobs.cactus_repair_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 0, "有空洞时局部修复应返回 0，实际 %d" % ok)
	after2 = read_block(w)
	expect(before == after2, "有空洞时局部修复动了棋盘")
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 0,
		"有空洞时核验必须不通过（绝不能拿去收割）")


# ------------------------------------------------------------
# (d) 已有序：0 次交换；核验通过
# ------------------------------------------------------------
def case_already_sorted():
	rng = random.Random(123)
	vals = [rng.randrange(0, 10) for _ in range(TILES)]
	vals.sort()
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, vals)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "已有序方块：返回 %d" % ok)
	expect(jobs.CZ_SWAPS[0] == 0, "已有序方块不该交换，实际 %d 次" % jobs.CZ_SWAPS[0])
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 1, "已有序方块：核验应通过")
	got = read_block(w)
	expect(got == vals, "已有序方块：值被改了")


# ------------------------------------------------------------
# (e) 兜底路径：局部修复从乱序必然收敛；核验拒绝乱序
# ------------------------------------------------------------
def case_repair_fallback():
	# e1：乱序格子上 cactus_verify_square 必须返回 0（这是「不半收」的闸门）
	rng = random.Random(555)
	vals = [rng.randrange(0, 10) for _ in range(TILES)]
	if grid_sorted(vals):
		vals[0] = 9
		vals[35] = 0
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, vals)
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 0,
		"乱序方块：核验必须不通过")

	# e2：局部修复（main.py v1，势能保证收敛）必须把乱序排好
	ok = jobs.cactus_repair_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "局部修复：返回 %d（应 1）" % ok)
	got = read_block(w)
	expect(same_multiset(vals, got), "局部修复：多重集变了")
	expect(grid_sorted(got), "局部修复：排完仍不有序 -> %s" % got)
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 1, "局部修复后核验应通过")

	# e3：多个随机种子，确保不是碰巧
	seed = 0
	while seed < 10:
		rng = random.Random(777 + seed)
		vals = [rng.randrange(0, 10) for _ in range(TILES)]
		w = make_world()
		ns, jobs = fresh_modules(w)
		plant_block(w, vals)
		ok = jobs.cactus_repair_square(BLOCK_X, BLOCK_Y, N)
		expect(ok == 1, "局部修复 seed %d：返回 %d" % (seed, ok))
		got = read_block(w)
		expect(grid_sorted(got), "局部修复 seed %d：仍不有序" % seed)
		expect(same_multiset(vals, got), "局部修复 seed %d：多重集变了" % seed)
		seed = seed + 1


# ------------------------------------------------------------
# (f) 端到端：cactus_shift 一刀 = 5184（任务验收判据）
# ------------------------------------------------------------
def case_shift_end_to_end():
	seed = 0
	while seed < 5:
		rng = random.Random(31337 + seed)
		sizes = [rng.randrange(0, 10) for _ in range(TILES)]
		w = make_world()
		ns, jobs = fresh_modules(w)
		plant_block(w, sizes)
		before = w.items.get("cactus", 0)
		got = jobs.cactus_shift(BLOCK_X, BLOCK_Y, N, N, 1, w.shape()[0], 0)
		gained = w.items.get("cactus", 0) - before
		expect(gained == WANT_KNIFE,
			"seed %d: 一刀 %d，应为 %d（排序/核验/收割链路没走通）" % (seed, gained, WANT_KNIFE))
		expect(got == WANT_KNIFE, "seed %d: 返回累计 %d，应为 %d" % (seed, got, WANT_KNIFE))
		# 日志必须出现「本刀 5184」与「理论 5184」，这是真机 output.txt 的判据
		hit_knife = 0
		hit_theory = 0
		for line in w.log:
			if "本刀 5184" in line:
				hit_knife = 1
			if "理论 5184" in line:
				hit_theory = 1
			if "排序核验没通过" in line:
				raise CaseFail("seed %d: 出现了「排序核验没通过」%s" % (seed, line))
		expect(hit_knife == 1, "seed %d: 日志里没有「本刀 5184」" % seed)
		expect(hit_theory == 1, "seed %d: 日志里没有「理论 5184」" % seed)
		# 收割后整片必须空（连锁收割把 36 株全收掉）
		left = 0
		i = 0
		while i < TILES:
			x = BLOCK_X + i % N
			y = BLOCK_Y + i // N
			if (x, y) in w.cactus:
				left = left + 1
			i = i + 1
		expect(left == 0, "seed %d: 收割后还剩 %d 株（没收全 = 产量口径不对）" % (seed, left))
		seed = seed + 1


# ------------------------------------------------------------
# (g) 并行互踩的闸门：排序后被别机改乱 ⇒ 核验必须拒绝；空洞时 shift 不半收
# ------------------------------------------------------------
def case_interference_gate():
	# g1：模拟「排序完成后，另一架副机把地改乱」⇒ 核验必须返回 0（不半收的闸门）
	rng = random.Random(8888)
	vals = [rng.randrange(0, 10) for _ in range(TILES)]
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, vals)
	ok = jobs.cactus_sort_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "g1：排序返回 %d" % ok)
	# 人为制造一个**必定**的逆序：西南角写 9、它东边写 0（east < me ⇒ 文档判无序）
	w.cactus[(BLOCK_X, BLOCK_Y)] = 9
	w.cactus[(BLOCK_X + 1, BLOCK_Y)] = 0
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 0,
		"g1：被改乱后核验必须拒绝（否则会半收 ✗）")
	# 修复后必须又能通过（现读现换 ⇒ 收敛）
	ok = jobs.cactus_repair_square(BLOCK_X, BLOCK_Y, N)
	expect(ok == 1, "g1：修复返回 %d" % ok)
	expect(jobs.cactus_verify_square(BLOCK_X, BLOCK_Y, N) == 1, "g1：修复后核验应通过")

	# g2：有空洞时 cactus_shift 必须不死、不收割、返回 0（半收比不收更糟 ✗）
	rng = random.Random(9999)
	holes = [rng.randrange(0, 10) for _ in range(TILES)]
	holes[0] = None
	holes[35] = None
	w = make_world()
	ns, jobs = fresh_modules(w)
	plant_block(w, holes)
	before = w.items.get("cactus", 0)
	got = jobs.cactus_shift(BLOCK_X, BLOCK_Y, N, N, 1, w.shape()[0], 0)
	expect(got == 0, "g2：有空洞时 shift 返回 %d（应 0 = 没收到）" % got)
	expect(w.items.get("cactus", 0) == before, "g2：有空洞时居然收到了仙人掌（半收 ✗）")


def main():
	REAL_PRINT("=" * 72)
	REAL_PRINT("仙人掌排序 v2 自测（farm_mock 假游戏）| 方块", N, "x", N,
		"| 每刀理论", WANT_KNIFE)
	REAL_PRINT("=" * 72)
	ok = 0
	bad = 0
	cases = [
		("(a) 随机 36 值 x 20 seed", case_random),
		("(b) 含重复值（全同/两值/三值随机）", case_duplicates),
		("(c) 0 值与 None 空洞", case_zero_and_holes),
		("(d) 已有序方块 = 0 次交换", case_already_sorted),
		("(e) 兜底：局部修复收敛 + 核验拒绝乱序", case_repair_fallback),
		("(f) 端到端：cactus_shift 一刀 = 5184", case_shift_end_to_end),
		("(g) 并行互踩闸门：核验拒绝改乱 + 空洞不半收", case_interference_gate),
	]
	for name, fn in cases:
		o, b = run_case(name, fn)
		ok = ok + o
		bad = bad + b
	REAL_PRINT("=" * 72)
	REAL_PRINT("结果：PASS %d / FAIL %d" % (ok, bad))
	return 0 if bad == 0 else 1


if __name__ == "__main__":
	sys.exit(main())
