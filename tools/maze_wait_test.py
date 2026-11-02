# -*- coding: utf-8 -*-
# ============================================================
# maze_wait_test.py —— wait_maze 两阶段握手的回归测试
#
# 为什么单独测它：假棋盘只有**一架**无人机，跑不出"同区两架抢重建"的时序 ✗，
# 所以这个 bug（pair 1 在旧迷宫上开始探图、pair 0 正好把它拆掉）一直漏到实跑才暴露。
# 这里用"可编程的世界"把三种关键时序钉死。
# ============================================================
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maze_mock as M       # noqa: E402


def make(script_hook):
    """建一个假世界 + 按脚本改变世界状态的 get_time"""
    w = M.Mock(seed=21, region=(0, 0), drift=1)
    w.bush = []
    ns = M.make_namespace(w)
    state = {"n": 0}

    def get_time():
        state["n"] += 1
        script_hook(w, state["n"])
        return state["n"] * 0.01

    ns["get_time"] = get_time
    g = M.load_script(ns)
    g["HOMEX"][0] = 0
    g["HOMEY"][0] = 0
    g["OTHX"][0] = 7
    g["OTHY"][0] = 7
    return w, g


def main():
    bad = []

    # ---- 场景 1：旧迷宫先消失、新迷宫后出现 ⇒ 应该返回 1（可以重新对齐）----
    def hook1(w, n):
        if n == 20:
            w.maze = None                 # pair 0 拆掉旧迷宫
        if n == 40:
            w.build_maze()                # pair 0 建好新迷宫

    w, g = make(hook1)
    r = g["wait_maze"](10.0)
    print("场景1 旧迷宫先消失再重建 -> wait_maze 返回", r, "（期望 1）")
    if r != 1:
        bad.append("场景1 返回 %s" % r)

    # ---- 场景 2：旧迷宫一直不消失（pair 0 卡住）⇒ 应该返回 0（由调用方接管）----
    def hook2(w, n):
        pass

    w, g = make(hook2)
    r = g["wait_maze"](3.0)
    print("场景2 旧迷宫一直不消失     -> wait_maze 返回", r, "（期望 0）")
    if r != 0:
        bad.append("场景2 返回 %s" % r)

    # ---- 场景 3：迷宫本来就没了，随后出现 ⇒ 应该返回 1 ----
    def hook3(w, n):
        if n == 30:
            w.build_maze()

    w, g = make(hook3)
    w.maze = None
    r = g["wait_maze"](10.0)
    print("场景3 迷宫已经没了再出现   -> wait_maze 返回", r, "（期望 1）")
    if r != 1:
        bad.append("场景3 返回 %s" % r)

    # ---- 场景 4：resync 在"我不在迷宫里"时应当**失败但不崩**，回家后能成功 ----
    def hook4(w, n):
        pass

    w, g = make(hook4)
    w.maze = None                          # 让无人机站在迷宫外
    g["MAPDIRTY"][0] = 0
    r = g["resync_maze"]()
    print("场景4 站在迷宫外 resync   -> 返回", r, "（期望 0，且不崩）")
    if r != 0:
        bad.append("场景4 返回 %s" % r)

    print()
    if bad:
        print("!! 可疑点:", bad)
    else:
        print("wait_maze / resync 时序：**0 可疑点** ✓")


main()
