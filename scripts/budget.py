# ============================================================
# budget.py —— 【策略层】买什么 / 留多少 / 什么时候才允许动「档位键」
#
# 为什么要单独一层：full_run 原来的 try_buy / reserve / wood_floor / hay_floor /
#   pumpkin_gate 全挤在主循环旁边，改一处就牵动产线（v36 的木材死锁、v35 的门槛死锁、
#   v40 的「买得越多产得越少」都出自这里）✗
#   ⇒ 采购是**策略**，与「哪块地干什么活」（档位文件）无关，单独成层 ✓
#
# 三条纪律（全部有实跑血泪）：
#   1) **不写死游戏数字**：价格一律 get_cost() 问出来（costs.md）；只允许写「策略缓冲」百分比。
#   2) **每轮只买一个**：多个解锁常抢同一批木材/干草 ⇒ 一次买光会把农场饿死（v41）。
#   3) **R1 闸门**：Expand / Megafarm 一动，「档位键」就变 ⇒ 只在没有副机在飞时才允许买，
#      否则副机会拿着过期几何继续干活（v58 的坐标错位就是这一类）。
#
# 本文件自足：只用游戏内置函数 + util.py。
# ============================================================

VERSION = 1
import util

# 想买的解锁，按优先级从高到低。分两轮用：
#   want=0：只买「还没解锁」的 ⇒ 保证解锁链一路推进，不被升级插队饿死 ✓
#   want=1：全都解锁过了 ⇒ 才开始堆等级（等级乘数才是这个游戏数量级的来源 ✓）
PLAN = [Unlocks.Expand, Unlocks.Plant, Unlocks.Speed, Unlocks.Grass, Unlocks.Carrots,
	Unlocks.Watering, Unlocks.Trees, Unlocks.Sunflowers, Unlocks.Pumpkins, Unlocks.Fertilizer,
	Unlocks.Polyculture, Unlocks.Cactus, Unlocks.Mazes, Unlocks.Megafarm, Unlocks.Hats,
	Unlocks.Dinosaurs,
	Unlocks.Leaderboard]
NAMES = ["Expand", "Plant", "Speed", "Grass", "Carrots",
	"Watering", "Trees", "Sunflowers", "Pumpkins", "Fertilizer",
	"Polyculture", "Cactus", "Mazes", "Megafarm", "Hats", "Dinosaurs", "Leaderboard"]

MARGIN = 20            # 策略缓冲（%）：不是游戏数据，是我们的选择
WINDOW = 1             # 「只为**最近的 k 个**目标留资源」——见 need_soon()


def is_key(t):
	# 「档位键」的两把钥匙：买下任何一个，档位键（world / drones）就变
	if t == Unlocks.Expand:
		return 1
	if t == Unlocks.Megafarm:
		return 1
	return 0


def key_change_allowed():
	# R1：键只在「没有副机在飞」时变 ⇒ 副机永远不会拿过期几何干活
	if num_unlocked(Unlocks.Megafarm) <= 0:
		return 1                       # 还没有多机 ⇒ 只可能是一架
	if util.drone_count() > 1:
		return 0
	return 1


def need_of(item):
	# 「**全部**还没买到、且要 item 的那些解锁」的成本累加。
	# ⚠ 只用来打印体检，**不要**拿它当「够不够」的判据 —— 理由见 need_soon()
	total = 0
	i = 0
	while i < len(PLAN):
		t = PLAN[i]
		if num_unlocked(t) <= 0:
			c = get_cost(t)
			if c != None:
				for k in c:
					if k == item:
						total = total + c[k]
		i = i + 1
	return total


def need_soon(item, k):
	# 只为**优先级最高的 k 个目标**留资源。判据用 `get_cost(t)`（= 当前等级的**下一级**报价）。
	#
	# ---- 两条都是实跑换来的（2026-10-07 真机那一跑，2268 秒才走到 world 4）----
	#
	# ① **必须把「已解锁项目的下一级」算进来**，不能只看「还没解锁的」：
	#    旧口径 `if num_unlocked(t) <= 0` 会把 Expand 整个跳掉（lv2 > 0），
	#    于是 Expansion 下一级要的 wood 30 / carrot 20 从不进保留线 ——
	#    这与 v64 在 Mazes 上踩的是同一个坑（「已买 lv1 就被排除 ⇒ 上限恒为 800」）✗
	#    ⇒ 改成对 PLAN 每一项都问 `get_cost(t)`；已满级自然返回 None 被跳过 ✓
	#
	# ② **k 必须小**（现在 = 1）：
	#    实跑里 k=2 让 Trees(50) + Pumpkins(500) 一起进了门槛 ⇒ 保留线 665，
	#    而 3x3 每轮只产 1~2 wood ⇒ **胡萝卜那一列到 t≈2250 才开工**，
	#    白烧约 1500 秒游戏时间；Trees(70 carrot) 到收工都没买上 ✗
	#    ⇒ 远期目标（Pumpkins 500 wood）不该管今天的播种 ✓
	total = 0
	n = 0
	i = 0
	while i < len(PLAN):
		t = PLAN[i]
		c = get_cost(t)                 # 下一级报价；已满级 = None
		if c != None:
			for kk in c:
				if kk == item:
					if n < k:
						total = total + c[kk]
						n = n + 1
		i = i + 1
	return total


def keep(item):
	# 保留线 = 最近 k 个目标的该物品需求 + 缓冲 + **永远为正的底**
	# 那个「底」是 v36 的教训：全部买完后 need 会归零，若拿 0 当判据就变成「永远不够」
	n = need_soon(item, WINDOW)
	return n + n * MARGIN // 100 + 5


def key_carrot_keep():
	# 只为**档位键**（Expand / Megafarm）的下一级留胡萝卜。
	#
	# 为什么不能拿整个 carrot_keep() 去当南瓜方块的补种底线：
	#   get_cost(Pumpkins) 是「下一级南瓜等级」的价（真机 lv1->2 = carrot 1000，之后更高），
	#   于是底线会**一级一级往上爬** ⇒ 方块永远等不到那么多胡萝卜 ⇒ 一颗南瓜都种不下去
	#   ⇒ Expand 要的 1000 南瓜永远攒不出来 ⇒ **整局卡死在 6x6** ✗✗
	#   （这正是 2026-10-07 那次「胡萝卜 9 个却一颗没种」的同型病，只是爬升源换成了等级价）
	# 口径：南瓜方块存在的意义就是喂 Expand；等级是**机会性**目标，不该拦住它 ✓
	total = 0
	KEYS = [Unlocks.Expand, Unlocks.Megafarm]
	i = 0
	while i < len(KEYS):
		c = get_cost(KEYS[i])
		if c != None:
			for k in c:
				if k == Items.Carrot:
					total = total + c[k]
		i = i + 1
	return total + 5


def wood_keep():
	return keep(Items.Wood)


def hay_keep():
	# 与 wood_keep 同口径。依据 docs/game/unlocks/carrots.md：种胡萝卜要 wood **and hay**
	return keep(Items.Hay)


def carrot_keep():
	return keep(Items.Carrot)


def pumpkin_keep():
	# 南瓜的底：Expand 从 lv4 起每级都吃南瓜，而它同时是 Cactus/Polyculture 的货币
	return keep(Items.Pumpkin)


def weird_goal():
	# 奇异物质的目标 = **还没解锁**那些要吃 weird 的解锁（Mazes 1000）+ 缓冲 + 迷宫储备。
	#
	# 两个口径要点：
	#  ① 用 need_of（只看未解锁）而不是 need_soon：Mazes 一旦买到，need_of 归零，
	#     否则会像南瓜等级那样把目标一级一级往上推（见 key_carrot_keep 的推导）✗
	#  ② 但也不能归零 ⇒ 加一个 MAZE_RESERVE：迷宫的每次建造/重定位都要吃同样多的 weird
	#     （docs/game/unlocks/mazes.md：金币/物质 = 迷宫边长），所以**永远留一笔迷宫本钱** ✓
	# 依据 fertilizer.md：感染的植物收割时一半产量变 weird ⇒ 目标就是「肥料该不该喂」的闸门
	n = need_of(Items.Weird_Substance)
	return n + n * MARGIN // 100 + MAZE_RESERVE


MAZE_RESERVE = 2000    # 迷宫本钱（策略常数）：够建/重定位一座满场迷宫很多次


def mazes_keep():
	# 给「迷宫等级」留多少钱（奇异物质）。用户 2026-10-07 指出「一直没升级迷宫」——
	# 根因是迷宫任务把 weird 吃干净了，`buy(1)` 永远等不到 Mazes 那一级 ✓
	# docs/game/unlocks/mazes.md：每升一级，宝藏与所需物质**同时翻倍**
	#   ⇒ 金币/物质恒定，但**每趟迷宫的金币翻倍** ⇒ 无人机时间紧张时是净赚 ✓
	# 只留**一半**价钱：全留会把金币线饿死（而金币才是终点要的东西）✗
	c = get_cost(Unlocks.Mazes)
	if c == None:
		return 0
	t = 0
	for k in c:
		if k == Items.Weird_Substance:
			t = t + c[k]
	# ⚠⚠⚠ **预留必须有上限**（真机 2026-11-02，由 maze-fixer 定位的恶性循环 ✓✓）：
	#   「留一半价钱」在 lv3+ 时是 512~4096 级别 ✗，而 w16 阶段 weird 只有 3498 ✗
	#   ⇒ `maze_shift` 顶部的 `weird < sub + keep` guard **永远成立** ⇒
	#   迷宫副机**整班静默空转 212 秒** ✗ ⇒ `ACTIVEB` 一直不清零 ✗ ⇒
	#   **农场类副机永远不重派** ✗ ⇒ hay 5 / power 0 / weird 起不来 ⇒ 反馈环 ✓✓
	#   （用户报的"能量长期不够用"正是这条链的末端 ✓）
	#   ⇒ 最多预留「约 30 次复用」的量 ✓（够本座跑满 30 颗 ✓，又不至于饿死迷宫线 ✓）
	lv = num_unlocked(Unlocks.Mazes)
	cap = 30 * 8
	k2 = 1
	while k2 < lv:
		cap = cap * 2
		k2 = k2 + 1
	half = t // 2
	if half > cap:
		print("[bg] mazes_keep 封顶:", half, "->", cap, "| 防止迷宫线被预饿死 ✓")
		return cap
	return half


def bone_goal():
	# 骨头目标 = **还没解锁**那些吃骨头的解锁（Leaderboard 200 万）+ 缓冲。
	# 用 need_of：Leaderboard 买到就归零（那是终点 ✓）；
	#   ⚠ Polyculture 后续等级也吃骨头（CONTEXT：lv2→3 = 10000），need_of 一并算进来 ✓
	n = need_of(Items.Bone)
	return n + n * MARGIN // 100 + 100


def gold_goal():
	# 金币目标 = **下一个**吃金币的目标（按 PLAN 顺序）+ 缓冲。
	#
	# 为什么用 need_soon（下一个）而不是 need_of（全部未解锁）：
	#   Megafarm 要 gold 2000、Leaderboard 要 gold 1000000，两者都没解锁时
	#   need_of 会给出 1,002,000 ⇒ 迷宫线一上来就想攒 100 万 ✗（而它本来该先换多无人机）
	#   need_soon 只看排在前面的那一个 ⇒ 先 2000（Megafarm），买到之后自动跳成 1,000,000 ✓
	n = need_soon(Items.Gold, 1)
	# ⚠⚠⚠ **终点前最后一道门**（真机实录 2026-11-02，由 maze-fixer 的统计抓出 ✓）：
	#   `[mzw] 金币目标已到 ⇒ 本班收工 | gold 614848 | 目标 **614450**` ✗✗
	#   ⇒ `need_soon` 在这条链上只给出 61.4 万 ✗，而 **Leaderboard 要 100 万** ✗
	#   ⇒ 迷宫副机到 61 万就**集体停工** ⇒ 金币永远到不了终点要求 ✓✓
	#   ⇒ 修正：只要 Leaderboard 还没解锁，目标就**至少**是它的 gold 价 ✓
	if num_unlocked(Unlocks.Leaderboard) <= 0:
		c = get_cost(Unlocks.Leaderboard)
		if c != None:
			lb = 0
			for k in c:
				if k == Items.Gold:
					lb = lb + c[k]
			if lb > n:
				n = lb
				print("[bg] 金币目标提升到 Leaderboard 价位:", n, "（终点要求 ✓）")
	return n + n * MARGIN // 100 + 50


def key_affordable():
	# 有没有「键」（Expand / Megafarm）现在**买得起且还没买** ✓
	# 用途（真机发现 2026-10-08）：full_run 的顺序是「派副机 → 干活 → 采购」，
	#   而 R1 规定键只能在**没有副机在飞**时买 ⇒ 刚放出去的副机会把采购挡住 ✗✗
	#   ⇒ 买得起时这一轮**先不派人**，让采购走通 ✓
	# ⚠ KEYS 是 key_change_allowed() 里的**局部变量**，这里引用不到 ✗
	#   真机报错实录：`Error: KEYS 从未被定义。在使用变量之前必须先给它赋值。`
	#   In: main <- key_affordable  ⇒ 自己带一份列表 ✓（模块层没定义过它 ✓）
	kl = [Unlocks.Expand, Unlocks.Megafarm]
	i = 0
	while i < len(kl):
		t = kl[i]
		# ⚠ 真机报错实录：`Error: can_afford 从未被定义。但它似乎在文件 wood_hay 中有定义。`
		#   ⇒ can_afford 在 **util** 里（wood_hay 是旧单体文件 ✗），必须写 util.can_afford ✓
		#   （budget.py 早就 import util 了；util 自身零导入 ⇒ 不存在导入环 ✓）
		# ⚠⚠ **必须与封顶一致**（真机 bug 2026-11-01）：
		#   Expand 已封顶 world 22 ✓、Megafarm 已封顶 lv4 ✓，但这里仍说"买得起" ✗
		#   ⇒ 调度器**每轮都 hold**（`键买得起了 ⇒ 本轮不派副机`）✗✗
		#   ⇒ 实测 `drones **1** / 16` —— 16 架额度只有 1 架在飞（后半程全线降速 ✗）
		#   ⇒ 封顶了就不许再算作"买得起" ✓
		capped = 0
		if t == Unlocks.Expand:
			if get_world_size() >= 22:
				capped = 1
		if t == Unlocks.Megafarm:
			if num_unlocked(Unlocks.Megafarm) >= 4:
				capped = 1
		if capped == 0:
			if util.can_afford(t) == 1:
				return 1
		i = i + 1
	return 0


def try_expand():
	# Expand 是**硬优先**：world 是后面所有产线的乘数。
	# v7 实测：Expand 排在 PLAN 第 2 却因为「总是差一点 hay」让世界卡在 3x3 二十分钟 ✗
	# ⇒ 只要买得起就立刻买，其余解锁排队 ✓（闸门 R1 照旧）
	# ⚠⚠ **Expand 封顶在 world 22**（真机实录 2026-11-01）：
	#   升到 world 32 后没有对应档位 ⇒ `[fr] !! world 32 没有对应档位 ⇒ 停机` ✗
	#   而当轮骨头已 2,403,428 ✓（超 Leaderboard 的 200 万 ✓），
	#   只差金币 529,088 / 1,000,000 ⇒ **更大的棋盘对终点毫无帮助** ✗
	#   ⇒ 22 是最后一级（w22 档位存在 ✓，32 不存在 ✗）
	if get_world_size() >= 22:
		return ""
	if key_change_allowed() == 0:
		return ""
	if util.can_afford(Unlocks.Expand) == 1:
		if unlock(Unlocks.Expand):
			print("[bg] 买到: Expand(硬优先) | hay", num_items(Items.Hay),
				"wood", num_items(Items.Wood), "carrot", num_items(Items.Carrot),
				"| world", get_world_size())
			return "Expand"
	return ""


def maze_level_first():
	# ⚠⚠ **奇异物质过剩时，Mazes 等级就是金币率的直接乘数**（2026-11-01 真机算账）：
	#   每颗宝藏 = 面积 64 × 2^(lv-1) 金 ✓，耗时 ≈ 走路时间（**与等级无关** ✓）
	#   升 1 级 ⇒ 金币 ×2、物质消耗 ×2 ✓；而实测 `weird 226,371` ✓ 严重过剩 ✓
	#   ⇒ 金币/分钟直接翻倍 ✓✓（我之前"升级不提高金币率"的结论只在"物质是瓶颈"时成立 ✗）
	#   门槛：留够 20 次复用的物质（每次 64 × 2^(lv-1) ✓）再升 ✓
	lv = num_unlocked(Unlocks.Mazes)
	if lv <= 0:
		return ""
	need = 8 * 64
	k = 1
	while k < lv:
		need = need * 2
		k = k + 1
	if num_items(Items.Weird_Substance) < need * 20:
		return ""
	if key_change_allowed() == 0:
		return ""
	if util.can_afford(Unlocks.Mazes) == 1:
		if unlock(Unlocks.Mazes):
			print("[bg] 买到: Mazes 升级(金币乘数) lv", lv, "->", num_unlocked(Unlocks.Mazes),
				"| weird", num_items(Items.Weird_Substance), "| gold", num_items(Items.Gold))
			return "Mazes"
	return ""


def buy(want):
	# 每轮只买一个 —— 买完照常干活，**不要 continue**（v41：一买得起就整天不干活 ✗）
	i = 0
	while i < len(PLAN):
		t = PLAN[i]
		lv = num_unlocked(t)
		ok = 0
		if want == 0:
			if lv <= 0:
				ok = 1
		else:
			if lv > 0:
				ok = 1
		if ok == 1:
			# ⚠ 同 try_expand：**world 22 之后不再扩**（32 没有档位 ⇒ 停机 ✗）
			if t == Unlocks.Expand:
				if get_world_size() >= 22:
					ok = 0
			# ⚠⚠ **Megafarm 封顶 lv4（16 架）**（真机 2026-11-01）：
			#   它是"键" ⇒ buy() 会一路升到 lv5（32 架 ✗），而它吃的是 **gold** ✓
			#   —— 那正是 Leaderboard 需要的 1,000,000 ✗✗
			#   实测：gold 从 529,088 **降到 335,304** ✗（左口袋倒右口袋 ✓）
			#   16 架对 w22 的 4 座迷宫 + 轮作/仙人掌/向日葵/南瓜 完全够用 ✓
			if t == Unlocks.Megafarm:
				if num_unlocked(Unlocks.Megafarm) >= 4:
					ok = 0
		if ok == 1:
			if is_key(t) == 1:
				if key_change_allowed() == 0:
					ok = 0
		if ok == 1:
			if util.can_afford(t) == 1:
				if unlock(t):
					print("[bg] 买到:", NAMES[i], "lv", lv, "->", num_unlocked(t),
						"| hay", num_items(Items.Hay), "wood", num_items(Items.Wood),
						"carrot", num_items(Items.Carrot), "power", num_items(Items.Power),
						"| world", get_world_size(), "drones", util.drone_count())
					return NAMES[i]
		i = i + 1
	return ""


def report_costs():
	# 开局一次，把「还买得动的下一级」全部问清楚（铁律：不许写估计值）
	print("[bg] 下一级报价 | Expand", util.cost_of(Unlocks.Expand, Items.Hay),
		"hay /", util.cost_of(Unlocks.Expand, Items.Wood), "wood /",
		util.cost_of(Unlocks.Expand, Items.Carrot), "carrot /",
		util.cost_of(Unlocks.Expand, Items.Pumpkin), "pumpkin")
	print("[bg] Speed", util.cost_of(Unlocks.Speed, Items.Hay), "hay",
		"| Plant", util.cost_of(Unlocks.Plant, Items.Hay), "hay",
		"| Grass", util.cost_of(Unlocks.Grass, Items.Hay), "hay")
	print("[bg] Carrots", util.cost_of(Unlocks.Carrots, Items.Wood), "wood",
		"| Watering", util.cost_of(Unlocks.Watering, Items.Wood), "wood",
		"| Trees", util.cost_of(Unlocks.Trees, Items.Wood), "wood +",
		util.cost_of(Unlocks.Trees, Items.Carrot), "carrot")
	print("[bg] Sunflowers", util.cost_of(Unlocks.Sunflowers, Items.Carrot), "carrot",
		"| Pumpkins", util.cost_of(Unlocks.Pumpkins, Items.Wood), "wood +",
		util.cost_of(Unlocks.Pumpkins, Items.Carrot), "carrot",
		"| Fertilizer", util.cost_of(Unlocks.Fertilizer, Items.Wood), "wood")
	print("[bg] 种一株 Carrot 要 | wood", util.cost_of(Entities.Carrot, Items.Wood),
		"hay", util.cost_of(Entities.Carrot, Items.Hay),
		"| 种一株 Pumpkin 要 | carrot", util.cost_of(Entities.Pumpkin, Items.Carrot))
	print("[bg] 保留线 | wood", wood_keep(), "hay", hay_keep(), "carrot", carrot_keep(),
		"pumpkin", pumpkin_keep())
	return 1
