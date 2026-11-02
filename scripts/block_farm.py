# ============================================================
# block_farm.py —— **可复用的"连片方块"农法模块**
#
# 为什么要单独一个文件（用户提出的正确方向）：
#   这个游戏所有高产出玩法都是**同一个模式**：
#       摆成一个连通方块 → 满足某个全局条件 → 一刀全收
#     * 南瓜：方块全部成熟 ⇒ 合并成巨型南瓜，产量 n^3（4x4=64、n>=6 时 n*n*6）
#     * 仙人掌：方块排好序 ⇒ 连锁收割，产量 n^2 x 等级
#     * 恐龙尾巴：整盘铺满 ⇒ 一次成型几千万骨头
#   而我前面把新作物一次次硬塞进 full_run 的 farm_round 分支链（三格→四格→加方块），
#   每塞一次就打乱一次节奏 —— v20 就是这么把整台机器改瘫的（1474 轮空转）✗
#   ⇒ 正确做法：**方块管理抽到这里**，full_run 只负责"什么时候调哪块地、钱怎么花"。
#
# 本文件可以直接单独运行（做一次 4x4 南瓜方块的完整验证），
# 也可以被 full_run.py 用 `import block_farm` 复用。
#
# 纪律（本项目连栽四次换来的）：
#   * 调用任何动词前先问"解锁了吗 / 付得起吗"（南瓜每株花胡萝卜）
#   * 不做 `import` 循环
#   * 死亡株必须补种：成熟后 20% 概率死，死南瓜 can_harvest() 恒 False、
#     且**死一株整片就合不了体** ⇒ 每轮都要"扫描 + 补种"
# ============================================================

VERSION = 16
HARV_TOTAL = [0]      # v14：累计收割次数（诊断用，full_run 的报告行会读它）
REPORT_SEC = 10.0

# 南瓜每株的胡萝卜成本（文档只说"costs carrots"，具体数由调用方按库存把关）


def carrot_floor():
	# ---- v11：保留线必须**动态**（用户指出种植逻辑有问题）----
	# 实测：模拟推进到南瓜阶段时 Trees(70)/Sunflowers(500) 早就买完了，
	# 可写死的 70 白留着 ⇒ 胡萝卜一触底就停补种 ⇒ 方块从 9/9 退化到 5/9 ✗
	# 正确口径：**只给还没买到的解锁留钱**，都买完就是 0 —— 胡萝卜全部可以喂南瓜
	# ---- v12：和 full_run.reserve() 同一口径 —— **向游戏问价**，不写死数字 ----
	# 依据 docs/game/unlocks/costs.md：get_cost(t) 返回 {Item: 数量}；已满级返回 None
	# 原来写死 70/500 ✗：哪天 Trees/Sunflowers 涨价或改料，这个数就悄悄错了
	keep = 0
	NEED = [Unlocks.Trees, Unlocks.Sunflowers]
	for t in NEED:
		if num_unlocked(t) <= 0:
			c = get_cost(t)
			if c != None:
				for k in c:
					if k == Items.Carrot:
						keep = keep + c[k]
	return keep + keep * 20 // 100


def go_to(tx, ty):
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


def block_size():
	# ---- v3：**方块边长必须每轮重算**（用户指出）----
	# 田的大小会变（Expand 一升级世界就变大；完全复位榜里世界一直在长）⇒
	# 开局算一次就一直用旧值，等于把方块锁死在旧尺寸 ✗
	# 口径：尽量吃满 n>=6 的倍率（n*n*6），但最多占世界一半，给 hay/wood/carrot 留地。
	# ---- v14：边长按**期望收益**选，不再取世界大小的一半 ----
	# 依据 docs/game/unlocks/pumpkins.md：成熟后每株 20% 概率死亡，而收割门要求每格都活
	#   ⇒ 单轮全活概率 0.8^(n*n)，单次产量 n^3（n<=5）/ n*n*6（n>=6）
	#   期望 = P × 产量：n=2 → 3.3 ｜ 【n=3 → 3.6 最优】｜ n=4 → 1.8 ｜ n=5 → 0.47 ｜ n=6 → 0.065
	# ⇒ v44 时 world 8 用的是 n=4（期望 1.8），改成 n=3 约翻倍；再大反而更差
	# 下一个杠杆：并排几个 3x3，各自独立开门 ⇒ 收益按块数倍增
	# ---- v15：方块**绝不能吞掉整块棋盘**（v45 的实测死锁）----
	# world 3 时 n=3 ⇒ 轮作要跳过全部 9 格 ⇒ 一格都种不了 ⇒ 万物为 0、连 Carrots 都买不起 ✗
	# ⇒ 棋盘不够大时**干脆不给方块留地**（n=0 ⇒ 轮作照常铺满 ✓）
	# ---- v16/v61：**恢复到文档结论：6x6** ----
	# docs/game/unlocks/pumpkins.md 原文：n>=6 时产量 n*n*6（6x6=216 ⇒ 每格 6，是 3x3 每格 3 的两倍）
	#   并明确写道：It is a good idea to get at least 6x6 size pumpkins to get the full multiplier
	# v14 我按 门开启频率 x 单次产量 算期望得出 3x3 最优 ✗ —— 那忽略了**补种正是无人机的工作** ✓
	#   （用户指出：多无人机的意义就是服务这种大田 ✓）
	# 但保留 v15 的教训：**绝不能吞掉整块棋盘** ⇒ n 不超过 ws//2 ✓
	ws = get_world_size()
	n = ws // 2
	if n > 6:
		n = 6
	if n < 2:
		n = 0
	if n > ws:
		n = ws
	return n


def live_pumpkins(n):
	# v6：诊断用的这块也要先回原点，否则报出来的"活南瓜数"是错位的读数 ✗
	go_to(0, 0)
	# 数方块里有几株活南瓜、几株是别的东西（死南瓜/草/空）
	alive = 0
	other = 0
	y = 0
	while y < n:
		x = 0
		while x < n:
			if get_entity_type() == Entities.Pumpkin:
				alive = alive + 1
			else:
				other = other + 1
			x = x + 1
			if x < n:
				move(East)
		y = y + 1
		if y < n:
			move(North)
		# ---- v5：回行首**只走 n-1 步** ----
		# 原来走 n 步 ⇒ 多走一格、**绕到世界另一头**（棋盘是环形，不会报错、只会静默错位）✗
		# 从第 2 行起方块扫描就偏了 ⇒ 种到方块外、漏掉方块内 ⇒ "活南瓜只有 5 个"的真因
		cnt = 0
		while cnt < n - 1:
			move(West)
			cnt = cnt + 1
	return alive, other


def init_block(n):
	# ---- v10：**南瓜区初始化**（用户指出：6x6 时这块地可能已被占据而种不下去）----
	# 做法照搬项目里已验证的两处：main.py 的 replant_pumpkin_band / cactus_farm 的 till_region
	#   * 把区域内**别的作物**收掉（灌木/胡萝卜/草）
	#   * 统一翻成土壤（南瓜像胡萝卜一样长在 tilled soil 上）
	#   * **唯独不碰南瓜本身**：成熟的大南瓜是收割门的一部分，收掉就等于把门拆了 ✗
	go_to(0, 0)
	y = 0
	while y < n:
		x = 0
		while x < n:
			e = get_entity_type()
			if e != Entities.Pumpkin:
				if can_harvest():
					harvest()
			if e != Entities.Pumpkin:
				if get_ground_type() != Grounds.Soil:
					till()
			x = x + 1
			if x < n:
				move(East)
		y = y + 1
		if y < n:
			move(North)
		cnt = 0
		while cnt < n - 1:
			move(West)
			cnt = cnt + 1
	go_to(0, 0)


def plant_block(n, floor):
	# 逐格补种。**v3 修的关键 bug**：v1/v2 的判据是"脚下不是活南瓜就补种" ✗
	# 而刚种下的南瓜在成形前**不是** Entities.Pumpkin ⇒ 被误判成空地、反复铲掉重种：
	# 实测 10 秒烧掉 4.8 万胡萝卜、16 格里只有 3 株活着 ✗✗
	# ⇒ 只在**明确是空地或草**时才种（和 full_run 里跑通的那条判据一致）✓
	#   死南瓜格留到下一轮由"成熟后仍不可收"另行处理（名字待查清，不猜）
	# ---- v6：**每次扫描前先回方块原点 (0,0)** ----
	# 漏这一步的后果：扫描走完最后一行时无人机停在 (0, n-1)（最上面一行的行首），
	# 而调用方只在最开头 go_to 一次 ⇒ 第二次扫描从 y=n-1 起**继续往北**，
	# 每轮向北漂 n-1 格 ⇒ 越扫越靠北、彻底脱离方块 —— 这就是"一直向上种"的真因 ✗
	go_to(0, 0)
	planted = 0
	y = 0
	while y < n:
		x = 0
		while x < n:
			e = get_entity_type()
			# ---- v4：按项目 ADR（docs/adr/0002-mega-pumpkin-harvest-gate.md）补最后一步 ----
			# ADR 原文规定：空格补种、**Dead Pumpkin 用 harvest() 清除后补种**。
			# 我之前一直在等死瓜自己消失 ✗ ⇒ 那些格子永远不产出、整片也合不了体。
			# 死瓜的枚举名我没有依据（不猜）⇒ 用**排除法**锁定它：
			#   不是空地、不是草、不是活南瓜、且 can_harvest() 为假 ⇒ 那就是死瓜；
			#   活南瓜走不到这里 ⇒ 不会被误铲 ✓
			if e != None and e != Entities.Grass and e != Entities.Pumpkin:
				if can_harvest() == False:
					harvest()
					e = get_entity_type()
			# ---- v8：判据改回 ADR 的写法 —— **只要不是活南瓜就补种** ----
			# v3 时我把它收紧成「只在空地/草种」，理由是当时看到「胡萝卜狂烧、只活 3 株」；
			# 但那个现象的真因是**坐标漂移**（种到了全世界），与判据无关 ✗。
			# 坐标已在 v6 修好（真实存档一刀 110,592 个为证）⇒ 收紧只会让方块永远凑不齐：
			# 死瓜格既不补种、收割门又要求每格都是活南瓜 ⇒ 永远等不到（实测卡在 4/9 ✗）
			if e != Entities.Pumpkin:
				if num_items(Items.Carrot) > floor:
					if get_ground_type() != Grounds.Soil:
						till()
					plant(Entities.Pumpkin)
					planted = planted + 1
			x = x + 1
			if x < n:
				move(East)
		y = y + 1
		if y < n:
			move(North)
		cnt = 0
		while cnt < n - 1:
			move(West)
			cnt = cnt + 1
	return planted


def ready_block(n):
	# v6：同样**先回原点** —— 否则这块的"读"也会跟着往北漂，收割门永远判不出来 ✗
	go_to(0, 0)
	# 全部都是活南瓜、而且都能收 ⇒ 已经合体（或等价于可以一刀收）
	y = 0
	while y < n:
		x = 0
		while x < n:
			if get_entity_type() != Entities.Pumpkin:
				return 0
			if can_harvest() == False:
				return 0
			x = x + 1
			if x < n:
				move(East)
		y = y + 1
		if y < n:
			move(North)
		cnt = 0
		while cnt < n - 1:
			move(West)
			cnt = cnt + 1
	return 1


def run_pumpkin_block(cycles, target_gain, floor, quiet = 0):
	# ⚠ target 是**相对增量**，不是绝对库存！
	# v1 自测第一轮就栽在这：真实存档南瓜已有 4.77 亿，而我判 `>= 3000` ⇒ 一进门就"达标"、
	# 一轮没跑就收工 ✗（项目记忆里原话："目标必须相对开局库存"，这是第三次踩同一个坑）
	# ---- v17（P2 模块化）：门槛改由**调用方**传进来 ----
	# 原来这里内部调 carrot_floor() = {Trees, Sunflowers} 的胡萝卜需求 +20% ≈ 684，
	# 而 6x6 时期全盘胡萝卜都没 684 ⇒ **一整轮一颗南瓜都种不下去** ✗
	# 这与 budget.py 里刚修掉的「门槛锁死」是同一种病（v35 / v36 / 2026-10-07 那次）
	# ⇒ 门槛是**策略**，归调用方（jobs.py 从 budget.carrot_keep() 拿）✓
	# 独立运行本文件时由 main() 传 carrot_floor()，行为不变 ✓
	n = block_size()
	if n < 2:
		print("[blk] 棋盘太小（n =", n, "）⇒ 本阶段不种南瓜，土地留给轮作")
		return 0
	got0 = num_items(Items.Pumpkin)
	if quiet == 0:
		print("[blk] 方块边长", n, "| world", get_world_size(), "| 起始南瓜", got0,
			"| 胡萝卜", num_items(Items.Carrot), "| 目标增量", target_gain)
	go_to(0, 0)
	# v10：开工前先把这块地**初始化**（清掉别的东西 + 翻土），否则可能被占据种不下去
	init_block(n)
	c = 0
	while c < cycles:
		c = c + 1
		# v3：**每轮重算边长** —— 田会随 Expand 变大（完全复位榜里一直在长），
		# 只算一次会把方块锁死在开局尺寸 ✗（用户指出）
		n = block_size()
		if num_items(Items.Pumpkin) >= got0 + target_gain:
			if quiet == 0:
				print("[blk] 已赚够", target_gain, "个，提前收工")
			break
		p = plant_block(n, floor)
		t0 = get_time()
		# 等成熟；期间不断补种死株（死一株整片就合不了体）
		rep = t0
		ok = 0
		while get_time() - t0 < 45.0:
			if ready_block(n) == 1:
				ok = 1
				break
			if plant_block(n, floor) > 0:
				p = p + 1
			if get_time() - rep > REPORT_SEC:
				rep = get_time()
				if quiet == 0:
					a, o = live_pumpkins(n)
					print("[blk] 第", c, "轮等待中 | 活南瓜", a, "| 非南瓜格", o,
						"| 胡萝卜", num_items(Items.Carrot), "| 南瓜", num_items(Items.Pumpkin))
		if ok == 0:
			if quiet == 0:
				print("[blk] 第", c, "轮还没全部成熟（本轮先让位，下一轮再来）")
			continue
		go_to(0, 0)
		harvest()
		HARV_TOTAL[0] = HARV_TOTAL[0] + 1
		print("[blk] 第", c, "轮收割完成 | 补种", p, "次 | 南瓜", num_items(Items.Pumpkin))
	print("[blk] DONE 收到", num_items(Items.Pumpkin) - got0, "个南瓜")
	return num_items(Items.Pumpkin) - got0


def main():
	print("=== block_farm v", VERSION, " 单文件自测 ===")
	print("[blk] world", get_world_size(), "| Pumpkins 解锁等级", num_unlocked(Unlocks.Pumpkins),
		"| 胡萝卜", num_items(Items.Carrot))
	if num_unlocked(Unlocks.Pumpkins) <= 0:
		print("[blk] Pumpkins 还没解锁 ⇒ 什么都不做（纪律：动词先问解锁）")
		return
	if num_items(Items.Carrot) <= carrot_floor():
		print("[blk] 胡萝卜不足（需 >", carrot_floor(), "）⇒ 先回去种胡萝卜")
		return
	run_pumpkin_block(4, 400, carrot_floor(), 0)
	print("=== block_farm end ===")


if __name__ == "__main__":
	main()
