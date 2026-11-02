# ============================================================
# lb_enter.py —— 排行榜"发令枪"
#
# 依据 docs/game/unlocks/leaderboard.md（权威）：
#   * `leaderboard_run(榜, 文件名, speedup)` 会**开一场模拟**，被点名的文件才是参赛程序；
#   * 成功条件成立**且程序自己结束**才算完成；不足 2 小时会自动重跑到满 2 小时取平均。
#
# 一、登上「Maze」榜（= 用户说的"登上排行榜"）
#   Maze 榜的起始条件：**全解锁** + 奇异物质 1e9 + 电力 1e9；
#   成功条件：`num_items(Items.Gold) >= 9863168`。
#   ⇒ 我们的 maze_gold2.py 正好是"目标 = 现有金币 + 10,000,000，达成即收工"，
#     而模拟里开局金币是 0 ⇒ 攒到 1000 万 > 986.3 万 ⇒ **成功条件必然先满足**，
#     而且它会自己收工退出（排行榜要求的"程序必须结束"）✓
#   ⇒ 直接点名它即可，**不用改一个字**。
#
# 二、登上「Fastest_Reset / 完全复位」榜（= "完全复位"排行榜）
#   起始条件：**一块地、零解锁、零物品**；
#   成功条件：`num_unlocked(Unlocks.Leaderboard) > 0`。
#   ⇒ 这需要一支"从零把整局自动化到解锁排行榜"的**新程序**（full_run.py），
#     现存脚本（main.py / wood_farm.py / cactus_big.py / maze_gold2.py）都假定
#     "已经解锁了一堆东西"，不能直接拿来用 ✗。
#   ⇒ 所以那一行先注释掉，等 full_run.py 写好再打开。
# ============================================================

WHICH = 2       # 1=Maze 2=**full_run(正式)** 3=probe_expand 4=lb_probe(二分)
#   ⚠ 暂时设 3：因为跑 2 时报 `Error: 导入的模块存在语法错误。In:`（空栈）
#     —— 这是**加载阶段**的错（不是运行时）✗
#     而 14 个文件都通过 py_compile / gamelang / 引号平衡 / 编码检查（无 BOM、LF、UTF-8）✓
#     普通运行（非排行榜）也能正常跑 ✓ ⇒ 同一批文件、同一套 import，一个能过一个不能 ✓
#     ⇒ 用探针档做**决定性实验**：
#        若 3 也报同样的错 ⇒ 问题在更底层（util/budget）或加载机制 ✓
#        若 3 正常       ⇒ 问题在 full_run 的依赖链；但同一批文件普通跑正常
#                          ⇒ 极可能是**编译缓存**坏了 ⇒ 重启游戏再试 ✓

print("[lb] WHICH =", WHICH, "（1 = Maze 榜，2 = 完全复位榜）")

if WHICH == 1:
	print("[lb] 开一场 Maze 榜模拟：全解锁 + 1e9 奇异物质 + 1e9 电力，目标金币 >= 9863168")
	leaderboard_run(Leaderboards.Maze, "maze_gold2", 256)
elif WHICH == 2:
	# import 探针已跑完（结论：模拟里 import 可用 ✓，但 layout 必须等棋盘长大后再 import）
	# ⇒ 参赛程序改回 full_run
	print("[lb] 开一场 Fastest_Reset 模拟：一块地 + 零解锁，参赛程序 = full_run.py")
	leaderboard_run(Leaderboards.Fastest_Reset, "full_run", 256)
elif WHICH == 3:
	# 探针档：模拟里 Expand 才是低等级（真实存档已满级 ⇒ 在那里问不出成本 ✗）
	# ✅ 已跑通（2026-10-27）：`probe_expand` 正常结束 ⇒ **加载机制没问题** ✓
	print("[lb] 开一场 Fastest_Reset 模拟：参赛程序 = probe_expand.py（问 Expand 各级成本）")
	leaderboard_run(Leaderboards.Fastest_Reset, "probe_expand", 256)
else:
	# 【二分档】逐模块 import，每步先打印 ⇒ 日志里最后一条 `[p] N xxx ok`
	#   就是最后一个成功的模块 ✓，下一条没打印的就是出问题的那个 ✓
	print("[lb] 开一场 Fastest_Reset 模拟：参赛程序 = lb_probe.py（逐模块 import 二分）")
	leaderboard_run(Leaderboards.Fastest_Reset, "lb_probe", 256)
