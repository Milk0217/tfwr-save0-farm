# ============================================================
# full_run.py —— 完全复位榜（Leaderboards.Fastest_Reset）参赛程序 · **调度层**
#
# 终点条件：num_unlocked(Unlocks.Leaderboard) > 0
# 用法：lb_enter.py 的 WHICH = 2 ⇒ 在真实存档里运行它 ⇒ 开一场 Fastest_Reset 模拟
#
# ============ 架构（P0，详见 docs/plans/full-run-modularization.md）============
#
#   档位键 = (world 大小, Expand 等级, 无人机架数) —— **三个数全是游戏自己回答的**
#     world  : get_world_size()
#     expand : num_unlocked(Unlocks.Expand)   ← 必须进键：形状会在 world 不变时变
#               （实测 Expand lv1 是「一行」、lv2 是 3x3，两者 world 都是 3 ✗）
#     drones : util.drone_cap()（Megafarm 未解锁时恒为 1）
#   ⇒ 调度器每轮现问游戏，**不可能与实况脱节**（zones.py 那次翻车就是这么来的）
#
#   三层分工：
#     stage_*.py  空间层：谁占哪块地（lands / verify_lands）+ 分派任务（assign）+ 主机作业（run）
#     jobs.py     算法层：怎么干活（只认脚下这一格或调用方给的矩形，零绝对坐标）
#     budget.py   策略层：买什么、留多少、**什么时候才允许动档位键**（R1）
#
# ============ 为什么重写（v75 的死因）============
#   v75 的 farm_round 里写着 `if zones.is_farm(x, y) == 0: harvest()` ——
#   而 zones.is_farm 的语义是「1 = 这一格归轮作」⇒ 判据反了 ⇒ 3x3 及以上的方块棋盘上
#   （zones.geom() 在 bs<2 时让全盘都算 "farm"）**收割永不发生**，
#   实测后果：world 3 卡死 237 轮 / 2470 秒，读数 wood 3 / carrot 0，只有 hay 在涨。
#   ⇒ 新结构里没有「中央分区表」这个东西：地块归属与作业在同一个档位文件里，
#     而且进档时 verify_lands() 会逐格验证「恰好铺满、两两不重叠」。
#
# ============ P0 的范围（明确的中间状态）============
#   本版只实现三个档位：1x1、一行（Expand lv1）、3x3。
#   撞到没有档位的 world 会**大声停机**（宁可停，不跑半套）——这是预期的，
#   下一轮 P2 补 4x4 / 6x6（含南瓜方块），P5 补 12x12 / 16x16。
#
# 血泪纪律（全部保留）：动词前先问解锁/付得起；不写死游戏数字；一处一验；
#   改条件不动 if/else 结构；跨机状态只走参数与返回值。
# ============================================================

VERSION = 79
REPORT_SEC = 10
STALL_LIMIT = 6            # 连续多少个报告窗口零收割就报警（6 x 10 秒）

import util
import budget
import jobs
import stage_w1
import stage_row
import stage_w3
import stage_w4
import stage_w6
import stage_w8
import stage_w12
import stage_w16
import stage_w22

KEY = [0, -1, 0]           # [world, expand 等级, 无人机架数] —— 上一次的键
LAST_HARV = [0]            # 停滞看门狗：上一次读到的累计收割次数
STALL = [0]                # 连续多少窗口收割次数没涨
SPAWNED = [0]
ACTIVEB = []             # 每个任务是否有无人机在飞（按名单下标 ✓）
SPAWN_START = [0]
# **任务下发时刻**（秒）—— 用于"按时过期"，让死掉的副机所属任务能被重派 ✓
#   ⚠ 真机 2026-11-02：`drones` 最高只到 **9 / 16** ✗（用户报的"利用率没修好"）
#     上一个"宁可少派不重复派"的做法 ✗ 让槽位一旦标记就再不清 ✗
#     ⇒ 现在给每个任务记 TTL：超过最长班次（迷宫 290s ✓）就认为它已结束 ✓
#     TTL 取 400s ⇒ **比任何班次都长** ⇒ 绝不会重复派 ✓ 又能回收死掉的任务 ✓
ACTIVE_T = []
# **副机句柄**（`spawn_drone` 的返回值）—— 用它 + `has_finished()` **精确**判断任务是否结束 ✓
#   ⚠ 之前只有 TTL 猜测（`ACTIVE_TTL_MAZE/OTHER`）✗ ⇒ 短任务死后要等到 TTL 才回收槽位 ✗
#   真机实测：w16 的 8 个槽只飞 2.45 架（30.6% ✗）、w22 的 16 个槽只飞 3.49 架（21.8% ✗✗）
#   `__builtins__.py` 里确认有 `def has_finished(drone: Drone) -> _bool` ✓
#   ⇒ 句柄 + has_finished ⇒ **任务一结束槽位立刻可重派** ✓（TTL 保留作兜底 ✓）
HANDLES = []
# ⚠⚠⚠ **必须按任务类型给 TTL**（真机回归，由 maze-fixer 抓出 ✓✓）：
#   我原来写死 400s（当时迷宫班次是 290s ✓），后来把 `MZ_SHIFT_SEC` 调到 **520s** ✗
#   ⇒ 400s 就把**还活着**的迷宫任务标记清掉 ✗ ⇒ 有空位时**再派一架** ✗
#   ⇒ **同一迷宫区两架副机**（我们花几轮修掉的 bug 又回来了 ✓✓）
#   真机证据：`[st] 放飞副机 maze0` 间隔出现 405~424s（< 520s 班次 ✓）、
#            `[mz] !! 进区失败 | 已试路线 4/4` 共 **475 条**（第二架进不去已建好的迷宫 ✗）
#   ⇒ 迷宫类 TTL = **620s**（> 520 + 收尾余量 ✓）；其余短任务 = **200s**（死槽快速回收 ✓）
ACTIVE_TTL_MAZE = 620.0
ACTIVE_TTL_OTHER = 200.0        # 派活轮换起点（让所有任务都有机会 ✓）              # 累计放飞过多少架副机（诊断用）


def pick_stage(w):
	# 显式分派表（字面量 import，不做动态 import）
	if w <= 1:
		return stage_w1, "w1"
	if w == 3:
		# 依据 docs/game/unlocks/expand_2.md：Expand lv1 的农场是「一行」
		xm, ym = util.board_shape()
		if xm == 0 or ym == 0:
			return stage_row, "row"
		return stage_w3, "w3"
	if w == 4:
		return stage_w4, "w4"
	if w == 6:
		return stage_w6, "w6"
	if w == 8:
		return stage_w8, "w8"
	if w == 12:
		return stage_w12, "w12"
	if w == 16:
		return stage_w16, "w16"
	if w == 22:
		return stage_w22, "w22"
	return 0, ""


def main():
	print("[fr] === full_run v", VERSION, "（P5：档位调度 + 1x1/一行/3x3/4x4/6x6/8x8/12x12）start ===")
	print("[fr] world", get_world_size(), "| drones", util.drone_count(), "/", util.drone_cap(),
		"| hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
		"carrot", num_items(Items.Carrot))
	budget.report_costs()
	t0 = get_time()
	rep = t0
	rounds = 0
	# 当前档位模块装在**局部变量**里（而不是列表元素）：
	#   依据 docs/game/unlocks/timing.md：「模块/函数经由参数或变量赋值传递后再使用，
	#   只花 1 tick 而不是 0」⇒ 这是文档明确支持的调用路径 ✓
	# 顺带避开一个静态检查假阳性：audit_save0.py 的 clean() 只能剥掉 `模块.函数` 形式的点号，
	#   剥不掉 `列表[0].函数` ⇒ 后者会被误报成「未定义名字 run」。
	cur = 0
	cur_name = ""
	while True:
		rounds = rounds + 1
		# 终点：排行榜要求程序**自己结束**
		if num_unlocked(Unlocks.Leaderboard) > 0:
			print("[fr] *** 终点达成：Leaderboard 解锁到手（完全复位榜完成）***")
			break
		# ---- 1) 档位键：变了就换档（只在边界发生，R1 保证副机不拿过期几何）----
		w = get_world_size()
		e = num_unlocked(Unlocks.Expand)
		d = util.drone_cap()
		if w != KEY[0] or e != KEY[1] or d != KEY[2]:
			st, nm = pick_stage(w)
			if st == 0:
				print("[fr] !! world", w, "没有对应档位 ⇒ 停机",
					"（P5 只做到 12x12；16x16 与实际产出线尚未写，这是预期的中间状态）")
				break
			if st.enter() == 0:
				print("[fr] !! 档位", nm, "自检不通过 ⇒ 停机（宁可停，不跑半套）")
				break
			if st.verify_lands() == 0:
				print("[fr] !! 档位", nm, "地块自检不通过 ⇒ 停机")
				break
			cur = st
			cur_name = nm
			KEY[0] = w
			KEY[1] = e
			KEY[2] = d
			print("[st] 换档 => world", w, "expand", e, "drones", d, "档位", nm, "| lands ok")
		# ⚠⚠ 采购闸门（真机发现 2026-10-08）：本循环顺序是「派副机 → 干活 → 采购」，
		#   而 R1 要求键（Expand/Megafarm）只能在**没有副机在飞**时买 ⇒
		#   刚放出去的副机会把后面的采购挡住 ✗✗ ⇒ 买得起键时本轮先不派人 ✓
		#   （⚠ 这段一度被我的派活段重写切掉 ⇒ `hold` 未定义 ⇒ 整轮 NameError ✗，
		#     由 scope_check 的「整文件未定义」判据当场抓住 ✓✓）
		hold = 0
		if budget.key_affordable() == 1:
			hold = 1
			print("[fr] 键买得起了 ⇒ 本轮不派副机，先把键买下来")
		# ---- 2) 副机派活（跟踪"每个任务是否真有无人机在飞"）----
		# 真机缺陷（2026-10-08）：
		#   ① 旧版只判断「总数 < 上限」⇒ 某班次结束后会把**名单第一个再派一次** ✗
		#      ⇒ 重复派活（一块地两架 → 违反 R5）+ 后面任务永远轮不上 ✗✗
		#      实测：`rot0: 21 次 / rot1: 1 次`
		#   ② 名单固定顺序 ⇒ 名额用完就停 ⇒ 尾部任务饿死 ✗
		#   ③ `ji = 0` 那段原来在 `if hold == 0:` **外面** ✗（hold=1 时会用上一轮的 js ✗）
		# 修法：ACTIVEB[i] = 第 i 个任务是否有无人机在飞 ✓
		#   每轮按 `drone_count() - 1` 对齐（多的按"最早放的先结束"丢弃 ✓ 启发式），
		#   再**只派不在 ACTIVEB 里的任务** ✓，并从 SPAWN_START 轮换起点开始扫 ✓
		js = []
		if d > 1:
			js = cur.assign(d)
		live = util.drone_count() - 1
		n_alive = 0
		i2 = 0
		while i2 < len(ACTIVEB):
			if ACTIVEB[i2] == 1:
				n_alive = n_alive + 1
			i2 = i2 + 1
		# ⚠⚠⚠ **重复放飞 bug 的修法**（真机 2026-11-01，由 cactus-fixer 定位 ✓）：
		#   旧逻辑「按 n_alive > live 逐条清掉**最小下标**」✗
		#   而副机死亡是**随机**的 ⇒ 任何一架死了都会把 index 0（仙人掌）的标记清掉 ✗
		#   ⇒ 下一轮又派一架仙人掌 ⇒ **同一块 6x6 上同时 2~4 架互相 swap** ✗✗
		#   证据：`[cz] 轮 2` 成对出现、排序 guard(144 步) 反复触发（单机理论 ≤36 步）
		#   ⇒ 收敛必然失败 ⇒ 仙人掌产量长期偏低 ✓✓
		# 新原则：**宁可不派，绝不重复派** ✓
		#   只有当**一架副机都没有**（live == 0）时才整体清零重来 ✓
		#   否则一律保持 ACTIVEB 不变 ⇒ 绝不会给同一任务派第二架 ✓
		# **TTL 回收**：超过 ACTIVE_TTL 的任务视为已结束 ⇒ 清标记让下一轮可重派 ✓
		# **句柄精确回收**（首选 ✓）：has_finished(handle) == True ⇒ 该任务已结束 ✓
		i4 = 0
		while i4 < len(ACTIVEB):
			if ACTIVEB[i4] == 1:
				if i4 < len(HANDLES):
					if HANDLES[i4] != None:
						if has_finished(HANDLES[i4]) == True:
							ACTIVEB[i4] = 0
							n_alive = n_alive - 1
			i4 = i4 + 1
		now_t = get_time()
		i3 = 0
		while i3 < len(ACTIVEB):
			if ACTIVEB[i3] == 1:
				if i3 < len(ACTIVE_T):
					ttl = ACTIVE_TTL_OTHER
					if i3 < len(js):
						nm3 = js[i3]["name"]
						if nm3 == "maze0" or nm3 == "maze1" or nm3 == "maze2" or nm3 == "maze3":
							ttl = ACTIVE_TTL_MAZE
						if js[i3]["cycles"] >= 6:
							ttl = ACTIVE_TTL_MAZE
					if now_t - ACTIVE_T[i3] > ttl:
						ACTIVEB[i3] = 0
						n_alive = n_alive - 1
			i3 = i3 + 1
		if live <= 0:
			i2 = 0
			while i2 < len(ACTIVEB):
				ACTIVEB[i2] = 0
				i2 = i2 + 1
			n_alive = 0
		while len(ACTIVEB) < len(js):
			append(ACTIVEB, 0)
		while len(ACTIVEB) > len(js):
			pop(ACTIVEB)
		if hold == 0:
			if len(js) > 0:
				start = SPAWN_START[0] % len(js)
				SPAWN_START[0] = SPAWN_START[0] + 1
				k = 0
				while k < len(js):
					ji = (start + k) % len(js)
					if ACTIVEB[ji] == 0:
						if util.drone_count() < d:
							j2 = js[ji]
							hd = spawn_drone(j2["entry"], j2["x0"], j2["y0"], j2["w"],
								j2["h"], j2["cycles"], w, j2["roles"])
							if hd != None:
								ACTIVEB[ji] = 1
								while len(HANDLES) <= ji:
									append(HANDLES, None)
								HANDLES[ji] = hd
								while len(ACTIVE_T) <= ji:
									append(ACTIVE_T, 0.0)
								ACTIVE_T[ji] = get_time()
								SPAWNED[0] = SPAWNED[0] + 1
								print("[st] 放飞副机", j2["name"], "@(", j2["x0"], ",",
									j2["y0"], ") 区", j2["w"], "x", j2["h"],
									"班次", j2["cycles"], "| 累计", SPAWNED[0],
									"| 在飞表", ACTIVEB)
					k = k + 1
		# ⚠ 只有**带副机的档位**（w8/w12/w16/w22）才有 set_active ✓
		#   真机报错实录：`Error: stage_w1.set_active 不存在` ✗（w1 的 d=1，本来就没副机 ✓）
		#   ⇒ 用 d > 1 作闸门 ✓（这些档位必定有 set_active ✓，其余档位不需要 ✓）
		if d > 1:
			cur.set_active(ACTIVEB)
		# ---- 3) 干活（先干活后采购 ⇒ 键只在「一轮的末尾」变，下一轮立刻换档）----
		cur.run()
		# ---- 3) 采购：Expand 硬优先；随后先解锁新东西、再堆等级；每轮各买一个 ----
		budget.try_expand()
		# **Mazes 升级优先**：奇异物质过剩时，每升 1 级金币/分钟 ×2 ✓
		mb = budget.maze_level_first()
		if mb == "":
			budget.buy(0)
			budget.buy(1)
		# ---- 4) 状态上报 + 停滞看门狗 ----
		# 看门狗判据 = **累计收割次数**（jobs.HARVEST，单调递增）而不是物品总量：
		#   实测假警报：买一次 Grass lv5 花掉 2560 hay，总量从 2537 掉到 0，
		#   而看门狗对着一次**正常采购**连报 3 次 ✗
		if get_time() - rep > REPORT_SEC:
			rep = get_time()
			if jobs.HARVEST[0] > LAST_HARV[0]:
				LAST_HARV[0] = jobs.HARVEST[0]
				STALL[0] = 0
			else:
				STALL[0] = STALL[0] + 1
				if STALL[0] == STALL_LIMIT:
					print("[fr] !! 停滞定位：主机", get_pos_x(), get_pos_y(), "脚下", get_entity_type(),
						"| 档位", cur_name, "| 收割", jobs.HARVEST[0], "| pumpkin", num_items(Items.Pumpkin),
						"carrot", num_items(Items.Carrot), "hay", num_items(Items.Hay),
						"gold", num_items(Items.Gold), "weird", num_items(Items.Weird_Substance),
						"| 在飞", util.drone_count(), "/", util.drone_cap())
					print("[fr] !! 停滞看门狗：", STALL_LIMIT * REPORT_SEC,
						"秒一次收割都没有 | 档位", cur_name, "| world", w,
						"| hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
						"carrot", num_items(Items.Carrot),
						"| 下一级 Expand 买得起?", util.can_afford(Unlocks.Expand))
			print("[fr] t", get_time() - t0, "rounds", rounds,
				"档位", cur_name,
				"| world", get_world_size(), "expand", num_unlocked(Unlocks.Expand),
				"drones", util.drone_count(), "/", util.drone_cap(),
				"| harv", jobs.HARVEST[0],
				"| hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
				"carrot", num_items(Items.Carrot), "power", num_items(Items.Power),
				"| plant", num_unlocked(Unlocks.Plant), "speed", num_unlocked(Unlocks.Speed),
				"grass", num_unlocked(Unlocks.Grass), "carrots", num_unlocked(Unlocks.Carrots),
				"trees", num_unlocked(Unlocks.Trees), "water", num_unlocked(Unlocks.Watering))
		# 兜底保险丝（正常永远不该触发：榜单自己会在 2 小时处结束）
		if get_time() - t0 > 1000000:
			print("[fr] !! 兜底保险丝到点")
			break
	print("[fr] === full_run v", VERSION, "end === rounds", rounds,
		"| world", get_world_size(), "| hay", num_items(Items.Hay),
		"wood", num_items(Items.Wood), "carrot", num_items(Items.Carrot))


main()
