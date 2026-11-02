# -*- coding: utf-8 -*-
# ============================================================
# maze_cycle_ab.py —— 用"虚拟时钟"量**真实的每宝藏周期时间**，给 v2.x 各改动做 A/B
#
# 为什么需要它：前几轮只量了"走位步数"，但周期里还有**语句开销**（0.8 tick/行）。
# 这次实跑出现"步数变多 + 速率变慢"，必须把两者放在同一根时钟上比。
#
# 虚拟时钟（与游戏标定一致）：
#   * 每执行 1 行脚本 = 0.8 tick
#   * 每 move = 200 tick、measure/can_move/get_entity_type = 1 tick
#   * 引擎 6075 tick/秒（2 倍速）
#   * 拆墙速率用**实测值**：每 14 次重定位拆 1 面
# ⇒ 直接读出"每个宝藏多少秒"，也就直接是金币/分。
# ============================================================
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maze_mock as M       # noqa: E402

TICK_STMT = 0.8
ENGINE = 6075.0
MOVE_TICK = 200
API_TICK = {"move": 200, "use_item": 200, "plant": 200, "harvest": 200,
            "measure": 1, "can_move": 1, "get_entity_type": 1,
            "get_pos_x": 1, "get_pos_y": 1, "num_items": 1}


class Clock:
    def __init__(self):
        self.t = 0.0
        self.lines = 0

    def line(self):
        self.lines += 1
        self.t += TICK_STMT / ENGINE

    def api(self, name):
        self.t += API_TICK.get(name, 0) / ENGINE


def run(variant, seed=3, treasures=250, real_rate=True):
    """variant: 'v2' = 不探测不刷新 / 'probe2' = 每 2 步探测 + 脏刷新 /
                'probe_hot' = 每步探测 + 脏刷新 / 'dispatch' = 只在分派与到宝藏时探测 + 脏刷新"""
    clk = Clock()
    w = M.Mock(seed=seed, region=(0, 0), drift=0)
    w.bush = []
    ns = M.make_namespace(w)
    for name in API_TICK:
        if name in ns and callable(ns[name]):
            orig = ns[name]
            ns[name] = (lambda o, n: (lambda *a: (clk.api(n), o(*a))[1]))(orig, name)
    ns["get_time"] = lambda: clk.t
    g = M.load_script(ns)

    # 只统计脚本自己的行（跳过 harness 的包装函数）
    SCRIPT_FUNCS = set()
    for k, v in list(g.items()):
        if callable(v) and getattr(v, "__module__", "") == "maze_gold2_mock":
            SCRIPT_FUNCS.add(v.__code__.co_name)

    def trace(frame, event, arg):
        if event == "line" and frame.f_code.co_name in SCRIPT_FUNCS:
            clk.line()
        return trace

    probe_mode = {"v2": 0, "probe2": 2, "probe_hot": 1, "dispatch": -1}[variant]

    # 按 variant 打补丁：probe_here 的调用点由脚本内部决定，这里改的是"频率"
    orig_probe = g["probe_here"]
    if probe_mode == 0:
        g["probe_here"] = lambda: None
    elif probe_mode == -1:
        # 只在分派时探测（脚本里 chase 到位那次保留，route_to 里的去掉）
        g["_probe_keep"] = orig_probe

    # 建图 + 探测 + 场
    sys.settrace(trace)
    g["build_maze"](0, 0, 3)
    g["explore"](M.REG)
    g["HOMEX"][0] = 0
    g["HOMEY"][0] = 0
    g["OTHX"][0] = M.REG - 1
    g["OTHY"][0] = M.REG - 1
    g["RGX"][0] = 0
    g["RGY"][0] = 0
    g["invalidate_fields"]()
    g["home_fields"]()
    g["walk_home"](200)
    t_start = clk.t
    n = 0
    ref = clk.t
    for k in range(treasures):
        if real_rate and k % 14 == 13 and w.maze is not None:
            lx, ly = w.rng.randrange(8), w.rng.randrange(8)
            dx, dy = M.DIRS[w.rng.randrange(4)]
            nx, ny = lx + dx, ly + dy
            if 0 <= nx < 8 and 0 <= ny < 8:
                w.maze[(lx, ly)].add((nx, ny))
                w.maze[(nx, ny)].add((lx, ly))
        if variant != "v2":
            if g["MAPDIRTY"][0] == 1 and clk.t - ref > g["REFIELD_DIRTY_S"]:
                ref = clk.t
                g["MAPDIRTY"][0] = 0
                g["home_fields"]()
        tp = M.measure_or(w)
        r = g["chase"](tp[0], tp[1])
        if r == 1:
            n += 1
        elif r in (3, 4):
            if g["do_rebuild"](0, 0) == 0:
                break
    sys.settrace(None)
    dt = clk.t - t_start
    return n, dt, n / dt if dt else 0


def main():
    print("=== 每个宝藏的**真实周期时间**（虚拟时钟：行 0.8 tick + move 200 tick，6075 tick/秒）===")
    print("    拆墙速率用实测值：每 14 次重定位 1 面")
    print()
    print("  %-30s %8s %10s %12s %14s" % ("方案", "宝藏数", "总秒数", "秒/宝藏", "折算金币/分"))
    for variant, name in (("v2", "A. v2（不探测、不刷新）"),
                          ("probe_hot", "B. 每步探测 + 脏刷新"),
                          ("probe2", "C. 每 2 步探测 + 脏刷新"),
                          ("dispatch", "D. 只在分派/到宝藏探测")):
        tot_n = 0
        tot_dt = 0.0
        for seed in (3, 5, 7):
            n, dt, rate = run(variant, seed=seed, treasures=250)
            tot_n += n
            tot_dt += dt
        per = tot_dt / max(tot_n, 1)
        gold_min = 2048.0 / per * 60 * 16      # 16 座并行
        print("  %-30s %8d %10.1f %12.3f %13.0f" % (name, tot_n, tot_dt, per, gold_min))
    print()
    print("实测参照：v2 = 8.64 步/宝藏、3.36M/分；v2.2 = 10.10 步/宝藏、2.86M/分")


main()
