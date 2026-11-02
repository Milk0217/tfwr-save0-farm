# -*- coding: utf-8 -*-
# ============================================================
# maze_size_ab.py —— 回答"为什么不用 32x32 迷宫"：把"拆墙收益"按尺寸算清楚
#
# 用户的问题：32x32 迷宫也会被复用拆墙，那是不是该用大迷宫？
#
# 关键事实：
#   * 一座 k x k 迷宫的内部墙数 = (k-1)^2：k=8 只有 49 面，k=32 有 961 面；
#   * 每次重定位"拆掉一些墙"——**拆墙次数是 300 次，与迷宫大小无关**；
#   * 产量 = 面积 x 32 金币，而"宝藏到最近的家的步数"只跟**每架管多少格**有关。
# ============================================================
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maze_sim2 as S

TICK_PER_MOVE = 0.0329      # 200 tick / 6075 tick每秒
STMT_OVERHEAD = 0.10        # 每次宝藏的语句开销（v2 约 640 行 ≈ 0.08 秒）


def main():
    print("=== 一、复用拆墙对「真实走位」的影响（最优走位；每拆 1 面墙 = 1 次重定位）===")
    print("  迷宫        内墙数  已拆  每次宝藏步数")
    for k, m in ((32, 32), (16, 8), (8, 2)):
        walls = (k - 1) ** 2
        for extra in (0, walls // 4, walls // 2, walls):
            o, g = S.scenario(k, m, ntrials=8, relocations=extra)
            print("  %2dx%-2d(%2d架) %5d %5d %12.1f" % (k, k, m, walls, extra, o))
        print()

    print("=== 二、换算成金币/分（产量 = 面积 x 32；走位 %.4f 秒/步 + %.2f 秒语句）==="
          % (TICK_PER_MOVE, STMT_OVERHEAD))
    cfg = ((32, 32, 1), (16, 8, 4), (8, 2, 16))
    for frac, label in ((0.0, "没拆墙"), (0.25, "拆了 1/4"), (0.5, "拆了一半"), (1.0, "全拆开")):
        for k, m, n_maze in cfg:
            walls = (k - 1) ** 2
            o, g = S.scenario(k, m, ntrials=8, relocations=int(walls * frac))
            t = o * TICK_PER_MOVE + STMT_OVERHEAD
            rate = n_maze * (k * k * 32) / t * 60
            tag = "%dx%d x%d座" % (k, k, n_maze)
            print("  %-10s | %-8s | %5.1f 步 -> %.3f 秒/宝藏 | %9.0f 金币/分"
                  % (tag, label, o, t, rate))
        print()

    print("=== 三、寿命账（一座迷宫复用 300 次，之后必须重建）===")
    for k, m, n_maze in cfg:
        walls = (k - 1) ** 2
        half = walls // 2 if walls // 2 > 0 else 1
        o0, _ = S.scenario(k, m, ntrials=6, relocations=0)
        o1, _ = S.scenario(k, m, ntrials=6, relocations=half)
        # 重建一次要重新"探测建图"：代价 ∝ 格子数
        explore_moves = k * k * 2 + k * k          # DFS 约 2 倍格子数 + 建图
        print("  %2dx%-2d x%2d座 | 建图代价 %5d 步（%.1f 秒）| 半开时 %4.1f 步/宝藏"
              % (k, k, n_maze, explore_moves, explore_moves * TICK_PER_MOVE, o1))


main()
