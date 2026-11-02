# -*- coding: utf-8 -*-
# ============================================================
# maze_profile.py —— 给 maze_gold2.py 做 tick 级体检（不开游戏）
#
# 为什么需要：实跑 947k 金币/分，而 power 的消耗速度（32.3 点/秒）说明
# **32 架无人机都在 100% 烧 tick 预算**（32.3 x 30 x 200 / 32 ≈ 6,060 tick/秒/架）。
# 也就是说：产量不是被"走位"卡住的，而是被**空转的语句**吃掉的。
#
# 做法：
#   * 用 maze_mock 的假棋盘加载真脚本；
#   * 用 sys.settrace 数**脚本自己执行了多少条语句**（0.8 tick/条）；
#   * 给每个游戏 API 记上项目标定过的 tick 成本（move=200、measure=1 …）；
#   * 输出「追一次宝藏」「空轮询一次」各花多少 tick ⇒ 直接换算成金币/分。
#
# 用法：python maze_profile.py [脚本名]
# ============================================================
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maze_mock as M       # noqa: E402

TICK = {
    "move": 200, "harvest": 200, "plant": 200, "use_item": 200, "till": 200,
    "clear": 200, "swap": 200,
    "measure": 1, "can_move": 1, "get_entity_type": 1, "get_pos_x": 1, "get_pos_y": 1,
    "num_items": 1, "get_water": 1, "get_ground_type": 1, "num_unlocked": 1,
    "get_time": 0, "get_tick_count": 0, "quick_print": 0, "print": 0, "len": 0,
}
STMT_TICK = 0.8
ENGINE = 6075.0
COUNTS = {}
STMTS = [0]
BYFUNC = {}
TARGET_FILE = ["maze_gold2.py"]


def _trace(frame, event, arg):
    if event == "line":
        STMTS[0] += 1
        n = frame.f_code.co_name
        BYFUNC[n] = BYFUNC.get(n, 0) + 1
    return _trace


def func_delta(before):
    out = {}
    for k, v in BYFUNC.items():
        d = v - before.get(k, 0)
        if d:
            out[k] = d
    return out


def instrument(ns):
    """把 ns 里的游戏 API 换成带计数的版本"""
    def wrap(name, fn):
        cost = TICK.get(name, 0)

        def f(*a):
            COUNTS[name] = COUNTS.get(name, 0) + 1
            if cost:
                STMTS[0] += 0
            return fn(*a)
        return f
    for name in list(TICK.keys()):
        if name in ns and callable(ns[name]):
            ns[name] = wrap(name, ns[name])


def ticks_since(mark):
    """返回 (语句数, [各 API 调用数], tick 合计)"""
    calls = dict(COUNTS)
    return STMTS[0] - mark[0], calls, 0


def snapshot():
    return (STMTS[0], dict(COUNTS))


def cost(before):
    stmts = STMTS[0] - before[0]
    calls = {}
    for k, v in COUNTS.items():
        d = v - before[1].get(k, 0)
        if d:
            calls[k] = d
    t = stmts * STMT_TICK
    for k, v in calls.items():
        t += v * TICK.get(k, 0)
    return stmts, calls, t


def profile(script="maze_gold2.py", treasures=40, drift=1, seed=3):
    src_path = os.path.join(M.SAVE, script)
    TARGET_FILE[0] = script
    w = M.Mock(seed=seed, region=(0, 0), drift=drift)
    ns = M.make_namespace(w)
    instrument(ns)
    g = M.load_script(ns)
    ax, ay = 0, 0
    # 建迷宫 + 探测（这两段是一次性开销，单独量）
    b0 = snapshot()
    sys.settrace(_trace)
    ok = g["build_maze"](ax, ay, 3)
    ex = g["explore"](M.REG)
    g["HOMEX"][0] = ax
    g["HOMEY"][0] = ay
    g["OTHX"][0] = (ax + M.REG - 1) % M.N
    g["OTHY"][0] = (ay + M.REG - 1) % M.N
    g["DFIELD"][0] = 0
    g["home_fields"]()
    g["walk_home"](200)
    sys.settrace(None)
    s, c, t = cost(b0)
    print("== 开场一次性：建迷宫 + 探测 64 格 + 两家的距离场 + 回位 ==")
    print("   语句 %d | tick %.0f | = %.2f 秒（只付一次，寿命 301 次宝藏）" % (s, t, t / ENGINE))
    # 每次宝藏要额外付的"分派"代价（O(1)，v2 新增的路径）
    b1 = snapshot()
    sys.settrace(_trace)
    n = 100
    for _ in range(n):
        g["home_fields"]() if False else None
        tx = w.treasure[0] % M.REG + 0
        ty = w.treasure[1] % M.REG + 0
        dm = g["DH"][ty * M.N + tx]
        dq = g["DO"][ty * M.N + tx]
    sys.settrace(None)
    s, c, t = cost(b1)
    print("== 分派一次（DH/DO 两次查表，v2 的 O(1) 判据）==" )
    print("   语句 %.1f 条 | tick %.1f" % (s / n, t / n))
    # 逐次宝藏
    tot = 0.0
    tot_s = 0
    per = []
    fns = {}
    sys.settrace(_trace)
    for i in range(treasures):
        before = snapshot()
        fb = dict(BYFUNC)
        tp = M.measure_or(w)
        # 与 worker 的真实主循环一致：hunter 直接从**当前位置**出发（route_to 会算 LCA 路径）
        r = g["chase"](tp[0], tp[1])
        s, c, t = cost(before)
        for k, v in func_delta(fb).items():
            fns[k] = fns.get(k, 0) + v
        tot += t
        tot_s += s
        per.append((s, t, c.get("move", 0), c.get("measure", 0)))
        if r == 3 or r == 4:
            g["do_rebuild"](ax, ay)
    sys.settrace(None)
    avg_s = tot_s / treasures
    avg_t = tot / treasures
    print("== 追一次宝藏（只算 hunter 路径，不含对手）==")
    print("   平均行数 %.0f | tick(0.8/行) %.0f | 走位 %.1f 步"
          % (avg_s, avg_t, sum(p[2] for p in per) / treasures))
    print("   按函数拆开（行/次）：")
    for k in sorted(fns, key=lambda x: -fns[x]):
        print("      %-14s %.0f" % (k, fns[k] / treasures))
    # 空轮询一次（yielder 的主循环代价）：用一次 measure + 比较来估
    before = snapshot()
    sys.settrace(_trace)
    n = 200
    for _ in range(n):
        v = g["measure"]()
        if v == None:
            pass
    sys.settrace(None)
    s, c, t = cost(before)
    print("== 空轮询一次（yielder 等待时的一圈）==" )
    print("   语句 %.1f 条 | tick %.1f | 每秒可轮询 %.0f 次"
          % (s / n, t / n, ENGINE / (t / n)))
    # ---- 换算 ----
    print()
    print("== 换算（16 座 x 2 架）==")
    per_treasure = avg_t + 12 * STMT_TICK * 0 + 0   # 对手的开销另算
    latency_s = avg_t / ENGINE
    print("   hunter 关键路径 = %.3f 秒/宝藏 ⇒ 单座上限 %.2f 次/秒 ⇒ 16 座 %.0f 金币/分"
          % (latency_s, 1 / latency_s, 16 * 2048 * 60 / latency_s))
    return avg_s, avg_t


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "maze_gold2.py"
    for drift in (0, 1):
        print("############ %s  drift=%d ############" % (name, drift))
        profile(name, drift=drift)
        print()
