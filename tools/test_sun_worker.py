# -*- coding: utf-8 -*-
# ============================================================
# test_sun_worker.py —— 向日葵（power 线）修复的自测（用 farm_mock 假游戏，不需要真机）
#
# 为什么必须写：2026-11-02 用户报「能量长期 0 ✗」。根因是**两条只有真跑才看得见**的：
#   ① 恐龙跑的 clear() 把整盘清成草原后，旧版 sun 代码**从不 till** ⇒ 向日葵（只能种在
#      土壤上）永远种不下去 ⇒ 向日葵带荒废 ⇒ power 0 ✗
#   ② 旧班次 24 遍全速扫完就退出（~1 分钟），而调度器一个批次要 3~10 分钟才重派
#      ⇒ 只有每班开头 40~60 秒有电，其余 76.6% 的 [fr] 报告 power=0 ✗
# 静态检查（py_compile/gamelang/loop_check）都看不出这两条 ⇒ 必须用假游戏真跑 ✓
#
# 覆盖：
#   (a) **草原自愈**：整条带是 Grassland（= 恐龙跑 clear() 之后）⇒ 一个班次内必须自己
#       till 成土壤、种满 32 株、并且收一波（**按花瓣降序 ⇒ 每株 8 倍**）
#   (b) **资源前提**：胡萝卜低于保护底 ⇒ 一株都不许种（保护南瓜线/升级线上游）
#   (c) **配速连续产出**：24 遍的班次必须持续收割（而不是开头一波就退场）
#   (d) 世界变了 ⇒ 立刻下岗（R3）
#   (e) 带内被别的作物占住的格子：不崩、不动它；带外的植物也不许碰
#
# 判据（每条都硬断言）：
#   * 8 倍口径：场上 32 株时按降序收 = 前 23 株 x8 + 后 9 株 x1 = **193 power/波**
#     （反编译 Core.dll Sunflower.Harvest：`number == Max && Count >= 10` ⇒ ×8）
#   * 只有「收割」会加 power；mock 里没有消耗模型 ⇒ power_made 就是总产出 ✓
#
# 用法：python tools/test_sun_worker.py
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

# stage_w16 的向日葵带：(14, 0) 起 2 x 16 = 32 格
BAND_X = 14
BAND_Y = 0
BAND_W = 2
BAND_H = 16
TILES = BAND_W * BAND_H
W0 = 16                       # world 16x16（Expand lv7，与真机 w16 档位同口径）
CARROTS = 5000                # 充足的胡萝卜（向日葵种子是胡萝卜，不是干草）
WAVE_BOOST = 23 * 8 + 9 * 1   # 32 株按降序收一波的理论 power = 193


class CaseFail(Exception):
	pass


def expect(cond, msg):
	if not cond:
		raise CaseFail(msg)


# ------------------------------------------------------------
# 假游戏世界 + 模块装配
# ------------------------------------------------------------
def make_world():
	w = FM.World(1000000.0)
	w.lv["expand"] = 7            # world 16
	w.lv["sunflowers"] = 1        # 向日葵 lv1 ⇒ 种子 1 胡萝卜/株
	w.lv["speed"] = 5             # 与真机 w16 同档：动作 tick 被 speed 升级缩短 ✓
	w.lv["megafarm"] = 1
	w.rebuild_board()
	w.items["carrot"] = CARROTS
	return w


def fresh_modules(w):
	# 假装游戏 API 注入 builtins，再重新导入 util/budget/jobs（模块顶层不许读棋盘 ✓）
	ns = FM.make_ns(w)
	for k in ns:
		setattr(builtins, k, ns[k])
	for nm in ["util", "budget", "jobs", "block_farm"]:
		sys.modules.pop(nm, None)
	import jobs
	return ns, jobs


def band_cells():
	out = []
	x = 0
	while x < BAND_W:
		y = 0
		while y < BAND_H:
			out.append((BAND_X + x, BAND_Y + y))
			y = y + 1
		x = x + 1
	return out


def set_band(w, petals, ground):
	# petals: 32 个 7~15 的整数；None = 该格留空
	# ground: "soil" / "grass"
	cells = band_cells()
	i = 0
	while i < TILES:
		x, y = cells[i]
		w.ground[(x, y)] = ground
		if petals[i] == None:
			w.ent.pop((x, y), None)
		else:
			w.ent[(x, y)] = "sunflower"
			w.petals[(x, y)] = petals[i]
			w.planted[(x, y)] = w.clock - 100.0      # 早就成熟
		i = i + 1


def read_band(w):
	out = []
	cells = band_cells()
	i = 0
	while i < TILES:
		x, y = cells[i]
		out.append((w.ent.get((x, y)), w.ground.get((x, y))))
		i = i + 1
	return out


# ------------------------------------------------------------
# 断言 / 报告
# ------------------------------------------------------------
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
# (a) 草原自愈 + 降序 8 倍：恐龙跑 clear() 之后一个班次内必须恢复整条带
# ------------------------------------------------------------
def case_till_and_boost():
	w = make_world()
	ns, jobs = fresh_modules(w)
	# 整条带 = 草原（模拟 dino_run 的 clear() 之后；旧版代码在这里永远种不下去 ✗）
	got = jobs.sun_simple_worker(BAND_X, BAND_Y, BAND_W, BAND_H, 2, W0, 0)
	expect(got == 32, "草原自愈班次应收到 32 株，实际 %d（till 没生效？）" % got)
	expect(w.power_made == WAVE_BOOST,
		"一波 32 株应产 %d power（降序 8 倍口径），实际 %d" % (WAVE_BOOST, w.power_made))
	cells = band_cells()
	soil = 0
	flowers = 0
	for (x, y) in cells:
		if w.ground.get((x, y)) == "soil":
			soil = soil + 1
		if w.ent.get((x, y)) == "sunflower":
			flowers = flowers + 1
	expect(soil == TILES, "整条带应被翻成土壤，实际 %d/%d 格" % (soil, TILES))
	expect(flowers == TILES, "整条带应种满 32 株，实际 %d 株" % flowers)
	expect(w.items.get("carrot", 0) >= 0, "胡萝卜被扣成负数")


# ------------------------------------------------------------
# (b) 资源前提：胡萝卜低于保护底 ⇒ 一株都不许种
# ------------------------------------------------------------
def case_carrot_gate():
	w = make_world()
	w.items["carrot"] = 100        # 低于 SUN_CARROT_KEEP=200 ⇒ 不许种
	ns, jobs = fresh_modules(w)
	got = jobs.sun_simple_worker(BAND_X, BAND_Y, BAND_W, BAND_H, 2, W0, 0)
	expect(got == 0, "胡萝卜不足时不该有收成，实际 %d" % got)
	expect(w.power_made == 0, "胡萝卜不足时不该产 power，实际 %d" % w.power_made)
	expect(w.items["carrot"] == 100, "胡萝卜不足时不该扣种子（实际库存 %s）" % w.items["carrot"])
	cells = band_cells()
	for (x, y) in cells:
		expect(w.ent.get((x, y)) != "sunflower", "胡萝卜不足时不该种向日葵（%d,%d）" % (x, y))
		expect(w.ground.get((x, y)) == "grass", "没种就不该动地面（%d,%d）" % (x, y))


# ------------------------------------------------------------
# (c) 配速连续产出：24 遍班次必须持续收割，而不是开头一波就退场
# ------------------------------------------------------------
def case_continuous_power():
	w = make_world()
	rng = random.Random(20261102)
	petals = [rng.randrange(7, 16) for _ in range(TILES)]
	set_band(w, petals, "soil")
	ns, jobs = fresh_modules(w)
	got = jobs.sun_simple_worker(BAND_X, BAND_Y, BAND_W, BAND_H, 24, W0, 0)
	expect(got >= 15 * TILES,
		"24 遍班次只收了 %d 株（配速没生效 ⇒ 又是开头一波就退场 ✗）" % got)
	expect(w.power_made > 2500,
		"24 遍班次只产 %d power（配速没生效；应 >= 15 波 x %d）" % (w.power_made, WAVE_BOOST))
	expect(w.items.get("carrot", 0) > 0, "胡萝卜被抽干")
	# 班次结束时整条带必须是「满 32 株 + 土壤」
	cells = band_cells()
	flowers = 0
	for (x, y) in cells:
		if w.ent.get((x, y)) == "sunflower":
			flowers = flowers + 1
	expect(flowers == TILES, "班次结束时应保持满 32 株，实际 %d 株" % flowers)
	# 量化上报（供真机判据对照）：这一班的波数 / 收割 / 产出
	REAL_PRINT("     [量化] 24 遍班次：收割", got, "株 =", got // TILES,
		"波 | power", w.power_made, "| 结束时刻", round(w.clock, 1), "秒")


# ------------------------------------------------------------
# (d) 世界变了 ⇒ 立刻下岗（R3）
# ------------------------------------------------------------
def case_world_changed():
	w = make_world()
	ns, jobs = fresh_modules(w)
	got = jobs.sun_simple_worker(BAND_X, BAND_Y, BAND_W, BAND_H, 24, 12, 0)
	expect(got == 0, "世界不匹配时应立刻下岗，实际收了 %d" % got)
	expect(w.power_made == 0, "世界不匹配时不该产 power")


# ------------------------------------------------------------
# (e) 被占格不崩不动；带外植物不碰
# ------------------------------------------------------------
def case_blocked_and_outside():
	w = make_world()
	rng = random.Random(555)
	petals = [rng.randrange(7, 16) for _ in range(TILES)]
	petals[0] = None                          # 带内第 0 格让给别的作物
	set_band(w, petals, "soil")
	w.ent[(BAND_X, BAND_Y)] = "carrot"         # 被占格（模拟其它产线残留）
	w.planted[(BAND_X, BAND_Y)] = w.clock - 100.0
	# 带外再放一株成熟向日葵 + 一根胡萝卜：**都不许被碰**
	w.ent[(0, 0)] = "sunflower"
	w.petals[(0, 0)] = 7
	w.planted[(0, 0)] = w.clock - 100.0
	w.ent[(1, 0)] = "carrot"
	w.planted[(1, 0)] = w.clock - 100.0
	ns, jobs = fresh_modules(w)
	got = jobs.sun_simple_worker(BAND_X, BAND_Y, BAND_W, BAND_H, 4, W0, 0)
	expect(got > 0, "被占一格的带子其余 31 株应能收到，实际 %d" % got)
	expect(w.ent.get((BAND_X, BAND_Y)) == "carrot", "带内被占格被动过了 ✗")
	expect(w.ent.get((0, 0)) == "sunflower", "带外向日葵被收了 ✗（越界！）")
	expect(w.ent.get((1, 0)) == "carrot", "带外胡萝卜被动过了 ✗（越界！）")


# ------------------------------------------------------------
# (f) 胡萝卜种植的 hay 保留线：干草见底时不许种胡萝卜（A 方案）
# ------------------------------------------------------------
def case_carrot_hay_gate():
	# 公共格：(2,12) 在 w16 的 farm_a 里；先设成「草原 + 尚未长好」避免误收草加 hay
	w = make_world()
	w.lv["carrots"] = 1
	w.items["wood"] = 1000
	w.ground[(2, 12)] = "grass"
	w.ent.pop((2, 12), None)
	w.ready[(2, 12)] = w.clock + 100000.0
	ns, jobs = fresh_modules(w)
	import util as U
	U.go_to(2, 12)

	# f1：hay 见底（10 < 保留线 50 + 一株成本）⇒ 付得起也不许种
	w.items["hay"] = 10
	got = jobs.work_carrot_tile()
	expect(got == 0, "hay=10 时不应种胡萝卜（返回 %d）" % got)
	expect(w.ent.get((2, 12)) != "carrot", "hay=10 时居然种下了胡萝卜 ✗（hay 会被抽干）")
	expect(w.items["hay"] == 10, "hay=10 时不该扣干草（实际 %s）" % w.items["hay"])

	# f2：hay 充足 ⇒ 正常种（保留线不误伤）
	w.items["hay"] = 1000
	U.go_to(2, 12)
	got = jobs.work_carrot_tile()
	expect(got == 1, "hay=1000 时应能种胡萝卜（返回 %d）" % got)
	expect(w.ent.get((2, 12)) == "carrot", "hay=1000 时应该种下胡萝卜 ✗")
	expect(w.items["hay"] < 1000, "种下胡萝卜应扣干草（实际 %s）" % w.items["hay"])

	# f3：hay 充足但 wood 不足 ⇒ 原 R7 判据仍生效、不许种
	w2 = make_world()
	w2.lv["carrots"] = 1
	w2.items["hay"] = 1000
	w2.items["wood"] = 0
	w2.ground[(2, 12)] = "grass"
	w2.ent.pop((2, 12), None)
	w2.ready[(2, 12)] = w2.clock + 100000.0
	ns2, jobs2 = fresh_modules(w2)
	import util as U2
	U2.go_to(2, 12)
	got = jobs2.work_carrot_tile()
	expect(got == 0, "wood=0 时不应种胡萝卜（返回 %d）" % got)
	expect(w2.ent.get((2, 12)) != "carrot", "wood=0 时居然种下了胡萝卜 ✗")


# ------------------------------------------------------------
# (g) stage_w16 的地面诊断行：w16 才执行 ⇒ 必须真跑一次防运行期错误
# ------------------------------------------------------------
def case_s16_ground_report():
	w = make_world()
	w.lv["plant"] = 1
	w.lv["carrots"] = 1
	w.lv["trees"] = 1
	w.lv["sunflowers"] = 1
	w.lv["pumpkins"] = 1
	w.lv["mazes"] = 1
	w.lv["cactus"] = 3
	w.rebuild_board()
	# 模拟「草列土壤化」：草列第 1 列两格是土壤
	w.ground[(1, 12)] = "soil"
	w.ground[(2, 13)] = "soil"
	w.ent[(4, 12)] = "carrot"
	w.planted[(4, 12)] = w.clock - 100.0
	ns = FM.make_ns(w)
	for k in ns:
		setattr(builtins, k, ns[k])
	for nm in ["util", "budget", "jobs", "block_farm", "stage_w16"]:
		sys.modules.pop(nm, None)
	import stage_w16
	w.log.clear()
	a = ["hay", "hay", "hay", "hay", "carrot", "wood"]
	b = ["hay", "hay", "hay", "hay", "hay", "hay", "carrot", "wood"]
	stage_w16.s16_report(a, b)
	hit = None
	for line in w.log:
		if "farm_a 地面" in line:
			hit = line
	expect(hit != None, "s16_report 没打印「farm_a 地面」诊断行（w16 会缺地面统计）")
	expect("草列(0-3)土壤化" in hit, "地面诊断行格式不对: %s" % hit)
	expect("土壤 2" in hit, "地面诊断行没统计出 2 格土壤: %s" % hit)


# ------------------------------------------------------------
# (h) 草列自愈 + 伴生不再翻土（C 后半条）
#   背景（反编译 Core.dll）：恐龙尾巴 `Dinosaur.OnRestart` 会把走过的每一格变成 Soil，
#   一趟 1 万+ 步覆盖整盘 ⇒ 草列 16/16 全土壤化 ⇒ 草长不回来 ⇒ hay 永久枯竭 ✗
# ------------------------------------------------------------
def case_hay_selfheal_and_companion():
	# h1：草列土壤化 ⇒ work_hay_tile 一次调用必须 till 回草原，再下一次能收到 hay
	w = make_world()
	w.lv["plant"] = 1
	w.ground[(0, 12)] = "soil"
	w.ent.pop((0, 12), None)
	w.ready[(0, 12)] = 0.0
	ns, jobs = fresh_modules(w)
	import util as U
	U.go_to(0, 12)
	got = jobs.work_hay_tile()
	expect(got == 0, "h1: 翻土那一遍不该有收成（返回 %d）" % got)
	expect(w.ground.get((0, 12)) == "grass",
		"h1: 草列土壤化后必须 till 回草原（实际 %r）" % (w.ground.get((0, 12)),))
	got = jobs.work_hay_tile()
	expect(got == 1, "h1: 翻回草原后应能收到 hay（返回 %d）" % got)
	expect(w.items.get("hay", 0) >= 1, "h1: 收草应加 hay")

	# h2：伴生请求的目标格是**草列**、kind=carrot ⇒ 绝不许翻土（翻土=永久毁草列 ✗）
	w2 = make_world()
	w2.lv["plant"] = 1
	w2.lv["trees"] = 1
	w2.lv["polyculture"] = 4
	w2.items["hay"] = 1000
	w2.ground[(0, 12)] = "grass"       # 草列目标格
	w2.ent.pop((0, 12), None)
	w2.ground[(5, 12)] = "grass"       # wood 列的树
	w2.ent[(5, 12)] = "tree"
	w2.planted[(5, 12)] = w2.clock - 100.0
	w2.comp[(5, 12)] = ("carrot", (0, 12))   # 伴生请求落在草列上
	ns2, jobs2 = fresh_modules(w2)
	# ⚠ farm_mock 的 ns["get_companion"] 是 stub（返回 None，mock 没建模伴生系统）⇒
	#   本用例需要真伴生行为 ⇒ 就地覆写 builtins 里的 get_companion（只影响本测试进程 ✓）
	builtins.get_companion = lambda: w2.comp.get(w2.pos)
	import util as U2
	jobs2.CUR_RECT[0] = 0
	jobs2.CUR_RECT[1] = 12
	jobs2.CUR_RECT[2] = 6
	jobs2.CUR_RECT[3] = 4
	U2.go_to(5, 12)
	r = jobs2.satisfy_companion()
	expect(w2.ground.get((0, 12)) == "grass", "h2: 伴生把草列翻成土壤了 ✗（hay 会永久枯竭）")
	expect(w2.ent.get((0, 12)) != "carrot", "h2: 草列上不该种胡萝卜")
	expect(r == 0, "h2: 草列上的胡萝卜伴生应放弃（返回 %d）" % r)

	# h3：伴生 kind=bush（grassland/soil 都能长）⇒ 直接种、不翻土
	w2.comp[(5, 12)] = ("bush", (0, 12))
	U2.go_to(5, 12)
	r = jobs2.satisfy_companion()
	expect(r == 1, "h3: 草地上的灌木伴生应能直接种（返回 %d）" % r)
	expect(w2.ground.get((0, 12)) == "grass", "h3: 种灌木不该翻土")
	expect(w2.ent.get((0, 12)) == "bush", "h3: 灌木没种上")

	# h4：伴生 kind=carrot 目标格是 Soil ⇒ 仍要过 hay 闸门（hay=10 不许种）
	w3 = make_world()
	w3.lv["plant"] = 1
	w3.lv["polyculture"] = 4
	w3.items["hay"] = 10
	w3.ground[(4, 12)] = "soil"
	w3.ent.pop((4, 12), None)
	w3.ground[(5, 12)] = "grass"
	w3.ent[(5, 12)] = "tree"
	w3.planted[(5, 12)] = w3.clock - 100.0
	w3.comp[(5, 12)] = ("carrot", (4, 12))
	ns3, jobs3 = fresh_modules(w3)
	builtins.get_companion = lambda: w3.comp.get(w3.pos)
	import util as U3
	jobs3.CUR_RECT[0] = 0
	jobs3.CUR_RECT[1] = 12
	jobs3.CUR_RECT[2] = 6
	jobs3.CUR_RECT[3] = 4
	U3.go_to(5, 12)
	jobs3.satisfy_companion()
	expect(w3.ent.get((4, 12)) != "carrot", "h4: hay=10 时伴生不许种胡萝卜（会抽干干草）")
	expect(w3.ground.get((4, 12)) == "soil", "h4: 土壤格不该被改动")


def main():
	REAL_PRINT("=" * 72)
	REAL_PRINT("向日葵（power 线）自测 | 带", BAND_W, "x", BAND_H, "| 一波理论", WAVE_BOOST)
	REAL_PRINT("=" * 72)
	ok = 0
	bad = 0
	cases = [
		("(a) 草原自愈 + 降序 8 倍（一波 193 power）", case_till_and_boost),
		("(b) 资源前提：胡萝卜不足不许种", case_carrot_gate),
		("(c) 配速连续产出：24 遍班次持续收割", case_continuous_power),
		("(d) 世界变了立刻下岗", case_world_changed),
		("(e) 被占格不崩不动 + 带外不碰", case_blocked_and_outside),
		("(f) 胡萝卜 hay 保留线（A 方案）", case_carrot_hay_gate),
		("(g) stage_w16 地面诊断行（w16 运行期验证）", case_s16_ground_report),
		("(h) 草列自愈 + 伴生不再翻土（C 后半条）", case_hay_selfheal_and_companion),
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
