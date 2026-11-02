# ============================================================
# layout.py —— **布局的唯一事实来源**（32×32 时代，v1）
#
# 为什么单独成文件：整套农场（南瓜 14 方阵 / 向日葵 / 胡萝卜 / 木草 / 仙人掌田）
# 的几何都从这几个常数推出来，改布局只应该改这一处。
#
# 依据（`docs/scripting/import.md`，权威）：
#   `import layout` 会**执行**本文件并把全局量给它；重复 import 返回**缓存**。
#   每次无人机执行都是独立的一次程序执行 ⇒ 每架无人机各有一份本文件的全局量，
#   语义与「同一文件里的全局量」完全一致 ⇒ 跨模块派无人机是安全的。
#   文档警告：用 `import 文件`，**不要** `from 文件 import *`（交叉引用时会拿到半加载的模块）。
#
# 布局（每对方阵必须在 x 或 y 上隔开 ≥1 格，否则连成 12×6 矩形、产量口径会变）：
#   右半区 x∈[16,32)  方阵 8 个：x=16 / x=23（间隔 x=22），y=0/7/14/21
#                     向日葵：最右 3 列 × y 0..25
#   左半区 x∈[0,16)   木草 3 行（y 0..2）
#                     胡萝卜 y 3..10（8 行 × 16 列 = 128 格）
#                     方阵 6 个：x=0 / x=9（间隔 x=6~8），y=12/19/26
# ============================================================

LAYOUT_VERSION = 1

SIZE_OF_BOARD = get_world_size()
HALF = SIZE_OF_BOARD // 2

PUMPKIN_SIZE = HALF
if PUMPKIN_SIZE > 6:
	PUMPKIN_SIZE = 6
PUMPKIN_TILE_COUNT = PUMPKIN_SIZE * PUMPKIN_SIZE

# 14 个方阵：右半区 8（x=HALF 与 HALF+7）× (y=0/7/14/21)，左半区 6（x=0 与 9）× (y=12/19/26)
PUMPKIN_SQUARES = 14
PUMPKIN_OX = [HALF, HALF, HALF, HALF, HALF + 7, HALF + 7, HALF + 7, HALF + 7, 0, 0, 9, 9, 0, 9]
PUMPKIN_OY = [0, 7, 14, 21, 0, 7, 14, 21, 12, 19, 12, 19, 26, 26]

# 向日葵带 = 最右 3 列 × 前 SUN_ROWS 行（必须用「最右 3 列」，用 x ≥ HALF+6 会把方阵圈进来）
SUN_ROWS = 26

# 左半区三带
WOOD_ROWS = 1
HAY_ROWS = 2
BUF_ROWS = WOOD_ROWS + HAY_ROWS        # 缓冲带 = 木 + 草
CARROT_START = BUF_ROWS
CARROT_END = 11                        # 胡萝卜 = y 3..10（32×32 时 8 行 × 16 列 = 128 格）

# 旧向日葵 v1 用的矩形（tend_sunflowers 已废弃，仅为兼容保留）
SUNFLOWER_W = SIZE_OF_BOARD - HALF
SUNFLOWER_H = SIZE_OF_BOARD - PUMPKIN_SIZE


def check_squares():
	# 方阵间距自检：每一对都必须在 x 或 y 上隔开 ≥ PUMPKIN_SIZE+1 格。
	# 这个检查必须机械做 —— BUILD 26 就是漏了 x=15↔16 紧挨，两块连成 12×6 矩形，
	# pyield 从 13,824 变成 27,648（产量口径被改变），而人眼在坐标表里看不出来。
	bad = 0
	i = 0
	while i < PUMPKIN_SQUARES:
		j = i + 1
		while j < PUMPKIN_SQUARES:
			dx = PUMPKIN_OX[i] - PUMPKIN_OX[j]
			if dx < 0:
				dx = -dx
			dy = PUMPKIN_OY[i] - PUMPKIN_OY[j]
			if dy < 0:
				dy = -dy
			if dx <= PUMPKIN_SIZE:
				if dy <= PUMPKIN_SIZE:
					bad = bad + 1
					print("[layout] ERROR: squares", i, j, "too close", PUMPKIN_OX[i], PUMPKIN_OY[i], PUMPKIN_OX[j], PUMPKIN_OY[j])
			j = j + 1
		i = i + 1
	return bad
