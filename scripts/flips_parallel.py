# ============================================================
# flips_parallel.py —— 验证"32 架一起翻"能否把 1000 次后空翻从 16.7 分钟压到 ~32 秒
#
# ============ 原理（为什么应该能加速）============
#  `do_a_flip()` 的说明是 "takes 1s to execute" 且 "not affected by speed upgrades"
#  ⇒ 这 1 秒是**每架无人机自己执行流里的延迟**，不是全局节拍。
#  无人机的执行是**并行**的（wood/carrot 那 32 架同时收割已经实测证实）
#  ⇒ 32 架一起翻，墙钟耗时 = 每架翻的次数（而不是总次数）。
#  本脚本会打印"总翻转次数 / 墙钟秒数"，这个商就是证据：
#      约 32 次/秒 ⇒ 并行成立 ✓        约 1 次/秒 ⇒ 其实是串行的 ✗
#
#  ============ 唯一的未知：计数器语义 ============
#  "一千次"是**全局计数**（任何一架翻都算）还是**每架各自计数**？
#  存根里没有任何能读翻转次数的接口（flip / stat / achievement 全查过）⇒ 脚本内无法自证。
#
#  **外部观测也失败了**：我原本打算对比 `save.json` 的 `unlocks` 列表
#  （帽子是解锁项，hats.md 显示"戴帽子 + 翻跟头"是拿帽子的方式），
#  但实测反查历史备份发现 02:04~02:11 四份备份的解锁数**一直是 155、毫无新增**
#  —— 连 quests.py 那一场（摸猪/治愈/巨型南瓜都跑完了）也没让 unlocks 变多。
#  ⇒ 这几项任务**不进 unlocks 列表**，只能靠**游戏界面自己的显示**来判断。
#
#  ⇒ 所以策略是"**先跑便宜的那一半，再用眼睛验收**"：
#  默认 FULL_PER_DRONE = 0：每架只翻 32 次（32 架共 1024 次，约 32 秒）。
#    若计数器是全局的 ⇒ 这一轮就够了，省下 16.2 分钟 ✓
#    若解锁列表毫无变化 ⇒ 说明是每架各自计数，把 FULL_PER_DRONE 改成 1 再跑
#    （每架都翻满 1000 次，两种语义都保底，代价是 16.7 分钟）。
#  **先跑便宜的、再根据可观测证据决定要不要跑贵的** —— 不要一上来就赌 16.7 分钟。
#
# ============ 纪律 ============
#  * 没有三元表达式，`**` 没用过 ⇒ 一律不写。
#  * `quick_print()` 免费（timing.md）；这里次数少，用普通 print 便于事后回看。
#  * 主机**先派工、再自己翻**，这样主机的 32 次和 31 架的 32 次是**同时**进行的。
# ============================================================

VERSION = 1
TOTAL_FLIPS = 1000
FULL_PER_DRONE = 0     # 0 = 每架只翻 1000/机器数（约 32 秒，赌全局计数）
					   # 1 = 每架都翻满 1000 次（两种语义都保底，约 16.7 分钟）


def flipper(n):
	# 翻 n 次，返回 [实际次数, 本机耗时]
	t0 = get_time()
	i = 0
	while i < n:
		do_a_flip()
		i = i + 1
	return [n, get_time() - t0]


def main():
	print("=== flips_parallel v", VERSION, "===")
	cap = max_drones()
	n = cap
	per = TOTAL_FLIPS // n
	if per * n < TOTAL_FLIPS:
		per = per + 1                      # 32 架 x 32 次 = 1024 >= 1000 ✓
	if FULL_PER_DRONE == 1:
		per = TOTAL_FLIPS
	print("机器", n, "架 | 每架", per, "次 | 合计", per * n, "次 | 模式",
		FULL_PER_DRONE, "(0=赌全局计数/约", per, "秒, 1=每架翻满/约", per * 1, "秒)")
	T0 = get_time()
	drones = []
	i = 1
	while i < n:
		d = spawn_drone(flipper, per)
		if d != None:
			append(drones, d)
		i = i + 1
	# **主机先派完工再自己翻** ⇒ 主机的次数和各 helper 是同时进行的
	mine = flipper(per)
	total = mine[0]
	i = 0
	while i < len(drones):
		r = wait_for(drones[i])
		total = total + r[0]
		i = i + 1
	DT = get_time() - T0
	print("总翻转", total, "次 | 墙钟耗时", DT, "秒 | 平均", total / DT, "次/秒")
	print("主机自己那", mine[0], "次用了", mine[1], "秒（应约等于次数）")
	if DT > 0:
		if total / DT > 5:
			print("判定: 并行成立 ✓ 32 架确实在同时翻（否则该是约 1 次/秒）")
		else:
			print("判定: 看起来没有并行 ✗ 检查 spawn_drone 是否真的跑起来了")
	print("=== flips_parallel end ===")
	print("怎么判断有没有算上: **看游戏里那个任务/成就本身的显示**。")
	print("  （我原本想用 save.json 的 unlocks 列表当信号，但已实测推翻：")
	print("    最近 4 份备份 02:04~02:11 解锁数一直是 155、毫无新增，")
	print("    说明这几项任务根本不进 unlocks 列表 ⇒ 只能靠界面显示来判断。）")
	print("  没算上就把 FULL_PER_DRONE 改成 1 再跑（每架翻满 1000 次，16.7 分钟，两种语义都保底）。")


main()
