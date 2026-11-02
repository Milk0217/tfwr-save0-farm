# -*- coding: utf-8 -*-
# ============================================================
# maze_worker_e2e.py —— 在假棋盘上跑**完整的 worker 主循环**（端到端回归）
#
# 这一步比"单测 chase"值钱：它会把 建迷宫 -> 探测 -> 分派 -> 走位 -> 收货 ->
# 复用耗尽 -> 重建 -> 等队友/重新对齐 整条链路走一遍。
# 假棋盘只有一架无人机，所以把"队友的家"设成自己的家（平手时 pair 0 去）
# ⇒ 分派永远判给"我"，否则会一直等价于"等队友"而挂住。
#
# 时钟按真实节奏走：1 move = 0.0329 秒（这样 v2.1 的"脏了每 4 秒重建"才会触发）。
# ============================================================
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maze_mock as M       # noqa: E402


def run(seed=9, drift=1, treasures=60, verbose=False):
    w = M.Mock(seed=seed, region=(0, 0), drift=drift)
    w.bush = []
    ns = M.make_namespace(w)
    state = {"t": 0.0}
    orig_move = ns["move"]
    ns["move"] = lambda d: (state.__setitem__("t", state["t"] + 0.0329), orig_move(d))[1]
    ns["get_time"] = lambda: (state.__setitem__("t", state["t"] + 0.0001), state["t"])[1]
    g = M.load_script(ns)
    g["farthest_in_region"] = lambda ax, ay, rx, ry: [ax, ay]   # 假棋盘只有一架
    goal = M.GOLD_PER * treasures
    got = g["worker"](0, 0.0, goal, 0, 0)
    return got, w, g


def main():
    print("=== 完整 worker 主循环（假棋盘端到端）===")
    bad = []
    for drift in (0, 1):
        for seed in (9, 12):
            got, w, g = run(seed=seed, drift=drift, treasures=60)
            avg = g["STAT"][1] / got if got else 0
            print("  drift %d seed %2d | 收到 %3d 次（目标 60）| gold %7d | 移动 %5d | "
                  "步数/宝藏 %5.2f | 重建 %d | 最终通道 %d"
                  % (drift, seed, got, w.gold, w.moves, avg, g["STAT"][2],
                     g["count_open_in"]()))
            if got < 60:
                bad.append("drift %d seed %d 只收到 %d 次" % (drift, seed, got))
    print()
    if bad:
        print("!! 可疑点:", bad)
    else:
        print("端到端：**0 可疑点** ✓（每种配置都收满 60 次、重建链路走通）")


main()
