# ============================================================
# jobs.py —— 【算法层】任务算法库
#
# 这一层**不含任何绝对坐标**：所有函数要么作用于「无人机脚下这一格」，要么由调用方
#   把矩形 (x0, y0, w, h) 传进来。「谁占哪块地」100% 写在 stage_*.py 里 ✓
#   （这是 zones.py 那次翻车的根治办法：地块归属与作业在同一个文件里，谁也脱不了节。）
#
# 每个**班次**函数（名字以 _shift 结尾）都必须遵守两条：
#   R2 副机不许 while True：cycles 用完或超过 SHIFT_SEC 就 return
#   R3 每轮校验 get_world_size() == my_world，不等就立刻下岗（世界一变手里坐标全废）
#
# 本文件自足：只用游戏内置函数 + util.py。
# ============================================================

VERSION = 2
import util
import budget
import block_farm

SHIFT_SEC = 20.0       # 单班上限（策略常数，不是游戏数据）

# 累计收割次数：**单调递增**，永远不因花钱而下降 ⇒ 是「还在不在产出」的唯一可靠判据。
# 为什么不用「物品总量」当判据：买一次 Grass lv5 要 2560 hay，总量会从 2537 掉到 0，
# 于是停滞看门狗对着一次正常采购报警（mock 实测 3 次假警报）✗
# ⚠ R8：跨机没有共享内存 ⇒ 每架各有一份，主机读到的只是主机自己的
HARVEST = [0]

# 向日葵带的诊断计数（跨机各一份；要打印的量由算它的那架自己 print —— R8）
SUN_DIAG = [0]
SUN_HARV = [0]     # 累计割成多少刀（判「power 到底有没有在产」）


def world_changed(my_world):
	if get_world_size() != my_world:
		return 1
	return 0


def plant_wood():
	# 灌木 1 wood/棵；Trees 解锁后改种树（5 wood/棵，docs/game/unlocks/trees.md）
	if num_unlocked(Unlocks.Plant) <= 0:
		return 0
	if num_unlocked(Unlocks.Trees) > 0:
		plant(Entities.Tree)
		return 1
	plant(Entities.Bush)
	return 1


# 当前正在扫的矩形（= 本机的辖区，R5）。satisfy_companion 用它判断「这个请求是不是我的地」
CUR_RECT = [0, 0, 0, 0]


def satisfy_companion():
	# 站在一株植物上，满足它的伴生请求（docs/game/unlocks/polyculture.md）
	#   * get_companion() 给出 (它想要的物种, 想要的坐标)，坐标在 3 步以内 ✓
	#   * 满足后**收割产量 × 5·2^等级**（等级 1 就是 ×10）✓
	#   * 成熟度无关紧要，种着就算 ✓
	#
	# ⚠ 为什么必须做（2026-10-07 用户指出「没考虑混合种植的产量提升」）：
	#   感染的植物收割时**一半产量变 weird** ⇒ 产量翻 10 倍，一口肥料换到的 weird 也翻 10 倍
	#   ⇒ 这是**奇异物质线（进而金币线）最大的乘数**，比升级肥料还直接 ✓
	# ⚠ 代价：来回约 6 个行动 = 1200 ticks（CONTEXT 的 Companion Hit 口径）
	#   ⇒ 只对**树**做：灌木/胡萝卜基础产量 1，倍率再高也是零头 ✗
	# ⚠ 只在**自己这个矩形内**满足：跨区会踩别人的地（R5），而多机时每架只管自己的片 ✓
	# ⚠⚠ 2026-11-02 真机 + 反编译修正：**伴生种植绝不能为了种而 till** ✗
	#   旧版「e==None/Grass ⇒ if ground != Soil: till() ⇒ plant」会
	#     ① 把目标格（可能落在**草列**）翻成 Soil ⇒ 草长不回来 ⇒ hay 产量永久下降 ✗✗
	#     ② 种胡萝卜时绕过 hay 保留线 ⇒ 4 棵/sweep x 64 hay 把干草抽干 ✗
	#   ⇒ 新规则（反编译 FarmObjectSO.placeableOn 权威）：
	#     * 胡萝卜**只能种在 Soil 上** ⇒ 只在目标格本来就是 Soil 时种，且要过 `carrot_ok()`
	#       hay 闸门；目标格是草地就**直接放弃**（绝不为它制造一块土壤化 ✓）
	#     * 草/灌木/树 的 placeableOn = ["grassland","soil"] ⇒ **直接种、不翻土** ✓
	#       （草地上的草 canBeOverplanted=true ⇒ plant 能直接盖过去 ✓）
	if num_unlocked(Unlocks.Polyculture) <= 0:
		return 0
	r = get_companion()
	if r == None:
		return 0
	kind = r[0]
	cx = r[1][0]
	cy = r[1][1]
	if cx < CUR_RECT[0] or cx >= CUR_RECT[0] + CUR_RECT[2]:
		return 0
	if cy < CUR_RECT[1] or cy >= CUR_RECT[1] + CUR_RECT[3]:
		return 0
	mx = get_pos_x()
	my = get_pos_y()
	util.go_to(cx, cy)
	e = get_entity_type()
	ok = 0
	if e == kind:
		ok = 1              # 已经是它要的物种 ⇒ **白拿**（CONTEXT：有一部分命中与脚本无关）
	else:
		if e == None or e == Entities.Grass:
			if kind == Entities.Carrot:
				# 胡萝卜只能种在土壤上：目标格已经是 Soil 才动手（**绝不翻土制造土壤化** ✗）
				if get_ground_type() == Grounds.Soil:
					if e == Entities.Grass:
						harvest()          # soil 上的草先收掉（白拿 hay，且草 canBeOverplanted）
					if carrot_ok() == 1:
						plant(Entities.Carrot)
						if get_entity_type() == Entities.Carrot:
							ok = 1
			else:
				# 草/灌木/树在 grassland 与 soil 都能长 ⇒ 直接种，不动地面 ✓
				plant(kind)
				if get_entity_type() == kind:
					ok = 1
	util.go_to(mx, my)
	return ok


def work_wood_tile():
	# 割草也能产 hay（草永远可割）⇒ 收成与补种一起做，不浪费任何一次访问
	if can_harvest():
		# ---- 奇异物质线：先满足伴生（产量乘数），再喂肥料（一半产量变 weird），最后收 ----
		# ⚠ 顺序不能反：喂了肥料再补伴生也有效，但先补伴生能让**同一口肥料**换到 ×10 的产量 ✓
		if get_entity_type() == Entities.Tree:
			satisfy_companion()
			if num_items(Items.Fertilizer) > 0:
				if num_items(Items.Weird_Substance) < budget.weird_goal():
					use_item(Items.Fertilizer)
		harvest()
		HARVEST[0] = HARVEST[0] + 1
	e = get_entity_type()
	if e == None or e == Entities.Grass:
		return plant_wood()
	return 0


def work_hay_tile():
	# 草地：只收不种（草自己长回来，docs/game/unlocks/plant.md）
	#
	# ⚠⚠ 2026-11-02 真机 + 反编译定位：**恐龙尾巴会把整盘踩成 Soil** ✗
	#   `Dinosaur.OnRestart`（反编译 Core.dll，Dinosaur : FarmObject）：
	#     它走过的每一格执行 `if (!(grounds[pos] is Soil)) SetGround(pos, "soil");`
	#   而一趟恐龙的蛇尾要走 1 万+ 步（真机 `[dino] 走了 11032 步`），棋盘只有 16x16=256 格
	#   ⇒ **整盘都会被土壤化**，真机日志 `[s16] farm_a 地面 | 草原 0 土壤 24 |
	#     各列土壤 [4,4,4,4,4,4] | 草列(0-3)土壤化 16` 就是它 ✓✓（另一小来源是旧的伴生 till，已堵）
	#   草**只长在 Grassland** ⇒ 不把土壤翻回去，草列就永久荒废（hay 再也长不出来 ✗）
	#   ⇒ 本函数负责**自愈**：地面是 Soil 就 till() 回 Grassland
	#     （反编译 Drone.ChangeGround：till 请求 soil 时若当前已是 soil ⇒ SetGround("grassland")
	#      并 SetEntity("grass") ⇒ 一次 till 就恢复成「草原 + 草」✓）
	if get_ground_type() == Grounds.Soil:
		e0 = get_entity_type()
		if e0 == None or e0 == Entities.Grass:
			till()
			return 0              # 刚翻回草原，等草长（下一遍来收；不空转 ✓）
		# 土壤上有别的作物（伴生/残留）：先白拿产物，别直接 till 掉 ✓
		if can_harvest():
			harvest()
			HARVEST[0] = HARVEST[0] + 1
		return 0
	if can_harvest():
		harvest()
		HARVEST[0] = HARVEST[0] + 1
		return 1
	return 0


# ---- 胡萝卜种植的「干草保留线」（2026-11-02，用户报 hay 长期贴 0）----
# 依据（反编译 Core.dll 的 Farm.Plant）：扣费 = objectSO.cost x 2^(yield升级等级-1)，
#   胡萝卜基础成本 = **1 wood + 1 hay** ⇒ 等级越高越贵（lv10 = 512 hay/株 ✗）。
#   干草的唯一消耗方就是胡萝卜种子 ⇒ 种之前不留一点库存，干草会被瞬间抽干，
#   然后胡萝卜列自己先断种（真机实录：`没有种植 Entities.Carrot 所需的物品`）✗
HAY_SAVE_CAP = 50
# ⚠ 为什么给 budget.hay_keep() **封顶**、而不是直接拿它当闸门：
#   hay_keep() = 「最近 1 个 PLAN 目标的 hay 预留价」，早期就可能是 500 / 2500 / 30000
#   （下一级 Speed/Grass 的 hay 价）⇒ 直接当闸门会让胡萝卜线**永久停摆** ✗
#   （与 budget.key_carrot_keep 那段注释同一个教训：别让「下一级升级价」拦住产线）
#   ⇒ 只保留 50 的缓冲：足以避免「抽干 → 锁死」，又把开局延迟压在几十秒内 ✓


def carrot_seed_hay():
	# 一株胡萝卜要多少 hay：**从 get_cost 动态取，不写死**（等级越高越贵）
	per = 0
	c = get_cost(Entities.Carrot)
	if c != None:
		for k in c:
			if k == Items.Hay:
				per = c[k]
	if per < 1:
		per = 1
	return per


def carrot_ok():
	# 种胡萝卜的两个前提：
	#   ① 付得起（R7 原判据，**保留** ✓）
	#   ② 种完不会把干草抽干（hay 保留线 ✓）
	if util.can_afford(Entities.Carrot) == 0:
		return 0
	keep = budget.hay_keep()
	if keep > HAY_SAVE_CAP:
		keep = HAY_SAVE_CAP
	if num_items(Items.Hay) <= keep + carrot_seed_hay():
		return 0
	return 1


def work_carrot_tile():
	# 依据 docs/game/unlocks/carrots.md：必须先 till() 成 Grounds.Soil 才能种胡萝卜，
	#   而种一株要 wood 1 + hay 1 ⇒ **付不起就不种**（R7：动词前先问付得起吗）✓
	#   ⚠ 2026-11-02：再加 hay 保留线 ⇒ 见 carrot_ok() 与 HAY_SAVE_CAP 的注释
	if num_unlocked(Unlocks.Carrots) <= 0:
		return work_hay_tile()
	e = get_entity_type()
	if e == Entities.Carrot:
		if can_harvest():
			harvest()
			HARVEST[0] = HARVEST[0] + 1
		if carrot_ok() == 1:
			plant(Entities.Carrot)
		return 1
	if can_harvest():
		harvest()
		HARVEST[0] = HARVEST[0] + 1
	if get_ground_type() != Grounds.Soil:
		till()
	if carrot_ok() == 1:
		plant(Entities.Carrot)
		return 1
	return 0


def grind_shift(seconds):
	# 原地割草：早期最快的干草来源（实测 1.26 hay/秒，见 full_run v4 日志）
	# 草 0.47 秒长回来，harvest 不花钱 ⇒ 站着一直割就是最优
	t0 = get_time()
	n = 0
	while get_time() - t0 < seconds:
		if can_harvest():
			harvest()
			HARVEST[0] = HARVEST[0] + 1
			n = n + 1
	return n


# ============================================================
# 通用走位：**按列扫一个矩形**
# ============================================================

def work_tile(role):
	if role == "wood":
		return work_wood_tile()
	if role == "carrot":
		return work_carrot_tile()
	return work_hay_tile()


def sweep_columns(x0, y0, w, h, roles):
	# 按**列**扫一个矩形：roles[i] = 这个矩形第 i 列的物种。
	#
	# 为什么按列而不是按行：档位的物种是**按列分配**的（左边木、中间胡萝卜、右边草），
	#   按列走一遍正好让「物种」与「走位」对齐，不会串列 ✓
	#
	# ⚠⚠ 回本列起点**必须走 h-1 步 South，绝不能用「走 h 步 North 靠棋盘环绕回来」**：
	#   环绕只在 h == 世界高度时成立；子矩形的 h 一般不等于高度
	#   （8x8 的 y=4..7 那条带：从 y=4 走 4 步 North 落在 y=0 ✗）
	#   ⇒ 整条扫描会**静默漂到别的区域**，不报错、只是把树种进向日葵带和南瓜方块 ✗✗
	#   mock 实测：8x8 首次进档时向日葵带 16 格里有 8 格是 tree ⇒ 向日葵永远凑不到 10 株
	#   同一个坑 block_farm v5 已经记过一次（"回行首只走 n-1 步"），这里又复发了 ——
	#   因为棋盘是环形的，写错了不会报错，只会一直错下去。
	util.go_to(x0, y0)
	CUR_RECT[0] = x0
	CUR_RECT[1] = y0
	CUR_RECT[2] = w
	CUR_RECT[3] = h
	i = 0
	while i < w:
		y = 0
		while y < h:
			work_tile(roles[i])
			y = y + 1
			if y < h:
				move(North)
		cnt = 0
		while cnt < h - 1:
			move(South)
			cnt = cnt + 1
		i = i + 1
		if i < w:
			move(East)
	return 1


# ============================================================
# 南瓜方块：包一层 block_farm（算法在那边，**门槛归策略层**）
# ============================================================

def pumpkin_shift(cycles, target_gain):
	if num_unlocked(Unlocks.Pumpkins) <= 0:
		return 0
	# 补种底线 = 方块种子钱 + 档位键要的胡萝卜 + **还没解锁**的那些目标的胡萝卜需求。
	#
	# 三段各有来历（2026-10-07，都是 mock 长跑换来的）：
	#   * 只用 block_farm 内部的 carrot_floor() ≈ 684 ⇒ 6x6 一颗都种不下去 ✗
	#   * 只用 budget.carrot_keep()：它是「下一级」的价，南瓜等级一升底线就往上爬
	#     ⇒ 方块永远等不到 ⇒ Expand 的 1000 南瓜永远攒不出来 ✗
	#   * 只用 key_carrot_keep()：底线低到 14 ⇒ 方块把胡萝卜吃干 ⇒
	#     Sunflowers（carrot 500，全局 2 倍速）永远买不上 ✗
	#   ⇒ 「还没解锁」这个过滤恰好两全：它**会过期**（买到就消失），所以不会无限爬升；
	#     而在 Sunflowers 这类大件没到手之前，它又能挡住方块 ✓
	side = block_farm.block_size()
	# ⚠⚠ **背不动就让位**（真机停滞实录 2026-10-08）：
	#   `停滞定位：主机 0 0 脚下 Entities.Pumpkin | 收割冻结 | carrot 0` ✗
	#   胡萝卜为 0 ⇒ 补种不了 ⇒ 方块会**死等 45 秒**（run_pumpkin_block 的等待循环）✗
	#   ⇒ 主机被困在方块里 ⇒ 全场收割冻结 ✗ ⇒ 干脆不进方块，
	#     把主机让出来去种胡萝卜 ✓（已种下的南瓜下一轮再收 ✓，损失很小 ✓）
	if num_unlocked(Unlocks.Pumpkins) <= 0:
		return 0
	if num_items(Items.Carrot) <= 0:
		print("[blk] 胡萝卜为 0 ⇒ 本轮回轮作（不进方块死等 ✓）")
		return 0
	floor = side * side + budget.key_carrot_keep() + budget.need_of(Items.Carrot)
	return block_farm.run_pumpkin_block(cycles, target_gain, floor)


def pumpkin_block_side():
	# 方块边长口径与 block_farm.block_size() **必须同一口径**，否则档位的 lands() 与它错位 ✗
	return block_farm.block_size()


# ============================================================
# 迷宫（金币线）
# ============================================================

MZ_DIRS = [North, East, South, West]
MZ_DIAG = [0]
# 迷宫左上角相对「建造时无人机位置」的偏移 —— **必须探针实测**，不许假设
#   CONTEXT.md 的 Maze Anchor 条目：落点规则可能是「脚下为左上角」，也可能是「以无人机为中心」，
#   后者在只测一个 k 时看不出来（平移量 = -k/2，**与边长有关**）。
#   真机证据（2026-10-07 用户报告）：在区域左上角建 12x12，迷宫**压到了 (0,0) 的南瓜方块**
#   ⇒ 锚点不是左上角（若居中则偏移 = -k/2）⇒ 不补偿就是两套系统抢地 ✗
MZ_ANCHOR = [999, 999]
MZ_ANCHOR_LV = [-1]        # 探针是在哪个迷宫等级下测的
MZ_ANCHOR_SIDE = [-1]      # ⚠ 还必须记住**边长**：居中锚点的偏移 = -side/2，与边长有关
						   #   （真机症状：w12 用边长 6 测出的 -3 被 w16 的边长 8 复用 ⇒ 差一列 ✗）
MZ_REUSE = [0]             # 本座迷宫还能复用几次（源码：treasureFactor 1→301 ⇒ 最多 300 次）
# ⚠⚠⚠ **复用协议已按游戏源码钉死**（2026-11-01 反编译 `Core.dll` 得到，不许再凭文档猜）：
#   * `Treasure.Harvest` → `HedgePlant.Harvest` → **RemoveMaze()**：
#     `harvest()` 在**宝藏上** = 收金币 + **抹掉整座迷宫**；在非宝藏树篱上 harvest 同样抹整座 ✓
#     ⇒ 想在原地连续吃多颗，**绝不能中途 harvest** ✗
#     旧实现「先 harvest 收第一颗、再 use_item 想复用」⇒ 那时迷宫已经没了 ⇒ 必然失败 ✓✓
#     （真机症状：每座只吃 1~2 颗、`复用第` 长期为 0、`复用后重建图仍走不到` 频繁 ✗）
#   * 站在宝藏上 `use_item(Items.Weird_Substance, sub)` → `RepositionTreasure()`：
#     立刻收金币（= 面积 × 2^(lv-1)）+ 200 tick 后把宝藏**随机搬到迷宫内另一格**，
#     并随机拆掉几面墙（每次约 0.26 面；8x8 的 49 面内墙约 190 次复用拆光 ⇒ 越刷越短）
#     ⇒ 这就是"复用"：上限 300 次，之后 use_item 不再给金币 ⇒ 最后 harvest 收尾（第 301 颗）✓
#     （与官方排行榜口径一致：`Maze = 301 × 32,768` / `Maze_Single = 301 × 2,048` ✓）
MZ_REUSE_MAX = 300         # 每座迷宫最多复用 300 次（源码 MAX_TREASURE_FACTOR=301）✓
# 单座寿命/班次时长（秒）。**240 秒**（v4，2026-11-02 按真机数据调）：
#   真机实测（新代码）w12 寿命 avg 141.8s、w16 avg 133.8s，且 66/69、71/80 座**顶满 140s cap**
#   ⇒ cap 是当时产量的唯一瓶颈。每颗综合成本 ≈ 2.3~2.4s（含每颗一次距离场 + 走位，建图 ~8s/座）
#   ⇒ cap 240 时每座 ≈ (240-8)/2.35 ≈ 95~100 颗（比 53~58 颗 +70%），建图成本进一步摊薄 ✓
#   班次 520s ≈ 2 座寿命：R1/R2 上主机采购间隔变长，但金币到目标就停 ⇒ 可接受 ✓
#   ⚠ 迷宫边界封闭 ⇒ 别的副机从 (0,0) 出生后要去东/北边地块时可能被迷宫挡住。
#     2026-11-01 已修掉两个跨产线根因：① stage_w16 的轮作切片不再切进 maze1 ✓
#     ② `util.go_to` 改成**有界**（撞墙 8 步就放弃并打印 `[ut] !! go_to 走不到`，不再永久卡死）✓
#   ⇒ 长寿命是安全的：就算被挡，副机最多损失 ~十几秒，不会把全班/整台机器卡死 ✓
#   （判据：下一跑里 `[ut] !! go_to 走不到` 应很少；若频繁出现 ⇒ 说明还有路径穿迷宫区，回报）
MZ_LIFE_SEC = 240.0        # 单座迷宫寿命上限（秒）：按真机数据调（140 时 w12/w16 常态顶满）
MZ_SHIFT_SEC = 520.0       # 副机班次时间上限（秒）：约 2 座寿命 ⇒ 班次有界（R2）✓
MZ_LIFE_CAP = [240.0]      # 本次调用允许的单座寿命（maze_worker 按班次剩余时间收紧它）✓


def maze_walk_bounds(side, max_steps):
	# 走遍迷宫（右手法则在无环迷宫里会遍历全部通道），返回访问格的包围盒
	#   用途：**反推迷宫真实落点** —— 这是探针唯一可靠的办法
	idx = 1
	steps = 0
	minx = get_pos_x()
	maxx = minx
	miny = get_pos_y()
	maxy = miny
	while steps < max_steps:
		r = (idx + 1) % 4
		if can_move(MZ_DIRS[r]):
			idx = r
			move(MZ_DIRS[idx])
		elif can_move(MZ_DIRS[idx]):
			move(MZ_DIRS[idx])
		else:
			idx = (idx - 1) % 4
			if can_move(MZ_DIRS[idx]):
				move(MZ_DIRS[idx])
			else:
				idx = (idx + 2) % 4
				move(MZ_DIRS[idx])
		if get_pos_x() < minx:
			minx = get_pos_x()
		if get_pos_x() > maxx:
			maxx = get_pos_x()
		if get_pos_y() < miny:
			miny = get_pos_y()
		if get_pos_y() > maxy:
			maxy = get_pos_y()
		steps = steps + 1
	return minx, maxx, miny, maxy


def maze_build_point(x0, y0, side):
	# 想让迷宫左上角正好落在区域左上角 (x0,y0)，无人机该站哪 —— 用探针量到的偏移反推
	#   偏移未知时返回 0（调用方先跑探针）
	if MZ_ANCHOR[0] == 999:
		return 0, 0
	bx = x0 - MZ_ANCHOR[0]
	by = y0 - MZ_ANCHOR[1]
	if bx < 0:
		bx = bx + get_world_size()
	if by < 0:
		by = by + get_world_size()
	return bx, by


def maze_anchor_probe(side):
	# 建一座迷宫 → 走遍它求包围盒 → 算出 (左上角 - 建造点) 的偏移并缓存 ✓
	# 选**棋盘中央**当探针点：离边界足够远，迷宫不会被棋盘环绕裁剪
	#   （被裁剪时包围盒宽度会小于 side-1 ⇒ 直接判失败、不写缓存，宁可不写也不写错）
	sub = maze_substance(side)
	if num_items(Items.Weird_Substance) < sub:
		return 0
	ws = get_world_size()
	px = ws // 2
	py = ws // 2
	util.go_to(px, py)
	e = get_entity_type()
	if e != None and e != Entities.Grass:
		if can_harvest():
			harvest()
	if get_entity_type() != Entities.Bush:
		plant(Entities.Bush)
	use_item(Items.Weird_Substance, sub)
	e = get_entity_type()
	if e != Entities.Hedge and e != Entities.Treasure:
		print("[mza] 探针：迷宫没长出来（脚下是", e, "）⇒ 放弃")
		return 0
	minx, maxx, miny, maxy = maze_walk_bounds(side, side * side * 6 + 400)
	if maxx - minx != side - 1 or maxy - miny != side - 1:
		print("[mza] 探针：包围盒", maxx - minx + 1, "x", maxy - miny + 1,
			"≠ 边长", side, "⇒ 疑似被棋盘环绕裁剪，不写缓存")
		maze_escape()
		return 0
	MZ_ANCHOR[0] = minx - px
	MZ_ANCHOR[1] = miny - py
	MZ_ANCHOR_LV[0] = num_unlocked(Unlocks.Mazes)
	print("[mza] 锚点探针：建造点", px, py, "⇒ 迷宫左上角", minx, miny,
		"| 偏移", MZ_ANCHOR[0], MZ_ANCHOR[1], "| 边长", side,
		"| 迷宫等级", MZ_ANCHOR_LV[0])
	maze_escape()
	return 1


# ============================================================
# 仙人掌（骨头线的前半）：排好序的方块一刀收 = n^2 x 等级倍率
# ============================================================

CZ_DIAG = [0]
CZ_DIAG2 = [0]          # 诊断：每 4 轮报一次方块状态（真机曾出现「一条 [cz] 都没有」✗）


def cactus_count(x0, y0, n):
	c = 0
	i = 0
	while i < n:
		j = 0
		while j < n:
			util.go_to(x0 + i, y0 + j)
			if get_entity_type() == Entities.Cactus:
				c = c + 1
			j = j + 1
		i = i + 1
	return c


def cactus_mature_count(x0, y0, n):
	c = 0
	i = 0
	while i < n:
		j = 0
		while j < n:
			util.go_to(x0 + i, y0 + j)
			if get_entity_type() == Entities.Cactus:
				if can_harvest():
					c = c + 1
			j = j + 1
		i = i + 1
	return c
CZ_LEVEL = [1]

# ---- 仙人掌排序 v2 的内存快照（**移植自 cactus_farm.py 的已验证实现**）----
#   行主序下标：idx = row * n + col，row 沿 y（北）、col 沿 x（东）
#   「升序 + 行主序」天然满足文档的「N/E 邻居 >= 自己、S/W 邻居 <= 自己」✓
#   ⚠ R8：模块全局在副机里是**各自一份的初始值**（无共享内存）⇒ 每架用自己的快照 ✓
CZ_GRID = []           # n*n 格尺寸快照（行主序）
CZ_WANT = []           # 升序目标排列
CZ_SWAPS = [0]         # 本次排序执行的相邻交换数（诊断）
CZ_FALLBACK = [0]      # 回退到局部修复循环的次数（诊断：并行互踩的指示器）


def cactus_cost():
	# 种一株的价钱（docs 没写；用 get_cost 问，别写死）
	c = get_cost(Entities.Cactus)
	if c == None:
		return 0
	for k in c:
		if k == Items.Pumpkin:
			return c[k]
	return 0


def cactus_levels():
	lv = num_unlocked(Unlocks.Cactus)
	if lv < 1:
		lv = 1
	return lv


def cactus_mature_square(x0, y0, n):
	# 全片都是成熟仙人掌？—— 收割门（docs：必须**整片**有序且成熟才会连锁）
	i = 0
	while i < n:
		j = 0
		while j < n:
			util.go_to(x0 + i, y0 + j)
			if get_entity_type() != Entities.Cactus:
				return 0
			if can_harvest() == False:
				return 0
			j = j + 1
		i = i + 1
	return 1


def cactus_plant_square(x0, y0, n):
	# 补种：空地/草 ⇒ 翻土 + 种（**付不起就不种** —— R7）
	planted = 0
	if num_unlocked(Unlocks.Cactus) <= 0:
		return 0
	i = 0
	while i < n:
		j = 0
		while j < n:
			util.go_to(x0 + i, y0 + j)
			e = get_entity_type()
			if e != Entities.Cactus:
				# ⚠⚠ 真机症状（用户 2026-10-08）：「仙人掌田里会出现其它作物占据位置，
				#    导致无法正常收获」—— 根因是 plant() 在**非空格**上会**静默失败**
				#    （返回 False、不报错 ✗），于是被占的格子永远种不上仙人掌 ⇒
				#    整片永远凑不齐「全成熟」⇒ cactus_shift 每轮都在成熟检查处 continue ✗✗
				#    ⇒ 先把占位作物收掉再翻土（正在长的收不了就下轮再来，自愈 ✓）
				if e != None:
					if can_harvest():
						harvest()
					else:
						j = j + 1
						continue
				e2 = get_entity_type()
				if e2 == None or e2 == Entities.Grass:
					if num_items(Items.Pumpkin) > cactus_cost():
						if get_ground_type() != Grounds.Soil:
							till()
						plant(Entities.Cactus)
						planted = planted + 1
			j = j + 1
		i = i + 1
	return planted


# ============================================================
# 仙人掌排序（v2：先看后动 + 目标驱动搬运）
#
# 为什么重写（真机 2026-11-01 复现）：
#   旧实现 = 逐行 gnome + 逐列 gnome 的两阶段排序。它**单机**是能排好的
#   （docs Hint 1「行排好再排列不会破坏行序」；本机用 mock 穷举 3x3 全排列 + 2 万次随机 6x6
#    验证过：排完 0 次无序 ✓），问题出在**并行**与**没有收割前核验**：
#   ① 真机日志反复出现 `[cz] !! 排序步数超上限`。单机 gnome 排 6 个数最多 ~36 步，
#      而 guard 是 144 ⇒ 触发只可能是「同一片地被 2~4 架副机同时 swap」互踩 ✗
#      （根因在 full_run 的 ACTIVEB 对账启发式，已由 Lead 另行修复）。
#   ② 更致命：旧流程排完**不核验有序**（只查成熟）⇒ guard 提前放弃后照样收割，
#      连锁只扩散一部分 ⇒ 一刀只收到零头（这正是「已种满已熟、库存却涨得很慢」✗）。
#   ⇒ 改用 cactus_farm.py（真机长期验证）的做法：**读快照 → 内存算出升序目标 →
#     把每个值沿 L 形路径直接推到它的最终下标**。
#   ⇒ 收敛性可证：目标下标 idx 之前的位置**永不参与搬运**（见 cactus_push_value），
#     每个位置最多写一次 ⇒ 一次排序最多 n*n 次搬运 ⇒ 必然结束 ✓
#   并行互踩时快照会失真 ⇒ 排序后**现读核验**，不过就不收割（宁可这轮白等，
#   也不收半片：一刀的产值 = 整片面积² × 等级倍率，半收等于扔掉 90%+ ✗）；
#   核验不过先回退 `cactus_repair_square`（每步现读现换，势能证明必然收敛）。
# ============================================================


def cactus_buf(n):
	# 按 n*n 准备两块内存快照（只增不减：一次运行里 n 不变，多出的尾巴不会被读 ✓）
	want = n * n
	while len(CZ_GRID) < want:
		append(CZ_GRID, 0)
	while len(CZ_WANT) < want:
		append(CZ_WANT, 0)


def cactus_read_square(x0, y0, n):
	# 蛇形读一遍：把 n*n 格尺寸按**行主序**写进 CZ_GRID，返回读不到尺寸的格数
	#   （参照 cactus_farm.py 的 read_grid：蛇形只省走位，写入下标仍是行主序 ✓）
	empty = 0
	row = 0
	while row < n:
		col = 0
		while col < n:
			c = col
			if row % 2 == 1:
				c = n - 1 - col
			util.go_to(x0 + c, y0 + row)
			v = measure()
			if v == None:
				empty = empty + 1
				v = 0
			CZ_GRID[row * n + c] = v
			col = col + 1
		row = row + 1
	return empty


def cactus_mem_swap(n, a, b):
	t = CZ_GRID[a]
	CZ_GRID[a] = CZ_GRID[b]
	CZ_GRID[b] = t


def cactus_push_value(x0, y0, n, src, dst):
	# 把 src 处的值用**相邻交换**推到 dst：先沿行对齐列、再沿列对齐行。
	# 路径安全性（照抄 cactus_farm.py / main.py 已验证的论证）：
	#   dst 是行主序下标 idx，src 只在 idx+1 之后找 ⇒ src > idx
	#   ⇒ 路径上经过的每一格行主序下标都 > idx ⇒ **绝不会碰已归位的前半段** ✓
	#   ⇒ 每个位置最多推一次、推完永久正确 ⇒ 排序必然收敛（最多 n*n 次搬运）✓
	# ⚠ swap() **不移动无人机** ⇒ 必须 swap 之后紧跟同方向 move（真机实测踩过 ✗）
	sx = src % n
	sy = src // n
	dx = dst % n
	dy = dst // n
	util.go_to(x0 + sx, y0 + sy)
	while sx != dx:
		if sx < dx:
			swap(East)
			move(East)
			cactus_mem_swap(n, sy * n + sx, sy * n + sx + 1)
			sx = sx + 1
		else:
			swap(West)
			move(West)
			cactus_mem_swap(n, sy * n + sx, sy * n + sx - 1)
			sx = sx - 1
		CZ_SWAPS[0] = CZ_SWAPS[0] + 1
	while sy != dy:
		if sy < dy:
			swap(North)
			move(North)
			cactus_mem_swap(n, sy * n + sx, (sy + 1) * n + sx)
			sy = sy + 1
		else:
			swap(South)
			move(South)
			cactus_mem_swap(n, sy * n + sx, (sy - 1) * n + sx)
			sy = sy - 1
		CZ_SWAPS[0] = CZ_SWAPS[0] + 1


def cactus_sorted_mem(n):
	# 只用内存快照判断「行主序单调不减」：行主序单调 ⇒ 行内朝东不减、列内朝北不减 ✓
	k = 1
	while k < n * n:
		if CZ_GRID[k] < CZ_GRID[k - 1]:
			return 0
		k = k + 1
	return 1


def cactus_sort_square(x0, y0, n):
	# 排序 v2：**先看后动** —— 蛇形读一遍 → 纯内存插入排序算目标 → 只执行必要的相邻交换
	#   参照 cactus_farm.py（真机验证过）的 sort_region：目标驱动比逐行/逐列冒泡省 1/3 走位，
	#   而且收敛性可证（见 cactus_push_value 的注释）✓
	cactus_buf(n)
	empty = cactus_read_square(x0, y0, n)
	if empty > 0:
		print("[cz] !! 排序跳过：方块里有", empty, "格读不到尺寸（空位/未熟）")
		return 0
	tiles = n * n
	k = 0
	while k < tiles:
		CZ_WANT[k] = CZ_GRID[k]
		k = k + 1
	# 纯内存插入排序（36 个元素、零行动开销）
	i = 1
	while i < tiles:
		v = CZ_WANT[i]
		j = i - 1
		done = 0
		while j >= 0 and done == 0:
			if CZ_WANT[j] > v:
				CZ_WANT[j + 1] = CZ_WANT[j]
				j = j - 1
			else:
				done = 1
		CZ_WANT[j + 1] = v
		i = i + 1
	# 逐位置归位：只在**还没归位的后半段**（scan > idx）找最近的持有者 ✓
	CZ_SWAPS[0] = 0
	idx = 0
	guard = 0
	while idx < tiles:
		guard = guard + 1
		if guard > tiles * 4:
			# 保险丝：理论上 idx 只前进 tiles 次（每个位置最多写一次），4 倍冗余永不触发 ✓
			print("[cz] !! 排序搬运超上限 ⇒ 放弃本次排序（保险丝 ✓）")
			return 0
		want = CZ_WANT[idx]
		if CZ_GRID[idx] != want:
			best = -1
			best_d = 999
			scan = idx + 1
			while scan < tiles:
				if CZ_GRID[scan] == want:
					d = abs(scan // n - idx // n) + abs(scan % n - idx % n)
					if d < best_d:
						best_d = d
						best = scan
				scan = scan + 1
			if best >= 0:
				cactus_push_value(x0, y0, n, best, idx)
		idx = idx + 1
	if cactus_sorted_mem(n) == 0:
		print("[cz] !! 排序后内存快照仍无序（不该发生）⇒ 放弃本次排序")
		return 0
	return 1


def cactus_repair_pass(x0, y0, n):
	# 局部修复一遍（main.py v1 的做法）：逐格把 E/N 邻居里的逆序 swap 掉。
	# **终止性可证**：势能 P = Σ 尺寸 × (x + y)。每次修复性交换：
	#   East 交换（e < me）⇒ P 增加 me-e ≥ 1；North 交换（nv < me）⇒ P 增加 me-nv ≥ 1 ✓
	#   而 P 有上界 ⇒ 交换总数有限 ⇒ 反复扫描必然收敛 ✓
	# 它是 v2 的**兜底**：并行副机互踩时 v2 的快照会失真，而这一遍每次都是现读现换 ✓
	# 返回本遍交换次数；-1 = 读到空位（放弃）
	swaps = 0
	row = 0
	while row < n:
		col = 0
		while col < n:
			util.go_to(x0 + col, y0 + row)
			me = measure()
			if me == None:
				return -1
			if col + 1 < n:
				e = measure(East)
				if e == None:
					return -1
				if e < me:
					swap(East)
					me = e
					swaps = swaps + 1
			if row + 1 < n:
				nv = measure(North)
				if nv == None:
					return -1
				if nv < me:
					swap(North)
					me = nv
					swaps = swaps + 1
			col = col + 1
		row = row + 1
	return swaps


def cactus_repair_square(x0, y0, n):
	# 反复做局部修复，直到「一整遍没有交换」= 全盘有序（硬上限只当保险丝）
	passes = 0
	while passes < 200:
		s = cactus_repair_pass(x0, y0, n)
		if s < 0:
			print("[cz] !! 局部修复读到空位 ⇒ 放弃本次排序")
			return 0
		passes = passes + 1
		if s == 0:
			return 1
	print("[cz] !! 局部修复步数超上限 ⇒ 放弃本次排序（保险丝 ✓）")
	return 0


def cactus_verify_square(x0, y0, n):
	# 收割前**紧挨着**做的一次核验（现读，不信任何内存快照）：
	#   整片都是成熟仙人掌 + 文档口径的有序（每格的 E/N 邻居 >= 自己）✓
	#   ⚠ 不能只查「行主序全序列单调」：那比文档要求**更强**，
	#     局部修复收敛出的合法有序盘（如 0 9 9 / 1 9 9）会被误判成没排好 ✗
	#   ⇒ 只有它能通过才收割 —— 并行副机把地改乱时宁可这轮不收（半收 = 扔掉 90%+ ✗）
	row = 0
	while row < n:
		col = 0
		while col < n:
			util.go_to(x0 + col, y0 + row)
			if get_entity_type() != Entities.Cactus:
				return 0
			if can_harvest() == False:
				return 0
			me = measure()
			if me == None:
				return 0
			if col + 1 < n:
				e = measure(East)
				if e == None:
					return 0
				if e < me:
					return 0
			if row + 1 < n:
				nv = measure(North)
				if nv == None:
					return 0
				if nv < me:
					return 0
			col = col + 1
		row = row + 1
	return 1



def cactus_shift(x0, y0, w, h, cycles, my_world, roles):
	# 副机/主机入口（统一契约 7 参）。一轮 = 补种 → 等熟 → 排序 → 一刀
	n = w
	if h < n:
		n = h
	if num_unlocked(Unlocks.Cactus) <= 0:
		return 0
	got = 0
	c = 0
	while c < cycles:
		if world_changed(my_world) == 1:
			print("[cz] 世界从", my_world, "变成", get_world_size(), "⇒ 下岗")
			return got
		c = c + 1
		before = num_items(Items.Cactus)
		cactus_plant_square(x0, y0, n)
		# 等成熟（最多 60 秒；期间继续补种）
		t0 = get_time()
		ok = 0
		while get_time() - t0 < 60.0:
			if cactus_mature_square(x0, y0, n) == 1:
				ok = 1
				break
			cactus_plant_square(x0, y0, n)
		if ok == 0:
			continue
		CZ_DIAG2[0] = CZ_DIAG2[0] + 1
		if CZ_DIAG2[0] % 4 == 1:
			print("[cz] 第", CZ_DIAG2[0], "轮 | 方块", n, "x", n,
				"| 已种", cactus_count(x0, y0, n), "/", n * n,
				"| 已熟", cactus_mature_count(x0, y0, n),
				"| 仙人掌", num_items(Items.Cactus), "| 南瓜", num_items(Items.Pumpkin))
		print("[cz] 轮", CZ_DIAG2[0], "| 方块", n, "x", n,
			"| 已种", cactus_count(x0, y0, n), "/", n * n,
			"| 已熟", cactus_mature_count(x0, y0, n),
			"| 仙人掌", num_items(Items.Cactus))
		# ---- 排序：v2 目标驱动；失败回退局部修复；最后必须**现读核验**通过才收割 ----
		#   ⚠ 真机 2026-11-01 的根因：并行副机互踩 ⇒ 旧 gnome 两阶段在 guard 处提前放弃，
		#     于是「已种满已全熟」却只收部分面积。v2 的收敛可证；核验保证「收就收满」✓
		#   ⚠ 核验不过时**不收**：半片收割 = 把整片产值扔掉 90%+（且日志会假装"收了"✗）
		sok = cactus_sort_square(x0, y0, n)
		if sok == 0:
			CZ_FALLBACK[0] = CZ_FALLBACK[0] + 1
			print("[cz] 排序 v2 未收敛 ⇒ 回退局部修复（势能保证收敛 ✓）")
			sok = cactus_repair_square(x0, y0, n)
		if sok == 0:
			continue
		if cactus_verify_square(x0, y0, n) == 0:
			# 并行副机可能正在改同一片地 ⇒ 再修一遍（现读现换），仍不行就不收 ✓
			CZ_FALLBACK[0] = CZ_FALLBACK[0] + 1
			sok = cactus_repair_square(x0, y0, n)
			if sok == 0:
				continue
			if cactus_verify_square(x0, y0, n) == 0:
				print("[cz] !! 排序核验没通过 ⇒ 本轮不收割（防半收 ✓）")
				continue
		util.go_to(x0, y0)
		harvest()                          # 一刀连锁收掉整片 ✓
		gain = num_items(Items.Cactus) - before
		got = got + gain
		CZ_DIAG[0] = CZ_DIAG[0] + 1
		if CZ_DIAG[0] % 2 == 1:
			print("[cz] 第", CZ_DIAG[0], "刀 | 方块", n, "x", n, "| 本刀", gain,
				"（理论", n * n * n * n * (2 ** (cactus_levels() - 1)), "）",
				"| 累计", got, "| 仙人掌", num_items(Items.Cactus))
	return got


# ============================================================
# 满场迷宫相（独占；开关式，默认关 ✓）
# ============================================================

# 已启用（2026-10-08）：上游已稳（`[s16] 地里 胡萝卜 8 草 72 木 8` ✓、`[blk] DONE` 持续 ✓）
# 依据文档 mazes.md L5-9（满场配方）+ L14（金币 = 面积）+ L38（复用**不**增加单位物质金币 ✗）
# ⇒ 金币/物质 = 迷宫边长：w16 从 8（8x8 区）→ **16**（满场）✓✓ / w22 从 16 → **22** ✓
# ⚠ 关掉（2026-10-08）：maze_gold2.py 的实跑数据表明**满场迷宫是错方向** ✗
#   16x16 有 (16-1)^2 = **225 面墙**（32x32 是 961 面）⇒ 300 次复用**拆不完**
#   ⇒ 迷宫越刷越绕、BFS 走不到 ⇒ 真机实测 `本趟 512 金`（只吃 2 颗就重建）✗✗
#   而 8x8 只有 49 面墙 ⇒ 会被拆到全开、**越刷越顺** ✓✓
#   ⇒ 改用「多座 8x8 迷宫 + 每座自己的宝藏」的真并行形态 ✓
FULL_MAZE_ON = 0
FULL_MAZE_DIAG = [0]


def full_maze_ready():
	# 能不能开一趟满场迷宫：开关开着 + 迷宫已解锁 + 金币还没够 + 物质够本 ✓
	if FULL_MAZE_ON == 0:
		return 0
	if num_unlocked(Unlocks.Mazes) <= 0:
		return 0
	if num_items(Items.Gold) >= budget.gold_goal():
		return 0
	ws = get_world_size()
	sub = maze_substance(ws)
	if num_items(Items.Weird_Substance) < sub + budget.mazes_keep():
		return 0
	return 1


def full_maze_run(my_world):
	# 清场 → 满场迷宫 → **走完寿命**（建图一次 + 连续 use_item 复用 + 最后 harvest 抹掉）
	#   → 农场下一轮自己补种 ✓
	#   协议与 maze_life 相同（源码：use_item 收货+重定位，harvest 收货+RemoveMaze）✓
	ws = get_world_size()
	sub = maze_substance(ws)
	per = maze_gold(ws)
	if num_items(Items.Weird_Substance) < sub:
		return 0
	clear()                      # 整块棋盘归迷宫 ✓（clear = 全草地 + 无人机回 (0,0) ✓）
	# ⚠ clear() 之后脚下可能还有 Grass 实体 ⇒ plant(Bush) 会**静默失败**、
	#   随后 use_item(weird) 会变成给 Grass 施肥（物质白烧 ✗）⇒ 用统一的清格逻辑 ✓
	if mz_plant_bush() == 0:
		print("[fmz] !! 满场迷宫种不上灌木（脚下", get_entity_type(), "）⇒ 放弃")
		return 0
	use_item(Items.Weird_Substance, sub)
	e = get_entity_type()
	if e != Entities.Hedge and e != Entities.Treasure:
		print("[fmz] !! 满场迷宫没长出来（脚下", e, "）⇒ 放弃")
		return 0
	MZ_IN[0] = 1                         # 满场迷宫建好了 ✓
	MZ_LIFE_CAP[0] = MZ_LIFE_SEC
	got = maze_life(0, 0, ws, sub, per)  # 内部已收尾（harvest 抹迷宫）✓
	if get_entity_type() == Entities.Hedge or get_entity_type() == Entities.Treasure:
		maze_escape()                    # 兜底：还困在迷宫里 ⇒ 抹掉 ✓
	MZ_IN[0] = 0
	FULL_MAZE_DIAG[0] = FULL_MAZE_DIAG[0] + 1
	print("[fmz] 第", FULL_MAZE_DIAG[0], "趟 | 满场", ws, "x", ws, "（面积", ws * ws,
		"）| 本趟", got, "金 | gold", num_items(Items.Gold),
		"| weird", num_items(Items.Weird_Substance))
	return got


def maze_substance(side):
	# docs/game/unlocks/mazes.md：n 份奇异物质 ⇒ n x n 迷宫；**每升一级翻倍**（金币同时翻倍）
	amt = side
	lv = num_unlocked(Unlocks.Mazes)
	i = 1
	while i < lv:
		amt = amt * 2
		i = i + 1
	return amt


def maze_gold(side):
	# 宝藏 = 迷宫面积 x 等级倍率 ⇒ **金币/物质 = 边长**（与等级无关）
	amt = side * side
	lv = num_unlocked(Unlocks.Mazes)
	i = 1
	while i < lv:
		amt = amt * 2
		i = i + 1
	return amt


# ============================================================
# 迷宫建图（BFS 解法的基础）：墙掩码 + DFS 走图 + BFS 寻路
# ============================================================

MZ_MAP = []          # 每格的墙掩码：1=N 2=E 4=S 8=W
MZ_MARK = []         # DFS 访问标记
MZ_PARENT = []       # BFS 父节点
MZ_SIDE = [0]        # 这张图是哪张迷宫（边长）
MZ_IN = [0]          # **我们在不在迷宫里**（建成功置 1 ✓、抹掉置 0 ✓）
					 #   ⚠ 不能用「脚下是不是树篱」判断：复用后宝藏被收走 ⇒ 脚下不再是树篱 ✗
					 #     ⇒ 那会把每一次复用都误判成「不在迷宫里」✗✗（真机 `复用第: 0` ✓）
MZ_BIT = [1, 2, 4, 8]
MZ_DX = [0, 1, 0, -1]
MZ_DY = [1, 0, -1, 0]
# ---- 距离场缓存（v3，2026-11-01）----
# ⚠⚠ 为什么必须缓存：旧实现 `maze_walk_to_treasure` **每走一步都调一次 maze_bfs_dir**
#   ⇒ 每步都重算 64 格 BFS（约 2,000 tick）× 每颗 8~12 步 ⇒ **单颗几十游戏秒** ✗✗
#   真机实测（2026-11-01）：每座寿命 196s 只收 6.4 颗（min 3 / max 14）——就是它 ✓
#   改成「以宝藏为源、算一次距离场，之后每步只做一次下坡比较（~10 条语句）」✓
#   （maze_gold2.py 的 field_to 就是这个思路，真机验证过 ✓）
MZ_DIST = []         # 到当前目标的 BFS 距离；-1 = 未知/不可达
MZ_DQ = []           # BFS 队列（用下标走，边 append 边读）
MZ_FTX = [-1]        # 这张距离场是给哪个宝藏算的
MZ_FTY = [-1]
MZ_FSIDE = [0]
MZ_MAPGEN = [0]      # 地图世代：任一格墙图变化就 +1（让距离场失效 ✓）
MZ_FGEN = [-1]       # 距离场是基于哪个地图世代算的
# ---- 进区路线诊断（真机 2026-11-02 加：副机"没进区"时必须能一眼看出卡在哪）----
MZ_ROUTE_N = [0]     # mz_goto_best 本次用掉了几条路线（1~4；=4 且失败 ⇒ 全部被挡）
MZ_ROUTE_P = [0, 0]  # 最后一次尝试结束时卡住的位置
MZ_LOWD = [0]        # "物质不足/金币目标已到"的提前收工计数（用来节流打印，防刷屏）


def list_reset(lst, n, v):
	# 游戏语言没有 global ⇒ 一律**就地修改**列表，绝不重新赋值 ✓
	while len(lst) > 0:
		pop(lst)
	i = 0
	while i < n:
		append(lst, v)
		i = i + 1


def mz_ix(x, y, x0, y0, side):
	return (y - y0) * side + (x - x0)


def mz_xy(i, x0, y0, side):
	return x0 + i % side, y0 + i // side


def mz_in_region(x0, y0, side):
	# 当前坐标在不在迷宫区域内 —— **所有"把坐标换算成区域下标"的地方都先过这一关** ✓
	#   （本项目因 MZ_MAP 下标越界崩过 3 次：真机 `索引 88 超出了列表(64 项)的范围` ✗）
	x = get_pos_x()
	y = get_pos_y()
	if x < x0 or x >= x0 + side:
		return 0
	if y < y0 or y >= y0 + side:
		return 0
	return 1


def mz_valid(i, n):
	# 区域下标界检查（MZ_MAP / MZ_MARK / MZ_PARENT 共用）✓
	if i < 0:
		return 0
	if i >= n:
		return 0
	return 1


def mz_has_wall(i, d):
	# 第 i 格的 d 方向有没有墙（调用方先做界检查；这里再兜一次 ✓）
	if i < 0:
		return 0
	if i >= len(MZ_MAP):
		return 0
	if MZ_MAP[i] // MZ_BIT[d] % 2 == 1:
		return 1
	return 0


def mz_set_wall(x, y, d, x0, y0, side):
	# 把「(x,y) 的 d 方向是墙」**双向**写进 MZ_MAP（邻居的反方向一起写 ✓）
	#   为什么必须双向：只写一边会造出"单向通道" ⇒ BFS 能进去、却回不来 ⇒ 原地震荡 ✗
	#   为什么记墙永远安全：源码里墙只会"从有变无"（复用随机拆墙），边界墙永不拆
	#   ⇒ 地图只会越来越**保守**（多记墙 = 绕远路，但绝不让 BFS 穿墙）✓
	n = side * side
	i = mz_ix(x, y, x0, y0, side)
	if mz_valid(i, n) == 0:
		return
	MZ_MAPGEN[0] = MZ_MAPGEN[0] + 1      # 墙图变了 ⇒ 距离场缓存作废 ✓
	if mz_has_wall(i, d) == 0:
		MZ_MAP[i] = MZ_MAP[i] + MZ_BIT[d]
	jx = x + MZ_DX[d]
	jy = y + MZ_DY[d]
	if jx < x0 or jx >= x0 + side or jy < y0 or jy >= y0 + side:
		return
	j = mz_ix(jx, jy, x0, y0, side)
	if mz_valid(j, n) == 0:
		return
	od = (d + 2) % 4
	if mz_has_wall(j, od) == 0:
		MZ_MAP[j] = MZ_MAP[j] + MZ_BIT[od]


def mz_scan_here(x0, y0, side):
	# 站在迷宫内：量当前格四向墙，写进 MZ_MAP（**双向**）⇒ 返回墙掩码；-1 = 下标越界
	#   ⚠ 地图一变 ⇒ 距离场缓存必须作废（MZ_MAPGEN +1 ✓）
	x = get_pos_x()
	y = get_pos_y()
	n = side * side
	i = mz_ix(x, y, x0, y0, side)
	if mz_valid(i, n) == 0:
		return -1
	m = mz_probe_walls()
	MZ_MAP[i] = m
	d = 0
	while d < 4:
		jx = x + MZ_DX[d]
		jy = y + MZ_DY[d]
		if jx >= x0 and jx < x0 + side and jy >= y0 and jy < y0 + side:
			j = mz_ix(jx, jy, x0, y0, side)
			if mz_valid(j, n) == 1:
				od = (d + 2) % 4
				if m // MZ_BIT[d] % 2 == 1:
					if mz_has_wall(j, od) == 0:
						MZ_MAP[j] = MZ_MAP[j] + MZ_BIT[od]
				else:
					if mz_has_wall(j, od) == 1:
						MZ_MAP[j] = MZ_MAP[j] - MZ_BIT[od]
		d = d + 1
	MZ_MAPGEN[0] = MZ_MAPGEN[0] + 1
	return m


def maze_field(tx, ty, x0, y0, side):
	# 以宝藏**(tx,ty) 为源**做一次 BFS，把距离写进 MZ_DIST（-1 = 不可达）
	#   之后每走一步只要"挑一个距离小 1 的邻居"（约 10 条语句）⇒ 不再每步都整张 BFS ✓✓
	#   返回 1 = 当前位置在距离场里可达；0 = 不可达/目标越界
	n = side * side
	if tx < x0 or tx >= x0 + side or ty < y0 or ty >= y0 + side:
		return 0
	ti = mz_ix(tx, ty, x0, y0, side)
	if mz_valid(ti, n) == 0:
		return 0
	list_reset(MZ_DIST, n, -1)
	list_reset(MZ_DQ, 0, 0)
	MZ_DIST[ti] = 0
	append(MZ_DQ, ti)
	MZ_FTX[0] = tx
	MZ_FTY[0] = ty
	MZ_FSIDE[0] = side
	MZ_FGEN[0] = MZ_MAPGEN[0]
	head = 0
	while head < len(MZ_DQ):
		cur = MZ_DQ[head]
		head = head + 1
		cx, cy = mz_xy(cur, x0, y0, side)
		nd = MZ_DIST[cur] + 1
		d = 0
		while d < 4:
			if MZ_MAP[cur] // MZ_BIT[d] % 2 == 0:
				jx = cx + MZ_DX[d]
				jy = cy + MZ_DY[d]
				if jx >= x0 and jx < x0 + side and jy >= y0 and jy < y0 + side:
					j = mz_ix(jx, jy, x0, y0, side)
					if MZ_DIST[j] < 0:
						MZ_DIST[j] = nd
						append(MZ_DQ, j)
			d = d + 1
	si = mz_ix(get_pos_x(), get_pos_y(), x0, y0, side)
	if mz_valid(si, n) == 0:
		return 0
	if MZ_DIST[si] < 0:
		return 0
	return 1


def mz_field_step(x0, y0, side):
	# 沿距离场下坡：返回朝宝藏的下一步方向；-1 = 没得走（场坏了），-2 = 已站在目标上
	n = side * side
	si = mz_ix(get_pos_x(), get_pos_y(), x0, y0, side)
	if mz_valid(si, n) == 0:
		return -1
	if MZ_DIST[si] < 0:
		return -1
	if MZ_DIST[si] == 0:
		return -2
	sx, sy = mz_xy(si, x0, y0, side)
	bd = MZ_DIST[si]
	best = -1
	d = 0
	while d < 4:
		if MZ_MAP[si] // MZ_BIT[d] % 2 == 0:
			jx = sx + MZ_DX[d]
			jy = sy + MZ_DY[d]
			if jx >= x0 and jx < x0 + side and jy >= y0 and jy < y0 + side:
				j = mz_ix(jx, jy, x0, y0, side)
				if mz_valid(j, n) == 1:
					if MZ_DIST[j] >= 0:
						if MZ_DIST[j] < bd:
							bd = MZ_DIST[j]
							best = d
		d = d + 1
	return best


def mz_field_valid(tx, ty, x0, y0, side):
	# 距离场缓存还有效吗：目标没换 + 边长/地图世代都没变 + 当前位置在场里 ✓
	if MZ_FTX[0] != tx:
		return 0
	if MZ_FTY[0] != ty:
		return 0
	if MZ_FSIDE[0] != side:
		return 0
	if MZ_FGEN[0] != MZ_MAPGEN[0]:
		return 0
	n = side * side
	si = mz_ix(get_pos_x(), get_pos_y(), x0, y0, side)
	if mz_valid(si, n) == 0:
		return 0
	if MZ_DIST[si] < 0:
		return 0
	return 1


def mz_goto(x, y, limit):
	# **有界**走位（空地上用；迷宫里绝对不能用 util.go_to ——
	#   它是 `while pos != target: move(...)` 的**无界**循环，撞墙时 move 只返回 False ⇒ 永久空转 ✗）
	steps = 0
	while steps < limit:
		cx = get_pos_x()
		cy = get_pos_y()
		if cx == x and cy == y:
			return 1
		moved = 0
		if cx != x:
			d = 1
			if cx > x:
				d = 3
			if can_move(MZ_DIRS[d]) == 1:
				move(MZ_DIRS[d])
				moved = 1
		if moved == 0:
			if cy != y:
				d = 0
				if cy > y:
					d = 2
				if can_move(MZ_DIRS[d]) == 1:
					move(MZ_DIRS[d])
					moved = 1
		if moved == 0:
			return 0
		steps = steps + 1
	return 0


def mz_goto_axis(d, n):
	# 朝 d 方向走 n 步（每步 can_move 检查；碰壁立刻停 ⇒ 有界）✓ 返回实际走了几步
	ws = get_world_size()
	got = 0
	i = 0
	while i < ws:
		if i >= n:
			break
		if can_move(MZ_DIRS[d]) == 0:
			break
		move(MZ_DIRS[d])
		got = got + 1
		i = i + 1
	return got


def mz_goto_route(bx, by, xsign, yfirst, limit):
	# 一种「从当前位置去建图点」的路线：先走一条轴、再走另一条轴；x 方向可以正向(E)/绕远(West)
	#   ⚠ 多座迷宫并存时（w16 两座 / w22 四座），直线路会被**邻区迷宫**挡住 ⇒ 必须能换路线 ✓
	ws = get_world_size()
	t = 0
	while t < limit:
		t = t + 1
		cx = get_pos_x()
		cy = get_pos_y()
		if cx == bx and cy == by:
			return 1
		moved = 0
		if yfirst == 1:
			if cy != by:
				d = 0
				if cy > by:
					d = 2
				if can_move(MZ_DIRS[d]) == 1:
					move(MZ_DIRS[d])
					moved = 1
			if moved == 0 and cx != bx:
				if xsign == 1:
					n = (bx - cx + ws) % ws
					d = 1
				else:
					n = (cx - bx + ws) % ws
					d = 3
				if mz_goto_axis(d, n) > 0:
					moved = 1
		else:
			if cx != bx:
				if xsign == 1:
					n = (bx - cx + ws) % ws
					d = 1
				else:
					n = (cx - bx + ws) % ws
					d = 3
				if mz_goto_axis(d, n) > 0:
					moved = 1
			if moved == 0 and cy != by:
				d = 0
				if cy > by:
					d = 2
				if can_move(MZ_DIRS[d]) == 1:
					move(MZ_DIRS[d])
					moved = 1
		if moved == 0:
			return 0
	return 0


def mz_goto_best(bx, by):
	# 去建图点：依次试 4 种路线（绕邻区迷宫）。起点在死路里时返回 0，让调用方放弃本轮 ✓
	# ⚠ 顺序 = **先 y 后 x**：w16 里 maze0 横在 (6..13, 0..7)，"先 x 走 y=0" 会穿 maze0 的
	#   建造区（两架迷宫副机同批出发时可能正好被建起来的 maze0 关在里面 ✗）；
	#   而"先沿 x=0 走到 y、再横向走"对 w16/w22 的 4 个迷宫区都不会穿别人正在建的区 ✓
	#   真机 2026-11-02：spawn 点 (0,0) 出来时 y 可能在南瓜方块里（植物不挡路 ✓），
	#   但若"先 x"会撞上 maze0 的树篱 ⇒ 必须 y 先 ✓
	# 诊断：MZ_ROUTE_N = 用了几条路线（4 = 全试过仍失败）；MZ_ROUTE_P = 最后卡住的位置 ✓
	n = get_world_size()
	limit = n * n
	MZ_ROUTE_N[0] = 0
	MZ_ROUTE_P[0] = get_pos_x()
	MZ_ROUTE_P[1] = get_pos_y()
	MZ_ROUTE_N[0] = 1
	if mz_goto_route(bx, by, 1, 1, limit) == 1:
		return 1
	MZ_ROUTE_P[0] = get_pos_x()
	MZ_ROUTE_P[1] = get_pos_y()
	MZ_ROUTE_N[0] = 2
	if mz_goto_route(bx, by, -1, 1, limit) == 1:
		return 1
	MZ_ROUTE_P[0] = get_pos_x()
	MZ_ROUTE_P[1] = get_pos_y()
	MZ_ROUTE_N[0] = 3
	if mz_goto_route(bx, by, 1, 0, limit) == 1:
		return 1
	MZ_ROUTE_P[0] = get_pos_x()
	MZ_ROUTE_P[1] = get_pos_y()
	MZ_ROUTE_N[0] = 4
	if mz_goto_route(bx, by, -1, 0, limit) == 1:
		return 1
	MZ_ROUTE_P[0] = get_pos_x()
	MZ_ROUTE_P[1] = get_pos_y()
	return 0


def mz_probe_walls():
	# 站在一格上探 4 向：走不动 = 有墙
	m = 0
	i = 0
	while i < 4:
		if can_move(MZ_DIRS[i]) == 0:
			m = m + MZ_BIT[i]
		i = i + 1
	return m


def maze_map_walk(x0, y0, side):
	# DFS 走遍迷宫记墙（迭代式 + 栈回溯，全程用 move ✓）
	#   自愈原则（移植 maze_gold2.py，真机验证）：
	#     * `move()` 失败 ⇒ **双向记墙**并把栈弹回去，**绝不假设走成功**
	#       （否则栈顶=邻居、现实还在原地 ⇒ 之后每格都量错 ⇒ 整张图全错 ✗✗）
	#     * **必须真的走满 side² 格**才返回 1；否则地图不完整 ⇒ BFS 会穿墙
	#       ⇒ 返 0，让调用方走「拆掉重建」那条路 ✓
	sx = get_pos_x()
	sy = get_pos_y()
	if sx < x0 or sx >= x0 + side or sy < y0 or sy >= y0 + side:
		# ⚠ 建图起点必须在区域内：否则下标越界（mock 实测 IndexError ✗）
		#   这通常意味着**锚点补偿没对上**（迷宫落到区域外了）⇒ 当成失败上报，
		#   让调用方走「拆掉重建」那条路 ✓（而不是以越界崩溃的形式炸掉整轮 ✗）
		print("[mz] !! 建图起点", sx, sy, "不在区域", x0, y0, side, "内 ⇒ 跳过")
		return 0
	n = side * side
	list_reset(MZ_MAP, n, 0)
	list_reset(MZ_MARK, n, 0)
	MZ_MAPGEN[0] = MZ_MAPGEN[0] + 1      # 新图 ⇒ 旧距离场作废 ✓
	MZ_SIDE[0] = side
	st = []
	append(st, mz_ix(sx, sy, x0, y0, side))
	visited = 0
	steps = 0
	limit = n * 8 + 400
	while len(st) > 0:
		if steps > limit:
			print("[mz] !! 建图步数超上限", limit, "（已走", visited, "/", n, "格）⇒ 判失败")
			MZ_IN[0] = 0
			return 0
		steps = steps + 1
		cur = st[len(st) - 1]
		if MZ_MARK[cur] == 0:
			if mz_scan_here(x0, y0, side) < 0:
				MZ_IN[0] = 0
				return 0
			MZ_MARK[cur] = 1
			visited = visited + 1
		cx, cy = mz_xy(cur, x0, y0, side)
		nxt = -1
		d = 0
		while d < 4:
			if MZ_MAP[cur] // MZ_BIT[d] % 2 == 0:
				jx = cx + MZ_DX[d]
				jy = cy + MZ_DY[d]
				if jx >= x0 and jx < x0 + side and jy >= y0 and jy < y0 + side:
					j = mz_ix(jx, jy, x0, y0, side)
					if MZ_MARK[j] == 0:
						nxt = d
						d = 4
			d = d + 1
		if nxt >= 0:
			# 先压栈、再走；**走失败就弹回去并记墙**（绝不假设成功 ✓）
			append(st, mz_ix(cx + MZ_DX[nxt], cy + MZ_DY[nxt], x0, y0, side))
			if move(MZ_DIRS[nxt]) == 0:
				pop(st)
				mz_set_wall(cx, cy, nxt, x0, y0, side)
			else:
				e2 = get_entity_type()
				if e2 != Entities.Hedge and e2 != Entities.Treasure:
					# 走出了迷宫（区域/锚点不对，或边界破了）⇒ 退回来并记墙，
					# 绝不把区域外的空地也记成"迷宫通道" ✓
					pop(st)
					move(MZ_DIRS[(nxt + 2) % 4])
					mz_set_wall(cx, cy, nxt, x0, y0, side)
		else:
			pop(st)
			if len(st) > 0:
				back = st[len(st) - 1]
				bx, by = mz_xy(back, x0, y0, side)
				d = 0
				while d < 4:
					if cx + MZ_DX[d] == bx and cy + MZ_DY[d] == by:
						if move(MZ_DIRS[d]) == 0:
							# 回退都走不动 ⇒ 现实与地图矛盾（被别的东西占了/墙被加回来了）
							# ⇒ 记墙并判失败，交给调用方重建整张图 ✓
							mz_set_wall(cx, cy, d, x0, y0, side)
							MZ_IN[0] = 0
							return 0
						d = 4
					d = d + 1
	if visited < n:
		print("[mz] !! 建图只走了", visited, "/", n, "格 ⇒ 地图不完整（区域/锚点不对）")
		MZ_IN[0] = 0
		return 0
	# ✅ 建图成功 ⇒ 我们**确实在迷宫里** ✓（统一在这一处置位：
	#   所有建图调用点（maze_shift / full_maze_run / 探针）都会经过这里 ✓）
	MZ_IN[0] = 1
	return 1


def maze_bfs_dir(tx, ty, x0, y0, side):
	# 用已知墙图 BFS：返回「朝宝藏走的下一步方向」；-1 = 走不到，-2 = 已经站在目标上
	n = side * side
	if tx < x0 or tx >= x0 + side or ty < y0 or ty >= y0 + side:
		return -1
	sx = get_pos_x()
	sy = get_pos_y()
	si = mz_ix(sx, sy, x0, y0, side)
	ti = mz_ix(tx, ty, x0, y0, side)
	# ⚠⚠ 真机越界实录（2026-10-27 第三次）：`索引 88 超出了列表(64 项)的范围` ✗
	#   无人机**站在区域外**时 si 越界（ti 早就有界检查 ✓，si 漏了 ✗）
	#   ⇒ 纪律：**凡是把"当前坐标"换算成区域下标，一律先界检查** ✓（这是第三处，全部补齐）
	if si < 0 or si >= n:
		return -1
	if ti < 0 or ti >= n:
		return -1
	if si == ti:
		return -2
	list_reset(MZ_PARENT, n, -1)
	q = []
	append(q, si)
	MZ_PARENT[si] = si
	head = 0
	while head < len(q):
		cur = q[head]
		head = head + 1
		cx, cy = mz_xy(cur, x0, y0, side)
		d = 0
		while d < 4:
			if MZ_MAP[cur] // MZ_BIT[d] % 2 == 0:
				jx = cx + MZ_DX[d]
				jy = cy + MZ_DY[d]
				if jx >= x0 and jx < x0 + side and jy >= y0 and jy < y0 + side:
					j = mz_ix(jx, jy, x0, y0, side)
					if MZ_PARENT[j] < 0:
						MZ_PARENT[j] = cur
						append(q, j)
			d = d + 1
	if MZ_PARENT[ti] < 0:
		return -1
	cur2 = ti
	while MZ_PARENT[cur2] != si:
		cur2 = MZ_PARENT[cur2]
		if cur2 == si:
			return -1
	gx, gy = mz_xy(cur2, x0, y0, side)      # cur2 = 从宝藏回溯到「起点的下一步」✓
	d = 0
	while d < 4:
		if sx + MZ_DX[d] == gx and sy + MZ_DY[d] == gy:
			return d
		d = d + 1
	return -1


def maze_walk_to_treasure(x0, y0, side, max_steps):
	# 用**距离场缓存**走到宝藏。**移植 maze_gold2.py 的"自愈三件套"**（2026-11-01 源码 + 真机双重确认）：
	#   ① `move()` 失败 ⇒ **双向记墙**（地图世代+1 ⇒ 距离场自动作废）⇒ 下一步用新场重算 ✓
	#   ② `measure()` 变 None / 脚下不再是树篱 ⇒ 迷宫没了（被别人抹了 / 真耗尽）⇒ 返回 0 ✓
	#   ③ 这里只负责"走到宝藏"；收货与"耗尽"判定由调用方做（只有它知道金币增量）✓
	#   ⚠⚠ v3 性能重写（2026-11-01 真机实测每颗 ~30 游戏秒的元凶）：
	#     旧版**每走一步都调 maze_bfs_dir** ⇒ 每步重算一次 64 格 BFS（≈2,000 tick）× 每颗 8~12 步
	#     ⇒ 单颗 ~20,000 tick（≈50 游戏秒）✗✗
	#     ⇒ 现在：**每颗只算 1 次距离场**（以宝藏为源，`maze_field`），之后每步只做一次
	#       "挑距离小 1 的邻居"（~50 条语句）⇒ 单颗应降到 ~1/3~1/4 ✓
	#   ⚠ 墙只会被复用**拆掉**（源码）⇒ 第一次建好的图**永远保守有效** ⇒ 复用期间不需要重探整张图 ✓
	steps = 0
	retry = 0
	while steps < max_steps:
		e = get_entity_type()
		if e == Entities.Treasure:
			return 1
		if e != Entities.Hedge:
			# 脚下不是树篱（被别的东西占了 / 迷宫没了）⇒ 交给调用方处理 ✓
			return 0
		if mz_in_region(x0, y0, side) == 0:
			return 0
		t = measure()
		if t == None:
			# 站在树篱上却量不到宝藏 ⇒ 迷宫已经不正常了（没有宝藏）⇒ 交给调用方重建 ✓
			return 0
		tx = t[0]
		ty = t[1]
		if tx < x0 or tx >= x0 + side or ty < y0 or ty >= y0 + side:
			return 0                      # 宝藏不在本区域 ⇒ 这不是我们的迷宫 ✓
		if mz_field_valid(tx, ty, x0, y0, side) == 0:
			# 目标换了 / 地图变了 / 当前位置不在场里 ⇒ **只在这里**重算一次距离场 ✓
			if maze_field(tx, ty, x0, y0, side) == 0:
				# 已知图里走不到：多半是地图不完整（有格子没量过）⇒ 就地补探当前格
				# （4 次 can_move ≈ 4 tick；同时地图世代 +1 ⇒ 下一次会重算场 ✓）
				if mz_scan_here(x0, y0, side) < 0:
					return 0
				retry = retry + 1
				if retry > 600:
					return 0
				steps = steps + 1
				continue
		d = mz_field_step(x0, y0, side)
		if d == -2:
			# 距离 0 但脚下不是宝藏：measure 还是旧坐标（复用重定位的 200 tick 定时器没到）
			# ⇒ **有界地等**，绝不能把"以为到了"当成到了（会在错误格子 harvest ⇒ 白拆迷宫 ✗）
			retry = retry + 1
			if retry > 600:
				return 0
			steps = steps + 1
			continue
		if d < 0:
			# 场坏了（理论上不会）⇒ 强制作废，下一轮重算 ✓
			MZ_FGEN[0] = -1
			retry = retry + 1
			if retry > 600:
				return 0
			steps = steps + 1
			continue
		px = get_pos_x()
		py = get_pos_y()
		if move(MZ_DIRS[d]) == 0:
			# ① 撞墙（地图说通、现实是墙）⇒ 双向记墙（世代+1 ⇒ 场作废）⇒ 继续 ✓
			mz_set_wall(px, py, d, x0, y0, side)
			retry = retry + 1
			if retry > 900:
				return 0
			steps = steps + 1
			continue
		retry = 0
		steps = steps + 1
	if get_entity_type() == Entities.Treasure:
		return 1
	return 0


def maze_solve(max_steps):
	# 右手法则：docs/game/unlocks/mazes.md Hint 2 —— 无环迷宫的墙是**连通的一堵墙**，
	#   顺着它走能遍历全部通道，所以约 10 行就能解 ✓（实现照搬 gold_mini.py，已在真机验证）
	# ⚠ 只能用于**无环**迷宫；重用过的迷宫会被随机拆墙长环 ⇒ 用 max_steps 兜底，别死转
	idx = 1
	steps = 0
	while steps < max_steps:
		if get_entity_type() == Entities.Treasure:
			return 1
		r = (idx + 1) % 4
		if can_move(MZ_DIRS[r]):
			idx = r
			move(MZ_DIRS[idx])
		elif can_move(MZ_DIRS[idx]):
			move(MZ_DIRS[idx])
		else:
			idx = (idx - 1) % 4
			if can_move(MZ_DIRS[idx]):
				move(MZ_DIRS[idx])
			else:
				idx = (idx + 2) % 4
				move(MZ_DIRS[idx])
		steps = steps + 1
	if get_entity_type() == Entities.Treasure:
		return 1
	return 0


def maze_escape():
	# 从迷宫里出来并**把整座迷宫抹掉**。
	#   为什么必须抹掉：迷宫边界封闭，无人机留在里面就出不去（util.go_to 会无限空转 ✗），
	#   而**新副机只在主机位置 (0,0) 出生**（megafarm.md）⇒ 留下的迷宫那个区域再也进不去 ✗✗
	#   源码（2026-11-01 反编译）：`HedgePlant.Harvest` → `RemoveMaze()`
	#   ⇒ **在任何一格树篱上 harvest = 抹掉整座迷宫** ✓（这是唯一的官方拆法）
	#   在宝藏上 harvest 也抹迷宫，但那会收掉一颗金币 ⇒ 语义上交给 maze_life 的收尾处理 ✓
	guard = 0
	while guard < 12:
		guard = guard + 1
		e = get_entity_type()
		if e == Entities.Hedge:
			harvest()                 # 非宝藏处 harvest ⇒ RemoveMaze ⇒ 整座迷宫消失 ✓
			MZ_IN[0] = 0
			continue
		if e == Entities.Treasure:
			# 先挪开一格（迷宫连通，必有可走方向）⇒ 再割树篱，避免把"收宝藏"混进这里 ✓
			moved = 0
			i = 0
			while i < 4:
				if moved == 0:
					if can_move(MZ_DIRS[i]):
						move(MZ_DIRS[i])
						moved = 1
				i = i + 1
			if moved == 0:
				MZ_IN[0] = 0
				return 0
			continue
		MZ_IN[0] = 0
		return 1
	MZ_IN[0] = 0
	return 0


def mz_plant_bush():
	# 在脚下种出灌木（迷宫唯一的合法基座）。返回 1 = 脚下确实是 Bush。
	# ⚠⚠⚠ w22 真机事故（2026-11-01）+ 源码解释（反编译 Core.dll 钉死）：
	#   `Drone.Plant` 的条件之一是「脚下没有实体，或实体 canBeOverplanted」；
	#   **Grass 挡路**：plant 对已有植物的格子**静默返回 false**（无 warning ✗）。
	#   而 `harvest()` **清不掉 Grass**：
	#     `Growable.Harvest` → `grid.RemoveEntity(pos)`，而 `RemoveEntity` 默认 `regrowGrass=true`
	#     ⇒ 在 Grassland 上它立刻 `SetEntity(pos, "grass")` **又长一棵** ✗✗
	#   所以「收草 → 再种」永远失败 —— 旧 `mz_plant_bush` 就死在"8 次 harvest 循环"里，
	#   真机症状：`[mz] !! 建图点 18 4 种不上灌木（脚下 Entities.Grass | 地面 Grounds.Grassland）`
	#   在 w16/w22 反复出现（本跑 5,529 次 ✗，w22 两座迷宫几乎零产能 ✓）
	#   ⇒ 唯一可靠的清格 = `till()`：`Drone.ChangeGround` 用 `regrowGrass:false` 清实体、并把地面改成 Soil；
	#     而 Bush 文档写明 **grassland 或 soil 都能长** ⇒ till 成 Soil 不影响建迷宫 ✓
	#   ⇒ 流程：能收就收（白拿 hay/wood）→ **till 清格** → 下一轮 plant ✓（全程有界重试）
	acts = []
	guard = 0
	while guard < 10:
		guard = guard + 1
		e = get_entity_type()
		if e == Entities.Bush:
			return 1
		if e == Entities.Hedge or e == Entities.Treasure:
			append(acts, "escape")
			maze_escape()
			continue
		if e != None:
			if can_harvest():
				append(acts, "harvest")
				harvest()              # 白拿一份产物（草=hay / 树=wood / 作物）
			e2 = get_entity_type()
			if e2 != None:
				append(acts, "till")
				till()             # ⚠ regrowGrass=false ⇒ 真正清掉 Grass/作物，地面变 Soil ✓
			continue
		# 脚下空了：地面是 Soil（till 后）或 Grassland 都能种 ✓
		plant(Entities.Bush)
		append(acts, "plant")
		if get_entity_type() == Entities.Bush:
			return 1
		# 种不上（极罕见：付不起/地面异常）⇒ 再清一轮；下面再失败就放弃并打印诊断 ✓
		till()
		append(acts, "till")
	e = get_entity_type()
	g = get_ground_type()
	print("[mz] !! 清格失败：建图点", get_pos_x(), get_pos_y(),
		"| 实体", e, "| 地面", g, "| 试过", acts)
	return 0


def maze_build(x0, y0, side, sub, bx, by):
	# 建一座 side x side 迷宫：去建图点 → 清格 → 种灌木 → 灌物质。
	#   返回 1 = 脚下已经是 Hedge/Treasure（迷宫真的长出来了 ✓）
	#   ⚠ 锚点未知时调用方已把 (bx,by) 设成区域中心（无论落点是"脚下为左上角"还是"以无人机为中心"，
	#     建在中心都不会被棋盘边界裁剪 ⇒ 只有这样才能量出真实落点 ✓）
	if mz_goto_best(bx, by) == 0:
		# 真机 2026-11-02：副机可能"根本没进区"就空转一整班 ⇒ 这里必须打印**可定位**的信息：
		#   目标建图点 / 现在位置 / 脚下实体 / 用掉几条路线（4 = 全试过）/ 最后卡在哪格 ✓
		print("[mz] !! 进区失败 | 目标建图点", bx, by,
			"| 现在", get_pos_x(), get_pos_y(), "| 实体", get_entity_type(),
			"| 已试路线", MZ_ROUTE_N[0], "/4 | 最后卡在", MZ_ROUTE_P[0], MZ_ROUTE_P[1])
		return 0
	if mz_plant_bush() == 0:
		print("[mz] !! 建图点", bx, by, "种不上灌木（脚下", get_entity_type(),
			"| 地面", get_ground_type(), "）⇒ 放弃本座")
		return 0
	if num_items(Items.Weird_Substance) < sub:
		print("[mz] !! 物质不够建迷宫（", num_items(Items.Weird_Substance), "<", sub, "）⇒ 放弃本座")
		return 0
	use_item(Items.Weird_Substance, sub)
	e = get_entity_type()
	if e == Entities.Hedge or e == Entities.Treasure:
		MZ_IN[0] = 1
		MZ_SIDE[0] = side
		return 1
	print("[mz] !! 迷宫没长出来（脚下是", e, "| 灌物质前应是 Bush）⇒ 放弃本座")
	return 0


def maze_life(x0, y0, side, sub, per):
	# 一座迷宫的**完整寿命**：建图一次 → 反复「走到宝藏 + use_item 收金币并重定位」
	#   → 复用耗尽/物质不够/到目标/世界变了/寿命到点 ⇒ 收尾（在宝藏上 harvest 收最后一颗 + RemoveMaze）。
	#   源码依据（2026-11-01 反编译 `Core.dll`，见 MZ_REUSE_MAX 上面的长注释）：
	#     * `use_item(weird, sub)` 在宝藏上 = 收金币 + 随机重定位（+随机拆墙），上限 300 次
	#     * `harvest()` 在任何树篱/宝藏上 = **RemoveMaze()** ⇒ 只有"准备放弃这座迷宫"时才能用 ✓
	#   ⇒ 每座迷宫最多 301 颗（300 次 use_item + 1 次收尾 harvest），与官方排行榜口径一致 ✓
	#   返回本座实测收到的金币数（用 num_items 增量累加，多机并行时也不会虚报 ✓）
	got = 0
	t_start = get_time()
	ws0 = get_world_size()
	life_cap = MZ_LIFE_CAP[0]
	if life_cap <= 0.0:
		life_cap = MZ_LIFE_SEC
	if life_cap > MZ_LIFE_SEC:
		life_cap = MZ_LIFE_SEC
	if maze_map_walk(x0, y0, side) == 0:
		print("[mz] !! 建图失败 ⇒ 本座放弃（拆掉，下一轮重建）")
		maze_escape()
		return 0
	if measure() == None:
		print("[mz] !! 建好图却 measure()=None ⇒ 迷宫不在这区域")
		maze_escape()
		return 0
	MZ_REUSE[0] = MZ_REUSE_MAX
	guard = 0
	guard_limit = MZ_REUSE_MAX * 2 + 32
	while MZ_REUSE[0] > 0:
		guard = guard + 1
		if guard > guard_limit:
			print("[mz] !! 复用循环超硬上限", guard_limit, "⇒ 收尾重建")
			break
		if get_time() - t_start > life_cap:
			break
		if num_items(Items.Gold) >= budget.gold_goal():
			break
		if get_world_size() != ws0:
			break
		if num_items(Items.Weird_Substance) < sub + budget.mazes_keep():
			print("[mz] 物质不够继续复用（要留迷宫升级本钱）⇒ 本座收尾 | weird",
				num_items(Items.Weird_Substance))
			break
		ok = maze_walk_to_treasure(x0, y0, side, side * side * 3 + 300)
		if ok == 0:
			# 地图可能被别的无人机弄脏了（邻区/重复派活）⇒ 整张图重探一次再试（只此一次 ✓）
			print("[mz] 复用中走不到 ⇒ 重探整张图一次")
			MZ_IN[0] = 1
			if maze_map_walk(x0, y0, side) == 0:
				break
			if measure() == None:
				break
			ok = maze_walk_to_treasure(x0, y0, side, side * side * 3 + 300)
			if ok == 0:
				print("[mz] 重探后仍走不到 ⇒ 放弃本座")
				break
		g0 = num_items(Items.Gold)
		px = get_pos_x()
		py = get_pos_y()
		use_item(Items.Weird_Substance, sub)
		g1 = num_items(Items.Gold)
		if g1 - g0 >= per:
			# ✅ 复用成功 = 收金币 + 宝藏随机重定位（立刻到账；墙随机拆几面）
			#   判据用「增量 >= per」而不是「== per」：多架同时收货会互相污染差值 ✓
			#   （等级中途升过 ⇒ 单颗金币会 > per；也放行 ✓）
			got = got + (g1 - g0)
			MZ_REUSE[0] = MZ_REUSE[0] - 1
			MZ_DIAG[0] = MZ_DIAG[0] + 1
			if MZ_DIAG[0] % 20 == 1:
				print("[mz] 复用第", MZ_DIAG[0], "颗 | 本次增量", g1 - g0,
					"（per=", per, "）| gold", g1, "| 本座剩复用", MZ_REUSE[0])
			# 等重定位落地：measure() 换成别的坐标才算完成（200 tick 定时器；有界等待 ✓）
			w = 0
			gone = 0
			while w < 500:
				tp = measure()
				if tp == None:
					gone = 2
					break
				if tp[0] != px or tp[1] != py:
					break
				w = w + 1
			if gone == 2:
				print("[mz] 复用后 measure()=None ⇒ 迷宫没了，收尾")
				break
			continue
		# ❌ use_item 没给金币 ⇒ 按 maze_gold2 的 ②③ 判据，**绝不 harvest 兜底**：
		tp = measure()
		if tp == None:
			break
		if tp[0] != get_pos_x() or tp[1] != get_pos_y():
			# 宝藏已不在本格（被同区另一架抢先 / 重定位还在路上）⇒ 继续追 ✓
			continue
		# 宝藏在脚下却不给金币：给重定位一点时间；仍不变 ⇒ 复用耗尽（300 上限）或物质/等级变了
		w = 0
		changed = 0
		while w < 500:
			tp2 = measure()
			if tp2 == None:
				changed = 2
				break
			if tp2[0] != get_pos_x() or tp2[1] != get_pos_y():
				changed = 1
				break
			w = w + 1
		if changed == 2:
			break
		if changed == 1:
			continue
		print("[mz] 复用耗尽（300 上限 / 物质不足 / 迷宫升级）⇒ 收掉最后一份再重建 | weird",
			num_items(Items.Weird_Substance))
		break
	# 收尾：迷宫还在、宝藏还在 ⇒ 收最后一份（第 301 颗）；
	#   **在宝藏上 harvest = 收金币 + RemoveMaze()**（源码）⇒ 干净结束本座 ✓
	#   ⚠ 两种入口都要覆盖：① 循环因复用耗尽而退出时**正站在宝藏上**（直接 harvest ✓）
	#                        ② 因寿命/目标/物质退出时站在树篱上（先走过去再 harvest ✓）
	if get_entity_type() == Entities.Treasure:
		harvest()
		got = got + per
		MZ_DIAG[0] = MZ_DIAG[0] + 1
	else:
		if measure() != None:
			if maze_walk_to_treasure(x0, y0, side, side * side * 3 + 300) == 1:
				if get_entity_type() == Entities.Treasure:
					harvest()
					got = got + per
					MZ_DIAG[0] = MZ_DIAG[0] + 1
	MZ_REUSE[0] = 0
	e2 = get_entity_type()
	if e2 == Entities.Hedge or e2 == Entities.Treasure:
		maze_escape()                 # 兜底：还困在迷宫里 ⇒ 抹掉（否则这个区域下一班进不来 ✗）
	MZ_IN[0] = 0
	print("[mz] 本座寿命结束 | 全局复用第", MZ_DIAG[0], "颗 | 本座实测", got, "金 | 用时",
		get_time() - t_start, "s | weird", num_items(Items.Weird_Substance))
	return got


def mz_cleanup():
	# 班次结束/异常退出的兜底：脚下还有迷宫就**必须先抹掉**。
	#   ⚠ 新副机只在主机位置 (0,0) 出生，而迷宫边界封闭 ⇒ 留下的迷宫会让这个区域**永远进不去** ✗✗
	guard = 0
	while guard < 6:
		guard = guard + 1
		e = get_entity_type()
		if e == Entities.Hedge or e == Entities.Treasure:
			maze_escape()
			continue
		break
	MZ_IN[0] = 0
	MZ_REUSE[0] = 0


def rotation_worker(x0, y0, w, h, cycles, my_world, roles):
	# 轮作副机入口（统一契约 7 参，见 maze_worker）。roles 是主机派活时**按值拷贝**过来的
	#   —— megafarm.md 原文：参数传过去的是副本 ⇒ 跨机安全 ✓
	# R2：有限班次（扫 cycles 遍就回来）；R3：世界一变就下岗（手里的列坐标全废）
	n = 0
	i = 0
	while i < cycles:
		if world_changed(my_world) == 1:
			print("[rw] 世界从", my_world, "变成", get_world_size(), "⇒ 副机下岗")
			return n
		sweep_columns(x0, y0, w, h, roles)
		n = n + 1
		i = i + 1
	return n


# ============================================================
# 恐龙跑（骨头）：蛇形遍历 + 卸帽结算
# ============================================================

DINO_DIAG = [0]
DINO_LAST = [-9999.0]     # 上一趟恐龙跑结束的时刻（节流用）
MAZE_EVERY = 4             # 组合班次里每几轮建一座迷宫（策略常数）
# 两趟之间至少让农场跑这么久（策略常数）。
# 真机读数（2026-10-08）：DINO_GAP=300 时农场已经**严重过剩**
#   （`hay 3467 wood 187305 carrot 771` ⇒ 木堆了 18 万没人用 ✓），
#   而**骨头是终点的限速项**（Leaderboard 要 200 万）⇒ 缩短间隔让恐龙多跑 ✓
#   ⚠ 不能设太小：每趟要 clear() 清场，农场得有时间重铺 ✓
# 两趟之间的间隔（秒）。**按"还差多少骨头"动态定**（真机利用率分析 2026-10-08）：
#   实测：一趟恐龙 ≈ 96 秒（12,000 步），而间隔 120 秒 ⇒ 每 216 秒里 **44% 处于恐龙相** ✓
#   恐龙相是**独占**的（尾巴铺满棋盘、还会挡住别的无人机）⇒ 那段时间 `assign()` 返空、
#   只有 1 架在飞 ⇒ 实测平均利用率：cap=4 时仅 **54.2%**（满编只有 9.1% 的时刻）✗✗
#   而利用率是**所有产线的公共乘数** ⇒ 独家相占比必须跟"骨头还差多少"匹配 ✓
#   骨头已到 110 万 / 200 万、×2 倍率下每趟 10 万 ⇒ 只需再 9 趟 ≈ 15 分钟 ⇒ 间隔可以放大 ✓
#   （骨头快到时自动拉长 ⇒ 农场拿回时间 ⇒ 金币产率上升 ✓；这是**新的限速项** ✓）
# 两趟恐龙之间的间隔（秒）。**必须让农场有机会稳住**（真机实测 2026-10-08）：
#   症状：`[s16] 地里 胡萝卜 0 草 80` / `库存 hay 4 carrot 0` 长期贴 0，
#         而日志最后一行是 `[dino] 农场已清空` ✗
#   链条：恐龙跑前要 clear()（docs 第 14 行：苹果只能落在没种东西的格子上 ✓）⇒
#         **整块农场被清空** ⇒ 要重新翻土/种树/种胡萝卜 ⇒ 而 600 秒后又清一次 ✗✗
#         ⇒ 农场永远处于"补种中" ⇒ 草/胡萝卜库存攒不起来 ✓✓
#   而骨头并不需要那么频繁：Dinosaurs lv3 ⇒ 每趟 224² × 4 = **200,704 骨头** ✓
#         还差约 57 万 ⇒ **约 3 趟** ✓ ⇒ 间隔拉长到 1800 秒完全够 ✓
#   ⚠ 判据：`[s16] 库存 hay/carrot` 应稳定在数百以上 ✓、`累计收割` 持续增长 ✓
DINO_GAP = 1800.0


def cactus_per_apple():
	# 一颗苹果 = 2 仙人掌 x 2^(恐龙等级-1)（CONTEXT 实测口径）
	amt = 2
	lv = num_unlocked(Unlocks.Dinosaurs)
	i = 1
	while i < lv:
		amt = amt * 2
		i = i + 1
	return amt


def dino_bone_mult():
	amt = 1
	lv = num_unlocked(Unlocks.Dinosaurs)
	i = 1
	while i < lv:
		amt = amt * 2
		i = i + 1
	return amt


def dino_ready():
	# 能不能开一趟恐龙跑。⚠ 必须**独占整块棋盘**：
	#   尾巴占格、而且别的无人机撞上尾巴就动不了 ⇒ 有副机在飞时不能开 ✗
	#   （CONTEXT 的 L3 口径：戴帽前确认没有其他无人机在工作）
	if num_unlocked(Unlocks.Dinosaurs) <= 0:
		return 0
	if num_items(Items.Bone) >= budget.bone_goal():
		return 0
	if num_items(Items.Cactus) < cactus_per_apple() * 4:
		return 0          # 至少攒够几颗苹果的本钱再开，别打一枪换一个地方
	# ⚠⚠ **没有备用帽子就绝对不许戴恐龙帽** —— 这条是拿一次整轮中止换来的：
	#   卸帽必须 change_hat(别的帽子)，而灰/紫/绿/棕属于 `Hats` 解锁；
	#   没解锁就调用 ⇒ `Error: 必须先解锁 Hats.Gray_Hat 才能使用此功能` ⇒ **程序中止** ✗✗
	if num_unlocked(Unlocks.Hats) <= 0:
		return 0
	# ---- 节流（这一条是 mock 抓出来的真 bug）----
	#   不给退出条件的话：骨头 7551 远小于目标 200 万 ⇒ **每一轮都开恐龙** ⇒
	#   农场被饿死（金币停摆、Megafarm 买不起、停滞看门狗报警）✗✗
	#   CONTEXT 的行星口径：恐龙相必须**与其他产线交替**，不能独占整个后半程 ✓
	if get_time() - DINO_LAST[0] < DINO_GAP:
		return 0
	return 1


# 回路表（每个无人机各一份内存，R8 ✓）
DINO_CX = []
DINO_CY = []
DINO_W = [-1]


def dino_cycle_build(W):
	# 往 DINO_CX/DINO_CY 里按顺序 append 出**覆盖全部 W*W 格**的哈密顿回路
	#   （游戏语言没有 global ⇒ 一律用「就地修改列表」，不重新赋值 ✓）
	while len(DINO_CX) > 0:
		pop(DINO_CX)
	while len(DINO_CY) > 0:
		pop(DINO_CY)
	y = 0
	while y < W:                     # 列 0：从下往上
		append(DINO_CX, 0)
		append(DINO_CY, y)
		y = y + 1
	c = 1
	while c < W:
		if c % 2 == 1:               # 奇数列：从 y=W-1 下行到 y=1
			y = W - 1
			while y >= 1:
				append(DINO_CX, c)
				append(DINO_CY, y)
				y = y - 1
		else:                        # 偶数列：从 y=1 上行到 y=W-1
			y = 1
			while y <= W - 1:
				append(DINO_CX, c)
				append(DINO_CY, y)
				y = y + 1
		c = c + 1
	# 最后一列走完停在 y=1（W 偶数 ⇒ W-1 是奇数 ⇒ 下行 ✓）⇒ 下到 y=0 再沿底行西行回起点 ✓
	append(DINO_CX, W - 1)
	append(DINO_CY, 0)
	c = W - 2
	while c >= 1:
		append(DINO_CX, c)
		append(DINO_CY, 0)
		c = c - 1
	DINO_W[0] = W
	return len(DINO_CX)


def dino_cycle_index(x, y, W):
	# 找 (x,y) 在回路里的下标（只在上机第一步做一次，线性扫可接受）
	i = 0
	while i < len(DINO_CX):
		if DINO_CX[i] == x and DINO_CY[i] == y:
			return i
		i = i + 1
	return -1


def dino_run(my_world):
	# 沿哈密顿回路一直走，踩到苹果就吃；卸帽结算（骨头 = 尾巴² x 倍率）
	if num_unlocked(Unlocks.Dinosaurs) <= 0:
		return 0
	per = cactus_per_apple()
	if num_items(Items.Cactus) < per:
		return 0
	need = budget.bone_goal() - num_items(Items.Bone)
	if need <= 0:
		return 0
	mult = dino_bone_mult()
	target = (need // mult)          # 骨头 = 尾巴² x 倍率 ⇒ 反算颗数
	guess = 1
	while guess * guess < target:
		guess = guess + 1
	W = get_world_size()
	cap = W * W - W * W // 8         # 蛇不能把自己堵死 ⇒ 上限 ≈ 格数 x 7/8
	if guess > cap:
		guess = cap
	if DINO_W[0] != W:
		dino_cycle_build(W)
		print("[dino] 回路表建好：", len(DINO_CX), "格（world", W, "）")
	# ⚠⚠ **开跑前必须 clear()**（docs/game/unlocks/dinosaurs.md 第 14 行）：
	#   「The apple cannot spawn if something else is **planted** where it wants to be.」
	#   农场上种满作物时苹果放不下来 ⇒ 一次失败就永久断粮（吃不到就不会再尝试放）✗✗
	#   真机症状就是这个：`no apple for 1025 steps, stopping at 26` ✓
	#   clear() = 把农场重置成**全草地**并把无人机送回 (0,0) ✓（植物没了 ⇒ 苹果能落 ✓）
	#   代价：跑完一趟农场要重铺（各档位的轮作/方块/迷宫/仙人掌都会自己补种回来 ✓）
	clear()
	print("[dino] 农场已清空（苹果只能落在没有作物的格子上）")
	change_hat(Hats.Dinosaur_Hat)
	idx = dino_cycle_index(get_pos_x(), get_pos_y(), W)
	if idx < 0:
		# 不在回路上（几乎不会发生：回路覆盖全场）⇒ 先走回起点 ✓
		util.go_to(0, 0)
		idx = dino_cycle_index(0, 0, W)
	eaten = 0
	steps = 0
	no_eat = 0
	lap = W * W
	while eaten < guess:
		if world_changed(my_world) == 1:
			break
		if no_eat > lap * 3:
			print("[dino] 连走", no_eat, "步没吃到苹果 ⇒ 收工",
				"（苹果落点被占就放不下来 —— docs 第 14 行）")
			break
		if measure() != None:
			eaten = eaten + 1        # 站在苹果上 ⇒ 下一步吃掉它（docs：苹果在脚下）
			no_eat = 0
		else:
			no_eat = no_eat + 1
		nx = idx + 1
		if nx >= lap:
			nx = 0
		tx = DINO_CX[nx]
		ty = DINO_CY[nx]
		x = get_pos_x()
		y = get_pos_y()
		ok = 0
		if tx > x:
			ok = move(East)
		elif tx < x:
			ok = move(West)
		elif ty > y:
			ok = move(North)
		elif ty < y:
			ok = move(South)
		if ok == 0:
			print("[dino] 走不动了（蛇已填满农场）⇒ 收工 | 吃了", eaten, "颗")
			break
		idx = nx
		steps = steps + 1
	change_hat(Hats.Straw_Hat)       # 卸帽（dino_ready 已保证 Hats 解锁 ⇒ 草帽一定有 ✓）
	DINO_LAST[0] = get_time()
	DINO_DIAG[0] = DINO_DIAG[0] + 1
	print("[dino] 第", DINO_DIAG[0], "趟 | 吃了", eaten, "/", guess, "颗 | 步数", steps,
		"| 倍率", mult, "| 骨头", num_items(Items.Bone), "| world", W)
	return eaten


def pumpkin_worker(x0, y0, w, h, cycles, my_world, roles):
	# 南瓜方块专职副机。为什么要专机（用户 2026-10-08 报「南瓜产率上不去」）：
	#   方块维护很费动作：补种 + 等熟（最长 45 秒）+ 清死瓜，一轮就吃掉主机大半时间，
	#   而主机还要管轮作/向日葵/仙人掌/迷宫 ⇒ 方块被服务得太稀 ⇒ 产率被拖死 ✗
	#   （旧 full_run 当年也是让一架专机守方块的 ✓）
	# R2 有限班次；R3 世界一变就下岗；方块位置由 block_farm 固定在 (0,0)，
	#   x0/y0 只用来做世界校验与打印 ✓
	n = 0
	i = 0
	while i < cycles:
		if world_changed(my_world) == 1:
			print("[pkw] 世界变了 ⇒ 副机下岗")
			return n
		if num_unlocked(Unlocks.Pumpkins) <= 0:
			return n
		before = num_items(Items.Pumpkin)
		pumpkin_shift(1, budget.pumpkin_keep())
		if num_items(Items.Pumpkin) > before:
			n = n + 1
		i = i + 1
	return n


# ============================================================
# 向日葵带的实现（power 线）—— 2026-11-02 重写：修「能量长期 0」
#
# 根因（两条，都有日志/反编译证据）：
#   ① **地面没人翻**：恐龙跑每趟都 `clear()` 把整盘清成草原；而向日葵只能种在土壤上
#      （反编译 Core.dll 的 Farm.Plant：ground 不在 objectSO.placeableOn 里 ⇒ 只发警告、
#      **静默失败**）。旧版 sun_simple_pass / sun_simple_worker **不 till** ⇒ 每次恐龙跑后
#      向日葵带永久荒废，只有主机偶尔 `sun_shift`（它会 till）时才恢复 ✗✗
#      证据：output.txt 里 14 次 `Warning: 不能在 Grounds.Grassland 上种植 Entities.Sunflower`
#   ② **班次太短、调度窗口太长**：旧版 24 遍全速扫完就退出（约 1 分钟），而调度器
#      一个批次要 3~10 分钟才重派 ⇒ 实测 **76.6% 的 [fr] 报告里 power = 0** ✗
#      （power 只在每班开头 40~60 秒 >0，然后被耗光）
#   ⇒ 现在：**自己 till** + **按生长节奏配速**（没收成就歇一会，把班次铺满批次窗口）
#     + **按花瓣降序收**（反编译 Sunflower.Harvest：收的若是当前花瓣最大的一株且场上
#       >=10 株 ⇒ 8 倍；按降序收 ⇒ **每一株都吃到 8 倍** ✓✓）
#     + **种之前先问胡萝卜库存**（向日葵种子 = 1 胡萝卜 x 2^(Sunflowers 等级-1)，**不是干草** ✓）
#
# 策略常数（不是游戏数据，是我们的选择）：
SUN_CARROT_KEEP = 200     # 胡萝卜保护底：整片补种最多只花“库存 - 此数”的那部分
SUN_WAVE_WAIT = 8.0       # 一整遍颗粒无收时歇多久再看（向日葵基础生长 5 秒 + 余量）
SUN_SHIFT_SEC = 200.0     # 单个班次时间上限（R2：有限班次）。**故意 < maze 的 213 秒**：
						  #   调度器一个批次要等所有任务结束才重派 ⇒ 若向日葵班次最长，
						  #   会把整个批次周期拉长、拖慢所有产线 ✗。200 秒已足够铺满窗口
						  #   （每波 ~10 秒 ⇒ 约 20 波、~3800 power，够全场用很久）✓
SUN_SWEEP = [0]           # 诊断：累计扫了多少遍
SUN_TOTAL = [0]           # 诊断：累计收割多少株
SUN_PLANTED = [0]         # 本遍补种株数
# ---- 一遍「看+收」用的内存暂存（每机一份，R8 ✓）----
SUN_PX = []
SUN_PY = []
SUN_PP = []
SUN_CNT = [0]             # 本遍看到的向日葵株数
SUN_ALMAX = [0]           # 本遍全场最大花瓣（**含未熟** —— 8 倍判据用的是它 ✓）


def sun_band_clear():
	# 清空本遍暂存（游戏语言没有 list.clear()，只能逐个 pop ✓）
	while len(SUN_PX) > 0:
		pop(SUN_PX)
	while len(SUN_PY) > 0:
		pop(SUN_PY)
	while len(SUN_PP) > 0:
		pop(SUN_PP)


def sun_carrot_floor(w, h):
	# 一次整片补种最多吃掉多少胡萝卜 = (每株种子价 x 格数) + 保护底
	#   依据反编译 Core.dll 的 Farm.Plant：cost = objectSO.cost x 2^(yield升级等级-1)
	#   向日葵的种子是**胡萝卜**（CONTEXT「种 1 株耗 1 胡萝卜」、ADR 0003 的实测口径）
	per = 0
	c = get_cost(Entities.Sunflower)
	if c != None:
		for k in c:
			if k == Items.Carrot:
				per = c[k]
	return SUN_CARROT_KEEP + per * w * h


def sun_scan_and_harvest(x0, y0, w, h):
	# 第一遍：读整片 → **按花瓣从大到小**收割（见文件头 ② 的 8 倍说明）
	#   ⚠ 顺序必须降序：先收小的会触发 hadIncorrectSunflowerHarvest 惩罚（下一次也没 8 倍）✗
	#   ⚠ 必须**收完再补种**：补种会立刻产生「花瓣更大但未熟」的株 ⇒ 破坏 8 倍判据 ✗
	#   ⚠ 本遍最大花瓣那株还没熟 ⇒ **一株都不割**（等它熟了整波都吃 8 倍，比现在割 1 倍强）✓
	# 返回本遍收割株数
	sun_band_clear()
	SUN_CNT[0] = 0
	SUN_ALMAX[0] = 0
	util.go_to(x0, y0)
	x = 0
	while x < w:
		y = 0
		while y < h:
			e = get_entity_type()
			if e == Entities.Sunflower:
				SUN_CNT[0] = SUN_CNT[0] + 1
				pt = measure()
				if pt == None:
					pt = 0
				if pt > SUN_ALMAX[0]:
					SUN_ALMAX[0] = pt
				if can_harvest():
					append(SUN_PX, x0 + x)
					append(SUN_PY, y0 + y)
					append(SUN_PP, pt)
			y = y + 1
			if y < h:
				move(North)
		c = 0
		while c < h - 1:
			move(South)
			c = c + 1
		x = x + 1
		if x < w:
			move(East)
	if len(SUN_PP) == 0:
		return 0
	mmax = 0
	k = 0
	while k < len(SUN_PP):
		if SUN_PP[k] > mmax:
			mmax = SUN_PP[k]
		k = k + 1
	if mmax < SUN_ALMAX[0]:
		return 0
	n = 0
	p = SUN_ALMAX[0]
	while p >= 1:
		k = 0
		while k < len(SUN_PP):
			if SUN_PP[k] == p:
				util.go_to(SUN_PX[k], SUN_PY[k])
				if can_harvest():
					harvest()
					n = n + 1
					SUN_HARV[0] = SUN_HARV[0] + 1
			k = k + 1
		p = p - 1
	return n


def sun_plant_pass(x0, y0, w, h):
	# 第二遍：补种空位。**必须自己 till**（恐龙跑的 clear() 会把整盘清成草原；
	#   向日葵 placeableOn 只有土壤，不翻土 plant 就是静默失败 ✗）
	# 资源前提：胡萝卜库存 > 整片补种的最大花费 + 保护底，才动手（不抽干南瓜线上游 ✓）
	# 返回补种株数
	if num_unlocked(Unlocks.Sunflowers) <= 0:
		return 0
	if num_items(Items.Carrot) <= sun_carrot_floor(w, h):
		return 0
	if util.can_afford(Entities.Sunflower) == 0:
		return 0
	planted = 0
	util.go_to(x0, y0)
	x = 0
	while x < w:
		y = 0
		while y < h:
			e = get_entity_type()
			if e == None or e == Entities.Grass:
				if get_ground_type() != Grounds.Soil:
					till()
				if util.can_afford(Entities.Sunflower) == 1:
					plant(Entities.Sunflower)
					planted = planted + 1
			y = y + 1
			if y < h:
				move(North)
		c = 0
		while c < h - 1:
			move(South)
			c = c + 1
		x = x + 1
		if x < w:
			move(East)
	return planted


def sun_simple_pass(x0, y0, w, h):
	# 一遍「看 + 收（降序 8 倍）+ 补种」整片（sun_simple_worker 与组合班次共用 ✓）
	# 返回本遍收割株数
	h1 = sun_scan_and_harvest(x0, y0, w, h)
	p1 = sun_plant_pass(x0, y0, w, h)
	SUN_PLANTED[0] = p1
	return h1


def sun_simple_worker(x0, y0, w, h, cycles, my_world, roles):
	# 专用向日葵机。契约同其它副机入口（统一 7 参 ✓）
	#   2026-11-02 重写：旧版「24 遍全速扫」1 分钟内跑完就退出，而调度器一个批次要
	#   3~10 分钟才重派 ⇒ 76.6% 的报告里 power=0 ✗。现在按生长节奏配速、铺满批次窗口。
	#   R2 双上限：cycles 用完 / SUN_SHIFT_SEC 到点 ⇒ 必回 ✓（不是 while True）
	n = 0
	planted = 0
	i = 0
	t0 = get_time()
	while i < cycles:
		if world_changed(my_world) == 1:
			print("[sun] 世界变了 ⇒ 副机下岗")
			return n
		if num_unlocked(Unlocks.Sunflowers) <= 0:
			return n
		if get_time() - t0 > SUN_SHIFT_SEC:
			break
		h1 = sun_simple_pass(x0, y0, w, h)
		n = n + h1
		planted = planted + SUN_PLANTED[0]
		i = i + 1
		if h1 == 0:
			# 本遍没收成：花在长 / 没种上 ⇒ 歇一会再看（get_time 是 0 tick，不空转 ✓）
			# 整片既没有花、补种也失败（地面被占 / 资源不够）⇒ 提前收工，把名额还给调度器 ✓
			if SUN_CNT[0] == 0:
				if SUN_PLANTED[0] == 0:
					break
		# 无论收没收成，都等一个生长周期再扫：
		#   收完 ⇒ 等刚补种的这一批熟（否则下一遍必然空扫 32 格 ✗）
		#   没收成 ⇒ 花正在长，等它
		tw = get_time()
		while get_time() - tw < SUN_WAVE_WAIT:
			pass
	SUN_SWEEP[0] = SUN_SWEEP[0] + i
	SUN_TOTAL[0] = SUN_TOTAL[0] + n
	# 诊断只打**每班一条**（Lead 2026-11-02：别刷屏淹掉 [mz] 日志 ✓）
	print("[sunw] 班次结束 | 遍", i, "| 收割", n, "株 | 补种", planted, "株 | 场上",
		SUN_CNT[0], "株 最大花瓣", SUN_ALMAX[0], "| power", num_items(Items.Power),
		"| carrot", num_items(Items.Carrot), "| 用时", get_time() - t0)
	return n


def sun_maze_worker(x0, y0, w, h, cycles, my_world, roles):
	# 【组合班次】名额只有 1 个时要干两件事（真机证据 2026-10-08）：
	#   w12 只有 1 个副机位，而名单 [sun, maze] 被调度器按顺序放飞 ⇒ sun 占住名额 ⇒
	#   日志实测 `sun: 97 次 / maze: 12 次`（迷宫只跑到 11% 的时间）✗✗
	#   ⇒ 一个名额 + 一个函数里轮着做：每轮割太阳，每 MAZE_EVERY 轮建一座迷宫 ✓
	#   契约仍是统一 7 参（x0/y0 在这里当**迷宫区**的左上角，「太阳带」由 roles 传：
	#   roles = [sun_x0, sun_y0, sun_w, sun_h] ✓ 参数是按值拷贝 ⇒ 跨机安全 ✓）
	if num_unlocked(Unlocks.Sunflowers) <= 0:
		return 0
	sx = 0
	sy = 0
	sw = 0
	sh = 0
	if len(roles) >= 4:
		sx = roles[0]
		sy = roles[1]
		sw = roles[2]
		sh = roles[3]
	n = 0
	i = 0
	while i < cycles:
		if world_changed(my_world) == 1:
			print("[smw] 世界变了 ⇒ 副机下岗")
			return n
		if sw >= 1:
			# 用户要求：向日葵**单纯种+收**（不做花瓣判断 ✓ 单位行动产出更高 ✓）
			sun_simple_pass(sx, sy, sw, sh)
		if i % MAZE_EVERY == 0:
			if num_unlocked(Unlocks.Mazes) > 0:
				# ⚠ maze_shift 只收 4 个参数 (x0, y0, side, cycles)：
				#   真机报错过 `maze_shift 需要 4 个参数。你传入的参数是：(0,6,6,6,1)` ✗
				#   迷宫区是正方形 ⇒ side 取 w 即可 ✓
				maze_shift(x0, y0, w, 1)
		i = i + 1
		n = n + 1
	return n


def sun_worker(x0, y0, w, h, cycles, my_world, roles):
	# 向日葵专职副机：**power 是全场共享的**（docs/game/unlocks/sunflowers.md：
	#   有电时所有无人机都跑 2 倍速），而每 30 个行动耗 1 点 ⇒ 副机越多耗得越快。
	#   真机症状：4~8 架副机时能量严重不足 —— 因为只有主机在割向日葵 ✗
	# ⇒ 把向日葵带交给一架专职副机，它一轮能割好几刀 ✓（R5：主机不再碰这一区）
	n = 0
	i = 0
	while i < cycles:
		if world_changed(my_world) == 1:
			return n
		if num_unlocked(Unlocks.Sunflowers) <= 0:
			return n
		n = n + sun_shift(x0, y0, w, h)
		i = i + 1
	return n


def maze_worker(x0, y0, w, h, cycles, my_world, roles):
	# 副机入口。签名必须与 full_run 派活时的**统一契约**一致：(x0, y0, w, h, cycles, world)
	#   （第一次写漏了 h ⇒ 真机会直接报参数个数不符、整轮中断 ✗）
	# R2：**有限班次** —— 班次受两个上限约束：`cycles` 座 或 `MZ_SHIFT_SEC` 秒 ✓
	#     （一座迷宫寿命 MZ_LIFE_SEC=140 秒 ⇒ 通常 2 座撑满班次 ⇒ 班次约 5 分钟 ✓）
	# R3：每轮开头校验世界没变（世界一变，手里的迷宫区坐标全废）
	# 依据 megafarm.md 的 No Shared Memory：副机有自己的内存，所以它只认传进来的参数 ✓
	# ⚠⚠ **迷宫不能跨班次保留**：新副机只在主机位置 (0,0) 出生，而迷宫边界封闭
	#   ⇒ 离开后再也进不去 ⇒ 每班结束前必须抹掉（maze_life / mz_cleanup 已保证）✓
	side = w
	if h < side:
		side = h
	# ✅ **探针结果传参**（用户 2026-11-01 要求；maze_gold2.py 的老教训：
	#   「模块全局在副机里是初始值 ⇒ 探针结果必须当参数传过去 ✓」）
	#   实测锚点在 side=8 时是 (-4, -4)（= 居中锚点的 -side/2 ✓）
	#   ⇒ 由主机算好放进 roles ✓ 副机直接采用 ⇒ **每架省掉一次约 5 秒的探针** ✓
	if roles != 0:
		if len(roles) >= 2:
			MZ_ANCHOR[0] = roles[0]
			MZ_ANCHOR[1] = roles[1]
			MZ_ANCHOR_SIDE[0] = side
			MZ_ANCHOR_LV[0] = num_unlocked(Unlocks.Mazes)
	n = 0
	i = 0
	attempts = 0
	lost = 0
	g_start = num_items(Items.Gold)
	t0 = get_time()
	while i < cycles:
		attempts = attempts + 1
		if attempts > cycles * 8 + 8:
			break
		if world_changed(my_world) == 1:
			print("[mzw] 世界从", my_world, "变成", get_world_size(), "⇒ 副机下岗")
			mz_cleanup()
			return n
		if num_unlocked(Unlocks.Mazes) <= 0:
			mz_cleanup()
			return n
		# 班次时间上限（R2）：到点就收工，让主机有机会采购 Expand 等"键" ✓
		if get_time() - t0 > MZ_SHIFT_SEC:
			break
		# ⚠⚠ 真机 bug 2026-11-02：**金币目标/物质不足时别空转整班**：
		#   旧版在物质不足时 maze_shift 静默秒返回，副机就在原地转满 290 秒，还打印误导性的
		#   "疑似被邻区干扰"；更糟的是副机一直活着 ⇒ full_run 的 ACTIVEB 不清零
		#   ⇒ **农场类副机不会被重派 ⇒ 物质永远产不上来（真机 hay 5/power 0 的反馈环）** ✗✗
		#   ⇒ 直接收工退出：让 live 归零、ACTIVEB 重置、农场类副机重新放飞产物质 ✓
		if num_items(Items.Gold) >= budget.gold_goal():
			MZ_LOWD[0] = MZ_LOWD[0] + 1
			if MZ_LOWD[0] % 20 == 1:
				print("[mzw] 金币目标已到 ⇒ 本班收工 | gold", num_items(Items.Gold),
					"| 目标", budget.gold_goal())
			mz_cleanup()
			return n
		# 等级可能在班次中途升过 ⇒ 每次重新算 sub/keep（升级后 sub 翻倍，不能吃旧值 ✗）
		sub = maze_substance(side)
		keep = budget.mazes_keep()
		if num_items(Items.Weird_Substance) < sub + keep:
			MZ_LOWD[0] = MZ_LOWD[0] + 1
			if MZ_LOWD[0] % 20 == 1:
				# 关键字段（Lead 2026-11-02 要求）：weird 值 / 需要值 / 世界大小 / 当前位置
				#   ⇒ 下一跑可以直接看"缺多少、在哪个世界"，判断趋势 ✓
				print("[mzw] !! 物质不足 ⇒ 本班提前收工（让农场类副机去产物质）| weird",
					num_items(Items.Weird_Substance), "< 需要", sub + keep,
					"| world", get_world_size(), "| 现在", get_pos_x(), get_pos_y())
			mz_cleanup()
			return n
		# 把「本班还剩多少秒」传给 maze_life ⇒ 单座寿命不会把班次拖爆 ✓（不跨机：模块全局 ✓）
		rem = MZ_SHIFT_SEC - (get_time() - t0)
		MZ_LIFE_CAP[0] = MZ_LIFE_SEC
		if rem < MZ_LIFE_CAP[0]:
			MZ_LIFE_CAP[0] = rem
		if MZ_LIFE_CAP[0] < 8.0:
			break
		before = num_items(Items.Gold)
		px0 = get_pos_x()
		py0 = get_pos_y()
		maze_shift(x0, y0, side, 1)
		if num_items(Items.Gold) > before:
			n = n + 1
			i = i + 1
			lost = 0
		else:
			# 没收到金币：可能是被邻区迷宫挡路 / 迷宫被别的产线拆了 / 世界瞬变
			# ⇒ 打印**可定位**的信息（目标建图点 / 现在位置 / 实体 / 已试路线 / 卡在哪格）✓
			#   真机 2026-11-02 要求：区分"没进区"与"进区后建座失败"
			lost = lost + 1
			tx = x0 + side // 2
			ty = y0 + side // 2
			if MZ_ANCHOR[0] != 999:
				tx, ty = maze_build_point(x0, y0, side)
			if lost == 1 or lost >= 3:
				print("[mzw] !! 没收到金币 | 区域", x0, y0, "边长", side,
					"| 目标建图点", tx, ty, "| 现在", get_pos_x(), get_pos_y(),
					"| 实体", get_entity_type(), "| 出发时", px0, py0,
					"| 已试路线", MZ_ROUTE_N[0], "/4 | 最后卡在", MZ_ROUTE_P[0], MZ_ROUTE_P[1])
			if lost >= 3:
				print("[mzw] !! 连续", lost, "次没收到金币 ⇒ 退避 3 秒（细节见上面 [mz]/[mzw] 行）")
				t1 = get_time()
				while get_time() - t1 < 3.0:
					pass
				lost = 0
			else:
				t1 = get_time()
				while get_time() - t1 < 1.0:
					pass
	mz_cleanup()
	print("[mzw] 副机班次结束：走了", i, "座迷宫 | 本班金币 +",
		num_items(Items.Gold) - g_start, "| gold", num_items(Items.Gold),
		"| weird", num_items(Items.Weird_Substance), "| world", get_world_size(),
		"| 用时", get_time() - t0, "s")
	return n


def maze_shift(x0, y0, side, cycles):
	# 在 (x0,y0) 起的 side x side 区域里：建一座迷宫 → **走完它的寿命**（连续复用，不是建完就拆 ✓）
	#   → 抹掉 → 再建下一座；最多 cycles 座。
	#   协议依据见 maze_life 与 MZ_REUSE_MAX 上面的注释（2026-11-01 反编译 Core.dll 钉死）✓
	# ⚠⚠ **迷宫里绝对不能用 util.go_to**（无界 while，撞墙就永久空转；见 maze_escape）✓
	# ⚠ 本函数**结束时一定把迷宫抹掉**：新副机只在主机位置 (0,0) 出生、迷宫边界封闭
	#   ⇒ 留下的迷宫会让这个区域**永远进不去** ✗（所以"留给下一班续用"是不可行的）
	if num_unlocked(Unlocks.Mazes) <= 0:
		return 0
	sub = maze_substance(side)
	per = maze_gold(side)
	got = 0
	c = 0
	while c < cycles:
		c = c + 1
		if num_items(Items.Gold) >= budget.gold_goal():
			break
		if num_items(Items.Weird_Substance) < sub + budget.mazes_keep():
			break
		# ---- 0) 区域里已经有迷宫（上一轮异常中断留下的）⇒ 直接续用，别浪费 ----
		resume = 0
		if mz_in_region(x0, y0, side) == 1:
			e0 = get_entity_type()
			if e0 == Entities.Hedge or e0 == Entities.Treasure:
				resume = 1
		if resume == 0:
			if mz_in_region(x0, y0, side) == 0:
				# 区域外 ⇒ 先过去（4 种有界路线，能绕开邻区迷宫 ✓；都被挡就本轮放弃，
				#   让 maze_worker 退避重试，别在这里空转 ✗）
				#   真机 2026-11-02：把"进区失败"打印到可定位（目标/现在/实体/已试路线/卡住格）✓
				if mz_goto_best(x0 + side // 2, y0 + side // 2) == 0:
					print("[mz] !! 进区失败（回不到迷宫区）| 区域", x0, y0, "边长", side,
						"| 目标中心", x0 + side // 2, y0 + side // 2,
						"| 现在", get_pos_x(), get_pos_y(), "| 实体", get_entity_type(),
						"| 已试路线", MZ_ROUTE_N[0], "/4 | 最后卡在",
						MZ_ROUTE_P[0], MZ_ROUTE_P[1])
					return got
			e0 = get_entity_type()
			if e0 == Entities.Hedge or e0 == Entities.Treasure:
				maze_escape()          # 区域中心残留树篱（异常）⇒ 先拆干净
			# ---- 1) 锚点：未知 / 边长变了 ⇒ 建在区域中心，用这次真实建造量包围盒 ----
			lv = num_unlocked(Unlocks.Mazes)
			if MZ_ANCHOR_SIDE[0] != side:
				MZ_ANCHOR[0] = 999
				MZ_ANCHOR[1] = 999
			unknown = 0
			if MZ_ANCHOR[0] == 999:
				unknown = 1
				bx = x0 + side // 2
				by = y0 + side // 2
			else:
				bx, by = maze_build_point(x0, y0, side)
			print("[mz] 建第", c, "座 | 建图点", bx, by, "| 锚点", MZ_ANCHOR[0],
				MZ_ANCHOR[1], "边长记", MZ_ANCHOR_SIDE[0],
				"| weird", num_items(Items.Weird_Substance), "gold", num_items(Items.Gold))
			if maze_build(x0, y0, side, sub, bx, by) == 0:
				return got
			if unknown == 1 or MZ_ANCHOR_LV[0] != lv:
				minx, maxx, miny, maxy = maze_walk_bounds(side, side * side * 6 + 400)
				if maxx - minx == side - 1 and maxy - miny == side - 1:
					MZ_ANCHOR[0] = minx - bx
					MZ_ANCHOR[1] = miny - by
					MZ_ANCHOR_LV[0] = lv
					MZ_ANCHOR_SIDE[0] = side
					print("[mza] 锚点实测：建造点", bx, by, "⇒ 左上角", minx, miny,
						"| 偏移", MZ_ANCHOR[0], MZ_ANCHOR[1], "| 边长", side)
					if minx != x0 or miny != y0:
						print("[mza] 落点", minx, miny, "不在区域", x0, y0,
							"⇒ 拆掉，下一轮按补偿点重建")
						maze_escape()
						continue
				else:
					print("[mza] 包围盒", maxx - minx + 1, "x", maxy - miny + 1,
						"≠ 边长", side, "⇒ 疑似被棋盘环绕裁剪，本座只解不记锚点")
		else:
			print("[mz] 续用区域里已有的迷宫 | 脚下", get_pos_x(), get_pos_y(),
				"| weird", num_items(Items.Weird_Substance), "gold", num_items(Items.Gold))
		# ---- 2) 走完这座迷宫的寿命（maze_life 内部：建图一次 → 连续复用 → 收尾抹掉）----
		g = maze_life(x0, y0, side, sub, per)
		got = got + g
		if MZ_DIAG[0] % 10 == 1:
			print("[mz] 第", c, "座结束 | 本座", g, "金 | gold", num_items(Items.Gold),
				"| weird", num_items(Items.Weird_Substance), "| 区域", side, "x", side)
	# 兜底：正常 maze_life 收尾会自己抹掉；万一残留（异常）⇒ 抹掉，绝不留场 ✓
	e9 = get_entity_type()
	if e9 == Entities.Hedge or e9 == Entities.Treasure:
		maze_escape()
	MZ_IN[0] = 0
	return got


# ============================================================
# 向日葵带：power（全局 2 倍速）
# ============================================================

def sun_shift(x0, y0, w, h):
	# 依据 docs/game/unlocks/sunflowers.md（权威）：
	#   * 收割成熟向日葵得 power；**场上 >= 10 株**且收的是**花瓣最多**那株 ⇒ 8 倍 ✓
	#   * 若场上还有花瓣更多的，则**这一次**没 8 倍，而且**下一次**也没有（惩罚顺延）✗
	#   ⇒ 只做安全的收割：**成熟株里的最大花瓣 == 全场最大花瓣** 时才割，一轮最多一刀
	# power 的作用（timing.md）：有电时无人机跑 2 倍速，每 30 个行动耗 1 点
	if num_unlocked(Unlocks.Sunflowers) <= 0:
		return 0
	util.go_to(x0, y0)
	# ---- 周期诊断（**无条件**上报）----
	# 为什么必须无条件：原来只在 cnt < 10 时打印 ⇒ 向日葵凑够 10 株之后就不再吭声，
	# 于是「到底有没有割成、吃没吃到 8 倍」在日志里完全看不出来
	# （2026-10-07 真机跑了 107 分钟、power 一路显示 0，却分不清是「产得少」还是「一次都没割成」）✗
	# 跨机各有一份计数器（R8），所以要打印的量只能由本机自己报 ✓
	SUN_DIAG[0] = SUN_DIAG[0] + 1
	diag = 0
	if SUN_DIAG[0] % 60 == 1:
		diag = 1
	allmax = -1        # 全场最大花瓣（**未成熟的也算**，见 CONTEXT.md 的 Petal Gate 口径）
	cnt = 0
	mmax = -1          # 成熟株里的最大花瓣
	bx = -1
	by = -1
	y = 0
	visited = 0
	planted = 0
	blocked = 0
	sample = None
	while y < h:
		x = 0
		while x < w:
			visited = visited + 1
			e = get_entity_type()
			if e == Entities.Sunflower:
				cnt = cnt + 1
				pt = measure()
				# ⚠⚠ 真机致命错误：`运算符 > 不能用于操作数 None 和 14` ✗（整轮中止）
				#   与仙人掌那次同型：measure() 可能返回 None ⇒ 绝不能直接拿去比大小 ✓
				if pt == None:
					x = x + 1
					continue
				if pt > allmax:
					allmax = pt
				if can_harvest():
					if pt > mmax:
						mmax = pt
						bx = x0 + x
						by = y0 + y
			else:
				if e == None or e == Entities.Grass:
					if get_ground_type() != Grounds.Soil:
						till()
					# 资源前提（2026-11-02）：向日葵种子是**胡萝卜**（反编译 Farm.Plant：
					#   cost x 2^(yield升级-1)），不是干草 ⇒ 库存低于保护底就不种，
					#   别把南瓜线/升级线的上游抽干（R7：动词前先问付得起吗）
					if num_items(Items.Carrot) > SUN_CARROT_KEEP:
						if util.can_afford(Entities.Sunflower) == 1:
							plant(Entities.Sunflower)
							planted = planted + 1
				else:
					blocked = blocked + 1
					if blocked == 1:
						sample = e
			x = x + 1
			if x < w:
				move(East)
		cnt2 = 0
		while cnt2 < w - 1:
			move(West)
			cnt2 = cnt2 + 1
		y = y + 1
		if y < h:
			move(North)
	if cnt < 10:
		if diag == 1:
			print("[sun] 第", SUN_DIAG[0], "次 | 走过", visited, "格 种下", planted,
				"株 | 现有株数", cnt, "被占", blocked, "（样本", sample, "）",
				"全场最大花瓣", allmax, "成熟最大", mmax,
				"| 胡萝卜", num_items(Items.Carrot), "| power", num_items(Items.Power))
		return 0                       # 不足 10 株 ⇒ 没有 8 倍，先等它长起来
	if bx < 0:
		if diag == 1:
			print("[sun] 第", SUN_DIAG[0], "次 | 株数", cnt, "全场最大", allmax,
				"但**一株成熟的都没有** | 胡萝卜", num_items(Items.Carrot),
				"| power", num_items(Items.Power))
		return 0
	if mmax < allmax:
		if diag == 1:
			print("[sun] 第", SUN_DIAG[0], "次 | 株数", cnt, "全场最大", allmax,
				"成熟最大", mmax, "⇒ 最大的那株还没熟，不割（避免连坐）",
				"| 胡萝卜", num_items(Items.Carrot), "| power", num_items(Items.Power))
		return 0                       # 全场最大那株还没熟 ⇒ 不割（割了要连坐两次）✗
	util.go_to(bx, by)
	harvest()
	SUN_HARV[0] = SUN_HARV[0] + 1
	if diag == 1:
		print("[sun] 第", SUN_DIAG[0], "次 | 割成第", SUN_HARV[0], "刀 @", bx, by,
			"| 株数", cnt, "花瓣", mmax, "（全场最大", allmax, "）",
			"| power", num_items(Items.Power))
	return 1
