# ============================================================
# get_top_hat.py —— 解锁高顶礼帽（Top Hat）
#
# 依据（**先问游戏，不许猜** —— 这是本项目的纪律，见 CONTEXT.md）：
#   * `Unlocks.Top_Hat` 在 Unlocks 枚举里 ⇒ 是**用物品买的**（奖杯帽才靠排行榜名次）；
#   * 游戏内文案 `@hat_descr_top_hat = It looks expensive and distinguished.`
#     / 中文「一顶非常时髦的帽子，只有最棒的无人机才能戴。」
#   * `get_cost(t)` 返回 `{Item: 数量}`；**已满级/不可买返回 None**（docs/game/unlocks/costs.md）。
#
# 本脚本做三件事：
#   1. 打印 `get_cost(Unlocks.Top_Hat)` 并翻译成人话（库存 vs 还差多少）；
#   2. 够就 `unlock()` + 戴上 + 翻个跟头；不够就打印"每样还差多少 + 该跑哪支脚本"；
#   3. 顺带把"这件要多少"和项目实测过的产率对上，给出 ETA。
#
# 用法：在游戏里运行本文件，然后看 output.txt 里的 [hat] 行。
# ============================================================

ITEMS = [Items.Hay, Items.Wood, Items.Carrot, Items.Pumpkin, Items.Cactus,
	Items.Bone, Items.Gold, Items.Weird_Substance, Items.Water,
	Items.Fertilizer, Items.Power]
INAMES = ["hay", "wood", "carrot", "pumpkin", "cactus",
	"bone", "gold", "weird", "water", "fert", "power"]
# 项目里**实测过的产率**（每分钟），用来给 ETA。没量过的一律写 0 = 不给 ETA（不许猜）。
IRATE = [96000000, 0, 0, 0, 870000, 108000, 3450000, 0, 0, 0, 0]
# 缺哪样就跑哪支脚本（都是本存档里已验证过的）
ISCRIPT = ["main.py（草带）", "main.py（木材带）", "carrot_farm.py", "pumpkin_farm.py",
	"cactus_farm.py / cactus_big.py", "dino_fast.py", "maze_gold2.py",
	"main.py（施肥副产）", "main.py（浇水）", "main.py（施肥）", "sun_farm.py"]


def num_of(it):
	return num_items(it)


def idx_of(it):
	j = 0
	for k in ITEMS:
		if it == k:
			return j
		j = j + 1
	return -1


def cost_line(c):
	line = ""
	for it in c:
		nm = "unknown"
		j = idx_of(it)
		if j >= 0:
			nm = INAMES[j]
		line = line + nm + "=" + str(c[it]) + " "
	if line == "":
		line = "(empty) "
	return line


print("[hat] === get_top_hat start ===")
print("[hat] world", get_world_size(), "| max_drones", max_drones(),
	"| gold", num_items(Items.Gold), "| power", num_items(Items.Power))

HAVE = num_unlocked(Unlocks.Top_Hat)
print("[hat] Top_Hat 当前等级 =", HAVE, "（>=1 就是已解锁）")

if HAVE > 0:
	# 已经解锁：戴上、翻跟头、收工
	change_hat(Hats.Top_Hat)
	do_a_flip()
	print("[hat] *** 高顶礼帽早就解锁了，已经戴上 ***")
	print("[hat] === get_top_hat end ===")
else:
	C = get_cost(Unlocks.Top_Hat)
	if C == None:
		print("[hat] get_cost(Unlocks.Top_Hat) = None ⇒ **不是用物品买的**")
		print("[hat] 那它只能靠别的条件（排行榜名次之类）—— 把这一行发我，我按实际情况改路线")
		print("[hat] === get_top_hat end ===")
	else:
		print("[hat] 要的料:", cost_line(C))
		# ---- 逐样对库存 ----
		missing = 0
		for it in C:
			need = C[it]
			have = num_of(it)
			j = idx_of(it)
			# 本语言**没有三元表达式** ⇒ 老老实实写 if（v: 2026-10-05 实跑踩过）
			nm = "unknown"
			if j >= 0:
				nm = INAMES[j]
			if have >= need:
				print("[hat]   ", nm, "需要", need, "有", have, "✓ 够")
			else:
				missing = missing + 1
				d = need - have
				line = "[hat]    " + nm + " 需要 " + str(need) + " 有 " + str(have) + " ✗ 还差 " + str(d)
				if j >= 0:
					if IRATE[j] > 0:
						# ETA（分钟，向上取整的粗算）
						line = line + "（约 " + str(d // IRATE[j] + 1) + " 分钟 @" + str(IRATE[j]) + "/分）"
					if ISCRIPT[j] != "":
						line = line + " ⇒ 跑 " + ISCRIPT[j]
				print(line)
		if missing == 0:
			print("[hat] 全部够料 ⇒ 现在解锁")
			if unlock(Unlocks.Top_Hat):
				print("[hat] unlock() 返回 True")
			else:
				print("[hat] unlock() 返回 False（资源被别的脚本花掉了？）")
			if num_unlocked(Unlocks.Top_Hat) > 0:
				change_hat(Hats.Top_Hat)
				do_a_flip()
				print("[hat] *** 高顶礼帽 UNLOCKED 并已戴上***")
			else:
				print("[hat] 解锁没生效 ⇒ 把上面几行发我")
		else:
			print("[hat] 还差", missing, "样 ⇒ 先按上面的提示跑对应脚本，然后再跑一次本文件")
	print("[hat] === get_top_hat end ===")
